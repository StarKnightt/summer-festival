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


_GPU_OK = []


def shoot(path, loc, target, lens=50, res=(800, 1000)):
    sc = setup(res)
    sc.camera = _cam(loc, target, lens)
    sc.render.filepath = path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.render.render(write_still=True)
    if not _GPU_OK:
        assert_gpu()          # the GPU context exists only once a render has started
        _GPU_OK.append(True)
    return path


def gpu_info():
    try:
        import gpu
        return f"{gpu.platform.backend_type_get()} | {gpu.platform.vendor_get()} | {gpu.platform.renderer_get()}"
    except Exception as e:
        return f"unavailable ({e})"


def assert_gpu():
    """Workbench renders on Blender's GPU context. Refuse to render on a software rasteriser
    (set HEROINE_ALLOW_SOFTWARE=1 to opt out on a machine without a GPU)."""
    info = gpu_info()
    print("[gpu]", info)
    low = info.lower()
    if os.environ.get("HEROINE_ALLOW_SOFTWARE") != "1" and (
            "unavailable" in low or any(k in low for k in ("llvmpipe", "swiftshader", "software", "basic render"))
            or "nvidia" not in low):
        raise RuntimeError(f"previews need the NVIDIA GPU, got: {info}")
    return info


FACE_SHOTS = {
    "face": ((0.0, -0.75, 1.47), (0, 0, 1.43), 85),
    "face_3q": ((0.45, -0.6, 1.48), (0, 0, 1.43), 85),
    "face_side": ((0.75, -0.02, 1.43), (0, -0.02, 1.43), 85),          # exact 90 degrees
    "face_3q_rear": ((0.65, 0.355, 1.45), (0, -0.02, 1.43), 85),        # 120 degrees from the front
}


def faces(outdir, tag=""):
    """Face close-ups: front, 3/4, side, blink, smile, blink+smile, and at the game's 3 m."""
    out = []
    for name, (loc, tgt, lens) in FACE_SHOTS.items():
        out.append(shoot(os.path.join(outdir, f"{name}{tag}.png"), loc, tgt, lens, (900, 900)))
    head = bpy.data.objects.get("heroine_head")
    if head is not None and head.data.shape_keys:
        kb = head.data.shape_keys.key_blocks
        for keys in (("blink",), ("smile",), ("blink", "smile")):
            for k in keys:
                kb[k].value = 1.0
            out.append(shoot(os.path.join(outdir, f"face_{'_'.join(keys)}{tag}.png"), (0.0, -0.75, 1.47), (0, 0, 1.43), 85,
                             (900, 900)))
            if keys == ("smile",):
                out.append(shoot(os.path.join(outdir, f"face_smile_3q{tag}.png"), (0.45, -0.6, 1.48), (0, 0, 1.43), 85,
                                 (900, 900)))
            for k in keys:
                kb[k].value = 0.0
        # Eyes at the game's distance: 3 m, 50 mm, 1280x720.
        out.append(shoot(os.path.join(outdir, f"face_at_3m{tag}.png"), (0.6, -2.95, 1.55), (0, 0, 1.35), 50, (1280, 720)))
    out += face_checks(outdir)
    return out


def turnaround(outdir, tag="", h=1.58):
    """Front, 3/4, side, back, game camera, face close-ups."""
    c = (0, 0, h * 0.52)
    shots = {
        "front": ((0, -2.9, 0.95), c, 50),
        "three_quarter": ((2.05, -2.05, 1.1), c, 50),
        "side": ((2.9, 0, 0.95), c, 50),
        "back": ((0, 2.9, 0.95), c, 50),
        "game_camera": ((0, 3.0, 1.70), (0, 0, 1.05), 35),
    }
    out = []
    for name, (loc, tgt, lens) in shots.items():
        res = (1200, 900) if name == "game_camera" else (800, 1000)
        out.append(shoot(os.path.join(outdir, f"{name}{tag}.png"), loc, tgt, lens, res))
    out += faces(outdir, tag)
    return out


def _toon_skin(color):
    """Check material: diffuse -> Shader to RGB -> constant ramp (one hard terminator, like the
    game's cel step) x skin colour, emitted. Any dent in the surface shows up as a jagged or
    stray terminator."""
    m = bpy.data.materials.new("toon_check_skin")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    dif = nt.nodes.new("ShaderNodeBsdfDiffuse")
    s2r = nt.nodes.new("ShaderNodeShaderToRGB")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = "CONSTANT"
    ramp.color_ramp.elements[0].position, ramp.color_ramp.elements[0].color = 0.0, (0.72, 0.6, 0.62, 1)
    ramp.color_ramp.elements[1].position, ramp.color_ramp.elements[1].color = 0.12, (1, 1, 1, 1)
    mul = nt.nodes.new("ShaderNodeMix")
    mul.data_type, mul.blend_type = "RGBA", "MULTIPLY"
    mul.inputs[0].default_value = 1.0
    mul.inputs[7].default_value = color
    em = nt.nodes.new("ShaderNodeEmission")
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(dif.outputs[0], s2r.inputs[0])
    nt.links.new(s2r.outputs[0], ramp.inputs[0])
    nt.links.new(ramp.outputs[0], mul.inputs[6])
    nt.links.new(mul.outputs[2], em.inputs[0])
    nt.links.new(em.outputs[0], out.inputs[0])
    return m


def face_checks(outdir):
    """Lit checks of the face: a hard-terminator toon skin under ONE sun from the upper front-left
    (her left), the same lit from her left side, and a flat (unshaded) Workbench render."""
    sc = bpy.context.scene
    head = bpy.data.objects["heroine_head"]
    skin = bpy.data.materials["skin"]
    toon = _toon_skin(tuple(skin.diffuse_color))
    slots = []
    for ob in bpy.data.objects:
        if ob.type == "MESH":
            for i, ms in enumerate(ob.material_slots):
                if ms.material == skin:
                    slots.append((ob, i))
                    ms.material = toon
    sd = bpy.data.lights.new("CheckSun", "SUN")
    sd.energy = 4.0
    sd.angle = 0.02
    sun = bpy.data.objects.new("CheckSun", sd)
    sc.collection.objects.link(sun)
    eng = [e.identifier for e in sc.render.bl_rna.properties["engine"].enum_items]
    old_engine = sc.render.engine
    out = []
    try:
        for tag, ldir, cam, tgt in (
                ("face_toon_key", (1.0, -1.0, 1.0), (0.0, -0.75, 1.47), (0, 0, 1.43)),
                ("face_toon_side", (1.0, -0.15, 0.25), (0.0, -0.75, 1.47), (0, 0, 1.43)),
                ("face_toon_key_3q", (1.0, -1.0, 1.0), (0.45, -0.6, 1.48), (0, 0, 1.43))):
            setup((900, 900))
            sc.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in eng else "BLENDER_EEVEE_NEXT"
            sc.world.color = (0.25, 0.25, 0.26)
            sun.rotation_mode = "QUATERNION"
            sun.rotation_quaternion = (-Vector(ldir)).to_track_quat("-Z", "Y")
            sc.camera = _cam(cam, tgt, 85)
            sc.render.filepath = os.path.join(outdir, f"{tag}.png")
            bpy.ops.render.render(write_still=True)
            out.append(sc.render.filepath)
        sc.render.engine = old_engine
    finally:
        for ob, i in slots:
            ob.material_slots[i].material = skin
        bpy.data.objects.remove(sun)
        bpy.data.lights.remove(sd)
        bpy.data.materials.remove(toon)
        sc.render.engine = old_engine
    setup((900, 900))
    sc.display.shading.light = "FLAT"
    sc.display.shading.show_cavity = False
    sc.camera = _cam((0.0, -0.75, 1.47), (0, 0, 1.43), 85)
    sc.render.filepath = os.path.join(outdir, "face_flat.png")
    bpy.ops.render.render(write_still=True)
    out.append(sc.render.filepath)
    setup((900, 900))
    return out
