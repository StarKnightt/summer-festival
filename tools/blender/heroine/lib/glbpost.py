"""GLB post-pass: drop bone scale animation channels (contract: no scale keys; the exporter's
forced sampling writes constant 1,1,1 tracks) and repack the binary chunk without the
orphaned accessors/bufferViews. Pure Python, deterministic."""
import json
import struct


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


def strip_scale_channels(path):
    gj, binary = _read(path)
    removed = 0
    for a in gj.get("animations", []):
        keep = [c for c in a["channels"] if c["target"]["path"] != "scale"]
        removed += len(a["channels"]) - len(keep)
        used = sorted({c["sampler"] for c in keep})
        remap = {o: n for n, o in enumerate(used)}
        a["samplers"] = [a["samplers"][i] for i in used]
        for c in keep:
            c["sampler"] = remap[c["sampler"]]
        a["channels"] = keep
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
    return removed
