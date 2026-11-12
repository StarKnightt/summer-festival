"""Blender object creation: scene/collection, the pattern texture, named materials, skinned meshes."""
import math
import os
import tempfile

import bmesh
import bpy
import numpy as np

from .geo import clean_weights, srgb

COLL = "People"
TEX_W, TEX_H, NCOL = 1000, 500, 5
TILE = 50  # px; 4 tiles per 200 px column, 10 down


def scene():
    sc = bpy.context.scene
    sc.render.fps, sc.render.fps_base = 30, 1.0
    sc.unit_settings.system = "METRIC"
    return sc


def fresh_collection():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)
    col = bpy.data.collections.new(COLL)
    bpy.context.scene.collection.children.link(col)
    return col


# ---------------------------------------------------------------- pattern texture

def _motif(col, u, v):
    """Coverage 0..1 of the motif for atlas column `col`, tile coords u, v in [0, 1)."""
    def disc(cx, cy, r, soft=0.02):
        du = (u - cx + 0.5) % 1.0 - 0.5
        dv = (v - cy + 0.5) % 1.0 - 0.5
        d = np.sqrt(du * du + dv * dv)
        return np.clip((r - d) / soft + 0.5, 0, 1)

    def line(x, w, coord, soft=0.015):
        d = np.abs((coord - x + 0.5) % 1.0 - 0.5)
        return np.clip((w / 2 - d) / soft + 0.5, 0, 1)

    if col == 0:   # scattered five-petal blossoms + small buds
        m = np.zeros_like(u)
        for (cx, cy, s, rot0) in ((0.30, 0.32, 1.0, 0.2), (0.78, 0.80, 0.62, 1.0)):
            for k in range(5):
                a = rot0 + 2 * math.pi * k / 5
                m = np.maximum(m, disc(cx + 0.13 * s * math.cos(a), cy + 0.13 * s * math.sin(a), 0.105 * s))
            m = np.where(disc(cx, cy, 0.05 * s) > 0.5, 0.45, m)
        m = np.maximum(m, disc(0.80, 0.25, 0.035) * 0.8)
        m = np.maximum(m, disc(0.22, 0.80, 0.03) * 0.8)
        return m
    if col == 1:   # paired fine stripes with broken (kasuri) dashes between
        m = np.maximum(line(0.10, 0.06, u), line(0.20, 0.035, u))
        dash = line(0.62, 0.05, u) * (((v * 3) % 1.0) < 0.55)
        return np.maximum(m, dash * 0.7)
    if col == 2:   # playful polka dots, two sizes
        return np.maximum(disc(0.25, 0.25, 0.16), disc(0.75, 0.75, 0.09))
    if col == 3:   # bold lozenge lattice for the happi
        a = line(0.0, 0.07, (u + v) % 1.0)
        b = line(0.0, 0.07, (u - v) % 1.0)
        return np.maximum(np.maximum(a, b), disc(0.5, 0.0, 0.06))
    if col == 4:   # fine lattice (koshi) with a thin inner line
        m = np.maximum(line(0.0, 0.07, u), line(0.0, 0.07, v))
        return np.maximum(m, 0.6 * np.maximum(line(0.5, 0.025, u), line(0.5, 0.025, v)))
    return np.zeros_like(u)


def pattern_image():
    name = "people_cloth_pattern"
    if name in bpy.data.images:
        bpy.data.images.remove(bpy.data.images[name])
    ss = 3
    W, H = TEX_W * ss, TEX_H * ss
    xs = (np.arange(W) + 0.5) / ss
    ys = (np.arange(H) + 0.5) / ss
    PX, PY = np.meshgrid(xs, ys)
    img = np.ones((H, W))
    colw = TEX_W // NCOL
    for c in range(NCOL):
        sel = (PX >= c * colw) & (PX < (c + 1) * colw)
        u = ((PX[sel] - c * colw) / TILE) % 1.0
        v = (PY[sel] / TILE) % 1.0
        img[sel] = 1.0 - 0.36 * _motif(c, u, v)
    img = img.reshape(TEX_H, ss, TEX_W, ss).mean(axis=(1, 3))
    rgba = np.ones((TEX_H, TEX_W, 4), dtype=np.float32)
    rgba[..., 0] = rgba[..., 1] = rgba[..., 2] = img
    im = bpy.data.images.new(name, TEX_W, TEX_H, alpha=False)
    im.colorspace_settings.name = "sRGB"
    im.pixels.foreach_set(rgba.ravel())
    tmp = os.path.join(tempfile.gettempdir(), "people_cloth_pattern.png")
    im.filepath_raw = tmp
    im.file_format = "PNG"
    im.save()
    bpy.data.images.remove(im)
    im = bpy.data.images.load(tmp)
    im.name = name
    im.pack()
    try:
        os.remove(tmp)
    except OSError:
        pass
    return im


# ---------------------------------------------------------------- materials

DEFAULT_COLOURS = {   # neutral defaults; the game tints per instance (see README / extras)
    "skin": "#f4d3bf", "hair": "#ffffff", "face": "#ffffff", "cloth_main": "#ffffff",
    "cloth_accent": "#e8c35a", "cloth_dark": "#2c3346", "wood_geta": "#c79a68", "cloth_shoe": "#30323a",
    # hair and glasses carry their colour in COLOR_0 (white base): grey elder hair, varied browns,
    # dark or metal frames; the lens tint AND opacity are in COLOR_0 (rgb, a) - see README
    "glasses_frame": "#ffffff", "glasses_lens": "#ffffff",
}


def material(name, image=None):
    m = bpy.data.materials.get(name)
    if m is not None:
        return m
    m = bpy.data.materials.new(name)
    c = srgb(DEFAULT_COLOURS[name])
    m.diffuse_color = (*c, 1.0)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (*c, 1.0)
    bsdf.inputs["Metallic"].default_value = 0.0
    bsdf.inputs["Roughness"].default_value = 1.0
    if image is not None:
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = image
        tex.extension = "REPEAT"
        tex.interpolation = "Linear"
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    return m


# ---------------------------------------------------------------- skinned mesh

MAT_ORDER = ["skin", "face", "hair", "cloth_main", "cloth_accent", "cloth_dark", "wood_geta", "cloth_shoe",
             "glasses_frame", "glasses_lens"]
MORPH = "face_b"


def make_mesh(mb, arm, col, mats):
    V = np.asarray(mb.V, float)
    names = [m for m in MAT_ORDER if m in set(mb.FM)]
    slot = {m: i for i, m in enumerate(names)}
    me = bpy.data.meshes.new(mb.name)
    me.from_pydata([tuple(p) for p in V], [], [tuple(f) for f in mb.F])
    me.validate(clean_customdata=False)
    for m in names:
        me.materials.append(mats[m])
    me.polygons.foreach_set("material_index", [slot[m] for m in mb.FM])
    me.polygons.foreach_set("use_smooth", [bool(s) for s in mb.FS])
    # per-corner UVs from the per-vertex values
    uvl = me.uv_layers.new(name="UVMap")
    vi = np.zeros(len(me.loops), dtype=np.int64)
    me.loops.foreach_get("vertex_index", vi)
    UV = np.asarray(mb.UV, float)
    uvl.data.foreach_set("uv", UV[vi].ravel())
    # vertex colour (multiplies the base colour in the game); alpha only matters for glasses_lens
    C = np.hstack([np.asarray(mb.C, float), np.asarray(mb.A, float)[:, None]])
    attr = me.color_attributes.new("Col", "BYTE_COLOR", "CORNER")
    attr.data.foreach_set("color", C[vi].ravel())
    me.color_attributes.active_color = attr
    me.color_attributes.render_color_index = 0
    ob = bpy.data.objects.new(mb.name, me)
    col.objects.link(ob)
    # weights
    groups = {}
    for i, w in enumerate(mb.W):
        for b, v in clean_weights(w).items():
            g = groups.get(b)
            if g is None:
                g = groups[b] = ob.vertex_groups.new(name=b)
            g.add([i], v, "REPLACE")
    NF = np.asarray(mb.NF, bool)
    if NF.any():
        gn = ob.vertex_groups.new(name="_nrm")
        gn.add([int(i) for i in np.where(NF)[0]], 1.0, "REPLACE")
    # face look B as a shape key (before the weld: bmesh keeps shape-key layers)
    extra = mb.morph_names()
    if mb.has_morph() or extra:
        ob.shape_key_add(name="Basis", from_mix=False)
        keys = ([(MORPH, mb.Vb)] if mb.has_morph() else []) + [(nm, mb.M[nm]) for nm in extra]
        for nm, P in keys:
            sk = ob.shape_key_add(name=nm, from_mix=False)
            sk.data.foreach_set("co", np.asarray(P, float).ravel())
            sk.slider_min, sk.slider_max, sk.value = 0.0, 1.0, 0.0
    # weld loft seams / coincident points so smooth normals do not split (UVs stay per corner)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bm.to_mesh(me)
    bm.free()
    # analytic normals on the head skin and the painted face (a clean toon terminator)
    if NF.any() and mb.normal_fn is not None:
        gi = ob.vertex_groups["_nrm"].index
        nv = len(me.vertices)
        flag = np.zeros(nv, bool)
        for v in me.vertices:
            for ge in v.groups:
                if ge.group == gi and ge.weight > 0.5:
                    flag[v.index] = True
        co = np.zeros(nv * 3)
        me.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        vi = np.zeros(len(me.loops), dtype=np.int64)
        me.loops.foreach_get("vertex_index", vi)
        cn = np.zeros(len(me.loops) * 3)
        me.corner_normals.foreach_get("vector", cn)
        cn = cn.reshape(-1, 3)
        idx = np.where(flag)[0]
        Nv = np.zeros((nv, 3))
        Nv[idx] = mb.normal_fn(co[idx])
        lf = flag[vi]
        cn[lf] = Nv[vi[lf]]
        me.normals_split_custom_set([tuple(n) for n in cn])
        ob.vertex_groups.remove(ob.vertex_groups["_nrm"])
    elif "_nrm" in ob.vertex_groups:
        ob.vertex_groups.remove(ob.vertex_groups["_nrm"])
    ob.parent = arm
    mod = ob.modifiers.new("Armature", "ARMATURE")
    mod.object = arm
    return ob


def tri_count(ob):
    return sum(len(p.vertices) - 2 for p in ob.data.polygons)
