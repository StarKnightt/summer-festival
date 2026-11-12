"""Pure-Python GLB read / prune / compact / inspect (no Blender needed)."""
import json
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


def prune_animations(js, keep_nodes, root_names=("root",)):
    """Keep one animation per name; only rotation channels (and translation on the root bone) on
    keep_nodes; drop scale and every other translation."""
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
