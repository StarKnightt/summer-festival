"""Eevee preview stills (GPU, asserted): lineups front / 3/4 / back, face close-ups, clip frames from a
street-level camera ~4 m away, the game camera view. Per-variant tints mimic the game's instancing."""
import math
import os

import bpy
import numpy as np

from .geo import srgb

TINTS = {
    "woman": dict(skin="#f6d5c2", hair="#ffffff", cloth_main="#f19aa6", cloth_accent="#f3c74f", cloth_dark="#3b3f6b", wood_geta="#c99a66", face="#ffffff"),
    "man": dict(skin="#e9c2a6", hair="#ffffff", cloth_main="#40507a", cloth_accent="#c9b98f", cloth_dark="#2a2a2e", wood_geta="#b88a5a", face="#ffffff"),
    "kid": dict(skin="#f7d9c6", hair="#ffffff", cloth_main="#7cc3ea", cloth_accent="#ffffff", cloth_dark="#2d3b6b", wood_geta="#d0a46e", face="#ffffff"),
    "keeper": dict(skin="#e3b896", hair="#ffffff", cloth_main="#d8423a", cloth_accent="#f4efe4", cloth_dark="#232a3a", cloth_shoe="#2a2c33", face="#ffffff"),
    "elder": dict(skin="#efcfb8", hair="#ffffff", cloth_main="#cfc6e6", cloth_accent="#6a4a7a", cloth_dark="#3a3040", wood_geta="#b08458", face="#ffffff"),
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
    if base.name == "glasses_lens":
        nt.links.new(va.outputs["Alpha"], bsdf.inputs["Alpha"])
        bsdf.inputs["Roughness"].default_value = 0.15
        try:
            m.surface_render_method = "BLENDED"
        except Exception:
            m.blend_method = "BLEND"
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


LK = {}           # variant -> leg scale (hips travel of the shared clips is multiplied by it; set by run_all)


def scaled_action(action, v):
    """Preview copy of a clip as variant v plays it: the hips translation times its leg scale
    (in the GLB the rest scales of root / hips do this, see glbtools.leg_units)."""
    from . import mocap
    return mocap.variant_action(action, LK.get(v, 1.0), v)


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


def compose(rows, out, gap=6, scale=1):
    """Tile rendered PNGs: rows = [[path, ...], ...] (top row first); deletes the inputs."""
    def load(p):
        im = bpy.data.images.load(p, check_existing=False)
        a = np.empty(im.size[0] * im.size[1] * 4, dtype=np.float32)
        im.pixels.foreach_get(a)
        a = a.reshape(im.size[1], im.size[0], 4)[::-1]          # top-down
        bpy.data.images.remove(im)
        if scale != 1:
            a = a.repeat(scale, 0).repeat(scale, 1)
        return a
    R = []
    for row in rows:
        arrs = [load(p) for p in row]
        h = max(a.shape[0] for a in arrs)
        parts = []
        for k, a in enumerate(arrs):
            if k:
                parts.append(np.ones((h, gap, 4), np.float32))
            if a.shape[0] < h:
                a = np.vstack([a, np.ones((h - a.shape[0], a.shape[1], 4), np.float32)])
            parts.append(a)
        R.append(np.concatenate(parts, 1))
    w = max(r.shape[1] for r in R)
    rows_ = []
    for k, r in enumerate(R):
        if k:
            rows_.append(np.ones((gap, w, 4), np.float32))
        if r.shape[1] < w:
            r = np.hstack([r, np.ones((r.shape[0], w - r.shape[1], 4), np.float32)])
        rows_.append(r)
    img = np.concatenate(rows_, 0)[::-1].copy()
    o = bpy.data.images.new("prev_cmp", img.shape[1], img.shape[0], alpha=False)
    o.pixels.foreach_set(img.ravel())
    o.filepath_raw = out
    o.file_format = "PNG"
    o.save()
    bpy.data.images.remove(o)
    for row in rows:
        for p in row:
            try:
                os.remove(p)
            except OSError:
                pass
    return out


def crop(path, x0, y0, x1, y1, scale=1):
    """Crop (top-down pixel box) a rendered PNG in place, optionally nearest-upscaled."""
    im = bpy.data.images.load(path, check_existing=False)
    W, H = im.size
    a = np.empty(W * H * 4, dtype=np.float32)
    im.pixels.foreach_get(a)
    bpy.data.images.remove(im)
    a = a.reshape(H, W, 4)[::-1][y0:y1, x0:x1]
    a = a.repeat(scale, 0).repeat(scale, 1)[::-1].copy()
    o = bpy.data.images.new("prev_crop", a.shape[1], a.shape[0], alpha=False)
    o.pixels.foreach_set(a.ravel())
    o.filepath_raw = path
    o.file_format = "PNG"
    o.save()
    bpy.data.images.remove(o)
    return path


class Dress:
    """Which hairstyle / specs / face look each variant shows in the previews."""

    def __init__(self, extras, meshes, nears):
        self.ex, self.meshes, self.nears = extras, meshes, nears

    def set(self, v, hair=0, specs=None, look="A", blink=0.0, smile=0.0):
        ex = self.ex[v]
        styles = list(ex["hair"])
        for i, st in enumerate(styles):
            ex["hair"][st].hide_render = i != (hair % len(styles))
        for k in ("glasses", "sunglasses"):
            if ex[k] is not None:
                ex[k].hide_render = specs != k
        for ob in (self.meshes[v], self.nears[v]):
            sk = ob.data.shape_keys
            if sk is not None:
                for nm, val in (("face_b", 1.0 if look == "B" else 0.0), ("blink", blink), ("smile", smile)):
                    if nm in sk.key_blocks:
                        sk.key_blocks[nm].value = val


def cam_vfov(loc, target, vfov_deg):
    cam = camera(loc, target)
    cam.data.sensor_fit = "VERTICAL"
    cam.data.angle_y = math.radians(vfov_deg)
    return cam


def walk_strip(arms, order, v, action, n_keys, key_rate, speed, outdir, tag, nshots=8):
    """Side view of one cycle: the armature advances at the clip speed (as the game moves it), the
    camera stays put, so a planted shoe must stay on the same ground tick from tile to tile.
    n_keys: key intervals in the cycle; key_rate: keys per second."""
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = 400, 520
    tiles = []
    a = arms[v]
    T = n_keys / key_rate
    for k in range(nshots):
        f = int(round(k * n_keys / nshots))
        solo(arms, order, v, action, 1 + f)
        t = f / key_rate
        a.location = (0, -speed * t + speed * T / 2, 0)
        bpy.context.view_layer.update()
        h = a.data.bones["head"].head_local.z
        cam = camera((3.2, 0, h * 0.58), (0, 0, h * 0.58))
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = h * 1.30
        tiles.append(render(os.path.join(outdir, f"_tmp_strip_{k}.png")))
    bpy.data.objects["PrevCam"].data.type = "PERSP"
    a.location = (0, 0, 0)
    return compose([tiles], os.path.join(outdir, f"{tag}.png"), gap=2)


def bench(top=0.45, show=True):
    """A plain 0.45 m seat behind the feet of the whole lineup, for the seated stills."""
    ob = bpy.data.objects.get("PrevBench")
    if ob is None:
        x, y0, y1 = 3.0, 0.14, 0.62
        V = [(-x, y0, 0), (x, y0, 0), (x, y1, 0), (-x, y1, 0), (-x, y0, top), (x, y0, top), (x, y1, top), (-x, y1, top)]
        F = [(0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7), (4, 5, 6, 7)]
        me = bpy.data.meshes.new("PrevBench")
        me.from_pydata(V, [], F)
        ob = bpy.data.objects.new("PrevBench", me)
        m = bpy.data.materials.new("prev_bench")
        m.use_nodes = True
        bs = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        bs.inputs["Base Color"].default_value = (*srgb("#8a6a48"), 1)
        bs.inputs["Roughness"].default_value = 1.0
        me.materials.append(m)
        bpy.context.scene.collection.objects.link(ob)
    ob.hide_render = not show
    return ob


def ground_ticks():
    """Thin dark lines across the ground every 10 cm (Y) to read foot slip in the walk strips."""
    if "PrevTicks" in bpy.data.objects:
        return bpy.data.objects["PrevTicks"]
    V, F = [], []
    for i in range(-30, 31):
        y = i * 0.1
        w = 0.006 if i % 5 else 0.012
        b = len(V)
        V += [(-0.6, y - w / 2, 0.001), (0.6, y - w / 2, 0.001), (0.6, y + w / 2, 0.001), (-0.6, y + w / 2, 0.001)]
        F.append((b, b + 1, b + 2, b + 3))
    me = bpy.data.meshes.new("PrevTicks")
    me.from_pydata(V, [], F)
    ob = bpy.data.objects.new("PrevTicks", me)
    m = bpy.data.materials.new("prev_ticks")
    m.use_nodes = True
    bs = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bs.inputs["Base Color"].default_value = (0.05, 0.05, 0.06, 1)
    me.materials.append(m)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def run_all(arms, meshes, nears, order, outdir, actions, lk=None, extras=None, speeds=None, clips=None, stills=None,
            full=True):
    LK.clear()
    LK.update(lk or {})
    for v in order:
        ex = extras[v]
        setup({v: meshes[v]})
        setup({v: nears[v]})
        for o in [ex["geta"], ex["glasses"], ex["sunglasses"]] + list(ex["hair"].values()):
            if o is not None:
                setup({v: o})
    sc = bpy.context.scene
    shots = []
    gpu_r = None          # queried right after the first render (no GPU context before it in background)
    D = Dress(extras, meshes, nears)
    os.makedirs(outdir, exist_ok=True)
    for f in os.listdir(outdir):
        if f.endswith(".png"):
            os.remove(os.path.join(outdir, f))
    idle = actions.get("idle")
    if full:
        # ---- crowd lineups (near LOD): every hairstyle, plain / glasses / sunglasses, both face looks
        show_lod(meshes, nears, "near")
        combos = [(0, None, "A"), (1, "glasses", "B"), (2, "sunglasses", "A")]
        rows = []
        for k, (hs, sp, lk) in enumerate(combos):
            row = []
            for yaw in (0.0, -35.0):
                for v in order:
                    D.set(v, hs, ("sunglasses" if sp else None) if v == "kid" else sp, lk)
                lineup(arms, order, yaw, idle, 0)
                camera((0, -6.2, 1.0), (0, 0, 0.85), lens=45)
                row.append(render(os.path.join(outdir, f"_tmp_l{k}_{int(yaw)}.png")))
                if gpu_r is None:
                    gpu_r = gpu_check()      # raises on a software rasteriser
            rows.append(row)
        shots.append(compose(rows, os.path.join(outdir, "lineup_crowd_mix.png")))
        # ---- per-variant face close-ups (near LOD). Row per look; front + 3/4 with style 0, then 3/4
        # with style 1 + glasses (kid: sunglasses) and style 2
        sc.render.resolution_x = sc.render.resolution_y = 520
        for v in order:
            rows = []
            for lk in ("A", "B"):
                row = []
                for hsx, sp in ((0, None), (1, "glasses" if v != "kid" else "sunglasses"), (2, None)):
                    D.set(v, hsx, sp, lk)
                    solo(arms, order, v, idle, 0)
                    show_lod(meshes, nears, "near", only=v)
                    a = arms[v]
                    hp = a.matrix_world @ a.pose.bones["head"].head
                    k_ = a.data.bones["head"].length / 0.12
                    views = ((0.0, "front"), (0.55, "tq")) if hsx == 0 else ((0.55, "tq"),)
                    for ang, nm in views:
                        dist = 0.95 * k_
                        zc = hp.z + 0.07 * k_
                        camera((hp.x + dist * math.sin(ang), hp.y - dist * math.cos(ang), zc + 0.01), (hp.x, hp.y, zc), lens=95)
                        row.append(render(os.path.join(outdir, f"_tmp_f{v}{lk}{hsx}{nm}.png")))
                rows.append(row)
            # expressions on look A (front / 3/4): blink, smile, both looks smiling at 3/4
            row = []
            for nm, kw, ang in (("blink", dict(blink=1.0), 0.0), ("blink", dict(blink=1.0), 0.55), ("smile", dict(smile=1.0), 0.0),
                                ("smileB", dict(smile=1.0, look="B"), 0.55)):
                D.set(v, 0, None, **kw)
                solo(arms, order, v, idle, 0)
                show_lod(meshes, nears, "near", only=v)
                a = arms[v]
                hp = a.matrix_world @ a.pose.bones["head"].head
                k_ = a.data.bones["head"].length / 0.12
                dist, zc = 0.95 * k_, hp.z + 0.07 * k_
                camera((hp.x + dist * math.sin(ang), hp.y - dist * math.cos(ang), zc + 0.01), (hp.x, hp.y, zc), lens=95)
                row.append(render(os.path.join(outdir, f"_tmp_x{v}{nm}{ang}.png")))
            rows.append(row)
            shots.append(compose(rows, os.path.join(outdir, f"face_{v}.png")))
            D.set(v, 0, None, "A")
            # hands (near): right hand from the front-side and the palm side, left hand from outside
            row = []
            a = arms[v]
            for side, view in (("R", (-0.25, -0.40, 0.05)), ("R", (0.30, -0.15, 0.02)), ("L", (0.40, -0.25, 0.05))):
                solo(arms, order, v, None, 0)
                show_lod(meshes, nears, "near", only=v)
                hb = a.data.bones[f"hand_{side}"]
                c = a.matrix_world @ ((hb.head_local + hb.tail_local) / 2)
                sc_ = hb.length / 0.15
                camera((c.x + view[0] * sc_, c.y + view[1] * sc_, c.z + view[2] * sc_), tuple(c), lens=85)
                row.append(render(os.path.join(outdir, f"_tmp_h{v}{side}{view[0]}.png")))
            solo(arms, order, v, None, 0)
            show_lod(meshes, nears, "far", only=v)
            hb = a.data.bones["hand_R"]
            c = a.matrix_world @ ((hb.head_local + hb.tail_local) / 2)
            camera((c.x - 0.25 * hb.length / 0.15, c.y - 0.40 * hb.length / 0.15, c.z + 0.05), tuple(c), lens=85)
            row.append(render(os.path.join(outdir, f"_tmp_h{v}far.png")))
            shots.append(compose([row], os.path.join(outdir, f"hands_{v}.png")))
        # ---- far LOD at 10 m with the game's 55 deg vertical FOV (full frame + faces cropped, 4x nearest)
        sc.render.resolution_x, sc.render.resolution_y = 1920, 1080
        show_lod(meshes, nears, "far")
        for k, v in enumerate(order):
            D.set(v, k, ("glasses" if v == "elder" else None), "A")
            extras[v]["geta"].hide_render = False
        lineup(arms, order, -15.0, idle, 0)
        cam_vfov((0, -10.0, 1.55), (0, 0, 1.30), 55.0)
        p = render(os.path.join(outdir, "far_10m_full.png"))
        shots.append(p)
        import shutil
        p2 = os.path.join(outdir, "far_10m_faces_x4.png")
        shutil.copyfile(p, p2)
        shots.append(crop(p2, 960 - 270, 540 - 150, 960 + 270, 540 + 60, scale=4))
        cam = bpy.data.objects["PrevCam"]
        cam.data.sensor_fit = "AUTO"
    # ---- side-view strips of every locomotion clip (near LOD, default hair)
    show_lod(meshes, nears, "near")
    for v in order:
        D.set(v, 0, None, "A")
        extras[v]["geta"].hide_render = False
    ticks = ground_ticks()
    plan = [("walk", v) for v in order] + [("walk_f", "woman"), ("walk_f", "elder"), ("run", "kid"), ("run", "man"),
                                            ("run", "woman"), ("sparkler", "kid")]
    for clip, v in plan:
        c = clips[clip]
        tag = f"walk_{v}" if clip == "walk" else f"{clip}_{v}"
        shots.append(walk_strip(arms, order, v, actions[clip], c["keys"] - 1, c["keyRate"], speeds[clip][v], outdir, tag))
        if gpu_r is None:
            gpu_r = gpu_check()          # raises on a software rasteriser
    bpy.data.objects.remove(ticks, do_unlink=True)
    # ---- a still (or two) of every clip on all five variants: 3/4 front above, side below
    sc.render.resolution_x, sc.render.resolution_y = 1600, 760
    for k, v in enumerate(order):
        D.set(v, k + 1, None, "B" if k % 2 else "A")
    for clip, frames in (stills or {}).items():
        act = actions[clip]
        seated = clips[clip].get("seated")
        bench(show=bool(seated))
        rows = []
        for fr in frames:
            row = []
            for yaw, cam in ((-28.0, ((0.0, -5.6, 1.25), (0, 0, 0.82))), (72.0, ((0.0, -5.6, 1.25), (0, 0, 0.82)))):
                lineup(arms, order, yaw, act, 1 + fr)
                camera(cam[0], cam[1], lens=40)
                row.append(render(os.path.join(outdir, f"_tmp_{clip}_{fr}_{int(yaw)}.png")))
            rows.append(row)
        shots.append(compose(rows, os.path.join(outdir, f"clip_{clip}.png")))
    if "PrevBench" in bpy.data.objects:
        bpy.data.objects.remove(bpy.data.objects["PrevBench"], do_unlink=True)
    for v in order:
        D.set(v, 0, None, "A")
    lineup(arms, order, 0.0, None, 1)
    return shots, gpu_r
