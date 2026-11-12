"""Shared headless-Blender toolkit for Summer Festival props.

A tiny mesh builder (verts / faces with per-face colour, material and optional UVs), primitive
generators (box, lathe, sphere, torus, tube, surface grid, slab, prism), a numpy texture painter,
object/empty helpers, glTF export and a GLB name post-pass.

Colours are given as sRGB hex and stored linear in a FLOAT_COLOR face-corner attribute "Col",
exported as COLOR_0 (the game multiplies it into the base colour).
"""
import json
import math
import os
import struct
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

# --------------------------------------------------------------------------- process / args


def lower_priority():
    """Below-normal priority for the whole headless run (contract)."""
    try:
        if os.name == "nt":
            import ctypes
            k = ctypes.windll.kernel32
            k.SetPriorityClass(k.GetCurrentProcess(), 0x00004000)
        else:
            os.nice(10)
    except Exception as e:  # pragma: no cover
        print("[kit] could not lower priority:", e)


def script_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = {}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--"):
            if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                out[a[2:]] = argv[i + 1]
                i += 1
            else:
                out[a[2:]] = True
        i += 1
    return out


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.fps, sc.render.fps_base = 30, 1.0
    sc.unit_settings.system = "METRIC"
    return sc


# --------------------------------------------------------------------------- colour


def s2l(c):
    c = float(c)
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hexc(h, a=1.0):
    """'#rrggbb' -> linear RGBA tuple."""
    h = h.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return (s2l(r), s2l(g), s2l(b), a)


def srgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)])


def mix(a, b, t):
    return tuple(a[i] * (1 - t) + b[i] * t for i in range(4))


def shade(c, k):
    return (c[0] * k, c[1] * k, c[2] * k, c[3])


WHITE = (1.0, 1.0, 1.0, 1.0)

# --------------------------------------------------------------------------- transforms


def T(x=0.0, y=0.0, z=0.0):
    return Matrix.Translation((x, y, z))


def R(axis, deg):
    return Matrix.Rotation(math.radians(deg), 4, axis)


def S(x, y=None, z=None):
    y = x if y is None else y
    z = x if z is None else z
    m = Matrix.Identity(4)
    m[0][0], m[1][1], m[2][2] = x, y, z
    return m


def look_rot(direction, up_axis="Z", track="Y"):
    return Vector(direction).normalized().to_track_quat(track, up_axis)


# --------------------------------------------------------------------------- geometry
# A "geo" is (V, F, UV): V list of xyz, F list of index tuples, UV None or list (per face) of uv lists.


def _bevel(V, F, width, seg=1, angle=30.0):
    bm = bmesh.new()
    vs = [bm.verts.new(v) for v in V]
    for f in F:
        try:
            bm.faces.new([vs[i] for i in f])
        except ValueError:
            pass
    bm.normal_update()
    lim = math.radians(angle)
    edges = [e for e in bm.edges if len(e.link_faces) == 2 and e.calc_face_angle(0.0) > lim]
    if edges:
        bmesh.ops.bevel(bm, geom=edges, offset=width, offset_type="OFFSET", segments=seg,
                        profile=0.5, affect="EDGES", clamp_overlap=True)
    bm.verts.index_update()
    V2 = [tuple(v.co) for v in bm.verts]
    F2 = [tuple(v.index for v in f.verts) for f in bm.faces]
    bm.free()
    return V2, F2, None


def box(sx, sy, sz, bevel=0.0, seg=1, center=(0, 0, 0), bottom=False):
    hx, hy, hz = sx / 2, sy / 2, sz / 2
    cx, cy, cz = center
    if bottom:
        cz += hz
    V = [(cx + x * hx, cy + y * hy, cz + z * hz) for z in (-1, 1) for y in (-1, 1) for x in (-1, 1)]
    # indices: 0(-,-,-) 1(+,-,-) 2(-,+,-) 3(+,+,-) 4(-,-,+) 5(+,-,+) 6(-,+,+) 7(+,+,+)
    F = [(0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (1, 3, 7, 5), (3, 2, 6, 7), (2, 0, 4, 6)]
    uv = [[(0, 0), (1, 0), (1, 1), (0, 1)] for _ in F]
    if bevel > 0:
        return _bevel(V, F, min(bevel, 0.45 * min(sx, sy, sz)), seg)
    return V, F, uv


def lathe(profile, n=12, cap0=False, cap1=False, phase=0.0, bevel=0.0, uv=True):
    """Revolve [(r, z), ...] about Z. r ~ 0 points become poles."""
    V, F, UV = [], [], []
    rings = []
    m = len(profile)
    for (r, z) in profile:
        if r < 1e-6:
            rings.append([len(V)])
            V.append((0.0, 0.0, z))
        else:
            idx = []
            for j in range(n):
                a = 2 * math.pi * j / n + phase
                idx.append(len(V))
                V.append((r * math.cos(a), r * math.sin(a), z))
            rings.append(idx)
    for i in range(m - 1):
        a, b = rings[i], rings[i + 1]
        va, vb = i / (m - 1), (i + 1) / (m - 1)
        for j in range(n):
            j1 = (j + 1) % n
            u0, u1 = j / n, (j + 1) / n
            if len(a) == 1 and len(b) == 1:
                continue
            if len(a) == 1:
                F.append((a[0], b[j1], b[j]))
                UV.append([((u0 + u1) / 2, va), (u1, vb), (u0, vb)])
            elif len(b) == 1:
                F.append((a[j], a[j1], b[0]))
                UV.append([(u0, va), (u1, va), ((u0 + u1) / 2, vb)])
            else:
                F.append((a[j], a[j1], b[j1], b[j]))
                UV.append([(u0, va), (u1, va), (u1, vb), (u0, vb)])
    if cap0 and len(rings[0]) > 1:
        up = profile[1][1] >= profile[0][1]
        r = rings[0]
        F.append(tuple(reversed(r)) if up else tuple(r))
        UV.append([(0.5, 0.5)] * n)
    if cap1 and len(rings[-1]) > 1:
        up = profile[-1][1] >= profile[-2][1]
        r = rings[-1]
        F.append(tuple(r) if up else tuple(reversed(r)))
        UV.append([(0.5, 0.5)] * n)
    if bevel > 0:
        return _bevel(V, F, bevel, 1, 50.0)
    return V, F, (UV if uv else None)


def cyl(r, h, n=12, r2=None, caps=True, bevel=0.0, z0=0.0):
    r2 = r if r2 is None else r2
    return lathe([(r, z0), (r2, z0 + h)], n, caps, caps, bevel=bevel)


def sphere(r, n=12, m=8, rz=None):
    rz = r if rz is None else rz
    prof = [(r * math.sin(math.pi * i / m), -rz * math.cos(math.pi * i / m)) for i in range(m + 1)]
    prof[0] = (0.0, -rz)
    prof[-1] = (0.0, rz)
    return lathe(prof, n)


def torus(R_, r, n=16, m=6, phase=0.0):
    V, F, UV = [], [], []
    for i in range(n):
        a = 2 * math.pi * i / n + phase
        for j in range(m):
            b = 2 * math.pi * j / m
            rr = R_ + r * math.cos(b)
            V.append((rr * math.cos(a), rr * math.sin(a), r * math.sin(b)))
    for i in range(n):
        for j in range(m):
            i1, j1 = (i + 1) % n, (j + 1) % m
            F.append((i * m + j, i1 * m + j, i1 * m + j1, i * m + j1))
            UV.append([(i / n, j / m), ((i + 1) / n, j / m), ((i + 1) / n, (j + 1) / m), (i / n, (j + 1) / m)])
    return V, F, UV


def tube(pts, r, n=6, caps=True, phase=None, closed=False):
    """Sweep a circle (radius r or per-point list; r may be (rx, ry) for an ellipse) along pts."""
    P = [Vector(p) for p in pts]
    k = len(P)
    rs = r if isinstance(r, list) else [r] * k  # list: per point; scalar or (rx, ry) tuple: constant
    if phase is None:
        phase = math.pi / n if n == 4 else 0.0
    tang = []
    for i in range(k):
        if closed:
            t = P[(i + 1) % k] - P[i - 1]
        else:
            t = (P[min(i + 1, k - 1)] - P[max(i - 1, 0)])
        tang.append(t.normalized())
    ref = Vector((0, 0, 1)) if abs(tang[0].z) < 0.9 else Vector((1, 0, 0))
    nrm = (ref - tang[0] * ref.dot(tang[0])).normalized()
    frames = []
    for i in range(k):
        if i > 0:
            nrm = nrm - tang[i] * nrm.dot(tang[i])
            if nrm.length < 1e-8:
                nrm = frames[-1][0]
            nrm.normalize()
        bi = tang[i].cross(nrm)
        frames.append((nrm.copy(), bi))
    V, F, UV = [], [], []
    for i in range(k):
        nr, bi = frames[i]
        ri = rs[i]
        rx, ry = (ri, ri) if isinstance(ri, (int, float)) else ri
        for j in range(n):
            a = 2 * math.pi * j / n + phase
            V.append(tuple(P[i] + nr * (math.cos(a) * rx) + bi * (math.sin(a) * ry)))
    segs = k if closed else k - 1
    for i in range(segs):
        i1 = (i + 1) % k
        for j in range(n):
            j1 = (j + 1) % n
            F.append((i * n + j, i * n + j1, i1 * n + j1, i1 * n + j))
            UV.append([(j / n, i / k), ((j + 1) / n, i / k), ((j + 1) / n, (i + 1) / k), (j / n, (i + 1) / k)])
    if caps and not closed:
        F.append(tuple(range(n))[::-1])
        UV.append([(0.5, 0.5)] * n)
        F.append(tuple((k - 1) * n + j for j in range(n)))
        UV.append([(0.5, 0.5)] * n)
    return V, F, UV


def surf(fn, nu, nv):
    """Grid surface: fn(u, v) -> xyz, u, v in [0, 1]. Normal = du x dv."""
    V, F, UV = [], [], []
    for j in range(nv + 1):
        for i in range(nu + 1):
            V.append(tuple(fn(i / nu, j / nv)))
    w = nu + 1
    for j in range(nv):
        for i in range(nu):
            a = j * w + i
            F.append((a, a + 1, a + 1 + w, a + w))
            UV.append([(i / nu, j / nv), ((i + 1) / nu, j / nv), ((i + 1) / nu, (j + 1) / nv), (i / nu, (j + 1) / nv)])
    return V, F, UV


def slab(fn, nu, nv, thick, uv_back=True):
    """Thin double-sided sheet: front = fn(u, v) (normal du x dv), back offset by -normal*thick."""
    P = np.array([[fn(i / nu, j / nv) for i in range(nu + 1)] for j in range(nv + 1)], float)
    du = np.gradient(P, axis=1)
    dv = np.gradient(P, axis=0)
    N = np.cross(du, dv)
    N /= np.maximum(np.linalg.norm(N, axis=2, keepdims=True), 1e-9)
    B = P - N * thick
    V = [tuple(p) for p in P.reshape(-1, 3)] + [tuple(p) for p in B.reshape(-1, 3)]
    off = (nu + 1) * (nv + 1)
    w = nu + 1
    F, UV = [], []
    for j in range(nv):
        for i in range(nu):
            a = j * w + i
            q = [(i / nu, j / nv), ((i + 1) / nu, j / nv), ((i + 1) / nu, (j + 1) / nv), (i / nu, (j + 1) / nv)]
            F.append((a, a + 1, a + 1 + w, a + w))
            UV.append(q)
            F.append((off + a + w, off + a + 1 + w, off + a + 1, off + a))
            UV.append(q[::-1])
    border = [(i, 0) for i in range(nu)] + [(nu, j) for j in range(nv)] + \
             [(i, nv) for i in range(nu, 0, -1)] + [(0, j) for j in range(nv, 0, -1)]
    for k in range(len(border)):
        i0, j0 = border[k]
        i1, j1 = border[(k + 1) % len(border)]
        a, b = j0 * w + i0, j1 * w + i1
        F.append((b, a, off + a, off + b))
        UV.append([(i1 / nu, j1 / nv), (i0 / nu, j0 / nv), (i0 / nu, j0 / nv), (i1 / nu, j1 / nv)])
    return V, F, UV


def prism(poly, z0, z1, bevel=0.0):
    """Extrude a CCW 2D polygon from z0 to z1."""
    n = len(poly)
    V = [(x, y, z0) for x, y in poly] + [(x, y, z1) for x, y in poly]
    F = [tuple(range(n))[::-1], tuple(range(n, 2 * n))]
    for i in range(n):
        i1 = (i + 1) % n
        F.append((i, i1, n + i1, n + i))
    if bevel > 0:
        return _bevel(V, F, bevel, 1, 40.0)
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    uvp = [((x - x0) / max(x1 - x0, 1e-6), (y - y0) / max(y1 - y0, 1e-6)) for x, y in poly]
    UV = [uvp[::-1], uvp] + [[uvp[i], uvp[(i + 1) % n], uvp[(i + 1) % n], uvp[i]] for i in range(n)]
    return V, F, UV


def ngon_sheet(poly, thick=0.004):
    """Flat double-sided plate in XY (for leaves, paper)."""
    return prism(poly, -thick / 2, thick / 2)


# --------------------------------------------------------------------------- mesh builder


class MB:
    """Accumulates parts: per-face colour (linear rgba), material name, uv."""

    def __init__(self):
        self.V, self.F, self.C, self.M, self.UV = [], [], [], [], []

    def add(self, geo, color=WHITE, mat="wood_plain", M=None, uvmap=None):
        V, F, UV = geo
        base = len(self.V)
        if M is not None:
            V = [tuple(M @ Vector(v)) for v in V]
        self.V.extend(V)
        for k, f in enumerate(F):
            self.F.append(tuple(base + i for i in f))
            if callable(color):
                pts = [Vector(V[i]) for i in f]
                c = sum(pts, Vector()) / len(pts)
                nrm = (pts[1] - pts[0]).cross(pts[-1] - pts[0])
                if nrm.length > 1e-12:
                    nrm.normalize()
                self.C.append(color(c, nrm))
            else:
                self.C.append(color)
            self.M.append(mat(k) if callable(mat) else mat)
            if UV is not None and uvmap is not None:
                # uvmap: callable(u, v) -> (u', v'), or True to keep the generator's UVs
                self.UV.append([(u, v) if uvmap is True else uvmap(u, v) for (u, v) in UV[k]])
            else:
                self.UV.append(None)
        return self

    def tris(self):
        return sum(len(f) - 2 for f in self.F)

    def empty(self):
        return not self.F


MATS = {}


def material(name, color=WHITE, image=None, emissive=None):
    """Toon-role material: metallic 0, roughness 1, base colour factor (+ optional texture)."""
    if name in MATS:
        return MATS[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Metallic"].default_value = 0.0
    bsdf.inputs["Roughness"].default_value = 1.0
    if image is not None:
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = image
        tex.interpolation = "Linear"
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    if emissive is not None:
        bsdf.inputs["Emission Color"].default_value = emissive
        bsdf.inputs["Emission Strength"].default_value = 1.0
    m.diffuse_color = color
    MATS[name] = m
    return m


def make_obj(name, mb, origin=(0, 0, 0), parent=None, sharp=38.0, coll=None, props=None):
    ox, oy, oz = origin
    me = bpy.data.meshes.new(name)
    me.from_pydata([(x - ox, y - oy, z - oz) for x, y, z in mb.V], [], mb.F)
    me.update()
    names = []
    for mn in mb.M:
        if mn not in names:
            names.append(mn)
    for mn in names:
        me.materials.append(MATS.get(mn) or material(mn))
    me.polygons.foreach_set("material_index", [names.index(mn) for mn in mb.M])
    # colours per corner
    cols = []
    for f, c in zip(mb.F, mb.C):
        cols.extend(list(c) * len(f))
    attr = me.color_attributes.new("Col", "FLOAT_COLOR", "CORNER")
    attr.data.foreach_set("color", cols)
    me.color_attributes.active_color = attr
    try:
        me.color_attributes.render_color_index = me.color_attributes.active_color_index
    except Exception:
        pass
    if any(u is not None for u in mb.UV):
        uvl = me.uv_layers.new(name="UVMap")
        flat = []
        for f, u in zip(mb.F, mb.UV):
            if u is None:
                u = [(0.0, 0.0)] * len(f)
            for p in u:
                flat.extend(p)
        uvl.uv.foreach_set("vector", flat)
    me.shade_smooth()
    me.set_sharp_from_angle(angle=math.radians(sharp))
    me.validate()
    ob = bpy.data.objects.new(name, me)
    (coll or bpy.context.scene.collection).objects.link(ob)
    ob.location = origin
    if parent is not None:
        ob.parent = parent
        ob.matrix_parent_inverse = parent.matrix_world.inverted()
    if props:
        for k, v in props.items():
            ob[k] = v
    return ob


def empty(name, loc=(0, 0, 0), parent=None, rot=None, size=0.15, kind="PLAIN_AXES", coll=None, props=None):
    ob = bpy.data.objects.new(name, None)
    ob.empty_display_type = kind
    ob.empty_display_size = size
    (coll or bpy.context.scene.collection).objects.link(ob)
    ob.location = loc
    if rot is not None:
        ob.rotation_mode = "QUATERNION"
        ob.rotation_quaternion = rot
    if parent is not None:
        ob.parent = parent
        ob.matrix_parent_inverse = parent.matrix_world.inverted()
    if props:
        for k, v in props.items():
            ob[k] = v
    return ob


def tri_count(ob):
    return sum(len(p.vertices) - 2 for p in ob.data.polygons)


# --------------------------------------------------------------------------- texture painter


class Canvas:
    """sRGB float canvas painted with SDF shapes at 2x then box-downsampled (anti-aliasing).
    Coordinates: (x, y) in [0,1] across the given region, y up."""

    def __init__(self, w, h, bg="#ffffff", ss=2):
        self.w, self.h, self.ss = w, h, ss
        W, H = w * ss, h * ss
        self.img = np.ones((H, W, 3)) * srgb(bg)
        ys, xs = np.mgrid[0:H, 0:W]
        self.X = (xs + 0.5) / W
        self.Y = 1.0 - (ys + 0.5) / H
        self.region = (0.0, 0.0, 1.0, 1.0)

    def set_region(self, x0, y0, x1, y1):
        self.region = (x0, y0, x1, y1)

    def _uv(self):
        x0, y0, x1, y1 = self.region
        return (self.X - x0) / (x1 - x0), (self.Y - y0) / (y1 - y0)

    def _inreg(self):
        x0, y0, x1, y1 = self.region
        return (self.X >= x0) & (self.X < x1) & (self.Y >= y0) & (self.Y < y1)

    def mask(self, m, col):
        m = m & self._inreg()
        self.img[m] = srgb(col)

    def fill(self, col):
        self.mask(np.ones_like(self.X, bool), col)

    def ellipse(self, cx, cy, rx, ry, col, rot=0.0):
        u, v = self._uv()
        c, s = math.cos(rot), math.sin(rot)
        dx, dy = u - cx, v - cy
        x = dx * c + dy * s
        y = -dx * s + dy * c
        self.mask((x / rx) ** 2 + (y / ry) ** 2 <= 1.0, col)

    def ring(self, cx, cy, rx, ry, w, col, a0=-math.pi, a1=math.pi):
        u, v = self._uv()
        dx, dy = (u - cx) / rx, (v - cy) / ry
        d = np.sqrt(dx * dx + dy * dy)
        ang = np.arctan2(dy, dx)
        self.mask((np.abs(d - 1.0) * min(rx, ry) <= w / 2) & (ang >= a0) & (ang <= a1), col)

    def line(self, p0, p1, w, col):
        u, v = self._uv()
        ax, ay = p0
        bx, by = p1
        px, py = u - ax, v - ay
        dx, dy = bx - ax, by - ay
        t = np.clip((px * dx + py * dy) / max(dx * dx + dy * dy, 1e-12), 0, 1)
        qx, qy = px - t * dx, py - t * dy
        self.mask(qx * qx + qy * qy <= (w / 2) ** 2, col)

    def poly(self, pts, col):
        u, v = self._uv()
        inside = np.zeros_like(u, bool)
        n = len(pts)
        for i in range(n):
            x0, y0 = pts[i]
            x1, y1 = pts[(i + 1) % n]
            cond = ((y0 > v) != (y1 > v))
            xint = x0 + (v - y0) * (x1 - x0) / ((y1 - y0) if y1 != y0 else 1e-12)
            inside ^= cond & (u < xint)
        self.mask(inside, col)

    def rect(self, x0, y0, x1, y1, col):
        u, v = self._uv()
        self.mask((u >= x0) & (u <= x1) & (v >= y0) & (v <= y1), col)

    def wave_band(self, y0, amp, freq, phase, col, below=True):
        u, v = self._uv()
        yy = y0 + amp * np.sin(2 * math.pi * (u * freq + phase))
        self.mask(v <= yy if below else v >= yy, col)

    def result(self):
        ss = self.ss
        H, W = self.img.shape[:2]
        return self.img.reshape(H // ss, ss, W // ss, ss, 3).mean(axis=(1, 3))

    def to_image(self, name, path):
        px = self.result()
        h, w = px.shape[:2]
        rgba = np.concatenate([px, np.ones((h, w, 1))], axis=2)[::-1].astype(np.float32)
        img = bpy.data.images.new(name, w, h, alpha=False)
        img.pixels.foreach_set(rgba.ravel())
        os.makedirs(os.path.dirname(path), exist_ok=True)
        img.filepath_raw = path
        img.file_format = "PNG"
        img.save()
        img.filepath = path
        img.reload()
        return img


# --------------------------------------------------------------------------- export


def export_glb(path, animations=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    gl = bpy.ops.export_scene.gltf.get_rna_type().properties.keys()
    opts = dict(
        filepath=path,
        export_format="GLB",
        use_selection=False,
        export_yup=True,
        export_apply=True,
        export_texcoords=True,
        export_normals=True,
        export_tangents=False,
        export_materials="EXPORT",
        export_image_format="AUTO",
        export_vertex_color="ACTIVE",
        export_all_vertex_colors=False,
        export_active_vertex_color_when_no_material=True,
        export_attributes=False,
        export_extras=True,
        export_lights=False,
        export_cameras=False,
        export_draco_mesh_compression_enable=False,
        export_animations=animations,
        export_animation_mode="ACTIONS",
        export_force_sampling=True,
        export_frame_step=1,
        export_anim_slide_to_zero=True,
        export_optimize_animation_size=False,
        export_skins=True,
        export_def_bones=False,
        export_leaf_bone=False,
        export_rest_position_armature=True,
        export_morph=False,
        export_anim_single_armature=False,
        export_bake_animation=False,
        export_reset_pose_bones=True,
    )
    bpy.ops.export_scene.gltf(**{k: v for k, v in opts.items() if k in gl or k == "filepath"})
    return os.path.getsize(path)


def glb_read(path):
    with open(path, "rb") as f:
        data = f.read()
    magic, ver, length = struct.unpack_from("<III", data, 0)
    off = 12
    js, binc = None, b""
    while off < length:
        clen, ctype = struct.unpack_from("<II", data, off)
        chunk = data[off + 8: off + 8 + clen]
        if ctype == 0x4E4F534A:
            js = json.loads(chunk.decode("utf-8"))
        elif ctype == 0x004E4942:
            binc = chunk
        off += 8 + clen
    return js, binc


def glb_write(path, js, binc):
    jb = json.dumps(js, separators=(",", ":")).encode("utf-8")
    jb += b" " * ((4 - len(jb) % 4) % 4)
    bb = binc + b"\0" * ((4 - len(binc) % 4) % 4)
    total = 12 + 8 + len(jb) + (8 + len(bb) if bb else 0)
    out = struct.pack("<III", 0x46546C67, 2, total) + struct.pack("<II", len(jb), 0x4E4F534A) + jb
    if bb:
        out += struct.pack("<II", len(bb), 0x004E4942) + bb
    with open(path, "wb") as f:
        f.write(out)


def glb_compact_colors(path):
    """Store COLOR_0 as normalized UNSIGNED_BYTE VEC4 instead of the exporter's FLOAT / UNSIGNED_SHORT
    (core glTF 2.0, no extension): 4-12 bytes per vertex saved."""
    js, binc = glb_read(path)
    acc = js["accessors"]
    bvs = js["bufferViews"]
    colors = set()
    for m in js.get("meshes", []):
        for p in m["primitives"]:
            if "COLOR_0" in p["attributes"]:
                colors.add(p["attributes"]["COLOR_0"])
    users = {}
    for i, a in enumerate(acc):
        if "bufferView" in a:
            users.setdefault(a["bufferView"], []).append(i)
    convert = {}
    for ai in colors:
        a = acc[ai]
        bv = a.get("bufferView")
        if a["componentType"] not in (5126, 5123) or bv is None or len(users[bv]) != 1 or bvs[bv].get("byteStride"):
            continue
        convert[bv] = ai
    out = bytearray()
    for i, bv in enumerate(bvs):
        start = bv.get("byteOffset", 0)
        data = binc[start:start + bv["byteLength"]]
        if i in convert:
            a = acc[convert[i]]
            nc = {"VEC3": 3, "VEC4": 4}[a["type"]]
            if a["componentType"] == 5126:
                f = np.frombuffer(data, dtype=np.float32, count=a["count"] * nc, offset=a.get("byteOffset", 0))
            else:  # the exporter's normalized uint16
                f = np.frombuffer(data, dtype="<u2", count=a["count"] * nc,
                                  offset=a.get("byteOffset", 0)).astype(np.float32) / 65535.0
            f = f.reshape(-1, nc)
            if nc == 3:
                f = np.concatenate([f, np.ones((len(f), 1), np.float32)], axis=1)
                a["type"] = "VEC4"
            # 8-bit linear: the palette is flat colours; worst case ~1 sRGB step in near-blacks
            q = np.clip(np.round(f * 255.0), 0, 255).astype(np.uint8)
            data = q.tobytes()
            a["componentType"] = 5121
            a["normalized"] = True
            a["byteOffset"] = 0
            a.pop("min", None)
            a.pop("max", None)
        while len(out) % 4:
            out.append(0)
        bv["byteOffset"] = len(out)
        bv["byteLength"] = len(data)
        out.extend(data)
    while len(out) % 4:
        out.append(0)
    js["buffers"][0]["byteLength"] = len(out)
    glb_write(path, js, bytes(out))
    return len(convert)


def glb_strip_anim_paths(path, paths=("scale",)):
    """Drop animation channels by target path (the exporter samples constant bone scale; the
    contract wants no scale keys). Orphaned sampler accessors stay (valid glTF, a few bytes)."""
    js, binc = glb_read(path)
    n = 0
    for a in js.get("animations", []):
        keep = [c for c in a["channels"] if c["target"]["path"] not in paths]
        n += len(a["channels"]) - len(keep)
        used = sorted({c["sampler"] for c in keep})
        remap = {old: i for i, old in enumerate(used)}
        a["samplers"] = [a["samplers"][i] for i in used]
        for c in keep:
            c["sampler"] = remap[c["sampler"]]
        a["channels"] = keep
    glb_write(path, js, binc)
    return n


def glb_strip_tags(path, sep="__"):
    """Blender needs unique object names; the game wants e.g. every stall's anchor called `keeper`.
    Objects are built as `keeper__goldfish`; this renames the glTF nodes to the part before `__`."""
    js, binc = glb_read(path)
    n = 0
    for node in js.get("nodes", []):
        nm = node.get("name", "")
        if sep in nm:
            node["name"] = nm.split(sep)[0]
            n += 1
    for mesh in js.get("meshes", []):
        nm = mesh.get("name", "")
        if sep in nm:
            mesh["name"] = nm.split(sep)[0]
    glb_write(path, js, binc)
    return n
