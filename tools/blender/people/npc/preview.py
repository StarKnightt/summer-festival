"""Eevee preview stills (GPU, asserted): lineups front / 3/4 / back, face close-ups, clip frames from a
street-level camera ~4 m away, the game camera view. Per-variant tints mimic the game's instancing."""
import math
import os

import bpy
import numpy as np

from .geo import srgb

TINTS = {
    "woman": dict(skin="#f6d5c2", hair="#3a2620", cloth_main="#f19aa6", cloth_accent="#f3c74f", cloth_dark="#3b3f6b", wood_geta="#c99a66", face="#ffffff"),
    "man": dict(skin="#e9c2a6", hair="#1f1a1c", cloth_main="#40507a", cloth_accent="#c9b98f", cloth_dark="#2a2a2e", wood_geta="#b88a5a", face="#ffffff"),
    "kid": dict(skin="#f7d9c6", hair="#4a3426", cloth_main="#7cc3ea", cloth_accent="#ffffff", cloth_dark="#2d3b6b", wood_geta="#d0a46e", face="#ffffff"),
    "keeper": dict(skin="#e3b896", hair="#24201f", cloth_main="#d8423a", cloth_accent="#f4efe4", cloth_dark="#232a3a", cloth_shoe="#2a2c33", face="#ffffff"),
    "elder": dict(skin="#efcfb8", hair="#bdb8b4", cloth_main="#cfc6e6", cloth_accent="#6a4a7a", cloth_dark="#3a3040", wood_geta="#b08458", face="#ffffff"),
}
SPACING = 0.95


def gpu_check():
    import gpu
    r = gpu.platform.renderer_get()
    print("[gpu]", r, "|", gpu.platform.backend_type_get())
    if any(k in r.lower() for k in ("llvmpipe", "swiftshader", "software", "basic render")):
        raise RuntimeError("software rasteriser: " + r)
    return r


def preview_material(base, v):
    name = f"prev_{base.name}_{v}"
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Roughness"].default_value = 0.9
    tint = TINTS[v].get(base.name, "#ffffff")
    rgb = nt.nodes.new("ShaderNodeRGB")
    rgb.outputs[0].default_value = (*srgb(tint), 1.0)
    va = nt.nodes.new("ShaderNodeVertexColor")
    va.layer_name = "Col"
    mul = nt.nodes.new("ShaderNodeMix")
    mul.data_type = "RGBA"
    mul.blend_type = "MULTIPLY"
    mul.inputs[0].default_value = 1.0
    nt.links.new(rgb.outputs[0], mul.inputs[6])
    nt.links.new(va.outputs["Color"], mul.inputs[7])
    out = mul.outputs[2]
    src = next((n for n in base.node_tree.nodes if n.type == "TEX_IMAGE"), None)
    if src is not None:
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = src.image
        mul2 = nt.nodes.new("ShaderNodeMix")
        mul2.data_type = "RGBA"
        mul2.blend_type = "MULTIPLY"
        mul2.inputs[0].default_value = 1.0
        nt.links.new(out, mul2.inputs[6])
        nt.links.new(tex.outputs["Color"], mul2.inputs[7])
        out = mul2.outputs[2]
    if base.name == "face":
        # the game draws face features unlit-ish: show them at their albedo
        nt.links.new(out, bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = 1.0
        bsdf.inputs["Base Color"].default_value = (0, 0, 0, 1)
        return m
    nt.links.new(out, bsdf.inputs["Base Color"])
    return m


def setup(meshes, res=(1600, 900)):
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    try:
        sc.eevee.taa_render_samples = 16
    except Exception:
        pass
    w = bpy.data.worlds.get("PrevWorld") or bpy.data.worlds.new("PrevWorld")
    w.use_nodes = True
    bg = next(n for n in w.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs[0].default_value = (0.62, 0.70, 0.80, 1.0)
    bg.inputs[1].default_value = 0.9
    sc.world = w
    if "PrevSun" not in bpy.data.objects:
        ld = bpy.data.lights.new("PrevSun", "SUN")
        ld.energy = 3.2
        ld.angle = math.radians(8)
        sun = bpy.data.objects.new("PrevSun", ld)
        sc.collection.objects.link(sun)
        sun.rotation_euler = (math.radians(50), 0, math.radians(-35))
        gm = bpy.data.meshes.new("PrevGround")
        s = 12
        gm.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
        g = bpy.data.objects.new("PrevGround", gm)
        mat = bpy.data.materials.new("prev_ground")
        mat.use_nodes = True
        b = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        b.inputs["Base Color"].default_value = (*srgb("#9a948c"), 1)
        b.inputs["Roughness"].default_value = 1.0
        gm.materials.append(mat)
        sc.collection.objects.link(g)
    for v, ob in meshes.items():
        for i, slot in enumerate(ob.material_slots):
            base = slot.material
            if base is not None and not base.name.startswith("prev_"):
                ob.data.materials[i] = preview_material(base, v)
    return sc


def camera(loc, target, lens=50):
    cam = bpy.data.objects.get("PrevCam")
    if cam is None:
        cam = bpy.data.objects.new("PrevCam", bpy.data.cameras.new("PrevCam"))
        bpy.context.scene.collection.objects.link(cam)
    cam.data.lens = lens
    cam.data.clip_start = 0.05
    loc, target = np.asarray(loc, float), np.asarray(target, float)
    d = target - loc
    rx = math.atan2(math.hypot(d[0], d[1]), -d[2])
    rz = math.atan2(-d[0], d[1])
    cam.location = tuple(loc)
    cam.rotation_euler = (rx, 0, rz)
    bpy.context.scene.camera = cam
    return cam


def render(path):
    sc = bpy.context.scene
    sc.render.filepath = path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.render.render(write_still=True)
    return path


ROOT_SCALE = {}   # (clip, variant) -> scale for root.position (set by run_all)
_SCALED = {}


def scaled_action(action, v):
    """Preview copy of a clip with root.location scaled for this variant's legs (what the game does)."""
    k = ROOT_SCALE.get((action.name, v), 1.0)
    if abs(k - 1.0) < 1e-4:
        return action
    key = (action.name, v)
    if key not in _SCALED:
        a2 = action.copy()
        a2.name = f"prev_{action.name}_{v}"
        for layer in a2.layers:
            for st in layer.strips:
                for cb in st.channelbags:
                    for fc in cb.fcurves:
                        if fc.data_path == 'pose.bones["root"].location':
                            for kp in fc.keyframe_points:
                                kp.co[1] *= k
        _SCALED[key] = a2
    return _SCALED[key]


def lineup(arms, order, yaw=0.0, action=None, frame=0, slot=None, spacing=SPACING):
    n = len(order)
    for i, v in enumerate(order):
        a = arms[v]
        act = scaled_action(action, v) if action is not None else None
        a.location = ((i - (n - 1) / 2) * spacing, 0, 0)
        a.rotation_euler = (0, 0, math.radians(yaw))
        ad = a.animation_data or a.animation_data_create()
        if action is None:
            ad.action = None
            for pb in a.pose.bones:
                pb.rotation_quaternion = (1, 0, 0, 0)
                pb.location = (0, 0, 0)
        else:
            ad.action = act
            try:
                ad.action_slot = act.slots[0]
            except Exception:
                pass
    bpy.context.scene.frame_set(frame)
    bpy.context.view_layer.update()


def show_lod(meshes, nears, which, only=None):
    """which: 'near' | 'far'; only: a variant to show alone (others hidden)."""
    for v in meshes:
        vis = only is None or v == only
        meshes[v].hide_render = not (vis and which == "far")
        nears[v].hide_render = not (vis and which == "near")


def side_by_side(paths, out, gap=8):
    ims = [bpy.data.images.load(p, check_existing=False) for p in paths]
    arrs = []
    for im in ims:
        a = np.empty(im.size[0] * im.size[1] * 4, dtype=np.float32)
        im.pixels.foreach_get(a)
        arrs.append(a.reshape(im.size[1], im.size[0], 4))
    h = max(a.shape[0] for a in arrs)
    sep = np.ones((h, gap, 4), dtype=np.float32)
    parts = []
    for k, a in enumerate(arrs):
        if k:
            parts.append(sep)
        parts.append(a)
    img = np.concatenate(parts, 1)
    o = bpy.data.images.new("prev_sbs", img.shape[1], img.shape[0], alpha=False)
    o.pixels.foreach_set(img.ravel())
    o.filepath_raw = out
    o.file_format = "PNG"
    o.save()
    for im in ims + [o]:
        bpy.data.images.remove(im)
    for p in paths:
        try:
            os.remove(p)
        except OSError:
            pass
    return out


def solo(arms, order, v, action, frame, yaw=0.0):
    """Put variant v alone at the origin, the others parked far away."""
    for i, w in enumerate(order):
        lineup({w: arms[w]}, [w], yaw, action, frame)
        if w != v:
            arms[w].location = (50 + 3 * i, 50, 0)
    arms[v].location = (0, 0, 0)
    bpy.context.scene.frame_set(frame)
    bpy.context.view_layer.update()


def run_all(arms, meshes, nears, order, outdir, actions, root_scale=None):
    ROOT_SCALE.clear()
    ROOT_SCALE.update(root_scale or {})
    setup({v: meshes[v] for v in order})
    setup({v: nears[v] for v in order})
    sc = bpy.context.scene
    shots = []
    gpu_r = None
    # near lineups at the first idle frame: front, 3/4, back; far 3/4 for reference
    show_lod(meshes, nears, "near")
    for tag, yaw in (("front", 0.0), ("threequarter", -38.0), ("back", 180.0)):
        lineup(arms, order, yaw, actions.get("idle"), 0)
        camera((0, -6.2, 1.0), (0, 0, 0.85), lens=45)
        shots.append(render(os.path.join(outdir, f"lineup_{tag}.png")))
        if gpu_r is None:
            gpu_r = gpu_check()
    show_lod(meshes, nears, "far")
    lineup(arms, order, -38.0, actions.get("idle"), 0)
    shots.append(render(os.path.join(outdir, "lineup_threequarter_far.png")))
    # game-camera close-ups, near | far side by side: ~1.5 m high, ~2.7 m away, 3/4 front
    sc.render.resolution_x, sc.render.resolution_y = 900, 1000
    for v, clip, frame, yaw in (("man", "idle", 30, -25.0), ("woman", "idle", 30, -25.0), ("woman", "walk", 7, -40.0),
                                ("woman", "walk", 22, -40.0), ("woman", "sparkler", 9, -40.0), ("woman", "wave", 15, -25.0),
                                ("man", "call", 20, -30.0), ("elder", "fan", 22, -30.0), ("man", "talk", 25, -25.0)):
        act = actions.get(clip)
        tmp = []
        for which in ("near", "far"):
            solo(arms, order, v, act, frame, yaw)
            show_lod(meshes, nears, which, only=v)
            camera((0.9, -2.55, 1.5), (0, 0, 1.0), lens=38)
            tmp.append(render(os.path.join(outdir, f"_tmp_{which}.png")))
        shots.append(side_by_side(tmp, os.path.join(outdir, f"closeup_{v}_{clip}_{frame:02d}_near_vs_far.png")))
    sc.render.resolution_x, sc.render.resolution_y = 1600, 900
    # clip frames of the near LODs from a street-level camera ~4 m away
    show_lod(meshes, nears, "near")
    for clip, frame in (("idle", 60), ("walk", 7), ("walk", 22), ("run", 4), ("run", 11), ("wave", 15), ("call", 20),
                        ("call", 60), ("talk", 25), ("fan", 22), ("lookup", 30), ("sparkler", 9)):
        act = actions.get(clip)
        if act is None:
            continue
        lineup(arms, order, 70.0, act, frame)
        camera((2.2, -4.2, 1.15), (0, 0, 0.8), lens=32)
        shots.append(render(os.path.join(outdir, f"clip_{clip}_{frame:02d}.png")))
    # face close-ups, near | far
    sc.render.resolution_x = sc.render.resolution_y = 600
    for v in order:
        tmp = []
        for which in ("near", "far"):
            solo(arms, order, v, actions.get("idle"), 0)
            show_lod(meshes, nears, which, only=v)
            a = arms[v]
            pb = a.pose.bones["head"]
            hp = a.matrix_world @ pb.head
            camera((hp.x + 0.14, hp.y - 0.62, hp.z + 0.07), (hp.x, hp.y, hp.z + 0.06), lens=85)
            tmp.append(render(os.path.join(outdir, f"_tmp_{which}.png")))
        shots.append(side_by_side(tmp, os.path.join(outdir, f"face_{v}.png")))
    sc.render.resolution_x, sc.render.resolution_y = 1600, 900
    show_lod(meshes, nears, "near")
    return shots, gpu_r
