"""Shared helpers: numpy geometry, Blender mesh/material creation, UVs, textures.

Blender frame used everywhere: metres, +Z up, she faces -Y, +X is HER LEFT.
The glTF export (export_yup) turns this into three.js space: +Y up, facing +Z, +X her left.
Generic tooling adapted from the bay-ride character scripts (maths, tubes, mesh creation).
"""
import math

import bpy
import numpy as np

COLL = "Heroine"

# ---------------------------------------------------------------- maths


def smooth(e0, e1, x):
    t = np.clip((np.asarray(x, dtype=float) - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def smin(a, b, k):
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b * (1.0 - h) + a * h - k * h * (1.0 - h)


def norm(v, axis=-1):
    v = np.asarray(v, dtype=float)
    n = np.linalg.norm(v, axis=axis, keepdims=True)
    return v / np.maximum(n, 1e-12)


def catmull(knots, x):
    """C1 cubic Hermite through table rows [x, v1, v2, ...] (x ascending), evaluated at x."""
    T = np.asarray(knots, dtype=float)
    xs, ys = T[:, 0], T[:, 1:]
    n = len(xs)
    x = np.clip(np.asarray(x, dtype=float), xs[0], xs[-1])
    m = np.zeros_like(ys)
    for i in range(n):
        if i == 0:
            m[i] = (ys[1] - ys[0]) / (xs[1] - xs[0])
        elif i == n - 1:
            m[i] = (ys[-1] - ys[-2]) / (xs[-1] - xs[-2])
        else:
            m[i] = (ys[i + 1] - ys[i - 1]) / (xs[i + 1] - xs[i - 1])
    i = np.clip(np.searchsorted(xs, x, side="right") - 1, 0, n - 2)
    x0, x1 = xs[i], xs[i + 1]
    h = (x1 - x0)[:, None]
    t = ((x - x0) / (x1 - x0))[:, None]
    t2, t3 = t * t, t * t * t
    return ((2 * t3 - 3 * t2 + 1) * ys[i] + (t3 - 2 * t2 + t) * h * m[i]
            + (-2 * t3 + 3 * t2) * ys[i + 1] + (t3 - t2) * h * m[i + 1])


def spline_points(ctrl, n):
    """Catmull-Rom through control points (K,3), resampled to n points evenly by arc length."""
    P = np.asarray(ctrl, dtype=float)
    P = np.vstack([2 * P[0] - P[1], P, 2 * P[-1] - P[-2]])
    dense = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        for t in np.linspace(0, 1, 24, endpoint=False):
            t2, t3 = t * t, t * t * t
            dense.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                                + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    dense.append(P[-2])
    D = np.array(dense)
    seg = np.linalg.norm(np.diff(D, axis=0), axis=1)
    s = np.concatenate([[0], np.cumsum(seg)])
    u = np.linspace(0, s[-1], n)
    return np.stack([np.interp(u, s, D[:, k]) for k in range(3)], axis=1)


def frames_along(path, up_hint=(0, 0, 1)):
    """Rotation-minimising frames along a polyline: tangent T, normal N, binormal B."""
    P = np.asarray(path, dtype=float)
    n = len(P)
    T = np.zeros_like(P)
    T[1:-1] = P[2:] - P[:-2]
    T[0] = P[1] - P[0]
    T[-1] = P[-1] - P[-2]
    T = norm(T)
    up = np.asarray(up_hint, dtype=float)
    N = np.zeros_like(P)
    v = np.cross(T[0], up)
    if np.linalg.norm(v) < 1e-6:
        v = np.cross(T[0], (1, 0, 0))
    N[0] = norm(np.cross(v, T[0]))
    for i in range(1, n):
        v1 = P[i] - P[i - 1]
        c1 = v1 @ v1
        if c1 < 1e-14:
            N[i] = N[i - 1]
            continue
        rL = N[i - 1] - (2 / c1) * (v1 @ N[i - 1]) * v1
        tL = T[i - 1] - (2 / c1) * (v1 @ T[i - 1]) * v1
        v2 = T[i] - tL
        c2 = v2 @ v2
        N[i] = rL - (2 / c2) * (v2 @ rL) * v2 if c2 > 1e-14 else rL
        N[i] = norm(N[i])
    B = np.cross(T, N)
    return T, N, B


def rot_axis(axis, ang):
    a = np.asarray(axis, dtype=float)
    a = a / np.linalg.norm(a)
    c, s = math.cos(ang), math.sin(ang)
    x, y, z = a
    return np.array([
        [c + x * x * (1 - c), x * y * (1 - c) - z * s, x * z * (1 - c) + y * s],
        [y * x * (1 - c) + z * s, c + y * y * (1 - c), y * z * (1 - c) - x * s],
        [z * x * (1 - c) - y * s, z * y * (1 - c) + x * s, c + z * z * (1 - c)],
    ])


def hash1(i):
    x = np.sin(np.asarray(i, dtype=float) * 12.9898 + 78.233) * 43758.5453
    return x - np.floor(x)


# ---------------------------------------------------------------- grids -> faces


def grid_faces(rows, cols, closed=True, flip=False, off=0):
    F = []
    cmax = cols if closed else cols - 1
    for r in range(rows - 1):
        for c in range(cmax):
            c2 = (c + 1) % cols
            a = off + r * cols + c
            b = off + r * cols + c2
            d = off + (r + 1) * cols + c
            e = off + (r + 1) * cols + c2
            F.append((a, b, e, d) if not flip else (a, d, e, b))
    return F


def tube(rings, closed=True, cap_start=False, cap_end=False):
    """Vertices + quads for a stack of rings (R, C, 3); caps are fans to a centre vertex.
    Winding is fixed afterwards with orient()."""
    R, C, _ = rings.shape
    V = rings.reshape(-1, 3).tolist()
    F = grid_faces(R, C, closed)
    if cap_start:
        ci = len(V)
        V.append(rings[0].mean(axis=0).tolist())
        for c in range(C if closed else C - 1):
            F.append((ci, (c + 1) % C, c))
    if cap_end:
        ci = len(V)
        V.append(rings[-1].mean(axis=0).tolist())
        o = (R - 1) * C
        for c in range(C if closed else C - 1):
            F.append((ci, o + c, o + (c + 1) % C))
    return np.array(V), F


def face_normals_np(V, F):
    V = np.asarray(V, dtype=float)
    out = np.zeros((len(F), 3))
    for i, f in enumerate(F):
        p = V[list(f)]
        n = np.zeros(3)
        for k in range(len(f)):
            n += np.cross(p[k], p[(k + 1) % len(f)])
        out[i] = n
    return norm(out)


def orient(V, F, inside):
    """Wind every face so its normal points away from inside(centroids) -> reference points."""
    V = np.asarray(V, dtype=float)
    Nf = face_normals_np(V, F)
    C = np.array([V[list(f)].mean(axis=0) for f in F])
    ref = inside(C)
    flip = np.einsum("ij,ij->i", Nf, C - ref) < 0
    return [tuple(reversed(f)) if fl else tuple(f) for f, fl in zip(F, flip)]


def nearest_on_polyline(P, path):
    """Closest point on a polyline for each point of P."""
    P = np.asarray(P, float)
    best = np.full(len(P), np.inf)
    out = np.zeros_like(P)
    for i in range(len(path) - 1):
        a, b = path[i], path[i + 1]
        ab = b - a
        t = np.clip(((P - a) @ ab) / max(ab @ ab, 1e-12), 0, 1)
        q = a + t[:, None] * ab
        d = np.linalg.norm(P - q, axis=1)
        m = d < best
        best = np.where(m, d, best)
        out[m] = q[m]
    return out


def mirror(V, F):
    """Mirror geometry x -> -x (her left -> her right), keeping outward winding."""
    V = np.array(V, dtype=float)
    V[:, 0] *= -1
    return V, [tuple(reversed(f)) for f in F]


def merge_geo(parts):
    """[(V, F), ...] -> one (V, F)."""
    Vs, Fs, o = [], [], 0
    for V, F in parts:
        Vs.append(np.asarray(V, float))
        Fs += [tuple(i + o for i in f) for f in F]
        o += len(V)
    return np.vstack(Vs), Fs


# ---------------------------------------------------------------- Blender objects


def scene():
    sc = bpy.context.scene
    sc.name = "Heroine"
    return sc


def collection(name=COLL):
    sc = scene()
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
    if col.name not in sc.collection.children:
        sc.collection.children.link(col)
    return col


def make_mesh(name, V, F, col=None, mats=None, face_mat=None, smooth_shade=True):
    """Mesh object from vertices (N,3) and faces. mats: list of materials; face_mat: per-face
    material index list."""
    me = bpy.data.meshes.new(name)
    V = np.asarray(V, dtype=float)
    me.from_pydata(V.tolist(), [], [tuple(int(i) for i in f) for f in F])
    me.validate(clean_customdata=False)
    me.update()
    ob = bpy.data.objects.new(name, me)
    (col or collection()).objects.link(ob)
    if mats:
        for m in mats:
            me.materials.append(m)
        if face_mat is not None:
            me.polygons.foreach_set("material_index", [int(i) for i in face_mat])
    me.polygons.foreach_set("use_smooth", [smooth_shade] * len(me.polygons))
    me.update()
    return ob


def verts(ob):
    me = ob.data
    a = np.zeros(len(me.vertices) * 3)
    me.vertices.foreach_get("co", a)
    return a.reshape(-1, 3)


def set_verts(ob, V):
    me = ob.data
    me.vertices.foreach_set("co", np.asarray(V, dtype=float).reshape(-1))
    me.update()


def set_colors(ob, C, name="Color"):
    """Per-vertex linear RGB(A) colour attribute (exported as COLOR_0)."""
    me = ob.data
    C = np.asarray(C, dtype=float)
    if C.shape[1] == 3:
        C = np.hstack([C, np.ones((len(C), 1))])
    attr = me.color_attributes.get(name) or me.color_attributes.new(name, "FLOAT_COLOR", "POINT")
    attr.data.foreach_set("color", C.reshape(-1))
    me.color_attributes.active_color = attr
    try:
        me.color_attributes.render_color_index = list(me.color_attributes).index(attr)
    except Exception:
        pass


def set_uv_loops(ob, uv_fn, name="UVMap"):
    """UVs per face corner: uv_fn(poly_index, vertex_indices) -> list of (u, v)."""
    me = ob.data
    uvl = me.uv_layers.get(name) or me.uv_layers.new(name=name)
    data = np.zeros(len(me.loops) * 2)
    for p in me.polygons:
        vids = [me.loops[li].vertex_index for li in p.loop_indices]
        uvs = uv_fn(p.index, vids)
        for k, li in enumerate(p.loop_indices):
            data[2 * li], data[2 * li + 1] = uvs[k]
    uvl.data.foreach_set("uv", data)


def set_uv_vertex(ob, UV, name="UVMap"):
    """UVs from a per-vertex (N,2) array."""
    UV = np.asarray(UV, float)
    set_uv_loops(ob, lambda pi, vids: [tuple(UV[v]) for v in vids], name)


def srgb(hexstr):
    h = hexstr.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return np.array([x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c])


def material(name, hexcol, image=None):
    """A named material (the game swaps it for its toon material by name prefix). Base colour
    factor = hexcol, or an image texture as base colour. metallic 0, roughness 1."""
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    c = srgb(hexcol) if image is None else np.ones(3)
    m.diffuse_color = (*srgb(hexcol), 1.0)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (*c, 1.0)
    bsdf.inputs["Metallic"].default_value = 0.0
    bsdf.inputs["Roughness"].default_value = 1.0
    if image is not None:
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = image
        tex.interpolation = "Linear"
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        nt.nodes.active = tex
    return m


def image_from_array(name, rgb):
    """(H, W, 3) sRGB float array (row 0 = top) -> packed PNG image datablock."""
    H, W, _ = rgb.shape
    img = bpy.data.images.get(name)
    if img is not None:
        bpy.data.images.remove(img)
    img = bpy.data.images.new(name, W, H, alpha=False)
    px = np.ones((H, W, 4), dtype=np.float32)
    px[:, :, :3] = np.clip(rgb[::-1], 0, 1)        # Blender rows go bottom-up
    img.pixels.foreach_set(px.ravel())
    img.file_format = "PNG"
    img.pack()
    return img


def tri_count(ob):
    return sum(len(p.vertices) - 2 for p in ob.data.polygons)
