"""Build the festival crowd NPCs and export public/models/people.glb.

Headless (below-normal priority, deterministic, no downloads):
  E:\\blender\\blender-5.1.2-windows-x64\\blender.exe --background --factory-startup \\
      --python tools/blender/people/build.py -- --out public/models/people.glb
Options after "--": --out <glb>, --no-previews.
Writes previews to tools/blender/people/previews/ and a summary JSON next to this file.
"""
import importlib
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
NEAR_BUDGET = int(os.environ.get("PEOPLE_NEAR_BUDGET", 12000))   # triangles per near-LOD mesh
SIZE_BUDGET = 4 * 1024 * 1024
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


def _args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = os.path.join(REPO, "public", "models", "people.glb")
    previews = True
    i = 0
    while i < len(argv):
        if argv[i] == "--out":
            out = os.path.abspath(argv[i + 1])
            i += 1
        elif argv[i] == "--no-previews":
            previews = False
        i += 1
    return out, previews


def _lower_priority():
    try:
        if os.name == "nt":
            import ctypes
            k = ctypes.windll.kernel32
            k.SetPriorityClass(k.GetCurrentProcess(), 0x00004000)  # BELOW_NORMAL
        else:
            os.nice(10)
    except Exception as e:  # pragma: no cover
        print("[build] could not lower priority:", e)


def export_glb(path, col, carrier):
    import bpy
    vl = bpy.context.view_layer
    for o in vl.objects:
        o.select_set(False)
    for o in col.all_objects:
        o.select_set(True)
    vl.objects.active = carrier
    os.makedirs(os.path.dirname(path), exist_ok=True)
    keys = bpy.ops.export_scene.gltf.get_rna_type().properties.keys()
    opts = dict(
        filepath=path, export_format="GLB", use_selection=True, use_active_scene=True,
        export_yup=True, export_apply=False, export_texcoords=True, export_normals=True,
        export_tangents=False, export_materials="EXPORT", export_image_format="AUTO",
        export_vertex_color="ACTIVE", export_all_vertex_colors=False, export_attributes=False,
        export_extras=True, export_skins=True, export_all_influences=False, export_def_bones=False,
        export_animations=True, export_animation_mode="ACTIONS", export_force_sampling=True,
        export_frame_step=1, export_optimize_animation_size=False, export_anim_slide_to_zero=True,
        export_rest_position_armature=True, export_morph=False, export_leaf_bone=False,
        export_lights=False, export_cameras=False, export_draco_mesh_compression_enable=False,
    )
    bpy.ops.export_scene.gltf(**{k: v for k, v in opts.items() if k in keys or k == "filepath"})


def main(out, do_previews):
    import bpy
    import numpy as np
    from npc import anim, bl, body, geo, glbtools, near, outfits, preview, rig
    for m in (geo, rig, body, outfits, near, bl, anim, glbtools, preview):
        importlib.reload(m)
    t0 = time.time()
    np.random.seed(7)
    bl.scene()
    col = bl.fresh_collection()
    img = bl.pattern_image()
    mats = {n: bl.material(n, img if n == "cloth_main" else None) for n in bl.MAT_ORDER}
    arms, meshes, nears, bodies, stats = {}, {}, {}, {}, {}
    for v in rig.ORDER:
        b = body.Body(v)
        outfits.BUILDERS[v](b)
        arm = rig.build_armature(bpy, f"npc_{v}", b.J, col)
        ob = bl.make_mesh(b.mb, arm, col, mats)
        arms[v], meshes[v], bodies[v] = arm, ob, b
        stats[v] = dict(tris=bl.tri_count(ob), verts=len(ob.data.vertices))
        parts = {}
        for tag, a, z in b.mb.parts:
            parts[tag] = parts.get(tag, 0)
        fstart = 0
        if os.environ.get("PEOPLE_PARTS"):
            vt = {}
            for f in b.mb.F:
                vt[f[0]] = vt.get(f[0], 0)
            tagof = []
            for tag, a, z in b.mb.parts:
                tagof.append((a, z, tag))
            cnt = {}
            for f in b.mb.F:
                t = next(tg for a, z, tg in tagof if a <= f[0] < z)
                cnt[t] = cnt.get(t, 0) + len(f) - 2
            print("[parts]", v, sorted(cnt.items(), key=lambda kv: -kv[1]))
        print(f"[build] {v}: {stats[v]['tris']} tris, {stats[v]['verts']} verts, materials "
              f"{[m.name for m in ob.data.materials]}")
        # near LOD: same skeleton, same joints, its own skinned mesh next to the far one
        nb_ = near.NearBody(v)
        near.BUILDERS[v](nb_)
        obn = bl.make_mesh(nb_.mb, arm, col, mats)
        nears[v] = obn
        stats[v].update(near_tris=bl.tri_count(obn), near_verts=len(obn.data.vertices))
        if os.environ.get("PEOPLE_PARTS"):
            cnt = {}
            tagof = [(a, z, tg) for tg, a, z in nb_.mb.parts]
            for f in nb_.mb.F:
                t = next(tg for a, z, tg in tagof if a <= f[0] < z)
                cnt[t] = cnt.get(t, 0) + len(f) - 2
            print("[parts-near]", v, sorted(cnt.items(), key=lambda kv: -kv[1]))
        print(f"[build] {v} near: {stats[v]['near_tris']} tris, {stats[v]['near_verts']} verts, materials "
              f"{[m.name for m in obn.data.materials]}")
        assert stats[v]["near_tris"] <= NEAR_BUDGET, (v, stats[v]["near_tris"])
        assert {m.name for m in obn.data.materials} >= {m.name for m in ob.data.materials} - {"cloth_shoe"}, v
    # identical rest rotations across variants (what makes the shared clips valid)
    R0 = {b.name: np.array(b.matrix_local)[:3, :3] for b in arms["woman"].data.bones}
    for v in rig.ORDER:
        for b in arms[v].data.bones:
            err = np.abs(np.array(b.matrix_local)[:3, :3] - R0[b.name]).max()
            assert err < 1e-5, (v, b.name, err)
    # clips (baked on the woman armature: the carrier; rotation tracks + root translation)
    fks = {v: anim.FK(arms[v], bodies[v].J) for v in ("woman", "kid")}
    clips, actions = {}, {}
    for name, n, ref in anim.CLIPS:
        out_frames, meta = anim.build_clip(name, n, fks[ref])
        meta["refSkeleton"] = ref
        meta["refHip"] = rig.VARIANTS[ref]["hip"]
        act, slot = anim.bake(arms["woman"], fks[ref], name, out_frames)
        clips[name], actions[name] = meta, act
        print(f"[build] clip {name}: {n} frames ({meta['duration']} s), ref {ref}, rootZ {meta['rootZ']} rootX {meta['rootX']}")
    # One NLA track per clip on the carrier: with several armatures in the file the exporter only
    # gathers actions that are explicitly bound to an object.
    ad = arms["woman"].animation_data_create()
    ad.action = None
    tracks = []
    for name, act in actions.items():
        tr = ad.nla_tracks.new()
        tr.name = name
        st = tr.strips.new(name, 0, act)
        try:
            st.action_slot = act.slots[0]
        except Exception:
            pass
        tracks.append(tr)
    export_glb(out, col, arms["woman"])
    for tr in tracks:
        ad.nla_tracks.remove(tr)
    # ---- post-process: prune channels, compact, add extras
    js, binc = glbtools.read(out)
    idx = {n.get("name"): i for i, n in enumerate(js["nodes"])}
    carrier_nodes = set(glbtools.subtree(js, idx["npc_woman"]))
    removed = glbtools.prune_animations(js, carrier_nodes)
    binc = glbtools.compact(js, binc)
    binc = glbtools.quantize_attributes(js, binc)
    binc = glbtools.compact(js, binc)
    W, parent = glbtools.world_mats(js)
    variants = {}
    for v in rig.ORDER:
        b = bodies[v]
        J, P = b.J, b.P
        sub = glbtools.subtree(js, idx[f"npc_{v}"])
        bone_idx = {js["nodes"][i]["name"]: i for i in sub}
        def local(bone, p_blender):
            M = W[bone_idx[bone]]
            p = glbtools.b2g(p_blender)
            return (np.linalg.inv(M) @ np.append(p, 1.0))[:3]
        def local_dir(bone, d_blender):
            M = W[bone_idx[bone]]
            return np.linalg.inv(M[:3, :3]) @ glbtools.b2g(d_blender)
        g = b.meta["grip"]["R"]
        gl = local("hand_R", g["point"])
        ax = local_dir("hand_R", g["axis"])
        pm = local_dir("hand_R", g["palm"])
        Vb = np.asarray(b.mb.V)
        hair_top = Vb[:, 2].max()
        top_pt = [0.0, J["top"][1], hair_top]
        tl = local("head", top_pt)
        mesh_node = next(i for i in sub if "mesh" in js["nodes"][i] and js["nodes"][i]["name"] == f"npc_{v}_body")
        near_node = next(i for i in sub if "mesh" in js["nodes"][i] and js["nodes"][i]["name"] == f"npc_{v}_near")
        msum = {m["name"]: m for m in glbtools.summarize(js, binc, 0)["meshes"]}
        tris = msum[js["meshes"][js["nodes"][mesh_node]["mesh"]]["name"]]["tris"]
        near_tris = msum[js["meshes"][js["nodes"][near_node]["mesh"]]["name"]]["tris"]
        leg = P["hip"]
        variants[v] = dict(
            node=f"npc_{v}", mesh=js["nodes"][mesh_node]["name"], nearMesh=js["nodes"][near_node]["name"],
            height=round(float(hair_top), 3),
            headTop=round(float(J["top"][2]), 3), hipHeight=leg, tris=tris, nearTris=near_tris,
            walkSpeed=round(anim.WALK_V * leg / rig.VARIANTS["woman"]["hip"], 3),
            runSpeed=round(anim.RUN_V * leg / rig.VARIANTS["kid"]["hip"], 3),
            rootScale={c: round(leg / clips[c]["refHip"], 4) for c in clips},
            handR_palm=dict(bone="hand_R", offset=[round(float(x), 4) for x in gl],
                            gripAxis=[round(float(x), 4) for x in glbtools.np.asarray(ax) / np.linalg.norm(ax)],
                            palmNormal=[round(float(x), 4) for x in pm / np.linalg.norm(pm)]),
            headTopOffset=dict(bone="head", offset=[round(float(x), 4) for x in tl]),
            bbox=dict(min=[round(float(x), 3) for x in np.minimum(glbtools.b2g(Vb.min(0)), glbtools.b2g(Vb.max(0)))],
                      max=[round(float(x), 3) for x in np.maximum(glbtools.b2g(Vb.min(0)), glbtools.b2g(Vb.max(0)))]),
            tints=preview.TINTS[v],
        )
        js["nodes"][idx[f"npc_{v}"]].setdefault("extras", {})["npc"] = variants[v]
    js.setdefault("scenes", [{}])[0].setdefault("extras", {})["people"] = dict(
        version=2, variants=list(rig.ORDER), clips=clips, clipCarrier="npc_woman",
        lod=dict(near="npc_X_near", far="npc_X_body", swapDistance=12.0, hysteresis=1.0,
                 note="same skeleton; show _near within swapDistance of the camera, _body beyond"),
        bones=[b for b, _ in rig.BONES],
        materials=["skin", "face", "hair", "cloth_main", "cloth_accent", "cloth_dark", "wood_geta", "cloth_shoe"],
        clothMainPattern=dict(texture="people_cloth_pattern", columns=list(body.COLUMNS.keys()), note="greyscale; multiply by tint"),
    )
    size = glbtools.write(out, js, binc)
    js2, bin2 = glbtools.read(out)
    summ = glbtools.summarize(js2, bin2, size)
    print(f"[build] wrote {out} ({size / 1024:.0f} KiB), pruned {removed} channels")
    assert size <= SIZE_BUDGET, size
    for m in summ["meshes"]:
        print(f"[glb] mesh {m['name']}: {m['tris']} tris, {m['materials']} {m['attributes']}")
    for a in summ["animations"]:
        print(f"[glb] anim {a['name']}: {a['duration']} s, {a['channels']} ch {a['paths']}, {a['keys']} keys")
    print("[glb] skins", summ["skins"])
    # ---- Blender re-import check (in its own scene)
    reimp = reimport(out)
    summary = dict(glb=summ, variants=variants, clips=clips, reimport=reimp, buildSeconds=round(time.time() - t0, 1))
    with open(os.path.join(HERE, "people_summary.json"), "w") as f:
        json.dump(summary, f, indent=1)
    if do_previews:
        rs = {(c, v): variants[v]["rootScale"][c] for v in rig.ORDER for c in clips}
        shots, gpu_r = preview.run_all(arms, meshes, nears, rig.ORDER, os.path.join(HERE, "previews"), actions, rs)
        summary["previews"] = [os.path.relpath(s, HERE) for s in shots]
        summary["gpu"] = gpu_r
        with open(os.path.join(HERE, "people_summary.json"), "w") as f:
            json.dump(summary, f, indent=1)
    print(f"[build] done in {time.time() - t0:.1f}s")


def reimport(path):
    """Re-import the GLB into the current scene, count what came back, then delete it again."""
    import bpy
    before = set(bpy.data.objects)
    before_act = set(bpy.data.actions)
    before_mat = set(bpy.data.materials)
    before_img = set(bpy.data.images)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    acts = [a for a in bpy.data.actions if a not in before_act]
    res = dict(objects=len(new), meshes=[], armatures=[])
    for o in new:
        if o.type == "MESH":
            res["meshes"].append(dict(name=o.name, tris=sum(len(p.vertices) - 2 for p in o.data.polygons),
                                      materials=[m.name for m in o.data.materials if m]))
        elif o.type == "ARMATURE":
            res["armatures"].append(dict(name=o.name, bones=len(o.data.bones)))
    res["actions"] = sorted(a.name for a in acts)
    print("[reimport]", json.dumps(res))
    for o in new:
        bpy.data.objects.remove(o, do_unlink=True)
    for a in acts:
        bpy.data.actions.remove(a)
    for m in [m for m in bpy.data.materials if m not in before_mat]:
        bpy.data.materials.remove(m)
    for i in [i for i in bpy.data.images if i not in before_img]:
        bpy.data.images.remove(i)
    return res


if __name__ == "__main__":
    o, p = _args()
    _lower_priority()
    try:
        main(o, p)
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
