"""GLB post-pass, deterministic:
  - drop bone scale animation channels (contract: no scale keys; the exporter's forced sampling
    writes constant 1,1,1 tracks);
  - additive layer clips (add_*): keep only the rotation channels of the spine/neck/head bones,
    and reduce add_ref to a single key (a 1-frame clip);
  - clips keyed at 60 Hz in Blender (the run): scale their key times back to seconds;
  - drop translation tracks that only hold a bone's rest offset;
  - slow clips: drop keys that linear interpolation between their neighbours reproduces within a
    tight tolerance (0.1 deg, 0.2 mm; never on walk / run or the hand-made task clips, whose
    every key is kept);
  - write the clip facts the game reads into scenes[0].extras and the armature node's extras;
  - repack the binary chunk without the orphaned accessors/bufferViews."""
import json
import struct

import numpy as np


def _read(path):
    with open(path, "rb") as f:
        data = f.read()
    clen, _ = struct.unpack_from("<II", data, 12)
    gj = json.loads(data[20:20 + clen].decode("utf8"))
    off = 20 + clen
    blen, _ = struct.unpack_from("<II", data, off)
    return gj, data[off + 8: off + 8 + blen]


def _write(path, gj, binary):
    js = json.dumps(gj, separators=(",", ":")).encode("utf8")
    js += b" " * ((4 - len(js) % 4) % 4)
    binary += b"\0" * ((4 - len(binary) % 4) % 4)
    total = 12 + 8 + len(js) + 8 + len(binary)
    with open(path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, total))
        f.write(struct.pack("<II", len(js), 0x4E4F534A))
        f.write(js)
        f.write(struct.pack("<II", len(binary), 0x004E4942))
        f.write(binary)


def _walk_accessor_refs(gj, fn):
    for m in gj.get("meshes", []):
        for p in m["primitives"]:
            for k in p["attributes"]:
                p["attributes"][k] = fn(p["attributes"][k])
            if "indices" in p:
                p["indices"] = fn(p["indices"])
            for t in p.get("targets", []):
                for k in t:
                    t[k] = fn(t[k])
    for s in gj.get("skins", []):
        if "inverseBindMatrices" in s:
            s["inverseBindMatrices"] = fn(s["inverseBindMatrices"])
    for a in gj.get("animations", []):
        for s in a["samplers"]:
            s["input"] = fn(s["input"])
            s["output"] = fn(s["output"])


_NC = {"SCALAR": 1, "VEC3": 3, "VEC4": 4}


def _acc_read(gj, binary, i):
    a = gj["accessors"][i]
    bv = gj["bufferViews"][a["bufferView"]]
    assert a["componentType"] == 5126 and "byteStride" not in bv
    nc = _NC[a["type"]]
    off = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    return np.frombuffer(binary, dtype="<f4", count=a["count"] * nc, offset=off).reshape(a["count"], nc).astype(np.float64)


def _acc_new(gj, extra, base_len, arr, typ, minmax=False):
    """Append a float accessor; `extra` collects the new bytes after the original binary."""
    arr = np.asarray(arr, dtype="<f4").reshape(len(arr), _NC[typ])
    while (base_len + len(extra)) % 4:
        extra += bytes(1)
    gj["bufferViews"].append({"buffer": 0, "byteOffset": base_len + len(extra), "byteLength": arr.nbytes})
    extra += arr.tobytes()
    acc = {"bufferView": len(gj["bufferViews"]) - 1, "componentType": 5126, "count": len(arr), "type": typ}
    if minmax:
        acc["min"], acc["max"] = [float(arr.min())], [float(arr.max())]
    gj["accessors"].append(acc)
    return len(gj["accessors"]) - 1


def _strip_scale(gj):
    removed = 0
    for a in gj.get("animations", []):
        keep = [c for c in a["channels"] if c["target"]["path"] != "scale"]
        removed += len(a["channels"]) - len(keep)
        a["channels"] = keep
    return removed


def _compact_samplers(gj):
    for a in gj.get("animations", []):
        used = sorted({c["sampler"] for c in a["channels"]})
        remap = {o: n for n, o in enumerate(used)}
        a["samplers"] = [a["samplers"][i] for i in used]
        for c in a["channels"]:
            c["sampler"] = remap[c["sampler"]]


def _reduce(t, v, quat, tol):
    """Indices of the keys to keep so that linear (slerp for rotations, as three.js does)
    interpolation between kept keys stays within tol of every dropped key."""
    n = len(t)
    if n <= 2:
        return list(range(n))

    def ok(a, b):
        k = np.arange(a + 1, b)
        u = ((t[k] - t[a]) / (t[b] - t[a]))[:, None]
        if quat:
            q0, q1 = v[a], v[b] if v[a] @ v[b] >= 0 else -v[b]
            d = float(np.clip(q0 @ q1, -1, 1))
            th = np.arccos(d)
            if th < 1e-5:
                q = q0 + (q1 - q0) * u
            else:
                q = (np.sin((1 - u) * th) * q0 + np.sin(u * th) * q1) / np.sin(th)
            q /= np.linalg.norm(q, axis=1, keepdims=True)
            err = 2 * np.arccos(np.clip(np.abs((q * v[k]).sum(axis=1)), -1, 1))
        else:
            err = np.linalg.norm(v[a] + (v[b] - v[a]) * u - v[k], axis=1)
        return bool((err <= tol).all())

    keep, a = [0], 0
    while a < n - 1:
        b = a + 1
        while b + 1 < n and ok(a, b + 1):
            b += 1
        keep.append(b)
        a = b
    return keep


def postprocess(path, meta=None, add_bones=(), time_scale=None, keep_all=("walk", "run", "crouch", "reach", "throw", "lookup"),
                tol_rot_deg=0.1, tol_pos=0.0002):
    gj, binary = _read(path)
    stats = {"scale_channels_removed": _strip_scale(gj)}
    node_name = [n.get("name") for n in gj["nodes"]]
    extra = bytearray()
    base = len(binary) + (4 - len(binary) % 4) % 4
    binary = binary + bytes(base - len(binary))
    time_scale = time_scale or {}
    in_cache = {}

    def new_input(times):
        key = np.asarray(times, dtype="<f4").tobytes()
        if key not in in_cache:
            in_cache[key] = _acc_new(gj, extra, base, np.asarray(times).reshape(-1, 1), "SCALAR", True)
        return in_cache[key]

    k0 = k1 = dropped = 0
    for a in gj.get("animations", []):
        name = a["name"]
        if name.startswith("add_"):
            a["channels"] = [c for c in a["channels"] if c["target"]["path"] == "rotation"
                             and node_name[c["target"]["node"]] in add_bones]
        # A translation track that only repeats the bone's rest offset says nothing: drop it
        # (the mixer leaves an untracked property at its bind value). Hips and skirt panels keep theirs.
        kept = []
        for c in a["channels"]:
            if c["target"]["path"] == "translation":
                v = _acc_read(gj, binary, a["samplers"][c["sampler"]]["output"])
                rest_t = np.array(gj["nodes"][c["target"]["node"]].get("translation", [0, 0, 0]), float)
                if np.abs(v - rest_t).max() < 2e-6:
                    dropped += 1
                    continue
            kept.append(c)
        a["channels"] = kept
        f = time_scale.get(name, 1.0)
        done = set()
        for c in a["channels"]:
            if c["sampler"] in done:
                continue
            done.add(c["sampler"])
            sm = a["samplers"][c["sampler"]]
            t = _acc_read(gj, binary, sm["input"])[:, 0] * f
            v = _acc_read(gj, binary, sm["output"])
            k0 += len(t)
            quat = c["target"]["path"] == "rotation"
            if name == "add_ref":
                idx, t = [0], t * 0.0
            elif name in keep_all or sm.get("interpolation", "LINEAR") != "LINEAR":
                idx = list(range(len(t)))
            else:
                idx = _reduce(t, v, quat, np.radians(tol_rot_deg) if quat else tol_pos)
            k1 += len(idx)
            if len(idx) != len(t) or f != 1.0:
                sm["input"] = new_input(t[idx])
                if len(idx) != len(t):
                    sm["output"] = _acc_new(gj, extra, base, v[idx], "VEC4" if quat else "VEC3")
    _compact_samplers(gj)
    stats["keys_before"], stats["keys_after"], stats["rest_translation_channels_dropped"] = k0, k1, dropped
    binary = binary + bytes(extra)
    if meta is not None:
        facts = {"clipSpeed": meta.get("clipSpeed", {}),
                 "clips": {k: {kk: vv for kk, vv in c.items() if kk in ("duration", "loop", "speed", "stride", "events", "additive")}
                           for k, c in meta.get("clips", {}).items()},
                 "additiveReference": "add_ref"}
        for sc in gj.get("scenes", []):
            sc.setdefault("extras", {}).update(facts)
        for n in gj["nodes"]:
            if "heroine" in (n.get("extras") or {}):
                n["extras"]["clipSpeed"] = facts["clipSpeed"]
    # Accessors still referenced.
    used_acc = set()
    _walk_accessor_refs(gj, lambda i: (used_acc.add(i), i)[1])
    acc_old = gj.get("accessors", [])
    acc_map = {o: n for n, o in enumerate(sorted(used_acc))}
    gj["accessors"] = [acc_old[i] for i in sorted(used_acc)]
    _walk_accessor_refs(gj, lambda i: acc_map[i])
    # BufferViews still referenced (accessors + images), repacked in original order.
    used_bv = {a["bufferView"] for a in gj["accessors"] if "bufferView" in a}
    for a in gj["accessors"]:
        sp = a.get("sparse")
        if sp:
            used_bv |= {sp["indices"]["bufferView"], sp["values"]["bufferView"]}
    used_bv |= {im["bufferView"] for im in gj.get("images", []) if "bufferView" in im}
    bv_old = gj.get("bufferViews", [])
    order = sorted(used_bv)
    out = bytearray()
    new_bv = []
    for i in order:
        bv = dict(bv_old[i])
        chunk = binary[bv.get("byteOffset", 0): bv.get("byteOffset", 0) + bv["byteLength"]]
        out += b"\0" * ((4 - len(out) % 4) % 4)
        bv["byteOffset"] = len(out)
        out += chunk
        new_bv.append(bv)
    bv_map = {o: n for n, o in enumerate(order)}
    gj["bufferViews"] = new_bv
    for a in gj["accessors"]:
        if "bufferView" in a:
            a["bufferView"] = bv_map[a["bufferView"]]
        sp = a.get("sparse")
        if sp:
            sp["indices"]["bufferView"] = bv_map[sp["indices"]["bufferView"]]
            sp["values"]["bufferView"] = bv_map[sp["values"]["bufferView"]]
    for im in gj.get("images", []):
        if "bufferView" in im:
            im["bufferView"] = bv_map[im["bufferView"]]
    out += b"\0" * ((4 - len(out) % 4) % 4)
    gj["buffers"][0]["byteLength"] = len(out)
    _write(path, gj, bytes(out))
    return stats
