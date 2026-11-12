"""Shared skeleton layout. Every variant gets its own armature with IDENTICAL bone names, hierarchy,
rest directions and rolls (only joint positions differ), so a rotation-only clip authored on one
plays correctly on all of them."""
import math

import numpy as np

from .geo import norm, smooth

ARM_DOWN = 74.0  # rest A-pose: upper arms 74 deg below horizontal

BONES = [  # name, parent
    ("root", None), ("hips", "root"), ("spine", "hips"), ("chest", "spine"), ("neck", "chest"),
    ("head", "neck"),
    ("shoulder_L", "chest"), ("upperarm_L", "shoulder_L"), ("forearm_L", "upperarm_L"), ("hand_L", "forearm_L"),
    ("shoulder_R", "chest"), ("upperarm_R", "shoulder_R"), ("forearm_R", "upperarm_R"), ("hand_R", "forearm_R"),
    ("sleeve_L1", "forearm_L"), ("sleeve_R1", "forearm_R"),
    ("thigh_L", "hips"), ("shin_L", "thigh_L"), ("foot_L", "shin_L"),
    ("thigh_R", "hips"), ("shin_R", "thigh_R"), ("foot_R", "shin_R"),
]
FINGERS = ["thumb", "index", "middle", "ring", "pinky"]
# Finger bones (added after the original 22, which keep their names, parents and rest pose): two per
# finger, children of the hand bone; the rest pose IS the relaxed curl (the clips do not key them).
for _s in ("L", "R"):
    for _f in FINGERS:
        BONES.append((f"finger_{_f}_1_{_s}", f"hand_{_s}"))
        BONES.append((f"finger_{_f}_2_{_s}", f"finger_{_f}_1_{_s}"))
PARENT = dict(BONES)

# Per-variant proportions (metres). hip = thigh joint height; ua/fa/hand = arm segment lengths;
# shw = shoulder joint half-width; hipw = thigh joint half-width; hunch = forward offset (-Y) of
# chest/neck/head joints (the elder's stoop).
VARIANTS = {
    "woman": dict(H=1.60, head=0.235, neck=0.040, hip=0.80, shw=0.148, hipw=0.078, ua=0.262, fa=0.222,
                  hand=0.150, hw=0.80, hd=0.86, hunch=(0, 0, 0)),
    "man": dict(H=1.74, head=0.245, neck=0.052, hip=0.875, shw=0.182, hipw=0.088, ua=0.292, fa=0.248,
                hand=0.170, hw=0.78, hd=0.86, hunch=(0, 0, 0)),
    "kid": dict(H=1.15, head=0.215, neck=0.026, hip=0.50, shw=0.110, hipw=0.058, ua=0.180, fa=0.158,
                hand=0.108, hw=0.88, hd=0.90, hunch=(0, 0, 0)),
    "keeper": dict(H=1.70, head=0.240, neck=0.050, hip=0.850, shw=0.180, hipw=0.088, ua=0.288, fa=0.244,
                   hand=0.168, hw=0.80, hd=0.86, hunch=(0, 0, 0)),
    "elder": dict(H=1.52, head=0.225, neck=0.040, hip=0.760, shw=0.138, hipw=0.076, ua=0.250, fa=0.212,
                  hand=0.142, hw=0.80, hd=0.86, hunch=(0.012, 0.045, 0.075)),
}
ORDER = ["woman", "man", "kid", "keeper", "elder"]


# Relaxed hand, in the hand frame (d along the hand bone, s forward = thumb side, n palm normal toward
# the body), lengths in units of the hand length hl / widths in k = hl / 0.15. The angles are the same
# for every variant, so the finger rest rotations match across variants like the rest of the rig.
FINGER_LAYOUT = {  # knuckle (along d in hl, across s in k), length (hl), splay deg, curl deg (seg 1, seg 2), radius k
    "index": dict(kd=0.475, ks=0.0245, L=0.46, splay=5.0, c1=22.0, c2=38.0, r=0.0086),
    "middle": dict(kd=0.485, ks=0.0080, L=0.51, splay=0.0, c1=28.0, c2=44.0, r=0.0090),
    "ring": dict(kd=0.475, ks=-0.0085, L=0.48, splay=-5.0, c1=34.0, c2=48.0, r=0.0084),
    "pinky": dict(kd=0.445, ks=-0.0240, L=0.38, splay=-11.0, c1=40.0, c2=52.0, r=0.0074),
}
SEG1 = 0.47     # proximal phalanx share of the finger length (bone 2 = middle + distal)


def hand_frame(J, side):
    sg = 1.0 if side == "L" else -1.0
    d = J[f"d0_{side}"]
    s = np.array([0, -1.0, 0])
    n = norm(np.cross(d, s)) * sg
    return d, s, n


def _rot(axis, deg, v):
    a = norm(axis)
    t = math.radians(deg)
    return v * math.cos(t) + np.cross(a, v) * math.sin(t) + a * (a @ v) * (1 - math.cos(t))


def finger_joints(J, side):
    """{finger: (base, mid, tip, radius)} at rest (relaxed curl, thumb opposed)."""
    d, s, n = hand_frame(J, side)
    wr = J[f"wr_{side}"]
    hl = J["P"]["hand"]
    k = hl / 0.15
    out = {}
    for f, L in FINGER_LAYOUT.items():
        base = wr + d * L["kd"] * hl + s * L["ks"] * k + n * 0.002 * k
        f0 = _rot(n, L["splay"], d)                    # splay in the palm plane (toward the thumb side +)
        side_ax = norm(np.cross(f0, n))
        d1 = _rot(side_ax, -L["c1"], f0)               # curl toward the palm
        d2 = _rot(side_ax, -(L["c1"] + L["c2"]), f0)
        if (d1 - f0) @ n < 0:                          # make sure the curl goes toward the palm
            d1 = _rot(side_ax, L["c1"], f0)
            d2 = _rot(side_ax, L["c1"] + L["c2"], f0)
        mid = base + d1 * L["L"] * hl * SEG1
        tip = mid + d2 * L["L"] * hl * (1 - SEG1)
        out[f] = (base, mid, tip, L["r"] * k)
    # thumb: from the thenar pad, forward and across toward the palm (opposed), slightly bent
    tb = wr + d * 0.255 * hl + s * 0.027 * k + n * 0.012 * k
    t1 = norm(d * 0.82 + s * 0.20 + n * 0.50)
    t2 = norm(d * 0.70 - s * 0.12 + n * 0.80)
    tm = tb + t1 * 0.205 * hl
    tt = tm + t2 * 0.185 * hl
    out["thumb"] = (tb, tm, tt, 0.0098 * k)
    return out


def skeleton(v):
    """Joint positions + bone (head, tail, parent) list for a variant (Blender coords)."""
    P = VARIANTS[v]
    H, hd, hip = P["H"], P["head"], P["hip"]
    lk = hip / 0.80                        # leg scale vs the reference woman
    hc, hn, hh = P["hunch"]
    J = {}
    J["P"] = P
    J["lk"] = lk
    J["ankle_z"] = 0.144 * hip
    J["sole"] = 0.045 * lk                 # sandal top (where the sole of the foot rests)
    J["heel"] = 0.075 * hip                # heel behind ankle
    J["toe"] = 0.21 * hip                  # toe tip ahead of ankle
    J["knee_z"] = J["ankle_z"] + (hip - J["ankle_z"]) * 0.5
    top = H
    neck_base = H - hd - P["neck"]
    J["neck_base"] = neck_base
    J["shoulder_z"] = neck_base - 0.018 * lk
    J["pelvis"] = np.array([0, 0, hip + 0.045 * lk])
    J["spine"] = np.array([0, 0, hip + 0.25 * (neck_base - hip)])
    J["chest"] = np.array([0, -hc, hip + 0.56 * (neck_base - hip)])
    J["neck"] = np.array([0, -hn, neck_base])
    J["headj"] = np.array([0, -hh + 0.004, H - hd * 0.86])
    J["top"] = np.array([0, -hh, top])
    J["chin_z"] = H - hd
    a = math.radians(ARM_DOWN)
    bones = {}
    bones["root"] = (np.zeros(3), np.array([0, 0, 0.12]))
    bones["hips"] = (J["pelvis"], J["pelvis"] + [0, 0, J["spine"][2] - J["pelvis"][2]])
    bones["spine"] = (J["spine"], J["spine"] + [0, 0, J["chest"][2] - J["spine"][2]])
    bones["chest"] = (J["chest"], J["chest"] + [0, 0, neck_base - J["chest"][2]])
    bones["neck"] = (J["neck"], J["neck"] + [0, 0, J["headj"][2] - neck_base])
    bones["head"] = (J["headj"], J["headj"] + [0, 0, top - J["headj"][2]])
    for s, sg in (("L", 1.0), ("R", -1.0)):
        sh = np.array([sg * 0.022, -hc - 0.6 * (hn - hc), J["shoulder_z"]])
        ua = np.array([sg * P["shw"], sh[1], J["shoulder_z"] - 0.012 * lk])
        d0 = np.array([sg * math.cos(a), 0, -math.sin(a)])
        el = ua + d0 * P["ua"]
        wr = el + d0 * P["fa"]
        tip = wr + d0 * P["hand"]
        bones[f"shoulder_{s}"] = (sh, sh + [sg * (P["shw"] - 0.022), 0, 0])
        bones[f"upperarm_{s}"] = (ua, el)
        bones[f"forearm_{s}"] = (el, wr)
        bones[f"hand_{s}"] = (wr, tip)
        sl = el + d0 * P["fa"] * 0.32
        bones[f"sleeve_{s}1"] = (sl, sl + [0, 0, -0.16 * lk])
        th = np.array([sg * P["hipw"], 0, hip])
        kn = np.array([sg * P["hipw"], 0, J["knee_z"]])
        an = np.array([sg * P["hipw"], 0, J["ankle_z"]])
        bones[f"thigh_{s}"] = (th, kn)
        bones[f"shin_{s}"] = (kn, an)
        bones[f"foot_{s}"] = (an, an + [0, -J["toe"] * 0.8, 0])
        J[f"d0_{s}"] = d0
        J[f"ua_{s}"], J[f"el_{s}"], J[f"wr_{s}"], J[f"tip_{s}"] = ua, el, wr, tip
        J[f"th_{s}"], J[f"kn_{s}"], J[f"an_{s}"] = th, kn, an
        J[f"sh_{s}"] = sh
        for f, (fb, fm, ft, fr) in finger_joints(J, s).items():
            bones[f"finger_{f}_1_{s}"] = (fb, fm)
            bones[f"finger_{f}_2_{s}"] = (fm, ft)
    J["bones"] = bones
    J["P"] = P
    return J


def build_armature(bpy, name, J, col):
    arm_data = bpy.data.armatures.new(name + "_skeleton")
    ob = bpy.data.objects.new(name, arm_data)
    col.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm_data.edit_bones
    for bname, parent in BONES:
        h, t = J["bones"][bname]
        b = eb.new(bname)
        b.head, b.tail = tuple(h), tuple(t)
        b.roll = 0.0
        b.use_deform = True
        if parent:
            b.parent = eb[parent]
            b.use_connect = False
    bpy.ops.object.mode_set(mode="OBJECT")
    for pb in ob.pose.bones:
        pb.rotation_mode = "QUATERNION"
    arm_data.display_type = "STICK"
    return ob


# ---------------------------------------------------------------- weight helpers

def chain(s, cuts, names, bw):
    """Weights along a 1-D chain: names[i] owns s in (cuts[i-1], cuts[i]); linear-smooth blend of
    half-width bw around each cut."""
    w = {}
    for i, nme in enumerate(names):
        lo = -1e9 if i == 0 else cuts[i - 1]
        hi = 1e9 if i == len(names) - 1 else cuts[i]
        a = 1.0 if i == 0 else float(smooth(lo - bw, lo + bw, s))
        b = 1.0 if i == len(names) - 1 else 1.0 - float(smooth(hi - bw, hi + bw, s))
        v = a * b
        if v > 1e-4:
            w[nme] = w.get(nme, 0) + v
    return w


def mix(*pairs):
    out = {}
    for k, wd in pairs:
        for n, v in wd.items():
            out[n] = out.get(n, 0) + k * v
    return out


def torso_w(J, p):
    """Spine weights by height (hips/spine/chest/neck/head)."""
    z = p[2]
    cuts = [J["spine"][2] + 0.01, J["chest"][2] + 0.01, J["neck_base"] + 0.005, J["headj"][2] + 0.01]
    return chain(z, cuts, ["hips", "spine", "chest", "neck", "head"], 0.05 * J["lk"])


def arm_s(J, side, p):
    return float((np.asarray(p) - J[f"ua_{side}"]) @ J[f"d0_{side}"])


def arm_w(J, side, p, bw=0.035):
    P = J["P"]
    s = arm_s(J, side, p)
    w = chain(s, [-0.01, P["ua"], P["ua"] + P["fa"]],
              [f"shoulder_{side}", f"upperarm_{side}", f"forearm_{side}", f"hand_{side}"], bw * J["lk"])
    if "shoulder_" + side in w and s < 0.0:
        # inner shoulder blends into the chest
        k = float(smooth(0.0, -0.06, s))
        w = mix((1 - k, w), (k, {"chest": 1.0}))
    return w


def leg_w(J, side, p, bw=0.045):
    z = p[2]
    s = J[f"th_{side}"][2] - z
    hip = J["P"]["hip"]
    w = chain(s, [0.0, hip - J["knee_z"], hip - J["ankle_z"] - 0.01],
              ["hips", f"thigh_{side}", f"shin_{side}", f"foot_{side}"], bw * J["lk"])
    return w


def side_of(x, width):
    """0 (right, -X) .. 1 (left, +X)."""
    return float(smooth(-width, width, x))
