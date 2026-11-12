"""Re-import the exported GLB in a clean scene and summarise it (meshes, tris, bones, clips,
morph targets, materials, textures, bounds, file size). Also parses the GLB JSON directly."""
import json
import os
import struct

import bpy
import numpy as np


def _glb_json(path):
    with open(path, "rb") as f:
        data = f.read()
    magic, ver, total = struct.unpack_from("<III", data, 0)
    clen, ctype = struct.unpack_from("<II", data, 12)
    return json.loads(data[20:20 + clen].decode("utf8"))


def summarize(path):
    gj = _glb_json(path)
    sc = bpy.data.scenes.new("Verify")
    bpy.context.window_manager.windows[0].scene = sc if bpy.context.window_manager.windows else None
    before = set(bpy.data.objects)
    win = bpy.context.window_manager.windows[0] if bpy.context.window_manager.windows else None
    with bpy.context.temp_override(scene=sc) if win is None else bpy.context.temp_override(window=win, scene=sc):
        bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new if o.type == "MESH" and o.name.startswith("heroine")]
    arms = [o for o in new if o.type == "ARMATURE"]
    tris = 0
    per = {}
    for o in meshes:
        me = o.data
        me.calc_loop_triangles()
        per[o.name] = len(me.loop_triangles)
        tris += len(me.loop_triangles)
    lo = np.full(3, np.inf)
    hi = np.full(3, -np.inf)
    for o in meshes:
        V = np.array([o.matrix_world @ v.co for v in o.data.vertices])
        lo = np.minimum(lo, V.min(0))
        hi = np.maximum(hi, V.max(0))
    clips = {}
    for a in gj.get("animations", []):
        tmax = 0.0
        for s in a["samplers"]:
            acc = gj["accessors"][s["input"]]
            tmax = max(tmax, acc.get("max", [0])[0])
        clips[a["name"]] = round(tmax, 4)
    morphs = {}
    for m in gj.get("meshes", []):
        names = (m.get("extras") or {}).get("targetNames")
        if names:
            morphs[m["name"]] = names
    max_inf = 0
    for m in gj.get("meshes", []):
        for p in m["primitives"]:
            if "WEIGHTS_1" in p["attributes"]:
                max_inf = 8
            elif "WEIGHTS_0" in p["attributes"]:
                max_inf = max(max_inf, 4)
    # Animation channels by path (no scale channels expected).
    paths = {}
    for a in gj.get("animations", []):
        for ch in a["channels"]:
            p = ch["target"]["path"]
            paths[p] = paths.get(p, 0) + 1
    # Bone world matrices at rest from the glTF node hierarchy (three.js space).
    nodes = gj["nodes"]
    parent = {}
    for i, n in enumerate(nodes):
        for c in n.get("children", []):
            parent[c] = i

    def local_m(n):
        t = np.array(n.get("translation", [0, 0, 0]), float)
        x, y, z, w = n.get("rotation", [0, 0, 0, 1])
        s = np.array(n.get("scale", [1, 1, 1]), float)
        R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                      [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                      [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
        M = np.eye(4)
        M[:3, :3] = R * s
        M[:3, 3] = t
        return M

    def world(i):
        M = local_m(nodes[i])
        while i in parent:
            i = parent[i]
            M = local_m(nodes[i]) @ M
        return M

    byname = {n.get("name"): i for i, n in enumerate(nodes)}
    from . import attach
    pts, dirs = attach.points()
    att = {}
    for k, (p, bone) in pts.items():
        g = np.array([p[0], p[2], -p[1], 1.0])
        Wm = world(byname[bone])
        loc = np.linalg.inv(Wm) @ g
        att[k] = {"bone": bone, "local": [round(v, 4) for v in loc[:3]], "gltfWorldRest": [round(v, 4) for v in g[:3]]}
    for k, (d, bone) in dirs.items():
        g = np.array([d[0], d[2], -d[1]])
        Wm = world(byname[bone])
        loc = np.linalg.inv(Wm[:3, :3]) @ g
        loc = loc / np.linalg.norm(loc)
        att[k] = {"bone": bone, "localDir": [round(v, 4) for v in loc], "gltfWorldRestDir": [round(v, 4) for v in g]}
    out = {
        "attachments": att,
        "anim_channel_paths": paths,
        "file": os.path.basename(path),
        "file_kib": round(os.path.getsize(path) / 1024, 1),
        "meshes": per,
        "triangles": tris,
        "bones": len(arms[0].data.bones) if arms else 0,
        "bone_names": [b.name for b in arms[0].data.bones] if arms else [],
        "clips": clips,
        "morph_targets": morphs,
        "materials": sorted(m["name"] for m in gj.get("materials", [])),
        "images": [(i.get("name"), i.get("mimeType")) for i in gj.get("images", [])],
        "max_influences": max_inf,
        "bounds_blender_zup": {"min": [round(x, 4) for x in lo], "max": [round(x, 4) for x in hi]},
        "nodes": [n.get("name") for n in gj.get("nodes", []) if "mesh" in n],
        "extensions_used": gj.get("extensionsUsed", []),
    }
    print("[verify]", json.dumps(out, indent=1))
    return out
