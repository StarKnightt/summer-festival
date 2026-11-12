"""Build the Summer Festival heroine and export her as a GLB.

Headless (below-normal priority, deterministic):
  E:\\blender\\blender-5.1.2-windows-x64\\blender.exe --background --factory-startup \\
      --python tools/blender/heroine/build.py -- --out public/models/heroine.glb
Options after "--":
  --out <glb>        output path (default public/models/heroine.glb)
  --no-export        build only
  --no-anim          skip the clips
  --previews         render preview PNGs into tools/blender/heroine/previews/
  --verify           re-import the GLB in a clean scene and print/save its summary
"""
import importlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


def _lower_priority():
    try:
        if os.name == "nt":
            import ctypes
            k = ctypes.windll.kernel32
            k.SetPriorityClass(k.GetCurrentProcess(), 0x4000)   # BELOW_NORMAL_PRIORITY_CLASS
        else:
            os.nice(10)
    except Exception as e:
        print("[build] could not lower priority:", e)


def _args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    o = {"out": os.path.join(REPO, "public", "models", "heroine.glb"), "export": True, "anim": True,
         "previews": False, "verify": False}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--out":
            o["out"] = os.path.abspath(argv[i + 1])
            i += 1
        elif a == "--no-export":
            o["export"] = False
        elif a == "--no-anim":
            o["anim"] = False
        elif a == "--previews":
            o["previews"] = True
        elif a == "--verify":
            o["verify"] = True
        i += 1
    return o


def main(o):
    import bpy
    from lib import common, shape, tex, rig, head, hair, body, outfit, anim, export, preview, verify
    for m in (common, shape, tex, rig, head, hair, body, outfit, anim, export, preview, verify):
        importlib.reload(m)
    t0 = time.time()
    # Clean factory scene.
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.actions, bpy.data.armatures, bpy.data.images,
                 bpy.data.cameras, bpy.data.lights):
        for d in list(coll):
            coll.remove(d)
    sc = common.scene()
    sc.render.fps, sc.render.fps_base = anim.FPS, 1.0
    col = common.collection()
    rig.reset()
    head.build(col)
    hair.build(col)
    body.build(col)
    outfit.build(col)
    arm = rig.build_armature()
    rig.apply_all(col, arm)
    rig.lift(col, arm, shape.SOLE)
    meta = {"sole": shape.SOLE}
    if o["anim"]:
        meta["clips"] = anim.build(arm)
    meshes = [ob for ob in col.all_objects if ob.type == "MESH"]
    tris = sum(common.tri_count(ob) for ob in meshes)
    print(f"[build] {len(meshes)} meshes, {tris} triangles, {len(arm.data.bones)} bones, {time.time() - t0:.1f}s")
    for ob in sorted(meshes, key=lambda x: x.name):
        print(f"[build]   {ob.name:22s} {common.tri_count(ob):6d} tris  mats={[m.name for m in ob.data.materials]}")
    if o["previews"]:
        outdir = os.path.join(HERE, "previews")
        preview.turnaround(outdir)
        print("[gpu]", preview.gpu_info())
        if o["anim"]:
            anim.preview_frames(arm, outdir)
    if o["export"]:
        n = export.export(o["out"], meta)
        print(f"[build] wrote {o['out']} ({n / 1024:.0f} KiB)")
        if o["verify"]:
            summary = verify.summarize(o["out"])
            with open(os.path.join(HERE, "glb_summary.json"), "w") as f:
                json.dump(summary, f, indent=1)
    with open(os.path.join(HERE, "build_meta.json"), "w") as f:
        json.dump(meta, f, indent=1)


if __name__ == "__main__":
    _lower_priority()
    try:
        main(_args())
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
