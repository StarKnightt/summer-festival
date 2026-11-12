"""Build the festival crowd NPCs and export public/models/people.glb.

Headless (below-normal priority, deterministic, no downloads):
  E:\\blender\\blender-5.1.2-windows-x64\\blender.exe --background --factory-startup \\
      --python tools/blender/people/build.py -- --out public/models/people.glb
Options after "--": --out <glb>, --no-previews, --clip-previews (only the walk strips and clip stills).
Writes previews to tools/blender/people/previews/, people_summary.json and clips_report.json (feet,
slip, seams per clip and variant, measured on the exported GLB) next to this file.

The clips need the raw Mixamo FBX files in assets/mixamo (see MANIFEST.md there; they are not in
the repository). The build stops at once, with the list, if one is missing. The retarget is
tools/blender/mixamo/retarget.py, driven by npc/mocap.py; the hand-made clips are npc/handmade.py.
"""
import importlib
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
NEAR_BUDGET = int(os.environ.get("PEOPLE_NEAR_BUDGET", 14000))   # near LOD + geta_R + biggest hair + glasses
SIZE_BUDGET = int(5.5 * 1024 * 1024)
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


def _args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = os.path.join(REPO, "public", "models", "people.glb")
    previews = "full"
    i = 0
    while i < len(argv):
        if argv[i] == "--out":
            out = os.path.abspath(argv[i + 1])
            i += 1
        elif argv[i] == "--no-previews":
            previews = None
        elif argv[i] == "--clip-previews":
            previews = "clips"
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
        export_rest_position_armature=True, export_morph=True, export_morph_normal=False, export_morph_tangent=False,
        export_morph_animation=False, export_leaf_bone=False,
        export_lights=False, export_cameras=False, export_draco_mesh_compression_enable=False,
    )
    bpy.ops.export_scene.gltf(**{k: v for k, v in opts.items() if k in keys or k == "filepath"})


def main(out, do_previews):
    import bpy
    import numpy as np
    from npc import anim, bl, body, face, geo, glasses, glbcheck, glbtools, hair, handmade, headshape, mocap, near, outfits, preview, rig
    for m in (geo, rig, headshape, face, body, outfits, near, hair, glasses, bl, anim, glbtools, glbcheck, mocap, handmade, preview):
        importlib.reload(m)
    mocap.require_fbx()          # stop now, with the list, if a raw Mixamo clip is missing
    t0 = time.time()
    np.random.seed(7)
    bl.scene()
    col = bl.fresh_collection()
    img = bl.pattern_image()
    mats = {n: bl.material(n, img if n == "cloth_main" else None) for n in bl.MAT_ORDER}
    arms, meshes, nears, bodies, stats = {}, {}, {}, {}, {}
    extras_ob = {}   # v -> dict(geta=ob, hair={style: ob}, glasses=ob|None, sunglasses=ob)
    hair_tops = {}
    for v in rig.ORDER:
        b = body.Body(v)
        b.geta_mb = geo.MB(f"npc_{v}_geta_R")      # the right geta: its own mesh, shared by both LODs
        outfits.BUILDERS[v](b)
        arm = rig.build_armature(bpy, f"npc_{v}", b.J, col)
        ob = bl.make_mesh(b.mb, arm, col, mats)
        ex = dict(geta=bl.make_mesh(b.geta_mb, arm, col, mats), hair={}, glasses=None, sunglasses=None)
        hair_tops[v] = {}
        for style, hmb in hair.build(b, v).items():
            ex["hair"][style] = bl.make_mesh(hmb, arm, col, mats)
            hair_tops[v][style] = float(np.asarray(hmb.V)[:, 2].max())
        if v != "kid":
            ex["glasses"] = bl.make_mesh(glasses.build(b, v, False), arm, col, mats)
        ex["sunglasses"] = bl.make_mesh(glasses.build(b, v, True), arm, col, mats)
        extras_ob[v] = ex
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
        ex = extras_ob[v]
        stats[v]["geta_R_tris"] = bl.tri_count(ex["geta"])
        stats[v]["hair_tris"] = {k: bl.tri_count(o) for k, o in ex["hair"].items()}
        stats[v]["glasses_tris"] = {k: bl.tri_count(ex[k]) for k in ("glasses", "sunglasses") if ex[k] is not None}
        worst = stats[v]["near_tris"] + stats[v]["geta_R_tris"] + max(stats[v]["hair_tris"].values()) +             max(stats[v]["glasses_tris"].values())
        stats[v]["near_worst"] = worst
        print(f"[build] {v} near: {stats[v]['near_tris']} tris, {stats[v]['near_verts']} verts, materials "
              f"{[m.name for m in obn.data.materials]}; geta_R {stats[v]['geta_R_tris']}, hair {stats[v]['hair_tris']}, "
              f"glasses {stats[v]['glasses_tris']}; worst near total {worst}")
        assert worst <= NEAR_BUDGET, (v, worst)
        assert max(stats[v]["hair_tris"].values()) <= 1500, (v, stats[v]["hair_tris"])
        assert {m.name for m in obn.data.materials} >= {m.name for m in ob.data.materials} - {"cloth_shoe"}, v
    # identical rest rotations across variants (what makes the shared clips valid)
    R0 = {b.name: np.array(b.matrix_local)[:3, :3] for b in arms["woman"].data.bones}
    for v in rig.ORDER:
        for b in arms[v].data.bones:
            err = np.abs(np.array(b.matrix_local)[:3, :3] - R0[b.name]).max()
            assert err < 1e-5, (v, b.name, err)
    # bones.json: the full skeleton (for the Mixamo retarget), Blender armature space (Z up, facing -Y)
    bj = dict(note="All five variants share ONE skeleton layout: identical bone names, parents, order, rest "
                   "directions and roll (0 for every bone); only joint positions / bone lengths differ "
                   "(asserted at build time). Coordinates: Blender armature space, metres, Z up, character "
                   "faces -Y, +X = character's left; glTF = (x, z, -y). The original 22 bones are unchanged; "
                   "the 20 finger bones are new (children of hand_L/R; their rest pose is the relaxed curl).",
              order=[b for b, _ in rig.BONES], variants={})
    for v in rig.ORDER:
        bj["variants"][v] = [dict(name=b.name, parent=b.parent.name if b.parent else None,
                                  head=[round(x, 5) for x in b.head_local], tail=[round(x, 5) for x in b.tail_local],
                                  roll=0.0, length=round(b.length, 5)) for b in arms[v].data.bones]
    with open(os.path.join(HERE, "bones.json"), "w") as f:
        json.dump(bj, f, indent=1)
    # clips: retargeted / authored once on the woman armature (the carrier), shared by all variants
    getas = {v: extras_ob[v]["geta"] for v in rig.ORDER}
    ctx, actions, clips, motions = mocap.build(arms, bodies, nears, getas)
    for name, c in clips.items():
        print(f"[build] clip {name}: {c['duration']} s, {'loop' if c['loop'] else 'one-shot'}, {c['kind']}")
    seat = mocap.seat_heights(ctx, nears, actions["sit"])
    mocap.drop_variant_actions()
    print("[build] seat", seat)
    # One NLA track per clip on the carrier: with several armatures in the file the exporter only
    # gathers actions that are explicitly bound to an object.
    ad = arms["woman"].animation_data_create()
    ad.action = None
    tracks = []
    for name, act in actions.items():
        tr = ad.nla_tracks.new()
        tr.name = name
        st = tr.strips.new(name, 1, act)
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
    removed = glbtools.prune_animations(js, carrier_nodes, root_names=("hips",), skip_prefix=(), drop=("root",))
    binc = glbtools.compact(js, binc)
    binc = glbtools.quantize_attributes(js, binc)
    binc = glbtools.compact(js, binc)
    for m in js.get("materials", []):
        if m.get("name") == "glasses_lens":
            m["alphaMode"] = "BLEND"
            m["doubleSided"] = False
    nmorph = glbtools.sparse_morphs(js, binc) if hasattr(glbtools, "sparse_morphs") else None
    if nmorph:
        binc = glbtools.compact(js, nmorph)
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
        hair_top = max(Vb[:, 2].max(), max(hair_tops[v].values()))
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
            legScale=round(ctx.lk[v], 5),
            handR_palm=dict(bone="hand_R", offset=[round(float(x), 4) for x in gl],
                            gripAxis=[round(float(x), 4) for x in glbtools.np.asarray(ax) / np.linalg.norm(ax)],
                            palmNormal=[round(float(x), 4) for x in pm / np.linalg.norm(pm)]),
            headTopOffset=dict(bone="head", offset=[round(float(x), 4) for x in tl]),
            bbox=dict(min=[round(float(x), 3) for x in np.minimum(glbtools.b2g(Vb.min(0)), glbtools.b2g(Vb.max(0)))],
                      max=[round(float(x), 3) for x in np.maximum(glbtools.b2g(Vb.min(0)), glbtools.b2g(Vb.max(0)))]),
            tints=preview.TINTS[v],
            getaR=f"npc_{v}_geta_R",
            hairStyles={st: dict(mesh=f"npc_{v}_hair_{st}", top=round(t, 3),
                                 headTopOffset=[round(float(x), 4) for x in local("head", [0.0, J["top"][1], t])])
                        for st, t in hair_tops[v].items()},
            glasses=[n for n in (f"npc_{v}_glasses", f"npc_{v}_sunglasses") if (n.endswith("_sunglasses") or v != "kid")],
            faceLooks=dict(A="basis", B=bl.MORPH, meshes=[f"npc_{v}_near", f"npc_{v}_body"]),
            nearTrisWorst=stats[v]["near_worst"], hairTris=stats[v]["hair_tris"], glassesTris=stats[v]["glasses_tris"],
            getaRTris=stats[v]["geta_R_tris"],
        )
        js["nodes"][idx[f"npc_{v}"]].setdefault("extras", {})["npc"] = variants[v]
    # ---- clip keys: the 60 Hz run back to seconds; slow clips lose the keys interpolation reproduces
    binc, kstats = glbtools.retime_and_thin(js, binc, time_scale={c: 30.0 / m["keyRate"] for c, m in clips.items() if m["keyRate"] != 30},
                                            keep_all=mocap.LOCO)
    binc = glbtools.compact(js, binc)
    # ---- hips travel in leg units: the same hips track fits every variant's legs (no game work)
    binc = glbtools.leg_units(js, binc, {f"npc_{v}": ctx.lk[v] for v in rig.ORDER})
    binc = glbtools.compact(js, binc)
    # ---- checks on the file as the game plays it: feet, slip, seams; clipSpeed is measured here
    model = glbcheck.Model(js, binc, rig.ORDER)
    loops = [c for c, m in clips.items() if m["loop"]]
    shots1 = [c for c, m in clips.items() if not m["loop"]]
    report = dict(method=[ln.strip() for ln in glbcheck.__doc__.strip().splitlines()],
                  restSkinErr_mm=glbcheck.rest_check(model, rig.ORDER), tracks=glbcheck.tracks(model),
                  seams=glbcheck.seams(model, loops, shots1), clipSpeed={}, slip={}, feet={}, keys={c: list(k) for c, k in kstats.items()})
    for c in mocap.LOCO:
        report["clipSpeed"][c], report["slip"][c] = {}, {}
        for v in rig.ORDER:
            sp = round(glbcheck.slip(model, v, c)["measuredSpeed"], 3)
            report["clipSpeed"][c][v] = sp
            report["slip"][c][v] = glbcheck.slip(model, v, c, sp)
            r = report["slip"][c][v]
            print(f"[slip] {c} {v}: {sp} m/s, max {r['maxSlip_cm_s']} cm/s, p95 {r['p95Slip_cm_s']}, contact {r['contactHeight_mm']} mm")
    for c in clips:
        report["feet"][c] = {v: glbcheck.clip_feet(model, v, c) for v in rig.ORDER}
    report["lookTurnDeg"] = {v: glbcheck.head_turn(model, v, "look") for v in rig.ORDER}
    report["seat"] = seat
    report.update(ctx.report)
    for c, m in clips.items():
        m["duration"] = round(model.duration(c), 4)
        if c in report["clipSpeed"]:
            m["speed"] = report["clipSpeed"][c]
    for v in rig.ORDER:
        variants[v]["walkSpeed"] = report["clipSpeed"]["walk"][v]
        variants[v]["runSpeed"] = report["clipSpeed"]["run"][v]
        variants[v]["seatHeight"] = seat[v]["seatHeight"]
    with open(os.path.join(HERE, "clips_report.json"), "w") as f:
        json.dump(report, f, indent=1)
    problems = []
    for v, e in report["restSkinErr_mm"].items():
        if e > 0.05:
            problems.append(f"rest pose of {v} moved by {e} mm")
    for c, sm in report["seams"].items():
        if sm["rot_deg"] > 0.05 or sm["pos_mm"] > 0.1:
            problems.append(f"{c}: {sm['kind']} seam {sm['rot_deg']} deg / {sm['pos_mm']} mm")
    for c, t in report["tracks"].items():
        if not (t["head"] and t["neck"]) or t["translation"] != ["hips"]:
            problems.append(f"{c}: tracks {t}")
    for c in clips:
        for v in rig.ORDER:
            ft = report["feet"][c][v]
            lo, hi = ft["lowestOfBoth_mm"]
            if lo < -4.0 or (hi > 4.0 and c != "run"):
                problems.append(f"{c} on {v}: soles {ft['lowestOfBoth_mm']} mm from the floor")
            # seated clips sit back, pick_up crouches, the bow counterbalances: their hips may travel
            if c not in ("sit", "sit_fan", "sit_sleep", "pick_up", "bow") and max(ft["hipsTravel_cm"]) > 4.5:
                problems.append(f"{c} on {v}: hips travel {ft['hipsTravel_cm']} cm")
    for c, lim in (("walk", 3.0), ("walk_f", 3.0), ("sparkler", 3.0), ("run", 5.0)):
        for v in rig.ORDER:
            if report["slip"][c][v]["maxSlip_cm_s"] > lim:
                problems.append(f"{c} on {v}: slip {report['slip'][c][v]['maxSlip_cm_s']} cm/s (limit {lim})")
    report["problems"] = problems
    with open(os.path.join(HERE, "clips_report.json"), "w") as f:
        json.dump(report, f, indent=1)
    for pr in problems:
        print("[check] PROBLEM", pr)
    js.setdefault("scenes", [{}])[0].setdefault("extras", {})["people"] = dict(
        version=4, variants=list(rig.ORDER), clips=clips, clipCarrier="npc_woman",
        clipSpeed=report["clipSpeed"],
        clipSpeedNote="ground speed in m/s the clip implies at rate 1 and scale 1; play it at rate = actual speed / "
                      "(clipSpeed[clip][variant] * model scale)",
        legScale={v: round(ctx.lk[v], 5) for v in rig.ORDER},
        hips=dict(track="hips.position", units="metres on npc_woman; root bone rest scale = legScale, hips bone rest scale = "
                  "1 / legScale, so the same track moves each variant's hips by legScale times as much",
                  game="nothing: keep hips.position, there is no root.position track; do not write to the scale of root or hips"),
        seat=dict(clips=["sit", "sit_fan", "sit_sleep"], seatHeight={v: seat[v]["seatHeight"] for v in rig.ORDER},
                  hipsBack={v: seat[v]["hipsBack"] for v in rig.ORDER},
                  note="the root stays at the feet (soles on the floor at the root's height); seatHeight is where the "
                       "underside of the thighs is, hipsBack how far the hip joints are behind the root, both in metres at "
                       "scale 1. To sit exactly on a seat whose top is at height h above the ground, put the root at "
                       "h - seatHeight[variant] * scale above the ground (the feet then hang by that much)"),
        lod=dict(near="npc_X_near", far="npc_X_body", swapDistance=12.0, hysteresis=1.0,
                 note="same skeleton; show _near within swapDistance of the camera, _body beyond"),
        bones=[b for b, _ in rig.BONES],
        materials=list(bl.MAT_ORDER),
        hair=dict(pattern="npc_<v>_hair_<style>", rule="show exactly one per NPC; 100% on head; colour in COLOR_0"),
        specs=dict(pattern="npc_<v>_glasses | npc_<v>_sunglasses", rule="at most one per NPC; kid has sunglasses only",
                   lens="glasses_lens: alphaMode BLEND, tint and opacity in COLOR_0 (rgb, a)"),
        faceMorph=dict(name=bl.MORPH, note="morph target 0 on _near and _body: influence 0 = look A, 1 = look B"),
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
    summary["checks"] = dict(clipSpeed=report["clipSpeed"], problems=problems,
                             slip={c: {v: dict(max=r["maxSlip_cm_s"], p95=r["p95Slip_cm_s"]) for v, r in d.items()}
                                   for c, d in report["slip"].items()})
    with open(os.path.join(HERE, "people_summary.json"), "w") as f:
        json.dump(summary, f, indent=1)
    if do_previews:
        K = {c: int(round(clips[c]["duration"] * clips[c]["keyRate"])) for c in clips}
        stills = {"idle": [0], "talk": [K["talk"] // 3, 2 * K["talk"] // 3], "look": [K["look"] // 4, 3 * K["look"] // 4],
                  "wave": [K["wave"] // 2], "bow": [K["bow"] // 2], "eat": [K["eat"] // 2], "cheer": [K["cheer"] // 2],
                  "point": [K["point"] // 2], "call": [20], "fan": [22], "lookup": [30], "sit": [10], "sit_fan": [15],
                  "sit_sleep": [90], "yawn": [36], "cry": [20], "pick_up": [33], "peace": [30]}
        shots, gpu_r = preview.run_all(arms, meshes, nears, rig.ORDER, os.path.join(HERE, "previews"), actions, ctx.lk,
                                       extras=extras_ob, speeds=report["clipSpeed"], clips=clips, stills=stills,
                                       full=do_previews == "full")
        mocap.drop_variant_actions()
        summary["previews"] = [os.path.relpath(s_, HERE) for s_ in shots]
        summary["gpu"] = gpu_r
        with open(os.path.join(HERE, "people_summary.json"), "w") as f:
            json.dump(summary, f, indent=1)
    if problems:
        raise SystemExit("[build] the GLB was written, but the clip checks found problems (see clips_report.json):\n  " + "\n  ".join(problems))
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
