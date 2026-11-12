"""Three stylized cats (sleeping ginger, sitting calico, loafing black cat with white socks), each
with a tiny rig and in-place clips -> public/models/cats.glb

  E:\\blender\\blender-5.1.2-windows-x64\\blender.exe --background --factory-startup --python-exit-code 1 \\
      --python tools/blender/cats/build.py -- --out public/models/cats.glb

Bodies are metaball blobs (smooth fused body / head / tail) converted to a mesh and decimated to
budget; ears, eyes, nose and mouth are small separate pieces merged into the same skinned mesh.
Skin weights are analytic: each vertex is weighted by the metaball elements that made it (each
element is tagged with a bone), so a tail vertex follows the tail, a cheek follows the head.
Blender axes: cats face -Y (= +Z in glTF), origin = ground under the body centre.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
sys.dont_write_bytecode = True

import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Euler, Matrix, Quaternion, Vector  # noqa: E402

import kit  # noqa: E402
from kit import MB, R, S, T, hexc, lathe, material, prism, sphere, tube  # noqa: E402

FPS = 30
VIS = 0.574  # metaball visible radius / element radius (stiffness 2, threshold 0.6), measured
TRI_TARGET = 2200  # body blob after decimation; parts add ~300

FUR = {
    "fur_ginger": "#E8964A", "fur_ginger_dark": "#C46A2A", "fur_cream": "#FBE7C6",
    "fur_white": "#FAF6EE", "fur_orange": "#E58A3C", "fur_black": "#2A2730", "fur_black_soft": "#3A3542",
}
FACE = {"face_pink": "#F28CA0", "face_line": "#3A2522", "eye_dark": "#2A2230", "eye_hilite": "#FFFFFF",
        "eye_green": "#8CC63F", "eye_amber": "#F2B731", "fur_inner_ear": "#F5A9B8"}


def setup_materials():
    for k, v in list(FUR.items()) + list(FACE.items()):
        material(k, color=hexc(v))


# ----------------------------------------------------------------------------- element helpers


def ball(co, r, bone, size=(1, 1, 1), rot=(0, 0, 0)):
    return dict(co=Vector(co), r=r, size=Vector(size), rot=Euler([math.radians(a) for a in rot]).to_quaternion(),
                bone=bone)


def chain(pts, radii, bones, step=0.6):
    """Balls along a polyline; bones: callable(t) -> bone name."""
    P = [Vector(p) for p in pts]
    L = [0.0]
    for i in range(1, len(P)):
        L.append(L[-1] + (P[i] - P[i - 1]).length)
    total = L[-1]
    out = []
    s = 0.0
    while s <= total + 1e-6:
        t = s / total
        # position along polyline
        i = max(k for k in range(len(L)) if L[k] <= s + 1e-9)
        i = min(i, len(P) - 2)
        u = (s - L[i]) / max(L[i + 1] - L[i], 1e-9)
        p = P[i].lerp(P[i + 1], u)
        r = radii[0] + (radii[1] - radii[0]) * t
        out.append(ball(p, r, bones(t)))
        s += max(r * step, 0.004)
    return out


def tail_bone(t):
    return "tail1" if t < 0.34 else ("tail2" if t < 0.67 else "tail3")


def blob_mesh(name, elements, res=0.006):
    mb = bpy.data.metaballs.new(name)
    mb.resolution = res
    mb.render_resolution = res
    mb.threshold = 0.6
    for e in elements:
        el = mb.elements.new(type="ELLIPSOID")
        el.co = e["co"]
        el.radius = e["r"] / VIS
        el.size_x, el.size_y, el.size_z = e["size"]
        el.rotation = e["rot"]
        el.stiffness = 2.0
    ob = bpy.data.objects.new(name, mb)
    bpy.context.scene.collection.objects.link(ob)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    tmp = bpy.data.objects.new(name + "_tmp", me)
    bpy.context.scene.collection.objects.link(tmp)
    bpy.data.objects.remove(ob)
    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    dec = tmp.modifiers.new("dec", "DECIMATE")
    dec.ratio = min(1.0, TRI_TARGET / max(tris, 1))
    dg = bpy.context.evaluated_depsgraph_get()
    me2 = bpy.data.meshes.new_from_object(tmp.evaluated_get(dg))
    V = [tuple(v.co) for v in me2.vertices]
    F = [tuple(p.vertices) for p in me2.polygons]
    bpy.data.objects.remove(tmp)
    bpy.data.meshes.remove(me)
    bpy.data.meshes.remove(me2)
    print(f"[cats] {name}: blob {tris} tris -> {sum(len(f) - 2 for f in F)}")
    return V, F


def field_weights(p, elements):
    acc = {}
    for e in elements:
        q = e["rot"].inverted() @ (p - e["co"])
        q = Vector((q.x / e["size"].x, q.y / e["size"].y, q.z / e["size"].z)) / e["r"]
        c = math.exp(-3.0 * q.length_squared)
        acc[e["bone"]] = acc.get(e["bone"], 0.0) + c
    return acc


# ----------------------------------------------------------------------------- face parts


def frame_on(normal, front=Vector((0, -1, 0))):
    z = Vector(normal).normalized()
    y = (Vector((0, 0, 1)) - z * z.z)
    if y.length < 1e-4:
        y = front - z * front.dot(z)
    y.normalize()
    x = y.cross(z)
    m = Matrix((x, y, z)).transposed().to_4x4()
    return m


def head_point(H, d):
    """Point on the head surface in direction d: ray-cast onto the real blob when it exists (so
    features sit on the muzzle, not inside it), else the head ellipsoid (centre c, radii r)."""
    d = Vector(d).normalized()
    r = H["radii"]
    p = Vector((d.x * r.x, d.y * r.y, d.z * r.z))
    if H.get("bvh") is not None:
        dirn = p.normalized()
        hit, nrm, _, _ = H["bvh"].ray_cast(H["c"] + dirn * 0.3, -dirn)
        if hit is not None:
            if nrm.dot(dirn) < 0:
                nrm = -nrm
            return hit, nrm.normalized()
    # normal of the ellipsoid at p
    n = Vector((p.x / r.x ** 2, p.y / r.y ** 2, p.z / r.z ** 2)).normalized()
    return H["c"] + p, n


def ear(parts, H, side, col_mat, size=1.0, tilt=0.0):
    d = Vector((side * 0.55, -0.12 + tilt, 0.84))
    base, n = head_point(H, d)
    z = Vector((side * 0.42, -0.08 + tilt, 0.9)).normalized()
    f = Vector((0, -1, 0))
    y = (f - z * f.dot(z)).normalized()
    x = y.cross(z)
    m = T(*(base - n * 0.012)) @ Matrix((x, y, z)).transposed().to_4x4()
    h, r = 0.062 * size, 0.034 * size
    g = lathe([(r, 0.0), (r * 0.55, h * 0.55), (0.0, h)], 8, cap0=True)
    parts.append((g, col_mat, m @ S(1, 0.42, 1), "ear_L" if side > 0 else "ear_R"))
    gi = lathe([(r * 0.62, 0.0), (r * 0.3, h * 0.5), (0.0, h * 0.82)], 6, cap0=True)
    parts.append((gi, "fur_inner_ear", m @ T(0, r * 0.3, h * 0.05) @ S(1, 0.25, 1), "ear_L" if side > 0 else "ear_R"))


def eye_open(parts, H, side, iris, d=None, scale=1.0):
    d = d or Vector((side * 0.42, -0.86, 0.12))
    p, n = head_point(H, d)
    m = T(*(p - n * 0.004)) @ frame_on(n)
    w, h = 0.019 * scale, 0.024 * scale
    parts.append((sphere(1.0, 10, 6), "eye_dark", m @ S(w, h, 0.008), "head"))
    parts.append((sphere(1.0, 10, 5), iris, m @ T(0, -0.002, 0.0045) @ S(w * 0.78, h * 0.72, 0.0045), "head"))
    parts.append((sphere(1.0, 6, 4), "eye_dark", m @ T(0, -0.002, 0.0075) @ S(w * 0.28, h * 0.55, 0.003), "head"))
    parts.append((sphere(1.0, 6, 3), "eye_hilite", m @ T(-0.006 * scale, 0.007 * scale, 0.0095) @ S(0.005 * scale), "head"))


def eye_closed(parts, H, side, d=None):
    d = d or Vector((side * 0.42, -0.86, 0.1))
    p, n = head_point(H, d)
    m = T(*(p + n * 0.001)) @ frame_on(n)
    pts = [(0.017 * math.cos(a), 0.008 - 0.012 * math.sin(a), 0.0) for a in np.linspace(0, math.pi, 7)]
    pts = [tuple(m @ Vector(q)) for q in pts]
    parts.append((tube(pts, 0.0028, 4), "face_line", Matrix.Identity(4), "head"))


def nose_mouth(parts, H, d_nose=(0, -0.97, -0.18)):
    p, n = head_point(H, d_nose)
    m = T(*(p + n * 0.001)) @ frame_on(n)
    parts.append((prism([(-0.009, 0.004), (0.009, 0.004), (0.0, -0.007)], -0.003, 0.003), "face_pink", m, "head"))
    for sx in (-1, 1):
        pts = [(sx * 0.0065 + 0.0065 * math.cos(a), -0.011 - 0.006 * math.sin(a), -0.001)
               for a in np.linspace(0, math.pi, 6)]
        pts = [tuple(m @ Vector(q)) for q in pts]
        parts.append((tube(pts, 0.0016, 4), "face_line", Matrix.Identity(4), "head"))


def whiskers(parts, H, side):
    p, n = head_point(H, (side * 0.5, -0.82, -0.25))
    for k, dz in enumerate((0.006, -0.004)):
        a = p + Vector((0, 0, dz))
        b = a + Vector((side * 0.05, -0.008, dz * 1.5 - 0.004 * k))
        parts.append((tube([tuple(a), tuple(b)], 0.0009, 3, caps=False), "face_line", Matrix.Identity(4), "head"))


# ----------------------------------------------------------------------------- cat designs


def design_sleep():
    """Ginger, curled up asleep. Body arcs round the centre, head resting at front right on its paws,
    tail wrapped round the front."""
    E = []
    E.append(ball((-0.085, 0.06, 0.075), 0.095, "body", (1.0, 1.05, 0.82)))
    E.append(ball((0.0, 0.1, 0.085), 0.092, "body", (1.1, 0.95, 0.85)))
    E.append(ball((0.08, 0.04, 0.08), 0.085, "body", (1.0, 1.0, 0.85)))
    E.append(ball((-0.11, -0.02, 0.05), 0.055, "body", (1.0, 1.2, 0.8)))     # hind leg
    E.append(ball((0.035, -0.075, 0.03), 0.03, "body", (1.6, 1.0, 0.75)))    # front paws
    E.append(ball((0.1, -0.095, 0.03), 0.028, "body", (1.5, 1.0, 0.75), (0, 0, 25)))
    Hc = Vector((0.06, -0.065, 0.085))
    H = dict(c=Hc, radii=Vector((0.082, 0.072, 0.066)))
    E.append(ball(Hc, 0.07, "head", (1.17, 1.03, 0.94)))
    E.append(ball(Hc + Vector((0, -0.05, -0.022)), 0.028, "head", (1.3, 1.0, 0.85)))  # muzzle
    tail = [(-0.13, 0.07, 0.035), (-0.17, 0.0, 0.03), (-0.15, -0.09, 0.028), (-0.07, -0.14, 0.026),
            (0.03, -0.155, 0.025)]
    E += chain(tail, (0.032, 0.022), tail_bone)
    def make_parts():
        parts = []
        for sd in (-1, 1):
            ear(parts, H, sd, "fur_ginger", 1.0)
            eye_closed(parts, H, sd)
            whiskers(parts, H, sd)
        nose_mouth(parts, H)
        return parts
    tail_pts = [Vector(p) for p in tail]

    def region(c, n):
        # cream: muzzle, chin, front paws, tail tip; darker stripes across the back and tail
        if (c - (Hc + Vector((0, -0.05, -0.026)))).length < 0.032:
            return "fur_cream"
        if min((c - Vector(p)).length for p in ((0.035, -0.075, 0.03), (0.1, -0.095, 0.03))) < 0.034:
            return "fur_cream"
        dtail = min((c - p).length for p in tail_pts)
        if dtail < 0.04:
            t = min(range(len(tail_pts)), key=lambda i: (c - tail_pts[i]).length) / (len(tail_pts) - 1)
            if t > 0.85:
                return "fur_cream"
            return "fur_ginger_dark" if int(t * 9) % 2 == 1 else "fur_ginger"
        if c.z > 0.1 and (c - Hc).length > 0.085:
            a = math.atan2(c.y - 0.02, c.x)
            if math.sin(a * 9) > 0.45:
                return "fur_ginger_dark"
        if (c - Hc).length < 0.09 and c.z > Hc.z + 0.03:
            a = math.atan2(c.z - Hc.z, c.x - Hc.x)
            if c.y < Hc.y and abs(c.x - Hc.x) < 0.03 and c.z > Hc.z + 0.045:
                return "fur_ginger_dark"
        return "fur_ginger"
    bones = dict(
        root=((0, 0, 0), (0, 0.06, 0)),
        body=((-0.09, 0.07, 0.08), (0.08, 0.05, 0.08)),
        head=((0.07, 0.0, 0.08), (0.06, -0.1, 0.09)),
        tail1=(tail[0], tail[1]), tail2=(tail[1], tail[3]), tail3=(tail[3], tail[4]),
        ear_L=(tuple(head_point(H, (0.5, -0.1, 0.8))[0]), tuple(head_point(H, (0.5, -0.1, 0.8))[0] + Vector((0.02, 0, 0.05)))),
        ear_R=(tuple(head_point(H, (-0.5, -0.1, 0.8))[0]), tuple(head_point(H, (-0.5, -0.1, 0.8))[0] + Vector((-0.02, 0, 0.05)))),
    )
    return E, H, make_parts, region, bones


def design_sit():
    """Calico, sitting upright, tail curled round its front paws."""
    E = []
    E.append(ball((0.0, 0.04, 0.085), 0.1, "body", (1.05, 1.15, 0.9)))       # haunches
    E.append(ball((0.0, -0.01, 0.17), 0.075, "body", (1.0, 0.95, 1.25)))     # chest
    for sx in (-1, 1):
        E.append(ball((sx * 0.085, 0.04, 0.06), 0.05, "body", (0.7, 1.3, 0.9)))          # hind thighs
        E.append(ball((sx * 0.07, -0.04, 0.02), 0.026, "body", (0.9, 1.5, 0.7)))         # hind feet
        E += chain([(sx * 0.035, -0.04, 0.17), (sx * 0.036, -0.07, 0.07), (sx * 0.036, -0.075, 0.02)],
                   (0.026, 0.022), lambda t: "body")
        E.append(ball((sx * 0.036, -0.088, 0.016), 0.024, "body", (1.0, 1.3, 0.7)))      # front paws
    Hc = Vector((0.0, -0.035, 0.318))
    H = dict(c=Hc, radii=Vector((0.095, 0.082, 0.078)))
    E.append(ball(Hc, 0.081, "head", (1.17, 1.01, 0.96)))
    E.append(ball(Hc + Vector((0, -0.06, -0.025)), 0.029, "head", (1.35, 1.0, 0.85)))
    E.append(ball((0.0, -0.022, 0.25), 0.04, "head", (1.25, 1.0, 0.8)))      # neck
    tail = [(0.0, 0.13, 0.03), (0.09, 0.12, 0.028), (0.13, 0.03, 0.026), (0.11, -0.07, 0.025), (0.05, -0.11, 0.024)]
    E += chain(tail, (0.03, 0.022), tail_bone)
    def make_parts():
        parts = []
        for sd in (-1, 1):
            ear(parts, H, sd, "fur_black" if sd > 0 else "fur_orange", 1.05)
            eye_open(parts, H, sd, "eye_green")
            whiskers(parts, H, sd)
        nose_mouth(parts, H)
        return parts
    patches = [((0.07, 0.06, 0.13), 0.075, "fur_orange"), ((-0.08, 0.1, 0.09), 0.07, "fur_black"),
               ((0.06, -0.05, 0.39), 0.06, "fur_black"), ((-0.055, -0.1, 0.36), 0.05, "fur_orange"),
               ((-0.085, -0.02, 0.17), 0.06, "fur_orange"), ((0.1, 0.02, 0.07), 0.06, "fur_black"),
               ((-0.02, 0.1, 0.2), 0.05, "fur_orange"), ((0.11, 0.0, 0.03), 0.045, "fur_black")]
    tail_pts = [Vector(p) for p in tail]

    def region(c, n):
        if (c - (Hc + Vector((0, -0.065, -0.03)))).length < 0.04:
            return "fur_white"
        dtail = min((c - p).length for p in tail_pts)
        if dtail < 0.04:
            t = min(range(len(tail_pts)), key=lambda i: (c - tail_pts[i]).length) / (len(tail_pts) - 1)
            return "fur_black" if t < 0.45 else ("fur_orange" if t < 0.8 else "fur_white")
        if c.y < -0.03 and c.z < 0.26 and abs(c.x) < 0.07:
            return "fur_white"   # bib + front legs
        best = None
        for (p, r, mat) in patches:
            d = (c - Vector(p)).length / r
            if d < 1.0 and (best is None or d < best[0]):
                best = (d, mat)
        return best[1] if best else "fur_white"
    bones = dict(
        root=((0, 0, 0), (0, 0.06, 0)),
        body=((0.0, 0.03, 0.07), (0.0, -0.02, 0.23)),
        head=((0.0, -0.02, 0.255), (0.0, -0.05, 0.39)),
        tail1=(tail[0], tail[1]), tail2=(tail[1], tail[3]), tail3=(tail[3], tail[4]),
        ear_L=(tuple(head_point(H, (0.5, -0.1, 0.8))[0]), tuple(head_point(H, (0.5, -0.1, 0.8))[0] + Vector((0.02, 0, 0.05)))),
        ear_R=(tuple(head_point(H, (-0.5, -0.1, 0.8))[0]), tuple(head_point(H, (-0.5, -0.1, 0.8))[0] + Vector((-0.02, 0, 0.05)))),
    )
    return E, H, make_parts, region, bones


def design_loaf():
    """Black cat in a loaf, paws tucked (white socks peeking out), tail along its right side."""
    E = []
    E.append(ball((0.0, 0.03, 0.085), 0.1, "body", (1.08, 1.55, 0.88)))
    E.append(ball((0.0, -0.07, 0.09), 0.085, "body", (1.1, 1.0, 0.95)))
    for sx in (-1, 1):
        E.append(ball((sx * 0.04, -0.135, 0.022), 0.024, "body", (1.0, 1.3, 0.75)))     # tucked front paws
        E.append(ball((sx * 0.085, 0.13, 0.025), 0.026, "body", (1.0, 1.4, 0.75)))      # hind feet
    Hc = Vector((0.0, -0.125, 0.18))
    H = dict(c=Hc, radii=Vector((0.086, 0.074, 0.07)))
    E.append(ball(Hc, 0.074, "head", (1.16, 1.0, 0.95)))
    E.append(ball(Hc + Vector((0, -0.052, -0.022)), 0.027, "head", (1.35, 1.0, 0.85)))
    tail = [(0.03, 0.2, 0.03), (0.1, 0.17, 0.028), (0.13, 0.07, 0.026), (0.125, -0.04, 0.025), (0.09, -0.12, 0.028)]
    E += chain(tail, (0.029, 0.022), tail_bone)
    def make_parts():
        parts = []
        for sd in (-1, 1):
            ear(parts, H, sd, "fur_black", 1.05)
            eye_open(parts, H, sd, "eye_amber", scale=1.05)
            whiskers(parts, H, sd)
        nose_mouth(parts, H)
        return parts
    tail_pts = [Vector(e["co"]) for e in E if e["bone"].startswith("tail")]

    def region(c, n):
        if c.z < 0.05 and (abs(c.y + 0.135) < 0.04 or abs(c.y - 0.13) < 0.045) and min(
                (c - p).length for p in tail_pts) > 0.04:
            return "fur_white"
        if (c - (Hc + Vector((0, -0.058, -0.03)))).length < 0.025:
            return "fur_black_soft"
        return "fur_black"
    bones = dict(
        root=((0, 0, 0), (0, 0.06, 0)),
        body=((0.0, 0.12, 0.08), (0.0, -0.06, 0.1)),
        head=((0.0, -0.07, 0.15), (0.0, -0.17, 0.2)),
        tail1=(tail[0], tail[1]), tail2=(tail[1], tail[3]), tail3=(tail[3], tail[4]),
        ear_L=(tuple(head_point(H, (0.5, -0.1, 0.8))[0]), tuple(head_point(H, (0.5, -0.1, 0.8))[0] + Vector((0.02, 0, 0.05)))),
        ear_R=(tuple(head_point(H, (-0.5, -0.1, 0.8))[0]), tuple(head_point(H, (-0.5, -0.1, 0.8))[0] + Vector((-0.02, 0, 0.05)))),
    )
    return E, H, make_parts, region, bones


# ----------------------------------------------------------------------------- build / rig


PARENT = dict(root=None, body="root", head="body", ear_L="head", ear_R="head", tail1="body", tail2="tail1",
              tail3="tail2")
ORDER = ["root", "body", "head", "ear_L", "ear_R", "tail1", "tail2", "tail3"]


def build_cat(name, design):
    E, H, make_parts, region, bones = design()
    V, F = blob_mesh(name + "_blob", E)
    from mathutils.bvhtree import BVHTree
    H["bvh"] = BVHTree.FromPolygons([Vector(v) for v in V], F)
    parts = make_parts()
    mb = MB()
    mats = []
    for f in F:
        pts = [Vector(V[i]) for i in f]
        c = sum(pts, Vector()) / len(pts)
        nrm = (pts[1] - pts[0]).cross(pts[-1] - pts[0])
        mats.append(region(c, nrm.normalized() if nrm.length > 0 else nrm))
    mb.add((V, F, None), kit.WHITE, lambda k: mats[k])
    nbody = len(mb.V)
    ranges = []
    for g, mat, m, bone in parts:
        s = len(mb.V)
        mb.add(g, kit.WHITE, mat, m)
        ranges.append((s, len(mb.V), bone))
    # armature
    ad = bpy.data.armatures.new(name)
    arm = bpy.data.objects.new(name, ad)
    bpy.context.scene.collection.objects.link(arm)
    arm["kind"] = "cat"
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    eb = {}
    for b in ORDER:
        h, t = bones[b]
        e = ad.edit_bones.new(b)
        e.head, e.tail = Vector(h), Vector(t)
        if (e.tail - e.head).length < 0.01:
            e.tail = e.head + Vector((0, 0, 0.02))
        e.roll = 0.0
        eb[b] = e
    for b in ORDER:
        if PARENT[b]:
            eb[b].parent = eb[PARENT[b]]
            eb[b].use_connect = False
    bpy.ops.object.mode_set(mode="OBJECT")
    for b in ad.bones:
        b.use_deform = b.name != "root"
    ob = kit.make_obj(name + "_body", mb, parent=arm, sharp=89)
    # weights
    groups = {b: ob.vertex_groups.new(name=b) for b in ORDER if b != "root"}
    for i in range(nbody):
        w = field_weights(Vector(mb.V[i]), E)
        tot = sum(w.values()) or 1.0
        items = sorted(((v / tot, k) for k, v in w.items()), reverse=True)[:4]
        items = [(v, k) for v, k in items if v > 0.03]
        s = sum(v for v, _ in items)
        for v, k in items:
            groups[k].add([i], v / s, "REPLACE")
    for s, e, bone in ranges:
        groups[bone].add(list(range(s, e)), 1.0, "REPLACE")
    mod = ob.modifiers.new("Armature", "ARMATURE")
    mod.object = arm
    print(f"[cats] {name}: {kit.tri_count(ob)} tris, {len(ob.data.vertices)} verts")
    return arm, ob


# ----------------------------------------------------------------------------- clips


def q_axis(axis, deg):
    return Quaternion(Vector(axis).normalized(), math.radians(deg))


def smooth_bump(t, c, w):
    """0..1..0 bump centred at c with half-width w (cosine)."""
    d = abs(t - c)
    return 0.5 * (1 + math.cos(math.pi * d / w)) if d < w else 0.0


def bake(arm, name, dur, pose_fn):
    """pose_fn(t) -> {bone: (Quaternion in armature axes at rest, location offset Vector or None)}.
    Writes a dense, seamless loop (last key == first key)."""
    n = int(round(dur * FPS))
    act = bpy.data.actions.new(name)
    act.use_fake_user = True
    slot = act.slots.new(id_type="OBJECT", name=arm.name)
    layer = act.layers.new("Layer")
    strip = layer.strips.new(type="KEYFRAME")
    cb = strip.channelbag(slot, ensure=True)
    rest = {b.name: b.matrix_local.to_quaternion() for b in arm.data.bones}
    frames = np.arange(n + 1, dtype=float) + 1
    rots = {b: np.zeros((n + 1, 4)) for b in ORDER}
    locs = {b: np.zeros((n + 1, 3)) for b in ORDER}
    for i in range(n + 1):
        t = (i % n) / FPS
        pose = pose_fn(t)
        for b in ORDER:
            q, loc = pose.get(b, (Quaternion(), None))
            Rb = rest[b]
            ql = Rb.inverted() @ q @ Rb
            if i > 0 and np.dot(rots[b][i - 1], [ql.w, ql.x, ql.y, ql.z]) < 0:
                ql.negate()
            rots[b][i] = [ql.w, ql.x, ql.y, ql.z]
            if loc is not None:
                locs[b][i] = list(Rb.inverted() @ Vector(loc))
    for b in ORDER:
        grp = cb.groups.new(b)
        for k in range(4):
            fc = cb.fcurves.new(f'pose.bones["{b}"].rotation_quaternion', index=k)
            fc.group = grp
            fc.keyframe_points.add(n + 1)
            fc.keyframe_points.foreach_set("co", np.stack([frames, rots[b][:, k]], axis=1).ravel())
            fc.keyframe_points.foreach_set("interpolation", [1] * (n + 1))
            fc.update()
        if np.abs(locs[b]).max() > 1e-7:
            for k in range(3):
                fc = cb.fcurves.new(f'pose.bones["{b}"].location', index=k)
                fc.group = grp
                fc.keyframe_points.add(n + 1)
                fc.keyframe_points.foreach_set("co", np.stack([frames, locs[b][:, k]], axis=1).ravel())
                fc.keyframe_points.foreach_set("interpolation", [1] * (n + 1))
                fc.update()
    act.use_frame_range = True
    act.frame_start, act.frame_end = 1, n + 1
    act.use_cyclic = True
    ad = arm.animation_data or arm.animation_data_create()
    tr = ad.nla_tracks.new()
    tr.name = name
    st = tr.strips.new(name, 1, act)
    if hasattr(st, "action_slot"):
        try:
            st.action_slot = slot
        except Exception:
            pass
    tr.mute = True
    return dict(name=name, seconds=dur, frames=n + 1, loop=True)


X, Y, Z = (1, 0, 0), (0, 1, 0), (0, 0, 1)
TAU = 2 * math.pi


def tail_wave(t, period, amp, axis=Z, lag=0.18, base=(0, 0, 0)):
    out = {}
    for k, b in enumerate(("tail1", "tail2", "tail3")):
        a = base[k] + amp[k] * math.sin(TAU * (t / period - lag * k))
        out[b] = (q_axis(axis, a), None)
    return out


def clips_sleep(arm):
    out = []

    def sleep(t):
        br = math.sin(TAU * t / 2.0)                       # two slow breaths in 4 s
        p = {"body": (q_axis(Y, 1.2 * br) @ q_axis(X, -0.8 * br), Vector((0, 0, 0.0035 * (br + 1) * 0.5)))}
        p["head"] = (q_axis(X, 0.8 * br), None)
        tw = smooth_bump(t, 2.6, 0.14)                      # one ear twitch
        p["ear_L"] = (q_axis(Y, -22 * tw) @ q_axis(X, 10 * tw), None)
        p["ear_R"] = (q_axis(Y, 2 * br), None)
        p.update(tail_wave(t, 4.0, (1.5, 3.0, 6.0)))
        return p
    out.append(bake(arm, "cat_sleep_sleep", 4.0, sleep))

    def purr(t):
        pr = 0.0012 * math.sin(TAU * 12 * t)               # purr shiver
        br = math.sin(TAU * t / 2.0)
        p = {"body": (q_axis(X, -0.6 * br), Vector((0, 0, pr + 0.002)))}
        # head lifted, nuzzling slightly (eyes stay closed: painted)
        p["head"] = (q_axis(X, -9 + 2.5 * math.sin(TAU * t / 2.0)) @ q_axis(Y, 4 * math.sin(TAU * t / 2.0 + 0.6)), None)
        p["ear_L"] = (q_axis(Y, -6), None)
        p["ear_R"] = (q_axis(Y, 6), None)
        p.update(tail_wave(t, 2.0, (4, 8, 14), axis=Z, base=(0, -3, -8)))
        return p
    out.append(bake(arm, "cat_sleep_purr", 2.0, purr))
    return out


def clips_sit(arm):
    out = []

    def idle(t):
        br = math.sin(TAU * t / 2.0)
        p = {"body": (q_axis(X, 0.8 * br), None)}
        turn = smooth_bump(t, 2.4, 0.9)                     # head turns to look aside and back
        p["head"] = (q_axis(Z, 22 * turn) @ q_axis(Y, -5 * turn) @ q_axis(X, 1.0 * br), None)
        flick = smooth_bump(t, 1.0, 0.18) - 0.6 * smooth_bump(t, 1.3, 0.15)
        tw = tail_wave(t, 4.0, (3, 5, 8))
        tw["tail3"] = (q_axis(Z, 8 * math.sin(TAU * (t / 4.0 - 0.36)) + 28 * flick) @ q_axis(X, -12 * flick), None)
        tw["tail2"] = (tw["tail2"][0] @ q_axis(Z, 10 * flick), None)
        p.update(tw)
        ew = smooth_bump(t, 3.4, 0.12)
        p["ear_L"] = (q_axis(Y, -15 * ew), None)
        p["ear_R"] = (q_axis(Y, 4 * turn), None)
        return p
    out.append(bake(arm, "cat_sit_idle", 4.0, idle))

    def look(t):
        s = math.sin(TAU * t / 3.0)
        p = {"body": (q_axis(X, -3 + 0.6 * s), None)}
        p["head"] = (q_axis(X, -24 + 2 * math.sin(TAU * t / 1.5)) @ q_axis(Y, 7 * s) @ q_axis(Z, 5 * math.sin(TAU * t / 3.0 + 1.0)),
                     None)
        p["ear_L"] = (q_axis(X, -12) @ q_axis(Y, 3 * s), None)
        p["ear_R"] = (q_axis(X, -12) @ q_axis(Y, -3 * s), None)
        p.update(tail_wave(t, 3.0, (3, 6, 10)))
        return p
    out.append(bake(arm, "cat_sit_look", 3.0, look))
    return out


def clips_loaf(arm):
    def idle(t):
        br = math.sin(TAU * t / 2.0)
        p = {"body": (q_axis(X, 0.6 * br), Vector((0, 0, 0.0015 * (br + 1) * 0.5)))}
        bob = smooth_bump(t, 1.6, 0.6)                      # slow blink-like nod
        p["head"] = (q_axis(X, 9 * bob) @ q_axis(Y, 2 * math.sin(TAU * t / 4.0)), None)
        p["ear_L"] = (q_axis(Y, -5 * bob), None)
        p["ear_R"] = (q_axis(Y, 5 * bob), None)
        f1 = smooth_bump(t, 2.9, 0.12)
        f2 = smooth_bump(t, 3.3, 0.12)
        tw = tail_wave(t, 4.0, (0.8, 1.5, 3.0))
        tw["tail3"] = (q_axis(Z, 3 * math.sin(TAU * (t / 4.0 - 0.36)) + 26 * f1 - 18 * f2) @ q_axis(X, -15 * (f1 + f2)), None)
        p.update(tw)
        return p
    return [bake(arm, "cat_loaf_idle", 4.0, idle)]


def main():
    kit.lower_priority()
    a = kit.script_args()
    out = os.path.abspath(a.get("out", os.path.join(REPO, "public", "models", "cats.glb")))
    kit.reset_scene()
    kit.MATS.clear()
    setup_materials()
    sc = bpy.context.scene
    sc.render.fps = FPS
    clips = []
    cats = {}
    for i, (nm, des, cl) in enumerate((("cat_sleep", design_sleep, clips_sleep), ("cat_sit", design_sit, clips_sit),
                                       ("cat_loaf", design_loaf, clips_loaf))):
        arm, ob = build_cat(nm, des)
        clips += cl(arm)
        arm.animation_data.action = None
        cats[nm] = (arm, ob)
    bpy.context.view_layer.update()
    for c in clips:
        print(f"[cats] clip {c['name']}: {c['seconds']} s, {c['frames']} keys, loop")
    if a.get("blend"):
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(a["blend"]))
    kit.export_glb(out, animations=True)
    kit.glb_compact_colors(out)
    kit.glb_strip_anim_paths(out, ("scale",))
    print(f"[cats] wrote {out} ({os.path.getsize(out) / 1024:.0f} KiB)")


if __name__ == "__main__":
    main()
