"""Headless preview stills (Workbench: textures, studio light, outlines) for self-checks."""
import math
import os

import bpy
from mathutils import Vector

PREV = "HeroinePreview"


def _cam(loc, target, lens):
    cam = bpy.data.objects.get("PrevCam")
    if cam is None:
        cd = bpy.data.cameras.new("PrevCam")
        cam = bpy.data.objects.new("PrevCam", cd)
        bpy.context.scene.collection.objects.link(cam)
    cam.location = Vector(loc)
    d = Vector(target) - Vector(loc)
    cam.rotation_mode = "QUATERNION"
    cam.rotation_quaternion = d.to_track_quat("-Z", "Y")
    cam.data.lens = lens
    cam.data.clip_start = 0.01
    cam.data.clip_end = 100
    return cam


def setup(res):
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_WORKBENCH"
    sh = sc.display.shading
    sh.light = "STUDIO"
    sh.color_type = "TEXTURE"
    sh.show_object_outline = True
    sh.object_outline_color = (0.12, 0.07, 0.06)
    sh.show_cavity = True
    sh.cavity_type = "WORLD"
    sh.show_shadows = False
    sh.show_specular_highlight = False
    sh.background_type = "WORLD"
    if sc.world is None:
        sc.world = bpy.data.worlds.new("PreviewWorld")
    sc.world.color = (0.55, 0.53, 0.50)
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = False
    sc.render.image_settings.file_format = "PNG"
    sc.view_settings.view_transform = "Standard"
    return sc


def shoot(path, loc, target, lens=50, res=(800, 1000)):
    sc = setup(res)
    sc.camera = _cam(loc, target, lens)
    sc.render.filepath = path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.render.render(write_still=True)
    return path


def gpu_info():
    try:
        import gpu
        return f"{gpu.platform.backend_type_get()} | {gpu.platform.vendor_get()} | {gpu.platform.renderer_get()}"
    except Exception as e:
        return f"unavailable ({e})"


def turnaround(outdir, tag="", h=1.58):
    """Front, 3/4, side, back, game camera, face close-up."""
    c = (0, 0, h * 0.52)
    shots = {
        "front": ((0, -2.9, 0.95), c, 50),
        "three_quarter": ((2.05, -2.05, 1.1), c, 50),
        "side": ((2.9, 0, 0.95), c, 50),
        "back": ((0, 2.9, 0.95), c, 50),
        "game_camera": ((0, 3.0, 1.70), (0, 0, 1.05), 35),
        "face": ((0.0, -0.75, 1.47), (0, 0, 1.43), 85),
        "face_3q": ((0.45, -0.6, 1.48), (0, 0, 1.43), 85),
    }
    out = []
    for name, (loc, tgt, lens) in shots.items():
        res = (900, 900) if name.startswith("face") else ((1200, 900) if name == "game_camera" else (800, 1000))
        out.append(shoot(os.path.join(outdir, f"{name}{tag}.png"), loc, tgt, lens, res))
    # Morph targets on the face.
    head = bpy.data.objects.get("heroine_head")
    if head is not None and head.data.shape_keys:
        kb = head.data.shape_keys.key_blocks
        for key in ("blink", "smile"):
            kb[key].value = 1.0
            out.append(shoot(os.path.join(outdir, f"face_{key}{tag}.png"), (0.0, -0.75, 1.47), (0, 0, 1.43), 85, (900, 900)))
            kb[key].value = 0.0
        # Eyes at the game's distance: 3 m, 50 mm, 1280x720.
        out.append(shoot(os.path.join(outdir, f"face_at_3m{tag}.png"), (0.6, -2.95, 1.55), (0, 0, 1.35), 50, (1280, 720)))
    return out
