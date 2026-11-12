"""Her clips at 30 fps, in place (the root never moves).

Retargeted from Mixamo motion (lib/mocap.py, tools/blender/mixamo/retarget.py):
  idle, walk, run, talk, look (loops); wave, bow, eat, cheer, point (one-shots);
  add_ref / add_nod / add_shake / add_look_l / add_look_r (additive layers).
Hand-made here, generated procedurally (unchanged):
  crouch  3.0 s loop   squat on her heels, right hand stroking forward-low (cat / goldfish tub)
  reach   3.0 s loop   at a stall counter, right hand forward at ~1.0 m choosing, left hand holding
                       the right sleeve back
  throw   1.2 s once   soft underhand ring toss with the right hand, release at 0.62 s
  lookup  4.0 s loop   head and chest tilted up at fireworks, hands clasped at the chest, slow sway

This module also has the shared machinery: forward kinematics with gravity-hung helper chains
(sleeves, hair, kanzashi dangles, obi tails), two-bone IK for the hand-made clips, the skirt
panels that follow the legs, the baker, and the gait checks.
"""
import math
import os

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector

from . import shape as S
from .common import norm, smooth

FPS = 30
DEG = math.pi / 180
X, Y, Z = np.eye(3)
FWD = np.array([0, -1.0, 0])
TOE_EDGE_Y = -0.131      # front edge of the front tooth (geta) - toe-off pivot
HEEL_EDGE_Y = 0.047      # back edge of the rear tooth - heel-strike pivot


def rot(axis, deg):
    a = np.asarray(axis, float)
    a = a / np.linalg.norm(a)
    t = deg * DEG
    c, s = math.cos(t), math.sin(t)
    x, y, z = a
    return np.array([[c + x * x * (1 - c), x * y * (1 - c) - z * s, x * z * (1 - c) + y * s],
                     [y * x * (1 - c) + z * s, c + y * y * (1 - c), y * z * (1 - c) - x * s],
                     [z * x * (1 - c) - y * s, z * y * (1 - c) + x * s, c + z * z * (1 - c)]])


def frame_from(yaxis, zhint):
    yv = norm(np.asarray(yaxis, float))
    zv = np.asarray(zhint, float)
    zv = norm(zv - yv * (zv @ yv))
    xv = np.cross(yv, zv)
    return np.stack([xv, yv, zv], axis=1)


def _slerp(Ra, Rb, k):
    qa = Matrix(Ra.tolist()).to_quaternion()
    qb = Matrix(Rb.tolist()).to_quaternion()
    if qa.dot(qb) < 0:
        qb.negate()
    return np.array(qa.slerp(qb, float(k)).to_matrix())


HANG = {  # bone prefix: (gravity share, what turns the hanging direction)
    "sleeve_L": (0.88, "forearm_L"), "sleeve_R": (0.88, "forearm_R"),
    "hairSideL": (0.45, "head"), "hairSideR": (0.45, "head"), "hairBack": (0.6, "head"),
    "kanzashi": (0.95, "head"), "obiTailL": (0.7, "hips"), "obiTailR": (0.7, "hips"),
}


def _hang_cfg(n):
    for p, v in HANG.items():
        if n.startswith(p) and n[len(p):].isdigit():
            return v
    return None


class FK:
    """Forward kinematics on the armature's rest matrices, with gravity-hanging helper chains."""

    def __init__(self, arm):
        bones = arm.data.bones
        self.rest = {b.name: np.array(b.matrix_local, dtype=float) for b in bones}
        self.parent = {b.name: (b.parent.name if b.parent else None) for b in bones}
        order, seen = [], set()

        def visit(n):
            if n in seen:
                return
            if self.parent[n]:
                visit(self.parent[n])
            seen.add(n)
            order.append(n)

        for b in bones:
            visit(b.name)
        self.order = order
        self.inv = {n: np.linalg.inv(m) for n, m in self.rest.items()}
        self.gravity = 1.0

    def _yaw_of(self, pose, ref):
        Pchg = pose[ref][:3, :3] @ self.rest[ref][:3, :3].T
        if ref.startswith("forearm"):
            v0 = self.rest[ref][:3, 1]
            v1 = pose[ref][:3, 1]
        else:
            v0 = FWD
            v1 = Pchg @ FWD
        h0, h1 = v0[:2], v1[:2]
        n0, n1 = np.linalg.norm(h0), np.linalg.norm(h1)
        if n0 < 1e-6 or n1 < 1e-6:
            return 0.0
        a = math.atan2(h0[0] * h1[1] - h0[1] * h1[0], h0 @ h1 / 1.0)
        a = math.atan2(math.sin(a), math.cos(a))
        w = min(1.0, n1 / 0.35)
        return a * w / DEG

    def solve(self, delta=None, absr=None, local=None, loc=None, grav=None):
        delta, absr, local, loc = delta or {}, absr or {}, local or {}, loc or {}
        grav = grav or {}
        pose, basis = {}, {}
        for n in self.order:
            Rr = self.rest[n]
            p = self.parent[n]
            M0 = pose[p] @ self.inv[p] @ Rr if p else Rr.copy()
            R0 = M0[:3, :3]
            cfg = _hang_cfg(n)
            if n in absr:
                Rp = absr[n]
            elif n in delta:
                Pchg = pose[p][:3, :3] @ self.rest[p][:3, :3].T if p else np.eye(3)
                Rp = Pchg @ delta[n] @ Rr[:3, :3]
            elif cfg is not None:
                k, ref = cfg
                k = k * grav.get(n.rstrip("0123456789"), self.gravity)
                Rh = rot(Z, self._yaw_of(pose, ref)) @ Rr[:3, :3]
                Rp = _slerp(R0, Rh, k)
            else:
                Rp = R0
            if n in local:
                Rp = Rp @ local[n]
            t = R0.T @ np.asarray(loc[n], float) if n in loc else np.zeros(3)
            M = np.eye(4)
            M[:3, :3] = Rp
            M[:3, 3] = M0[:3, 3] + R0 @ t
            pose[n] = M
            basis[n] = (t, R0.T @ Rp)
        return pose, basis

    def head_if(self, pose, child):
        p = self.parent[child]
        return (pose[p] @ self.inv[p] @ self.rest[child])[:3, 3]

    def rest_head(self, n):
        return self.rest[n][:3, 3]

    def rest_axes(self, n):
        return self.rest[n][:3, :3]


def two_bone(H, A, L1, L2, pole, reach=0.996):
    d = A - H
    dist = np.linalg.norm(d)
    u = d / max(dist, 1e-9)
    dist = np.clip(dist, abs(L1 - L2) + 1e-4, (L1 + L2) * reach)
    ca = np.clip((L1 * L1 + dist * dist - L2 * L2) / (2 * L1 * dist), -1, 1)
    sa = math.sqrt(1 - ca * ca)
    v = norm(pole - u * (pole @ u))
    K = H + L1 * (ca * u + sa * v)
    return K, H + u * dist


class Body:
    def __init__(self, fk):
        self.fk = fk
        R = fk.rest_head
        self.L, self.A = {}, {}
        for sf in ("L", "R"):
            self.L[sf] = (np.linalg.norm(R(f"shin_{sf}") - R(f"thigh_{sf}")), np.linalg.norm(R(f"foot_{sf}") - R(f"shin_{sf}")))
            self.A[sf] = (np.linalg.norm(R(f"forearm_{sf}") - R(f"upperarm_{sf}")), np.linalg.norm(R(f"hand_{sf}") - R(f"forearm_{sf}")))

    def foot_points(self, sf):
        """Rest ankle, rear-tooth back edge and front-tooth front edge (on the ground, z = 0)."""
        A0 = self.fk.rest_head(f"foot_{sf}")
        x = A0[0] + (0.002 if sf == "L" else -0.002)
        return A0, np.array([x, HEEL_EDGE_Y, 0.0]), np.array([x, TOE_EDGE_Y, 0.0])

    def foot_pose(self, sf, kind, pivot_ground, pitch_up, yaw=0.0):
        A0, heel, toe = self.foot_points(sf)
        Rf = rot(Z, yaw) @ rot(X, -pitch_up)
        piv0 = heel if kind == "heel" else toe
        ankle = pivot_ground + Rf @ (A0 - piv0)
        return ankle, Rf

    def leg(self, pose, sf, ankle, Rfoot, pole=None):
        fk = self.fk
        H = fk.head_if(pose, f"thigh_{sf}")
        L1, L2 = self.L[sf]
        pl = pole if pole is not None else norm(FWD + np.array([0.06 if sf == "L" else -0.06, 0, 0]))
        K, A2 = two_bone(H, ankle, L1, L2, pl)
        return {
            f"thigh_{sf}": frame_from(K - H, pl),
            f"shin_{sf}": frame_from(A2 - K, pl),
            f"foot_{sf}": Rfoot @ fk.rest_axes(f"foot_{sf}"),
            f"toe_{sf}": Rfoot @ fk.rest_axes(f"toe_{sf}"),
        }

    def arm(self, pose, sf, wrist, pole, hand_dir, palm_out, reach=0.995):
        """IK: upper arm + forearm reach `wrist`, elbow toward `pole`; hand along hand_dir with the
        palm facing palm_out."""
        fk = self.fk
        H = fk.head_if(pose, f"upperarm_{sf}")
        L1, L2 = self.A[sf]
        E, W = two_bone(H, wrist, L1, L2, norm(pole), reach)
        up, fo = norm(E - H), norm(W - E)
        zu = fo - up * (fo @ up)
        if np.linalg.norm(zu) < 1e-3:
            zu = np.cross(up, np.cross(norm(pole), up))
        zf = -up - fo * (-up @ fo)
        if np.linalg.norm(zf) < 1e-3:
            zf = zu
        return {
            f"upperarm_{sf}": frame_from(up, zu),
            f"forearm_{sf}": frame_from(fo, zf),
            f"hand_{sf}": frame_from(norm(hand_dir), -norm(palm_out)),
        }


def hand_local(sf, curl=25.0, thumb=10.0):
    """Extra finger curl on top of the relaxed rest curl (deg at the fingertip, as the old single
    `fingers` bone had it), spread over the two bones of each finger."""
    out = {}
    for f in ("index", "middle", "ring", "pinky"):
        out[f"finger_{f}_1_{sf}"] = rot(X, -curl * 0.6)
        out[f"finger_{f}_2_{sf}"] = rot(X, -curl * 0.7)
    out[f"finger_thumb_1_{sf}"] = rot(X, -thumb) @ rot(Z, thumb * 0.5 * (1 if sf == "L" else -1))
    out[f"finger_thumb_2_{sf}"] = rot(X, -thumb * 0.6)
    return out


SWAY = ("sleeve_L", "sleeve_R", "hairSideL", "hairSideR", "hairBack", "hairBun", "kanzashi", "obiTailL", "obiTailR",
        "skirtF", "skirtB")


def secondary(fk, t, period, amp, trail=0.0, side=0.0, phase=0.0, scale=None):
    """Lagged sway on every helper chain: pitch about the bone X (+ swings the tip forward) and a
    smaller sideways roll. All terms are periodic in `period`."""
    loc = {}
    scale = scale or {}
    for n in fk.order:
        base = n.rstrip("0123456789")
        if base not in SWAY:
            continue
        k = int(n[len(base):] or 1)
        sc = scale.get(base, 1.0)
        if sc == 0:
            continue
        lag = 0.10 * k + (0.08 if base.startswith("kanzashi") else 0.0)
        w = 2 * math.pi * (t / period - lag) + phase
        a = amp * sc * (0.7 + 0.3 * k)
        pitch = trail * sc * (0.6 + 0.4 * k) + a * math.sin(w)
        roll = side * sc + 0.45 * a * math.sin(w + 1.3 + 0.7 * k)
        if base in ("skirtF", "skirtB"):
            pitch, roll = pitch * 0.5, roll * 0.3
        loc[n] = rot(X, pitch) @ rot(Z, roll)
    return loc


def bake(arm, fk, name, frames, loop=True):
    act = bpy.data.actions.new(name)
    act.use_fake_user = True
    slot = act.slots.new(id_type="OBJECT", name=arm.name)
    layer = act.layers.new("Layer")
    strip = layer.strips.new(type="KEYFRAME")
    cb = strip.channelbag(slot, ensure=True)
    n = len(frames)
    rots = {b: np.zeros((n, 4)) for b in fk.order}
    locs = {b: np.zeros((n, 3)) for b in fk.order}
    for i, fr in enumerate(frames):
        pose, basis = fk.solve(*fr)
        for b in fk.order:
            t, Rb = basis[b]
            q = Matrix(Rb.tolist()).to_quaternion()
            if i > 0 and np.dot(rots[b][i - 1], [q.w, q.x, q.y, q.z]) < 0:
                q.negate()
            rots[b][i] = [q.w, q.x, q.y, q.z]
            locs[b][i] = t
    fr_idx = np.arange(n, dtype=float) + 1
    for b in fk.order:
        grp = cb.groups.new(b)
        for k in range(4):
            fc = cb.fcurves.new(f'pose.bones["{b}"].rotation_quaternion', index=k)
            fc.group = grp
            fc.keyframe_points.add(n)
            fc.keyframe_points.foreach_set("co", np.stack([fr_idx, rots[b][:, k]], axis=1).ravel())
            fc.keyframe_points.foreach_set("interpolation", [1] * n)
            fc.update()
        if np.abs(locs[b]).max() > 1e-7:
            for k in range(3):
                fc = cb.fcurves.new(f'pose.bones["{b}"].location', index=k)
                fc.group = grp
                fc.keyframe_points.add(n)
                fc.keyframe_points.foreach_set("co", np.stack([fr_idx, locs[b][:, k]], axis=1).ravel())
                fc.keyframe_points.foreach_set("interpolation", [1] * n)
                fc.update()
    act.use_frame_range = True
    act.frame_start, act.frame_end = 1, n
    act.use_cyclic = loop
    return act, slot


# ---------------------------------------------------------------- shared pieces


def planted_legs(fk, body, pose, absr, feet=None):
    """Both geta flat on the ground at (rest + offset) positions; feet: sf -> (dx, dy, yaw, pole)."""
    feet = feet or {}
    for sf in ("L", "R"):
        dx, dy, yaw, pole = feet.get(sf, (0.0, 0.0, 0.0, None))
        A0, heel, toe = body.foot_points(sf)
        ankle, Rf = body.foot_pose(sf, "heel", heel + np.array([dx, dy, 0]), 0.0, yaw)
        absr.update(body.leg(pose, sf, ankle, Rf, pole))


def clasp_arms(fk, body, pose, absr, local, center, spread=0.035, palms_in=True, lift=0.0):
    """Hands lightly together in front (right over left): wrists either side of `center`."""
    for sf, s in (("L", 1), ("R", -1)):
        w = center + np.array([s * spread, 0.0 if sf == "L" else -0.012, -0.004 * s + lift])
        hd = norm(np.array([-s * 0.75, -0.25, -0.6]))
        po = norm(np.array([-s * 0.2, 0.75, 0.25])) if palms_in else norm(np.array([-s, 0.2, 0.0]))
        pole = norm(np.array([s * 0.8, 0.45, -0.35]))
        absr.update(body.arm(pose, sf, w, pole, hd, po))
        local.update(hand_local(sf, 22.0, 12.0))


def idle_frame(fk, body, t, T=4.0):
    br = math.sin(2 * math.pi * t / T * 2)            # two breaths per loop
    sw = math.sin(2 * math.pi * t / T)                # one slow weight shift
    delta, absr, local, loc = {}, {}, {}, {}
    loc["hips"] = np.array([0.012 * sw, 0.0, -0.004 + 0.0015 * br - 0.002 * abs(sw)])
    delta["hips"] = rot(Y, 1.8 * sw) @ rot(Z, 1.2 * sw)
    delta["spine"] = rot(Y, -0.8 * sw)
    delta["spine1"] = rot(X, 0.8 * br) @ rot(Y, -0.6 * sw)
    delta["spine2"] = rot(X, -1.2 * br) @ rot(Y, -0.4 * sw)
    delta["neck"] = rot(X, 2.0)
    delta["head"] = rot(X, 3.0 - 0.6 * br) @ rot(Y, 2.5 + 1.2 * sw) @ rot(Z, 1.5 * math.sin(2 * math.pi * t / T + 1.0))
    for sf, s in (("L", 1), ("R", -1)):
        delta[f"shoulder_{sf}"] = rot(Y, s * (1.2 * br - 1.0))
    pose, _ = fk.solve(delta, absr, local, loc)
    planted_legs(fk, body, pose, absr, {"L": (0.004, -0.010, 4.0, None), "R": (-0.004, 0.012, -6.0, None)})
    pose, _ = fk.solve(delta, absr, local, loc)
    clasp_arms(fk, body, pose, absr, local, np.array([0.0, -0.150, 0.955 + 0.003 * br]))
    local.update(secondary(fk, t, T / 2, 1.2, 0.0))
    return delta, absr, local, loc, None


def crouch_frame(fk, body, t, T=3.0):
    """Squatting on her heels, knees together, right hand stroking forward-low."""
    br = math.sin(2 * math.pi * t / T * 2)
    st = math.sin(2 * math.pi * t / T * 2)              # two strokes per loop
    delta, absr, local, loc = {}, {}, {}, {}
    rest_h = fk.rest_head("hips")
    loc["hips"] = np.array([0.0, 0.10, 0.40 - rest_h[2] + 0.004 * br])
    delta["hips"] = rot(X, 28.0)
    delta["spine"] = rot(X, 8.0)
    delta["spine1"] = rot(X, 6.0 + 0.6 * br) @ rot(Z, -3.0)
    delta["spine2"] = rot(X, 4.0) @ rot(Z, -4.0)
    delta["neck"] = rot(X, 8.0)
    delta["head"] = rot(X, 14.0 + 2.0 * st) @ rot(Z, -6.0) @ rot(Y, -4.0)
    delta["shoulder_R"] = rot(X, 6.0)
    pose, _ = fk.solve(delta, absr, local, loc)
    for sf, s in (("L", 1), ("R", -1)):
        A0, heel, toe = body.foot_points(sf)
        ankle, Rf = body.foot_pose(sf, "toe", toe + np.array([-s * 0.004, 0.02, 0.0]), -12.0, -s * 4.0)
        pole = norm(np.array([s * 0.05, -1.0, 0.45]))
        absr.update(body.leg(pose, sf, ankle, Rf, pole))
    pose, _ = fk.solve(delta, absr, local, loc)
    # Right hand: forward and low, palm down, stroking.
    wr = np.array([-0.06 - 0.008 * st, -0.40 - 0.055 * st, 0.17 + 0.012 * (1 - st * st)])
    absr.update(body.arm(pose, "R", wr, np.array([-0.6, 0.5, 0.4]), np.array([0.1, -1.0, -0.25]), np.array([0, 0.1, -1.0])))
    local.update(hand_local("R", 18.0 + 6.0 * st, 8.0))
    # Left hand holds the right sleeve back at the forearm (so it does not trail on the ground).
    pose, _ = fk.solve(delta, absr, local, loc)
    fa = pose["forearm_R"]
    tgt = fa[:3, 3] + fa[:3, 1] * 0.06 + np.array([0.02, 0.03, 0.035])
    absr.update(body.arm(pose, "L", tgt, np.array([0.7, 0.3, -0.6]), norm(np.array([-0.8, -0.3, -0.3])),
                         norm(np.array([-0.2, 0.2, -1.0]))))
    local.update(hand_local("L", 50.0, 25.0))
    local.update(secondary(fk, t, T / 2, 1.0, 0.0))
    local["sleeve_R1"] = rot(X, 50.0) @ local.get("sleeve_R1", np.eye(3))
    local["sleeve_R2"] = rot(X, 30.0) @ local.get("sleeve_R2", np.eye(3))
    return delta, absr, local, loc, {"sleeve_R": 0.15, "sleeve_L": 0.45}


def reach_frame(fk, body, t, T=3.0):
    """At a stall counter: right hand forward at ~1.0 m choosing; left hand holds the right sleeve."""
    br = math.sin(2 * math.pi * t / T * 2)
    a1 = math.sin(2 * math.pi * t / T)
    a2 = math.sin(2 * math.pi * t / T * 2 + 0.8)
    delta, absr, local, loc = {}, {}, {}, {}
    loc["hips"] = np.array([0.006, -0.012, -0.006])
    delta["hips"] = rot(X, 3.0) @ rot(Z, -4.0)
    delta["spine"] = rot(X, 3.0)
    delta["spine1"] = rot(X, 4.0 + 0.6 * br) @ rot(Z, -3.0)
    delta["spine2"] = rot(X, 2.0) @ rot(Z, -3.0) @ rot(Y, 1.5)
    delta["neck"] = rot(X, 4.0)
    delta["head"] = rot(X, 10.0) @ rot(Z, -4.0 - 4.0 * a1) @ rot(Y, 3.0)
    delta["shoulder_R"] = rot(X, 6.0) @ rot(Z, -4.0)
    pose, _ = fk.solve(delta, absr, local, loc)
    planted_legs(fk, body, pose, absr, {"L": (0.004, 0.02, 4.0, None), "R": (-0.006, -0.03, -5.0, None)})
    pose, _ = fk.solve(delta, absr, local, loc)
    wr = np.array([-0.11 + 0.045 * a1, -0.40 + 0.015 * a2, 1.00 + 0.012 * a2])
    hd = norm(np.array([0.15 + 0.15 * a1, -1.0, -0.15]))
    po = norm(np.array([0.25 * a1, -0.1, -1.0]))
    absr.update(body.arm(pose, "R", wr, np.array([-0.8, 0.3, -0.6]), hd, po))
    local.update(hand_local("R", 16.0 + 14.0 * (0.5 + 0.5 * a2), 8.0))
    pose, _ = fk.solve(delta, absr, local, loc)
    # Left hand on the right forearm (holding the sleeve back).
    fa = pose["forearm_R"]
    tgt = fa[:3, 3] + fa[:3, 1] * 0.07 + np.array([0.0, 0.035, -0.04])
    absr.update(body.arm(pose, "L", tgt, np.array([0.6, 0.4, -0.7]), norm(np.array([-0.8, -0.4, -0.2])),
                         norm(np.array([-0.3, 0.2, -1.0]))))
    local.update(hand_local("L", 45.0, 25.0))
    local.update(secondary(fk, t, T / 2, 1.0, 0.0))
    return delta, absr, local, loc, {"sleeve_R": 0.75}


THROW_RELEASE = 0.62


def _keys(t, table):
    """Smooth (Catmull-Rom) interpolation of row vectors keyed in time."""
    from .common import catmull
    return catmull(table, [t])[0]


def throw_frame(fk, body, t, idle0):
    """Soft underhand ring toss. Starts and ends on idle's first pose."""
    delta, absr, local, loc, _ = idle0
    delta, absr, local, loc = dict(delta), {}, dict(local), dict(loc)
    w_in = smooth(0.0, 0.18, t) * (1 - smooth(0.95, 1.2, t))
    # body: wind (twist right, crouch a little), then step through and lean into the toss.
    K = [[0.0, 0, 0, 0], [0.18, 0, 0, 0], [0.42, -10.0, 0.020, -4.0], [0.62, 6.0, 0.012, 7.0], [0.82, 4.0, 0.0, 4.0],
         [1.2, 0, 0, 0]]
    tw, dip, lean = _keys(t, K)
    delta["spine1"] = delta["spine1"] @ rot(Z, tw * 0.5) @ rot(X, lean * 0.5)
    delta["spine2"] = delta["spine2"] @ rot(Z, tw * 0.5) @ rot(X, lean * 0.3)
    delta["head"] = delta["head"] @ rot(Z, -tw * 0.6) @ rot(X, -lean * 0.4 + 3.0 * w_in)
    loc["hips"] = loc["hips"] + np.array([0, 0, -dip])
    pose, _ = fk.solve(delta, {}, local, loc)
    planted_legs(fk, body, pose, absr, {"L": (0.004, -0.010, 4.0, None), "R": (-0.004, 0.012, -6.0, None)})
    pose, _ = fk.solve(delta, absr, local, loc)
    clasp_arms(fk, body, pose, absr, local, np.array([0.0, -0.150, 0.955]))
    if 0.0 < t < 1.2:
        H = fk.head_if(pose, "upperarm_R")
        # Right wrist path (relative to the shoulder), smoothly keyed.
        WK = [[0.00, -0.035 - H[0], -0.162 - H[1], 0.959 - H[2]],
              [0.18, -0.06, -0.14, -0.36],
              [0.42, -0.07, 0.13, -0.47],
              [0.56, -0.03, -0.12, -0.46],
              [0.62, -0.01, -0.30, -0.34],
              [0.80, 0.01, -0.40, -0.16],
              [0.98, -0.02, -0.25, -0.33],
              [1.20, -0.035 - H[0], -0.162 - H[1], 0.959 - H[2]]]
        # Keep the end keys equal to the clasp target (computed from the idle pose's shoulder).
        rel = _keys(t, WK)
        clasp = absr["hand_R"].copy()
        k = smooth(0.0, 0.16, t) * (1 - smooth(1.0, 1.2, t))
        wr = H + rel
        hd = norm(np.array([0.05, -0.35 - 0.6 * smooth(0.45, 0.62, t), -1.0 + 0.8 * smooth(0.5, 0.75, t)]))
        po = norm(np.array([0.3, -0.9 * smooth(0.4, 0.6, t) + 0.3, 0.4 * smooth(0.5, 0.7, t)]))
        arm = body.arm(pose, "R", wr, np.array([-0.7, 0.6, -0.3]), hd, po)
        clasp_r = {kk: absr[kk] for kk in ("upperarm_R", "forearm_R", "hand_R")}
        for kk in arm:
            absr[kk] = _slerp(clasp_r[kk], arm[kk], k)
        curl = 22.0 * (1 - k) + k * (40.0 * (1 - smooth(0.58, 0.66, t)) + 8.0 * smooth(0.58, 0.66, t))
        local.update(hand_local("R", curl, 14.0))
        # Left hand drops a little to her side for balance.
        wl = H * np.array([-1, 1, 1]) + np.array([0.08, -0.08, -0.38])
        arml = body.arm(pose, "L", wl, np.array([0.6, 0.6, -0.3]), np.array([-0.2, -0.3, -1.0]), np.array([-1.0, 0.2, 0]))
        cl = {kk: absr[kk] for kk in ("upperarm_L", "forearm_L", "hand_L")}
        for kk in arml:
            absr[kk] = _slerp(cl[kk], arml[kk], 0.7 * k)
    local.update(secondary(fk, t, 0.6, 3.0 * smooth(0.3, 0.6, t) * (1 - smooth(0.9, 1.2, t)) + 1.0, 0.0))
    return delta, absr, local, loc, None


def lookup_frame(fk, body, t, T=4.0):
    br = math.sin(2 * math.pi * t / T * 2)
    sw = math.sin(2 * math.pi * t / T)
    delta, absr, local, loc = {}, {}, {}, {}
    loc["hips"] = np.array([0.010 * sw, 0.010, -0.004 + 0.0015 * br])
    delta["hips"] = rot(X, -3.0) @ rot(Y, 1.5 * sw) @ rot(Z, 2.0 * sw)
    delta["spine"] = rot(X, -3.0)
    delta["spine1"] = rot(X, -5.0 + 0.8 * br)
    delta["spine2"] = rot(X, -7.0 - 1.0 * br) @ rot(Z, -1.0 * sw)
    delta["neck"] = rot(X, -12.0)
    delta["head"] = rot(X, -18.0 - 1.5 * br) @ rot(Y, -2.5 * sw) @ rot(Z, 3.0 * math.sin(2 * math.pi * t / T + 0.6))
    pose, _ = fk.solve(delta, absr, local, loc)
    planted_legs(fk, body, pose, absr, {"L": (0.006, -0.01, 5.0, None), "R": (-0.006, 0.01, -5.0, None)})
    pose, _ = fk.solve(delta, absr, local, loc)
    ch = pose["spine2"][:3, 3]
    fwd = pose["spine2"][:3, :3] @ fk.rest_axes("spine2").T @ FWD
    c = ch + fwd * 0.155 + np.array([0, 0, 0.015])
    for sf, s in (("L", 1), ("R", -1)):
        w = c + np.array([s * 0.028, 0.0, -0.035])
        hd = norm(np.array([-s * 0.55, -0.15, 0.8]))
        po = norm(np.array([-s * 0.85, 0.3, 0.0]))
        absr.update(body.arm(pose, sf, w, np.array([s * 0.7, 0.4, -0.6]), hd, po))
        local.update(hand_local(sf, 55.0, 25.0))
    local.update(secondary(fk, t, T / 2, 1.0, 0.0))
    return delta, absr, local, loc, None


def skirt_follow(fk, fr, mode):
    """Pose skirtF1 / skirtB1 as a rigid blend of the two shins' motion: in gaits the front panel
    follows the forward leg and the back panel the rear leg (no 'trouser' crease between the legs);
    otherwise both follow the average of the legs."""
    delta, absr, local, loc, grav = fr
    absr, loc = dict(absr), dict(loc)
    pose, _ = fk.solve(delta, absr, {k: v for k, v in local.items() if not k.startswith("skirt")}, loc, grav)
    M = {sf: pose[f"shin_{sf}"] @ fk.inv[f"shin_{sf}"] for sf in ("L", "R")}
    for bone, ysgn in (("skirtF1", -1.0), ("skirtB1", 1.0)):
        rest = fk.rest[bone]
        tail = rest[:3, 3] + rest[:3, 1] * 0.55
        mapped = {sf: (M[sf] @ np.r_[tail, 1.0])[:3] for sf in ("L", "R")}
        if mode == "gait":
            d = (mapped["L"][1] - mapped["R"][1]) * ysgn       # > 0: the left leg is further out
            wl = 1.0 / (1.0 + math.exp(-d / 0.02))
            wl = 0.05 + 0.9 * wl
        else:
            wl = 0.5
        RL, RR = M["L"][:3, :3], M["R"][:3, :3]
        Rb = _slerp(RR, RL, wl)
        p = mapped["L"] * wl + mapped["R"] * (1 - wl)
        D = np.eye(4)
        D[:3, :3] = Rb
        D[:3, 3] = p - Rb @ tail
        if mode == "hang" and bone == "skirtF1":
            # Crouching: the front panel drapes straight down from the knees like a curtain.
            K = 0.5 * (pose["shin_L"][:3, 3] + pose["shin_R"][:3, 3]) + np.array([0, -0.05, 0])
            P = D[:3, :3] @ tail + D[:3, 3]
            r = np.linalg.norm(P - K)
            Pt = np.array([P[0], K[1] - 0.03, max(0.04, K[2] - math.sqrt(max(r * r - 0.03 ** 2, 0.0)))])
            a, b = norm(P - K), norm(Pt - K)
            ax = np.cross(a, b)
            if np.linalg.norm(ax) > 1e-6:
                ang = math.degrees(math.atan2(np.linalg.norm(ax), a @ b))
                Rk = rot(ax, ang)
                T = np.eye(4)
                T[:3, :3] = Rk
                T[:3, 3] = K - Rk @ K
                D = T @ D
        target = D @ rest
        absr[bone] = target[:3, :3]
        loc[bone] = target[:3, 3] - fk.head_if(pose, bone)
    return delta, absr, local, loc, grav

# ---------------------------------------------------------------- build

LEG_BONES = tuple(f"{b}_{s}" for s in "LR" for b in ("thigh", "shin", "foot", "toe"))


def rebase(fk, body, fr, ref, w):
    """Blend a frame toward a reference frame (w = 1: the frame itself, 0: the reference): every
    bone's world orientation and the hips offset are blended, then the legs are re-planted on the
    standing stance and the skirt panels re-fitted, so the feet do not move."""
    if w >= 1.0:
        return skirt_follow(fk, fr, "avg")
    pa, _ = fk.solve(*fr)
    pb, _ = fk.solve(*ref)
    absr = {b: _slerp(pb[b][:3, :3], pa[b][:3, :3], w) for b in fk.order
            if b not in LEG_BONES and not b.startswith("skirt") and b != "root"}
    loc = {"hips": np.asarray(ref[3]["hips"]) * (1 - w) + np.asarray(fr[3]["hips"]) * w}
    pose, _ = fk.solve({}, absr, {}, loc)
    planted_legs(fk, body, pose, absr, {"L": (0.004, -0.010, 4.0, None), "R": (-0.004, 0.012, -6.0, None)})
    return skirt_follow(fk, ({}, absr, {}, loc, None), "avg")


CLIPS = {}
INFO = {}        # clip metadata of the last build (durations, speeds, frames)


def build(arm):
    """Hand-made task clips (crouch, reach, throw, lookup: authored here, unchanged) plus the
    Mixamo-retargeted clips and additive layers (lib/mocap.py). Returns (clips, clipSpeed)."""
    from . import mocap
    fk = FK(arm)
    body = Body(fk)
    clips = {}

    def loop_frames(fn, dur):
        n = int(round(dur * FPS))
        return [skirt_follow(fk, fn(i / FPS), "avg") for i in range(n + 1)]

    once_frames = loop_frames
    acts = {}
    speed = mocap.build(arm, fk, acts, clips)
    n = int(round(3.0 * FPS))
    acts["crouch"] = bake(arm, fk, "crouch", [skirt_follow(fk, crouch_frame(fk, body, i / FPS), "hang") for i in range(n + 1)])
    clips["crouch"] = {"duration": 3.0, "loop": True, "events": {"strokeForward": [0.375, 1.875]}}
    acts["reach"] = bake(arm, fk, "reach", loop_frames(lambda t: reach_frame(fk, body, t), 3.0))
    clips["reach"] = {"duration": 3.0, "loop": True}
    # The throw is authored on the hand-made standing pose (hands clasped in front); its first
    # 0.25 s and last 0.25 s are eased from / to the idle clip's first pose (arms at her sides),
    # so it starts and ends where the idle is. Between 0.25 s and 0.95 s it is exactly as authored.
    idle0 = idle_frame(fk, body, 0.0)
    ref = mocap.IDLE0[0]

    def throw_rebased(t):
        w = float(smooth(0.0, 0.25, t) * (1 - smooth(0.95, 1.2, t)))
        return rebase(fk, body, throw_frame(fk, body, t, idle0), ref, w)

    acts["throw"] = bake(arm, fk, "throw", [throw_rebased(i / FPS) for i in range(int(round(1.2 * FPS)) + 1)], loop=False)
    clips["throw"] = {"duration": 1.2, "loop": False, "events": {"release": THROW_RELEASE}}
    acts["lookup"] = bake(arm, fk, "lookup", loop_frames(lambda t: lookup_frame(fk, body, t), 4.0))
    clips["lookup"] = {"duration": 4.0, "loop": True}
    # Release point of the throw (right palm, glTF coordinates) for the game's ring spawn.
    rel = throw_frame(fk, body, THROW_RELEASE, idle0)
    pose, _ = fk.solve(*rel)
    p = pose["hand_R"][:3, 3] + pose["hand_R"][:3, 1] * 0.05
    clips["throw"]["releasePoint"] = [round(p[0], 3), round(p[2], 3), round(-p[1], 3)]
    pre = throw_frame(fk, body, THROW_RELEASE - 1 / FPS, idle0)
    pp, _ = fk.solve(*pre)
    q = pp["hand_R"][:3, 3] + pp["hand_R"][:3, 1] * 0.05
    vel = (p - q) * FPS
    clips["throw"]["releaseHandVelocity"] = [round(vel[0], 2), round(vel[2], 2), round(-vel[1], 2)]
    ad = arm.animation_data or arm.animation_data_create()
    ad.action = None
    CLIPS.clear()
    CLIPS.update(acts)
    INFO.clear()
    INFO.update(clips)
    return clips, speed


def rest_pose(arm):
    """Unassign the clip AND put every bone back to rest (clearing the action alone leaves the
    last evaluated pose on the bones)."""
    ad = arm.animation_data
    if ad:
        ad.action = None
    for pb in arm.pose.bones:
        pb.location = (0.0, 0.0, 0.0)
        pb.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        pb.scale = (1.0, 1.0, 1.0)
    bpy.context.scene.frame_set(1)


def set_pose(arm, name, frame):
    act, slot = CLIPS[name]
    ad = arm.animation_data or arm.animation_data_create()
    ad.action = act
    try:
        ad.action_slot = slot
    except Exception:
        pass
    bpy.context.scene.frame_set(int(frame))


def n_frames(name):
    """Keys in the clip's action (the run is keyed at 60 Hz, everything else at 30)."""
    return int(round(INFO[name]["duration"] * INFO[name].get("keyRate", FPS)))


def preview_frames(arm, outdir):
    from . import preview
    nw, nr = n_frames("walk"), n_frames("run")
    mid = lambda name, k: 1 + int(round(k * n_frames(name)))
    shots = [("walk", 1 + int(0.25 * nw), (2.6, -1.2, 1.0), (0, 0, 0.8), 50, "walk_mid"),
             ("walk", 1 + int(0.25 * nw), (0.0, 3.0, 1.7), (0, 0, 1.05), 35, "walk_gamecam"),
             ("run", 1 + int(0.25 * nr), (2.6, -1.2, 1.0), (0, 0, 0.8), 50, "run_mid"),
             ("crouch", 1, (1.9, -1.7, 1.1), (0, -0.15, 0.45), 50, "crouch"),
             ("crouch", 1, (2.6, 0.0, 0.7), (0, -0.1, 0.45), 50, "crouch_side"),
             ("run", 1 + int(0.25 * nr), (0.0, -2.8, 1.0), (0, 0, 0.8), 50, "run_front"),
             ("reach", 1, (1.6, -2.2, 1.3), (0, -0.1, 0.85), 50, "reach"),
             ("throw", 1 + int(THROW_RELEASE * FPS), (2.2, -2.0, 1.2), (0, -0.1, 0.85), 50, "throw_release"),
             ("lookup", 1, (1.6, -2.4, 1.0), (0, 0, 0.9), 50, "lookup"),
             ("idle", 1, (0.9, -2.6, 1.1), (0, 0, 0.85), 50, "idle")]
    # One-shots at their mid pose, front-left and side; talk / look at a telling frame.
    # look: the frame where her head is turned furthest.
    yaws = []
    for i in range(n_frames("look") + 1):
        set_pose(arm, "look", 1 + i)
        Rh = arm.pose.bones["head"].matrix.to_3x3() @ arm.data.bones["head"].matrix_local.to_3x3().inverted()
        f = Rh @ Vector((0.0, -1.0, 0.0))
        yaws.append(abs(math.atan2(f.x, -f.y)))
    k_look = int(np.argmax(yaws)) / n_frames("look")
    for name, k in (("wave", 0.5), ("bow", 0.42), ("eat", 0.55), ("cheer", 0.5), ("point", 0.4), ("talk", 0.45), ("look", k_look)):
        shots.append((name, mid(name, k), (0.9, -2.6, 1.15), (0, 0, 0.9), 50, name))
        shots.append((name, mid(name, k), (2.8, -0.2, 1.0), (0, 0, 0.9), 50, f"{name}_side"))
    # Hands: the five fingers, at rest and holding (reach = left hand on the sleeve).
    shots.append(("idle", 1, (0.75, -0.75, 0.95), (0.28, -0.02, 0.86), 85, "hand_idle"))
    shots.append(("reach", 1, (0.45, -1.1, 1.25), (-0.05, -0.3, 1.02), 85, "hand_reach"))
    shots.append(("cheer", mid("cheer", 0.5), (0.5, -1.3, 1.5), (0.0, -0.1, 1.45), 60, "hand_cheer"))
    for name, fr, loc, tgt, lens, tag in shots:
        set_pose(arm, name, fr)
        preview.shoot(os.path.join(outdir, f"pose_{tag}.png"), loc, tgt, lens, (800, 1000))
    rest_pose(arm)


# ---------------------------------------------------------------- gait checks (foot slip, strips)


def _seam(act):
    seam = 0.0
    for fc in act.layers[0].strips[0].channelbags[0].fcurves:
        kp = fc.keyframe_points
        seam = max(seam, abs(kp[0].co[1] - kp[len(kp) - 1].co[1]))
    return seam


def gait_report(arm, speed, sub=4):
    """Measure walk and run on the baked, skinned result (retarget.slip_report: the skinned geta
    mesh, `sub` samples per frame with the game's linear interpolation between keys; a geta is in
    contact while its lowest vertex is within 3 mm of the floor; slip = its horizontal velocity
    minus the ground's at the clip's speed). Adds head and arm facts and the loop seam, and for
    every clip the root / hips travel and the head yaw at both ends."""
    import retarget as rt
    geta = bpy.data.objects["heroine_geta"]
    rest = np.array([v.co[:] for v in geta.data.vertices])
    side_idx = {"L": np.where(rest[:, 0] > 0)[0], "R": np.where(rest[:, 0] < 0)[0]}
    sc = bpy.context.scene
    report = {"clipSpeed": dict(speed)}
    for name in ("walk", "run"):
        n = n_frames(name)
        act, slot = CLIPS[name]
        T, kr = INFO[name]["duration"], INFO[name].get("keyRate", FPS)
        out = {"source": INFO[name].get("source"), "cycle_s": round(T, 4), "keys": n, "key_rate": kr,
               "steps_per_s": round(2 / T, 2), "step_m": round(speed[name] * T / 2, 3)}
        out.update(rt.slip_report(arm, geta, side_idx, act, slot, speed[name], n, sub, fps=kr))
        head, arm_ang, hips = [], [], []
        for i in range(n * sub):
            fr = i / sub
            sc.frame_set(1 + int(fr), subframe=fr - int(fr))
            pb = arm.pose.bones
            hm = arm.matrix_world @ pb["head"].matrix
            Rh = hm.to_3x3() @ arm.data.bones["head"].matrix_local.to_3x3().inverted()
            fwd = Rh @ Vector((0.0, -1.0, 0.0))
            head.append([hm.translation.z, math.degrees(math.atan2(fwd.x, -fwd.y))])
            up = arm.matrix_world.to_3x3() @ (pb["upperarm_L"].tail - pb["upperarm_L"].head)
            arm_ang.append(math.degrees(math.atan2(-up.y, -up.z)))
            hips.append(list((arm.matrix_world @ pb["hips"].matrix).translation))
        H, P = np.array(head), np.array(hips)
        out.update({"head_bob_cm": round((H[:, 0].max() - H[:, 0].min()) * 100, 2),
                    "head_yaw_range_deg": round(H[:, 1].max() - H[:, 1].min(), 2),
                    "head_yaw_mean_deg": round(float(H[:, 1].mean()), 2),
                    "upperarm_L_swing_deg": [round(min(arm_ang), 1), round(max(arm_ang), 1)],
                    "hips_travel_cm_xyz": [round(float(v) * 100, 2) for v in (P.max(0) - P.min(0))]})
        out["loop_seam_max_abs"] = round(_seam(act), 8)
        report[name] = out
        print(f"[gait] {name}: {out}")
    allc = {}
    for name, (act, slot) in CLIPS.items():
        if name.startswith("add_"):
            continue
        n = n_frames(name)
        set_pose(arm, name, 1)
        P, yaw = [], []
        for i in range(n + 1):
            sc.frame_set(1 + i)
            pb = arm.pose.bones
            P.append(list(pb["hips"].matrix.translation) + list(pb["root"].matrix.translation))
            Rh = pb["head"].matrix.to_3x3() @ arm.data.bones["head"].matrix_local.to_3x3().inverted()
            f = Rh @ Vector((0.0, -1.0, 0.0))
            yaw.append(math.degrees(math.atan2(f.x, -f.y)))
        P = np.array(P)
        allc[name] = {"hips_xy_range_cm": [round(float(v) * 100, 2) for v in (P[:, :2].max(0) - P[:, :2].min(0))],
                      "hips_xy_end_minus_start_cm": [round(float(v) * 100, 3) for v in (P[-1, :2] - P[0, :2])],
                      "root_travel_cm": round(float(np.abs(P[:, 3:] - P[0, 3:]).max()) * 100, 4),
                      "head_yaw_start_end_deg": [round(yaw[0], 2), round(yaw[-1], 2)],
                      "head_yaw_range_deg": [round(min(yaw), 1), round(max(yaw), 1)],
                      "first_last_key_diff": round(_seam(act), 6)}
    report["clips"] = allc
    rest_pose(arm)
    return report


def gait_strips(arm, outdir, cols=8):
    """idle, walk and run as frame strips, side and front: `cols` evenly spaced frames each."""
    from . import preview
    import tempfile
    tmp = tempfile.mkdtemp(prefix="heroine_strip_")
    sc = bpy.context.scene
    for name in ("idle", "walk", "run"):
        n = n_frames(name)
        for view, loc, tgt in (("side", (3.2, 0.0, 0.85), (0, 0, 0.78)), ("front", (0.0, -3.2, 0.85), (0, 0, 0.78))):
            tiles = []
            for c in range(cols):
                fr = c * n / cols
                set_pose(arm, name, 1)
                sc.frame_set(1 + int(fr), subframe=fr - int(fr))
                p = os.path.join(tmp, f"{name}_{view}_{c}.png")
                preview.shoot(p, loc, tgt, 50, (300, 560))
                img = bpy.data.images.load(p)
                a = np.array(img.pixels[:], dtype=np.float32).reshape(img.size[1], img.size[0], 4)
                bpy.data.images.remove(img)
                tiles.append(a)
            strip = np.concatenate(tiles, axis=1)
            H, W = strip.shape[:2]
            im = bpy.data.images.new(f"strip_{name}_{view}", W, H, alpha=True)
            im.pixels.foreach_set(strip.ravel())
            im.filepath_raw = os.path.join(outdir, f"strip_{name}_{view}.png")
            im.file_format = "PNG"
            im.save()
            bpy.data.images.remove(im)
            print(f"[gait] wrote strip_{name}_{view}.png ({cols} frames over {n})")
    for f in os.listdir(tmp):
        os.remove(os.path.join(tmp, f))
    os.rmdir(tmp)
    rest_pose(arm)
