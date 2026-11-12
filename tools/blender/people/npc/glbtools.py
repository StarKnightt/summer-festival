"""Pure-Python GLB read / prune / compact / inspect (no Blender needed)."""
import json
import math
import struct

import numpy as np

CT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def read(path):
    data = open(path, "rb").read()
    magic, ver, length = struct.unpack_from("<III", data, 0)
    assert magic == 0x46546C67
    off = 12
    js, binc = None, b""
    while off < length:
        clen, ctype = struct.unpack_from("<II", data, off)
        chunk = data[off + 8: off + 8 + clen]
        if ctype == 0x4E4F534A:
            js = json.loads(chunk.decode("utf-8"))
        elif ctype == 0x004E4942:
            binc = chunk
        off += 8 + clen
    return js, binc


def write(path, js, binc):
    j = json.dumps(js, separators=(",", ":")).encode("utf-8")
    j += b" " * ((4 - len(j) % 4) % 4)
    binc = binc + b"\0" * ((4 - len(binc) % 4) % 4)
    total = 12 + 8 + len(j) + 8 + len(binc)
    with open(path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, total))
        f.write(struct.pack("<II", len(j), 0x4E4F534A))
        f.write(j)
        f.write(struct.pack("<II", len(binc), 0x004E4942))
        f.write(binc)
    return total


def accessor(js, binc, i):
    a = js["accessors"][i]
    bv = js["bufferViews"][a["bufferView"]]
    dt = CT[a["componentType"]]
    nc = NC[a["type"]]
    off = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    stride = bv.get("byteStride", 0)
    isz = np.dtype(dt).itemsize * nc
    if stride and stride != isz:
        raw = np.frombuffer(binc, dtype=np.uint8, count=stride * a["count"], offset=off).reshape(a["count"], stride)[:, :isz]
        arr = np.frombuffer(raw.tobytes(), dtype=dt).reshape(a["count"], nc)
    else:
        arr = np.frombuffer(binc, dtype=dt, count=a["count"] * nc, offset=off).reshape(a["count"], nc)
    return arr


def prune_animations(js, keep_nodes, root_names=("root",), skip_prefix=("finger_",), drop=()):
    """Keep one animation per name; only rotation channels (and translation on the bones named in
    root_names) on keep_nodes; drop scale and every other translation, every channel of the bones
    named in `drop`, and bones whose name starts with one of skip_prefix."""
    names = {i: n.get("name", "") for i, n in enumerate(js["nodes"])}
    out, seen = [], set()
    removed = 0
    for an in js.get("animations", []):
        if an["name"] in seen:
            removed += len(an["channels"])
            continue
        ch2, samp2, remap = [], [], {}
        for ch in an["channels"]:
            node = ch["target"].get("node")
            path = ch["target"]["path"]
            ok = node in keep_nodes and (path == "rotation" or (path == "translation" and names[node] in root_names))
            if skip_prefix:
                ok = ok and not names[node].startswith(tuple(skip_prefix))
            ok = ok and names[node] not in drop
            if not ok:
                removed += 1
                continue
            s = ch["sampler"]
            if s not in remap:
                remap[s] = len(samp2)
                samp2.append(an["samplers"][s])
            ch2.append({"sampler": remap[s], "target": ch["target"]})
        if not ch2:
            continue
        seen.add(an["name"])
        an2 = dict(an)
        an2["channels"], an2["samplers"] = ch2, samp2
        out.append(an2)
    js["animations"] = out
    return removed


def compact(js, binc):
    """Drop accessors / bufferViews nothing references and repack the binary chunk."""
    used_acc = set()
    for m in js.get("meshes", []):
        for p in m["primitives"]:
            used_acc.update(p["attributes"].values())
            if "indices" in p:
                used_acc.add(p["indices"])
            for t in p.get("targets", []):
                used_acc.update(t.values())
    for s in js.get("skins", []):
        if "inverseBindMatrices" in s:
            used_acc.add(s["inverseBindMatrices"])
    for an in js.get("animations", []):
        for s in an["samplers"]:
            used_acc.add(s["input"])
            used_acc.add(s["output"])
    acc_map = {}
    new_acc = []
    for i, a in enumerate(js["accessors"]):
        if i in used_acc:
            acc_map[i] = len(new_acc)
            new_acc.append(a)
    used_bv = {a["bufferView"] for a in new_acc if "bufferView" in a}
    for a in new_acc:                      # sparse accessors (the exporter writes morph targets sparse)
        if "sparse" in a:
            used_bv.add(a["sparse"]["indices"]["bufferView"])
            used_bv.add(a["sparse"]["values"]["bufferView"])
    for im in js.get("images", []):
        if "bufferView" in im:
            used_bv.add(im["bufferView"])
    bv_map, new_bv, chunks, off = {}, [], [], 0
    for i, bv in enumerate(js["bufferViews"]):
        if i not in used_bv:
            continue
        o = bv.get("byteOffset", 0)
        raw = binc[o:o + bv["byteLength"]]
        pad = (4 - off % 4) % 4
        if pad:
            chunks.append(b"\0" * pad)
            off += pad
        nb = dict(bv)
        nb["byteOffset"] = off
        chunks.append(raw)
        off += len(raw)
        bv_map[i] = len(new_bv)
        new_bv.append(nb)
    for a in new_acc:
        if "bufferView" in a:
            a["bufferView"] = bv_map[a["bufferView"]]
        if "sparse" in a:
            for k in ("indices", "values"):
                a["sparse"][k]["bufferView"] = bv_map[a["sparse"][k]["bufferView"]]
    for im in js.get("images", []):
        if "bufferView" in im:
            im["bufferView"] = bv_map[im["bufferView"]]
    js["accessors"], js["bufferViews"] = new_acc, new_bv
    for m in js.get("meshes", []):
        for p in m["primitives"]:
            p["attributes"] = {k: acc_map[v] for k, v in p["attributes"].items()}
            if "indices" in p:
                p["indices"] = acc_map[p["indices"]]
            if "targets" in p:
                p["targets"] = [{k: acc_map[v] for k, v in t.items()} for t in p["targets"]]
    for s in js.get("skins", []):
        if "inverseBindMatrices" in s:
            s["inverseBindMatrices"] = acc_map[s["inverseBindMatrices"]]
    for an in js.get("animations", []):
        for s in an["samplers"]:
            s["input"], s["output"] = acc_map[s["input"]], acc_map[s["output"]]
    newbin = b"".join(chunks)
    js["buffers"][0]["byteLength"] = len(newbin)
    return newbin


def _as_unit_float(js, binc, i):
    a = js["accessors"][i]
    arr = accessor(js, binc, i).astype(np.float64)
    if a["componentType"] == 5121:
        arr /= 255.0
    elif a["componentType"] == 5123:
        arr /= 65535.0
    return arr


def quantize_attributes(js, binc):
    """Store WEIGHTS_0 and COLOR_0 as normalized UNSIGNED_BYTE (core glTF 2.0, no extension needed).
    Weights are rounded so every vertex still sums to exactly 255. Returns the new binary chunk;
    the old accessors become unreferenced (run compact() afterwards)."""
    out = bytearray(binc)
    done = {}

    def add_view(raw):
        pad = (4 - len(out) % 4) % 4
        out.extend(b"\0" * pad)
        off = len(out)
        out.extend(raw)
        js["bufferViews"].append({"buffer": 0, "byteOffset": off, "byteLength": len(raw), "target": 34962})
        return len(js["bufferViews"]) - 1

    for m in js.get("meshes", []):
        for p in m["primitives"]:
            for key in ("WEIGHTS_0", "COLOR_0"):
                ai = p["attributes"].get(key)
                if ai is None or js["accessors"][ai]["componentType"] == 5121:
                    continue
                if ai in done:
                    p["attributes"][key] = done[ai]
                    continue
                a = js["accessors"][ai]
                f = np.clip(_as_unit_float(js, binc, ai), 0.0, 1.0)
                if a["type"] == "VEC3":       # pad colour to RGBA so each element stays 4-byte aligned
                    f = np.hstack([f, np.ones((len(f), 1))])
                q = np.rint(f * 255.0).astype(np.int64)
                if key == "WEIGHTS_0":
                    s = f.sum(1, keepdims=True)
                    f = f / np.where(s > 0, s, 1.0)
                    q = np.floor(f * 255.0).astype(np.int64)
                    rem = 255 - q.sum(1)
                    frac = f * 255.0 - q
                    order = np.argsort(-frac, axis=1)
                    for r in range(4):
                        sel = rem > r
                        q[np.where(sel)[0], order[sel, r]] += 1
                q = np.clip(q, 0, 255).astype(np.uint8)
                bv = add_view(q.tobytes())
                js["accessors"].append({"bufferView": bv, "componentType": 5121, "normalized": True,
                                        "count": int(len(q)), "type": "VEC4"})
                done[ai] = len(js["accessors"]) - 1
                p["attributes"][key] = done[ai]
    js["buffers"][0]["byteLength"] = len(out)
    return bytes(out)


# ---------------------------------------------------------------- transforms

def quat_mat(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def node_local(n):
    M = np.eye(4)
    if "matrix" in n:
        return np.array(n["matrix"]).reshape(4, 4).T
    S = np.diag(n.get("scale", [1, 1, 1]))
    R = quat_mat(n.get("rotation", [0, 0, 0, 1]))
    M[:3, :3] = R @ S
    M[:3, 3] = n.get("translation", [0, 0, 0])
    return M


def world_mats(js):
    parent = {}
    for i, n in enumerate(js["nodes"]):
        for c in n.get("children", []):
            parent[c] = i
    W = {}

    def get(i):
        if i in W:
            return W[i]
        M = node_local(js["nodes"][i])
        if i in parent:
            M = get(parent[i]) @ M
        W[i] = M
        return M
    for i in range(len(js["nodes"])):
        get(i)
    return W, parent


def subtree(js, i):
    out = [i]
    for c in js["nodes"][i].get("children", []):
        out += subtree(js, c)
    return out


def b2g(p):
    """Blender (x, y, z) Z-up -> glTF (x, z, -y) Y-up."""
    p = np.asarray(p, float)
    return np.array([p[0], p[2], -p[1]])


def summarize(js, binc, size):
    s = {"fileBytes": size, "meshes": [], "animations": [], "materials": [m["name"] for m in js.get("materials", [])],
         "images": [(im.get("name"), im.get("mimeType")) for im in js.get("images", [])], "skins": []}
    for m in js.get("meshes", []):
        tris = 0
        prims = []
        for p in m["primitives"]:
            n = js["accessors"][p["indices"]]["count"] if "indices" in p else js["accessors"][p["attributes"]["POSITION"]]["count"]
            tris += n // 3
            prims.append(js["materials"][p["material"]]["name"] if "material" in p else None)
        attrs = sorted(m["primitives"][0]["attributes"].keys())
        s["meshes"].append({"name": m["name"], "tris": tris, "materials": prims, "attributes": attrs})
    for sk in js.get("skins", []):
        s["skins"].append({"name": sk.get("name"), "joints": len(sk["joints"])})
    for an in js.get("animations", []):
        dur = 0.0
        paths = {}
        for smp in an["samplers"]:
            a = js["accessors"][smp["input"]]
            dur = max(dur, a["max"][0])
        for ch in an["channels"]:
            paths[ch["target"]["path"]] = paths.get(ch["target"]["path"], 0) + 1
        keys = js["accessors"][an["samplers"][0]["input"]]["count"]
        s["animations"].append({"name": an["name"], "duration": round(dur, 4), "channels": len(an["channels"]),
                                "paths": paths, "keys": keys})
    return s


# ---------------------------------------------------------------- clip keys: retime, thin

def _append(js, out, arr, typ, minmax=False):
    arr = np.ascontiguousarray(arr, dtype="<f4").reshape(len(arr), NC[typ])
    out.extend(b"\0" * ((4 - len(out) % 4) % 4))
    js["bufferViews"].append({"buffer": 0, "byteOffset": len(out), "byteLength": arr.nbytes})
    out.extend(arr.tobytes())
    acc = {"bufferView": len(js["bufferViews"]) - 1, "componentType": 5126, "count": int(len(arr)), "type": typ}
    if minmax:
        acc["min"], acc["max"] = [float(arr.min())], [float(arr.max())]
    js["accessors"].append(acc)
    return len(js["accessors"]) - 1


def _reduce(t, v, quat, tol):
    """Indices of the keys to keep so that linear interpolation (slerp for rotations, as three.js
    does) between kept keys stays within tol of every dropped key."""
    n = len(t)
    if n <= 2:
        return list(range(n))

    def ok(a, b):
        k = np.arange(a + 1, b)
        u = ((t[k] - t[a]) / (t[b] - t[a]))[:, None]
        if quat:
            q0, q1 = v[a], v[b] if v[a] @ v[b] >= 0 else -v[b]
            th = np.arccos(float(np.clip(q0 @ q1, -1, 1)))
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


def retime_and_thin(js, binc, time_scale=None, keep_all=(), tol_rot_deg=0.1, tol_pos=0.0002):
    """time_scale: {clip: factor} for clips keyed denser than 30 Hz in Blender (their key times
    are scaled back to seconds). Every other clip not named in keep_all loses the keys that linear
    interpolation between their neighbours reproduces within the tolerance (0.1 deg, 0.2 mm); a
    constant track keeps its first and last key. Returns (binary, stats); run compact() after."""
    out = bytearray(binc)
    time_scale = time_scale or {}
    stats = {}
    for an in js.get("animations", []):
        name = an["name"]
        ts = time_scale.get(name, 1.0)
        thin = name not in keep_all
        before = after = 0
        cache = {}
        for smp in an["samplers"]:
            t = accessor(js, binc, smp["input"]).astype(np.float64)[:, 0] * ts
            v = accessor(js, binc, smp["output"]).astype(np.float64)
            before += len(t)
            typ = js["accessors"][smp["output"]]["type"]
            keep = _reduce(t, v, typ == "VEC4", math.radians(tol_rot_deg) if typ == "VEC4" else tol_pos) if thin else None
            if keep is not None and len(keep) < len(t):
                t, v = t[keep], v[keep]
                smp["output"] = _append(js, out, v, typ)
            elif ts == 1.0:
                after += len(t)
                continue
            key = t.tobytes()
            if key not in cache:
                cache[key] = _append(js, out, t[:, None], "SCALAR", True)
            smp["input"] = cache[key]
            after += len(t)
        stats[name] = (before, after)
    js["buffers"][0]["byteLength"] = len(out)
    return bytes(out), stats


# ---------------------------------------------------------------- hips travel in leg units

def leg_units(js, binc, scales):
    """scales: {armature node name: lk}. Gives each variant's `root` bone the rest scale lk and
    its `hips` bone 1 / lk (and the hips rest offset in root units, the same number on every
    variant), so the hips translation track of a shared clip, written in the carrier's metres,
    moves each variant's hips by lk times as much: what its legs need. World rest transforms of
    hips and everything below are unchanged; the root joint's inverse bind matrix is rescaled.
    Returns the binary (new IBM accessors appended; run compact() after)."""
    out = bytearray(binc)
    idx = {n.get("name"): i for i, n in enumerate(js["nodes"])}
    done = {}
    for arm, lk in scales.items():
        if abs(lk - 1.0) < 1e-9:
            continue
        sub = subtree(js, idx[arm])
        byname = {js["nodes"][i]["name"]: i for i in sub}
        root, hips = byname["root"], byname["hips"]
        assert hips in js["nodes"][root].get("children", []), arm
        for nd in (js["nodes"][root], js["nodes"][hips]):
            assert "scale" not in nd and "matrix" not in nd, (arm, nd.get("name"))
        js["nodes"][root]["scale"] = [lk, lk, lk]
        js["nodes"][hips]["scale"] = [1.0 / lk] * 3
        js["nodes"][hips]["translation"] = [x / lk for x in js["nodes"][hips].get("translation", [0, 0, 0])]
        for sk in js.get("skins", []):
            if root not in sk["joints"]:
                continue
            key = (sk["inverseBindMatrices"], root)
            if key not in done:
                ibm = accessor(js, binc, sk["inverseBindMatrices"]).astype(np.float64).copy()
                j = sk["joints"].index(root)
                M = ibm[j].reshape(4, 4).T
                M = np.diag([1.0 / lk, 1.0 / lk, 1.0 / lk, 1.0]) @ M
                ibm[j] = M.T.ravel()
                arr = np.ascontiguousarray(ibm, dtype="<f4")
                out.extend(b"\0" * ((4 - len(out) % 4) % 4))
                js["bufferViews"].append({"buffer": 0, "byteOffset": len(out), "byteLength": arr.nbytes})
                out.extend(arr.tobytes())
                js["accessors"].append({"bufferView": len(js["bufferViews"]) - 1, "componentType": 5126,
                                        "count": int(len(arr)), "type": "MAT4"})
                done[key] = len(js["accessors"]) - 1
            sk["inverseBindMatrices"] = done[key]
    js["buffers"][0]["byteLength"] = len(out)
    return bytes(out)
