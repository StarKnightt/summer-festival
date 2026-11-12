"""Her clips, generated procedurally at 30 fps, in place (root never moves):

  idle    4.0 s loop   breathing, slow weight shift, hands lightly clasped in front
  walk    0.7 s loop   small quick geta steps, 1.10 m/s
  run     0.5 s loop   light trot, elbows bent holding the sleeves in, 2.80 m/s
  crouch  3.0 s loop   squat on her heels, right hand stroking forward-low (cat / goldfish tub)
  reach   3.0 s loop   at a stall counter, right hand forward at ~1.0 m choosing, left hand holding
                       the right sleeve back
  throw   1.2 s once   soft underhand ring toss with the right hand, release at 0.62 s
  lookup  4.0 s loop   head and chest tilted up at fireworks, hands clasped at the chest, slow sway
  wave    1.5 s once   small friendly wave with the right hand

Legs are two-bone IK against explicit geta kinematics: a geta is rigid, so the foot rocks on the
back edge of its rear tooth at heel strike and on the front edge of its front tooth at toe-off,
and in stance the planted contact slides back at exactly the clip speed (no foot skate when the
game plays the clip at speed / clipSpeed). Arms are IK to hand targets. Sleeves, hair, kanzashi
dangles and obi tails hang under gravity (their rest orientation, turned with the body) plus a
lagged sway; every motion term is periodic in the clip length, so loops are seamless.
"""
import math
import os

import bpy
import numpy as np
from mathutils import Matrix, Quaternion

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
    return {f"fingers_{sf}": rot(X, -curl), f"thumb_{sf}": rot(X, -thumb) @ rot(Z, thumb * 0.5 * (1 if sf == "L" else -1))}


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


LAST_DROP = [0.0]


def gait_frame(fk, body, t, T, v, duty, run=False, drop=None):
    delta, absr, local, loc = {}, {}, {}, {}
    ph = (t / T) % 1.0
    stance_len = v * T * duty
    y_hs = -(0.42 if not run else 0.38) * stance_len
    HS = 5.0 if not run else 3.0
    TO = -16.0 if not run else -26.0
    feet = {}
    for sf, off in (("L", 0.0), ("R", 0.5)):
        p = (ph + off) % 1.0
        A0, heel, toe = body.foot_points(sf)
        inward = 0.018 if not run else 0.010            # small steps close to the centre line
        xg = heel[0] - (inward if sf == "L" else -inward)
        ht = toe - heel
        yaw = (-3.0 if sf == "L" else 3.0)               # a touch pigeon-toed, as in geta
        if p < duty:
            yg = y_hs + v * T * p
            f = p / duty
            if f < 0.12:
                kind, pitch, pg = "heel", HS * (1 - smooth(0, 0.12, f)), np.array([xg, yg, 0])
            elif f < 0.55:
                kind, pitch, pg = "heel", 0.0, np.array([xg, yg, 0])
            else:
                g = (f - 0.55) / 0.45
                kind, pitch = "toe", TO * smooth(0.0, 1.0, g) ** 1.2
                pg = np.array([xg + ht[0], yg + ht[1], 0])
            ankle, Rf = body.foot_pose(sf, kind, pg, pitch, yaw)
            feet[sf] = (ankle, Rf, True)
        else:
            f = (p - duty) / (1 - duty)
            y0 = y_hs + v * T * duty
            a_off, R_off = body.foot_pose(sf, "toe", np.array([xg + ht[0], y0 + ht[1], 0]), TO, yaw)
            a_on, R_on = body.foot_pose(sf, "heel", np.array([xg, y_hs, 0]), HS, yaw)
            D = a_on[1] - a_off[1]
            m = v * T * (1 - duty) / D if abs(D) > 1e-6 else 0.0
            e = (-2 * f ** 3 + 3 * f ** 2) + m * ((f ** 3 - 2 * f ** 2 + f) + (f ** 3 - f ** 2))
            ankle = a_off * (1 - e) + a_on * e
            lift = (0.050 if not run else 0.13) * math.sin(math.pi * min(1.0, f * 1.1)) ** (1.2 if not run else 0.8)
            back = (0.0 if not run else 0.06) * math.sin(math.pi * min(1.0, f * 1.4))
            ankle = ankle + np.array([0, back * (1 - f), lift])
            pitch = TO * (1 - smooth(0.0, 0.5, f)) + HS * smooth(0.5, 1.0, f) - 6.0 * math.sin(math.pi * f)
            Rf = rot(Z, yaw) @ rot(X, -pitch)
            feet[sf] = (ankle, Rf, False)
    w = 2 * math.pi * ph
    if not run:
        z = -0.014 - 0.007 * math.cos(2 * w)
        x = 0.010 * math.sin(w + 0.3)
        yaw, roll, lean = 3.0 * math.sin(w), 2.0 * math.sin(2 * w - 0.6), 2.5
    else:
        z = -0.040 + 0.018 * math.cos(2 * w + 0.4)
        x = 0.006 * math.sin(w)
        yaw, roll, lean = 5.0 * math.sin(w), 2.5 * math.sin(2 * w - 0.5), 8.0
    hips_loc = np.array([x, -0.006 if run else 0.0, z])
    delta["hips"] = rot(Z, -yaw) @ rot(Y, roll) @ rot(X, lean * 0.3)
    if drop is not None:
        loc["hips"] = hips_loc - np.array([0, 0, drop])
    else:
        dz = 0.0
        for _ in range(8):
            loc["hips"] = hips_loc - np.array([0, 0, dz])
            pose, _ = fk.solve(delta, absr, local, loc)
            worst = 0.0
            for sf, (ankle, Rf, planted) in feet.items():
                if planted:
                    H = fk.head_if(pose, f"thigh_{sf}")
                    worst = max(worst, np.linalg.norm(ankle - H) / sum(body.L[sf]))
            if worst <= 0.990:
                break
            dz += (worst - 0.988) * sum(body.L["L"])
        LAST_DROP[0] = dz
    delta["spine"] = rot(Z, yaw * 0.45) @ rot(X, lean * 0.3)
    delta["spine1"] = rot(Z, yaw * 0.45) @ rot(X, lean * 0.25)
    delta["spine2"] = rot(Z, yaw * 0.5) @ rot(Y, -roll * 0.6)
    delta["neck"] = rot(Z, -yaw * 0.3) @ rot(X, -lean * 0.3)
    delta["head"] = rot(Z, -yaw * 0.3) @ rot(X, -lean * 0.4 + 2.0) @ rot(Y, -roll * 0.3)
    pose, _ = fk.solve(delta, absr, local, loc)
    for sf, (ankle, Rf, planted) in feet.items():
        absr.update(body.leg(pose, sf, ankle, Rf))
    pose, _ = fk.solve(delta, absr, local, loc)
    for sf, s in (("L", 1), ("R", -1)):
        a = math.sin(w + (0.0 if sf == "L" else math.pi))     # arm swings with the opposite leg
        H = fk.head_if(pose, f"upperarm_{sf}")
        if not run:
            wrist = H + np.array([s * 0.075, -0.045 - 0.075 * a, -0.40 + 0.01 * abs(a)])
            hd = norm(np.array([-s * 0.15, -0.25 - 0.1 * a, -1.0]))
            po = np.array([-s * 1.0, 0.25, 0.0])
            pole = np.array([s * 0.5, 0.8, -0.2])
            local.update(hand_local(sf, 26.0, 10.0))
        else:
            # Elbows bent, hands near the waist holding the sleeves in, swinging a little.
            wrist = H + np.array([s * 0.015 - s * 0.01 * a, -0.17 - 0.07 * a, -0.27 + 0.03 * a])
            hd = norm(np.array([-s * 0.65, -0.55, -0.25]))
            po = np.array([-s * 0.4, 0.3, -0.8])
            pole = np.array([s * 0.7, 0.7, -0.2])
            local.update(hand_local(sf, 70.0, 30.0))
        absr.update(body.arm(pose, sf, wrist, pole, hd, po))
        delta[f"shoulder_{sf}"] = rot(X, 2.0 * a) @ rot(Y, s * -1.5)
    if not run:
        local.update(secondary(fk, t, T / 2, 2.0, -3.0, scale={"sleeve_L": 1.6, "sleeve_R": 1.6, "skirtF": 1.5,
                                                               "skirtB": 1.5}))
    else:
        local.update(secondary(fk, t, T / 2, 4.0, -10.0, scale={"sleeve_L": 1.2, "sleeve_R": 1.2, "skirtF": 1.2,
                                                                "skirtB": 1.2}))
    grav = {"sleeve_L": 0.65, "sleeve_R": 0.65} if run else None
    return delta, absr, local, loc, grav


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


def wave_frame(fk, body, t, idle0):
    delta, absr, local, loc, _ = idle0
    delta, absr, local, loc = dict(delta), {}, dict(local), dict(loc)
    k = smooth(0.0, 0.38, t) * (1 - smooth(1.12, 1.5, t))
    delta["head"] = delta["head"] @ rot(Y, -5.0 * k) @ rot(Z, -4.0 * k)
    delta["spine2"] = delta["spine2"] @ rot(Y, 2.0 * k)
    pose, _ = fk.solve(delta, {}, local, loc)
    planted_legs(fk, body, pose, absr, {"L": (0.004, -0.010, 4.0, None), "R": (-0.004, 0.012, -6.0, None)})
    pose, _ = fk.solve(delta, absr, local, loc)
    clasp_arms(fk, body, pose, absr, local, np.array([0.0, -0.150, 0.955]))
    H = fk.head_if(pose, "upperarm_R")
    wv = math.sin(2 * math.pi * (t - 0.38) / 0.36) * smooth(0.36, 0.48, t) * (1 - smooth(1.0, 1.14, t))
    wr = H + np.array([-0.10 + 0.035 * wv, -0.10, 0.16])
    hd = norm(np.array([-0.15 - 0.6 * wv * 0.5, -0.12, 1.0]))
    po = norm(np.array([0.1, -1.0, 0.1]))
    arm = body.arm(pose, "R", wr, np.array([-0.5, 0.2, -1.0]), hd, po)
    for kk in arm:
        absr[kk] = _slerp(absr[kk], arm[kk], k)
    local.update(hand_local("R", 22.0 * (1 - k) + 6.0 * k, 12.0 * (1 - k) + 2.0 * k))
    local.update(secondary(fk, t, 0.36, 1.5 * k + 0.8, 0.0))
    return delta, absr, local, loc, {"sleeve_R": 1.0}



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
            wl = 1.0 / (1.0 + math.exp(-d / 0.03))
            wl = 0.15 + 0.7 * wl
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

CLIPS = {}


def build(arm):
    fk = FK(arm)
    body = Body(fk)
    clips = {}

    def loop_frames(fn, dur):
        n = int(round(dur * FPS))
        return [skirt_follow(fk, fn(i / FPS), "avg") for i in range(n + 1)]

    once_frames = loop_frames

    def gait_frames(T, v, duty, run):
        n = int(round(T * FPS))
        need = []
        for i in range(n):
            gait_frame(fk, body, i / FPS, T, v, duty, run)
            need.append(LAST_DROP[0])
        need = np.array(need)
        k = 3
        mx = np.array([max(need[(i + j) % n] for j in range(-k, k + 1)) for i in range(n)])
        g = np.exp(-0.5 * (np.arange(-k, k + 1) / 1.5) ** 2)
        g /= g.sum()
        sm = np.array([sum(g[j + k] * mx[(i + j) % n] for j in range(-k, k + 1)) for i in range(n)])
        sm = np.maximum(sm, need)
        return [skirt_follow(fk, gait_frame(fk, body, i / FPS, T, v, duty, run, drop=float(sm[i % n])), "gait")
                for i in range(n + 1)]

    acts = {}
    acts["idle"] = bake(arm, fk, "idle", loop_frames(lambda t: idle_frame(fk, body, t), 4.0))
    clips["idle"] = {"duration": 4.0, "loop": True}
    T, v, duty = 0.7, 1.10, 0.60
    acts["walk"] = bake(arm, fk, "walk", gait_frames(T, v, duty, False))
    clips["walk"] = {"duration": T, "loop": True, "speed": v, "stride": round(v * T, 3), "step": round(v * T / 2, 3),
                     "events": {"footDownL": 0.0, "footUpL": round(duty * T, 3), "footDownR": round(0.5 * T, 3),
                                "footUpR": round((duty - 0.5) * T, 3)}}
    T, v, duty = 14 / FPS, 2.70, 0.40
    acts["run"] = bake(arm, fk, "run", gait_frames(T, v, duty, True))
    clips["run"] = {"duration": round(T, 4), "loop": True, "speed": v, "stride": round(v * T, 3), "step": round(v * T / 2, 3),
                    "events": {"footDownL": 0.0, "footUpL": round(duty * T, 3), "footDownR": round(0.5 * T, 3),
                               "footUpR": round((0.5 + duty) * T, 3)}}
    n = int(round(3.0 * FPS))
    acts["crouch"] = bake(arm, fk, "crouch", [skirt_follow(fk, crouch_frame(fk, body, i / FPS), "hang") for i in range(n + 1)])
    clips["crouch"] = {"duration": 3.0, "loop": True, "events": {"strokeForward": [0.375, 1.875]}}
    acts["reach"] = bake(arm, fk, "reach", loop_frames(lambda t: reach_frame(fk, body, t), 3.0))
    clips["reach"] = {"duration": 3.0, "loop": True}
    idle0 = idle_frame(fk, body, 0.0)
    acts["throw"] = bake(arm, fk, "throw", once_frames(lambda t: throw_frame(fk, body, t, idle0), 1.2), loop=False)
    clips["throw"] = {"duration": 1.2, "loop": False, "events": {"release": THROW_RELEASE}}
    acts["lookup"] = bake(arm, fk, "lookup", loop_frames(lambda t: lookup_frame(fk, body, t), 4.0))
    clips["lookup"] = {"duration": 4.0, "loop": True}
    acts["wave"] = bake(arm, fk, "wave", once_frames(lambda t: wave_frame(fk, body, t, idle0), 1.5), loop=False)
    clips["wave"] = {"duration": 1.5, "loop": False}
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
    return clips


def set_pose(arm, name, frame):
    act, slot = CLIPS[name]
    ad = arm.animation_data or arm.animation_data_create()
    ad.action = act
    try:
        ad.action_slot = slot
    except Exception:
        pass
    bpy.context.scene.frame_set(int(frame))


def preview_frames(arm, outdir):
    from . import preview
    shots = [("walk", 1 + int(0.25 * 0.7 * FPS), (2.6, -1.2, 1.0), (0, 0, 0.8), 50, "walk_mid"),
             ("walk", 1 + int(0.25 * 0.7 * FPS), (0.0, 3.0, 1.7), (0, 0, 1.05), 35, "walk_gamecam"),
             ("run", 1 + int(0.25 * 14), (2.6, -1.2, 1.0), (0, 0, 0.8), 50, "run_mid"),
             ("crouch", 1, (1.9, -1.7, 1.1), (0, -0.15, 0.45), 50, "crouch"),
             ("crouch", 1, (2.6, 0.0, 0.7), (0, -0.1, 0.45), 50, "crouch_side"),
             ("run", 1 + int(0.25 * 14), (0.0, -2.8, 1.0), (0, 0, 0.8), 50, "run_front"),
             ("reach", 1, (1.6, -2.2, 1.3), (0, -0.1, 0.85), 50, "reach"),
             ("throw", 1 + int(THROW_RELEASE * FPS), (2.2, -2.0, 1.2), (0, -0.1, 0.85), 50, "throw_release"),
             ("lookup", 1, (1.6, -2.4, 1.0), (0, 0, 0.9), 50, "lookup"),
             ("wave", 1 + int(0.7 * FPS), (0.8, -2.6, 1.2), (0, 0, 0.95), 50, "wave"),
             ("idle", 1, (0.9, -2.6, 1.1), (0, 0, 0.85), 50, "idle")]
    for name, fr, loc, tgt, lens, tag in shots:
        set_pose(arm, name, fr)
        preview.shoot(os.path.join(outdir, f"pose_{tag}.png"), loc, tgt, lens, (800, 1000))
    ad = arm.animation_data
    ad.action = None
    bpy.context.scene.frame_set(1)
