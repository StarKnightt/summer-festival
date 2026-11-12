"""Armature definition and analytic skin weights.

Bones (names as in glTF / three.js; underscores, never dots):
  root > hips > spine > spine1 > spine2 > neck > head
  spine2 > shoulder_L > upperarm_L > forearm_L > hand_L > (thumb_L, fingers_L)      (same for _R)
  hand_L > finger_<thumb|index|middle|ring|pinky>_1_L > finger_<...>_2_L           (same for _R)
      five separate fingers; their rest pose is the relaxed curl. thumb_L / fingers_L are the old
      one-bone-per-hand controls: kept (same name, parent and rest) but no vertex is weighted to
      them any more.
  hips > thigh_L > shin_L > foot_L > toe_L                                         (same for _R)
  helper chains registered by the builders with add_chain(): sleeve_L1-2 / sleeve_R1-2 (forearm),
  hairSideL1-2, hairSideR1-2, hairBack1-3, hairBun1 (head), kanzashi1-2 (hairBun1),
  obiTailL1-2, obiTailR1-2 (spine), skirtF1, skirtB1 (hips).

Weights are smooth analytic fields evaluated per mesh (skin and cloth alike), so a garment and the
skin under it bend with the same blend. Builders store each object's weights in WEIGHTS.
"""
import bpy
import numpy as np
from mathutils import Vector

from . import shape as S
from .common import collection, norm, smooth

EXTRA = []       # (name, head, tail, parent, roll) helper chains
WEIGHTS = {}     # object name -> {bone: weights}


def reset():
    EXTRA.clear()
    WEIGHTS.clear()


def _v(p):
    return Vector((float(p[0]), float(p[1]), float(p[2])))


def L2R(name):
    return name[:-2] + "_R" if name.endswith("_L") else name


# ---------------------------------------------------------------- hand frame (left side)


def hand_frame():
    """Left hand axes: d along the hand, w toward the thumb, n out of the palm (palm faces her
    side, thumb forward)."""
    d = norm(S.WRI - S.ELB + np.array([0.0, -0.01, -0.02]))
    n0 = np.array([-1.0, -0.12, 0.0])
    n = norm(n0 - d * (n0 @ d))
    w = norm(np.cross(n, d))
    return d, w, n


HAND_LEN = 0.082     # wrist to knuckles
FINGER_LEN = 0.070


def hand_points():
    d, w, n = hand_frame()
    W = S.WRI
    knuck = W + d * HAND_LEN
    thumb0 = W + d * 0.022 + w * 0.020 + n * 0.008
    tdir = norm(d * 0.70 + w * 0.55 + n * 0.45)
    return {"wrist": W, "knuck": knuck, "fing_tip": knuck + norm(d + n * 0.35) * FINGER_LEN,
            "thumb0": thumb0, "thumb1": thumb0 + tdir * 0.052, "d": d, "w": w, "n": n}


FINGERS = ("thumb", "index", "middle", "ring", "pinky")
# finger: offset of the knuckle across the hand (+ = thumb side), length, radius, curl, fan (deg).
# Distinct lengths, curls and a slight fan keep the fingers apart, so the hand never reads as a mitten.
_FDEF = {
    "index": (0.0228, 0.062, 0.0068, 0.75, 5.0),
    "middle": (0.0078, 0.069, 0.0070, 1.00, 1.0),
    "ring": (-0.0072, 0.064, 0.0066, 1.25, -3.5),
    "pinky": (-0.0218, 0.051, 0.0059, 1.50, -8.5),
}


def finger_joints():
    """Left hand, relaxed curl: finger -> (base, mid, bend, tip, radius). Bone _1 runs base -> mid
    (the first phalanx), bone _2 runs mid -> tip (the other two, with the last bend in the mesh)."""
    import math
    hp = hand_points()
    d, w, n = hp["d"], hp["w"], hp["n"]
    out = {}
    for f, (off, L, r, c, fan) in _FDEF.items():
        dd = norm(d * math.cos(math.radians(fan)) + w * math.sin(math.radians(fan)))
        a1 = math.radians(6.0 + 12.0 * c)
        a2 = a1 + math.radians(26.0 * c)
        a3 = a2 + math.radians(20.0 * c)
        dr = lambda a: dd * math.cos(a) + n * math.sin(a)
        p0 = hp["knuck"] + w * off - d * 0.004
        p1 = p0 + dr(a1) * L * 0.40
        p2 = p1 + dr(a2) * L * 0.33
        p3 = p2 + dr(a3) * L * 0.27
        out[f] = (p0, p1, p2, p3, r)
    t0 = hp["thumb0"]
    tdir = norm(hp["thumb1"] - t0)
    q1 = t0 + tdir * 0.027
    q2 = t0 + tdir * 0.044 + d * 0.008 + n * 0.006
    q3 = t0 + tdir * 0.056 + d * 0.016 + n * 0.012
    out["thumb"] = (t0, q1, q2, q3, 0.0082)
    return out


def bone_defs():
    """[(name, head, tail, parent, roll_vector)] in the bind pose (barefoot frame)."""
    B = []
    fwd = (0, -1, 0)
    j = S.J
    B.append(("root", (0, 0, 0), (0, 0, 0.12), None, fwd))
    B.append(("hips", j["hips"], j["spine"], "root", fwd))
    B.append(("spine", j["spine"], j["spine1"], "hips", fwd))
    B.append(("spine1", j["spine1"], j["spine2"], "spine", fwd))
    B.append(("spine2", j["spine2"], j["neck"], "spine1", fwd))
    B.append(("neck", j["neck"], j["head"], "spine2", fwd))
    B.append(("head", j["head"], j["head_end"], "neck", fwd))
    hp = hand_points()
    left = [
        ("shoulder_L", S.CLAV, S.SH, "spine2", fwd),
        ("upperarm_L", S.SH, S.ELB, "shoulder_L", fwd),
        ("forearm_L", S.ELB, S.WRI, "upperarm_L", fwd),
        ("hand_L", hp["wrist"], hp["knuck"], "forearm_L", tuple(-hp["n"])),
        ("thumb_L", hp["thumb0"], hp["thumb1"], "hand_L", tuple(-hp["n"])),
        ("fingers_L", hp["knuck"], hp["fing_tip"], "hand_L", tuple(-hp["n"])),
    ]
    for f in FINGERS:
        p0, p1, p2, p3, r = finger_joints()[f]
        left.append((f"finger_{f}_1_L", p0, p1, "hand_L", tuple(-hp["n"])))
        left.append((f"finger_{f}_2_L", p1, p3, f"finger_{f}_1_L", tuple(-hp["n"])))
    left += [
        ("thigh_L", S.HIP, S.KNEE, "hips", fwd),
        ("shin_L", S.KNEE, S.ANKLE, "thigh_L", fwd),
        ("foot_L", S.ANKLE, S.BALL, "shin_L", (0, 0, 1)),
        ("toe_L", S.BALL, S.TOE, "foot_L", (0, 0, 1)),
    ]
    for (nm, h, t, p, r) in left:
        B.append((nm, tuple(h), tuple(t), p, r))
    for (nm, h, t, p, r) in left:
        hR, tR = S.side(h, -1), S.side(t, -1)
        rR = (-r[0], r[1], r[2])
        B.append((L2R(nm), tuple(hR), tuple(tR), L2R(p), rR))
    return B


def add_chain(prefix, points, parent, roll=(0, -1, 0)):
    names = []
    for i in range(len(points) - 1):
        nm = f"{prefix}{i + 1}"
        EXTRA.append((nm, tuple(points[i]), tuple(points[i + 1]), parent if i == 0 else names[-1], roll))
        names.append(nm)
    return names


def chain_points(prefix):
    pts = []
    for (nm, h, t, p, r) in EXTRA:
        if nm.startswith(prefix) and nm[len(prefix):].isdigit():
            if not pts:
                pts.append(np.array(h))
            pts.append(np.array(t))
    return np.array(pts)


def build_armature(name="heroine_rig"):
    col = collection()
    arm = bpy.data.armatures.new(name)
    ob = bpy.data.objects.new(name, arm)
    col.objects.link(ob)
    vl = bpy.context.view_layer
    vl.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm.edit_bones
    for (nm, h, t, parent, roll) in bone_defs() + EXTRA:
        b = eb.new(nm)
        b.head = _v(h)
        b.tail = _v(t)
        b.align_roll(_v(roll))
        if parent:
            b.parent = eb[parent]
            b.use_connect = False
        b.use_deform = nm != "root"
    bpy.ops.object.mode_set(mode="OBJECT")
    arm.display_type = "STICK"
    return ob


# ---------------------------------------------------------------- weight fields


def _partition(bones, steps, n):
    W, acc = {}, np.ones(n)
    for i, bn in enumerate(bones):
        if i < len(steps):
            W[bn] = W.get(bn, 0) + acc * (1 - steps[i])
            acc = acc * steps[i]
        else:
            W[bn] = W.get(bn, 0) + acc
    return W


def chain(P, joints, bones, blends):
    """Each bone owns its segment of the joint polyline; neighbours blend across inner joints."""
    J = np.asarray(joints, dtype=float)
    n = len(P)
    seg = np.linalg.norm(np.diff(J, axis=0), axis=1)
    cum = np.concatenate([[0], np.cumsum(seg)])
    best = np.full(n, np.inf)
    sp = np.zeros(n)
    for i in range(len(J) - 1):
        a, b = J[i], J[i + 1]
        ab = b - a
        t = np.clip(((P - a) @ ab) / (ab @ ab), -0.5 if i == 0 else 0.0, 1.0 if i < len(J) - 2 else 1.8)
        d = np.linalg.norm(P - (a + t[:, None] * ab), axis=1)
        m = d < best
        best = np.where(m, d, best)
        sp = np.where(m, cum[i] + t * seg[i], sp)
    steps = [smooth(cum[i + 1] - blends[i], cum[i + 1] + blends[i], sp) for i in range(len(bones) - 1)]
    return _partition(bones, steps, n), sp


def merge(dst, src, k=1.0):
    for bn, w in src.items():
        dst[bn] = dst.get(bn, 0) + np.asarray(w) * k
    return dst


def scale(W, k):
    return {bn: np.asarray(w) * k for bn, w in W.items()}


def spine_weights(P):
    z = P[:, 2]
    names = ["hips", "spine", "spine1", "spine2", "neck", "head"]
    knots = [S.J[k][2] for k in ("spine", "spine1", "spine2", "neck", "head")]
    blends = [0.05, 0.05, 0.05, 0.035, 0.02]
    steps = [smooth(k - b, k + b, z) for k, b in zip(knots, blends)]
    return _partition(names, steps, len(P))


def _sided(P, s):
    Q = np.array(P, float)
    Q[:, 0] *= s
    return Q


def _rename(W, s):
    return W if s > 0 else {L2R(k): v for k, v in W.items()}


def arm_weights(P, s, hand=True):
    """Shoulder -> upper arm -> forearm (-> hand) by projection on the arm chain; the shoulder end
    blends into the chest."""
    Q = _sided(P, s)
    hp = hand_points()
    J = [S.CLAV + np.array([0.04, 0, 0]), S.SH, S.ELB, S.WRI] + ([hp["knuck"]] if hand else [])
    bones = ["shoulder_L", "upperarm_L", "forearm_L"] + (["hand_L"] if hand else [])
    W, sp = chain(Q, J, bones, [0.045, 0.04, 0.03][:len(bones) - 1])
    k = 1 - smooth(-0.01, 0.07, sp)
    W = scale(W, 1)
    W["shoulder_L"] = W["shoulder_L"] * (1 - k)
    W["spine2"] = k
    return _rename(W, s)


def leg_weights(P, s, hip_blend=0.06):
    Q = _sided(P, s)
    J = [S.HIP, S.KNEE, S.ANKLE, S.BALL, S.TOE]
    W, sp = chain(Q, J, ["thigh_L", "shin_L", "foot_L", "toe_L"], [0.05, 0.03, 0.02])
    z = Q[:, 2]
    crease = S.HIP[2] - 0.02 + 0.02 * smooth(0.0, 0.08, Q[:, 1])
    k = smooth(crease - hip_blend * 0.4, crease + hip_blend, z)
    W = scale(W, 1)
    for bn in list(W):
        W[bn] = W[bn] * (1 - k)
    W["hips"] = k
    return _rename(W, s)


def finalize(W, n, maxinf=4):
    names = [k for k in W if np.any(np.asarray(W[k]) > 1e-4)]
    M = np.stack([np.clip(np.broadcast_to(np.asarray(W[k], dtype=float), (n,)), 0, None) for k in names], axis=1)
    if M.shape[1] > maxinf:
        idx = np.argsort(-M, axis=1)[:, maxinf:]
        np.put_along_axis(M, idx, 0.0, axis=1)
    M[M < 0.01] = 0.0
    tot = M.sum(axis=1, keepdims=True)
    M = np.where(tot > 1e-8, M / np.maximum(tot, 1e-8), 0)
    return {nm: M[:, i] for i, nm in enumerate(names) if M[:, i].max() > 0}


def store(ob, W):
    n = len(ob.data.vertices)
    WEIGHTS[ob.name] = finalize(W, n)


def apply_all(col, arm_ob):
    for ob in col.all_objects:
        if ob.type != "MESH":
            continue
        W = WEIGHTS[ob.name]
        for vg in list(ob.vertex_groups):
            ob.vertex_groups.remove(vg)
        for bn, w in W.items():
            vg = ob.vertex_groups.new(name=bn)
            idx = np.nonzero(w > 0)[0]
            for i in idx:
                vg.add([int(i)], float(w[i]), "REPLACE")
        mod = ob.modifiers.new("Armature", "ARMATURE")
        mod.object = arm_ob
        ob.parent = arm_ob
        ob.matrix_parent_inverse.identity()
        tot = np.zeros(len(ob.data.vertices))
        for w in W.values():
            tot += w
        if np.any(np.abs(tot - 1) > 1e-3):
            raise RuntimeError(f"{ob.name}: {int(np.sum(np.abs(tot - 1) > 1e-3))} vertices without weights")


def lift(col, arm_ob, dz):
    """Raise every mesh vertex (and shape key) and every bone but the root by dz (the geta)."""
    for ob in col.all_objects:
        if ob.type != "MESH":
            continue
        me = ob.data
        if me.shape_keys:
            for kb in me.shape_keys.key_blocks:
                a = np.zeros(len(kb.data) * 3)
                kb.data.foreach_get("co", a)
                a = a.reshape(-1, 3)
                a[:, 2] += dz
                kb.data.foreach_set("co", a.ravel())
        a = np.zeros(len(me.vertices) * 3)
        me.vertices.foreach_get("co", a)
        a = a.reshape(-1, 3)
        a[:, 2] += dz
        me.vertices.foreach_set("co", a.ravel())
        me.update()
    vl = bpy.context.view_layer
    vl.objects.active = arm_ob
    bpy.ops.object.mode_set(mode="EDIT")
    for b in arm_ob.data.edit_bones:
        if b.name == "root":
            continue
        b.head.z += dz
        b.tail.z += dz
    bpy.ops.object.mode_set(mode="OBJECT")
