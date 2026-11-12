"""Shared clips, authored procedurally at 30 fps.

Every clip is rotation-only on every bone, plus a small `root` translation (bob / sway). Legs are
solved with analytic two-bone IK against explicit foot kinematics: a planted foot moves backward at
exactly the clip speed (no sliding); the root drops just enough for the planted legs to reach and is
smoothed (low-passed, then shifted down so no leg ever over-extends). Because all variants share
bone rest directions and rolls, a rotation clip authored on one plays on all; the root translation
is in metres for the clip's reference leg length (scale it by leg / refLeg, see README).
"""
import math

import numpy as np
from mathutils import Matrix

from .geo import lerp, norm, rot, smooth
from .rig import PARENT

FPS = 30
X, Y, Z = np.eye(3)
FWD = np.array([0, -1.0, 0])
DOWN = np.array([0, 0, -1.0])


class FK:
    def __init__(self, arm, J):
        self.J = J
        bones = arm.data.bones
        self.rest = {b.name: np.array(b.matrix_local, dtype=float) for b in bones}
        self.R = {n: m[:3, :3] for n, m in self.rest.items()}
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

    def solve(self, root_t=None, delta=None, absq=None):
        delta, absq = delta or {}, absq or {}
        pose, basis = {}, {}
        for n in self.order:
            Rr = self.rest[n]
            p = self.parent[n]
            M0 = pose[p] @ self.inv[p] @ Rr if p else Rr.copy()
            R0 = M0[:3, :3]
            if n in absq:
                Rp = absq[n] @ self.R[n]
            elif n in delta:
                Pchg = pose[p][:3, :3] @ self.R[p].T if p else np.eye(3)
                Rp = Pchg @ delta[n] @ self.R[n]
            else:
                Rp = R0
            M = np.eye(4)
            M[:3, :3] = Rp
            M[:3, 3] = M0[:3, 3]
            t = np.zeros(3)
            if n == "root" and root_t is not None:
                M[:3, 3] = M0[:3, 3] + np.asarray(root_t, float)
                t = R0.T @ np.asarray(root_t, float)
            pose[n] = M
            basis[n] = (t, R0.T @ Rp)
        return pose, basis

    def head(self, pose, n):
        return pose[n][:3, 3]

    def head_if(self, pose, child):
        p = self.parent[child]
        return (pose[p] @ self.inv[p] @ self.rest[child])[:3, 3]

    def Q(self, pose, n):
        """Armature-space rotation change of bone n (pose vs rest)."""
        return pose[n][:3, :3] @ self.R[n].T


def align(y0, l0, y1, l1):
    """Rotation taking the orthonormal pair (y0, l0) to (y1, l1)."""
    y0, y1 = norm(y0), norm(y1)
    l0 = norm(l0 - y0 * (l0 @ y0))
    l1 = norm(l1 - y1 * (l1 @ y1))
    B0 = np.stack([y0, l0, np.cross(y0, l0)], 1)
    B1 = np.stack([y1, l1, np.cross(y1, l1)], 1)
    return B1 @ B0.T


def two_bone(H, A, L1, L2, pole, reach=0.995):
    d = A - H
    dist = np.linalg.norm(d)
    u = d / max(dist, 1e-9)
    dist = float(np.clip(dist, abs(L1 - L2) + 1e-4, (L1 + L2) * reach))
    ca = np.clip((L1 * L1 + dist * dist - L2 * L2) / (2 * L1 * dist), -1, 1)
    sa = math.sqrt(1 - ca * ca)
    v = norm(pole - u * (pole @ u))
    K = H + L1 * (ca * u + sa * v)
    return K, H + u * dist


# ---------------------------------------------------------------- pose building

class Pose:
    def __init__(self):
        self.root = np.zeros(3)
        self.delta = {}
        self.feet = {}   # side -> (ankle world pos, pitch deg, yaw deg)
        self.arms = {}   # side -> dict(u=, e=, hint=, tw=, wrist=(flex, dev, twist)) in chest space, or target=
        self.sleeve_g = 0.8


def Rx(a):
    return rot(X, a)


def Ry(a):
    return rot(Y, a)


def Rz(a):
    return rot(Z, a)


def chain_rot(*ms):
    R = np.eye(3)
    for m in ms:
        R = R @ m
    return R


def geta_pivots(J):
    """(front, rear) ground-contact edges of the geta teeth, as Y offsets from the ankle (+Y = back):
    the foot rocks forward on the FRONT edge of the front tooth and back on the REAR edge of the rear
    tooth (see body.Body.geta: teeth at y1 + 0.42 hl and y0 - 0.38 hl, half length 0.011 lk)."""
    lk = J["lk"]
    hl = (J["heel"] + J["toe"] + 0.024 * lk) / 2
    front = -(J["toe"] + 0.012 * lk) + 0.42 * hl - 0.011 * lk
    rear = (J["heel"] + 0.012 * lk) - 0.38 * hl + 0.011 * lk
    return front, rear


def foot_ankle(J, flat_ankle, pitch):
    """Ankle position for a foot whose flat (pitch 0) ankle would be at flat_ankle; positive pitch
    lifts the heel (rocking on the front tooth's front edge), negative lifts the toes (rocking on the
    rear tooth's rear edge). The contact edge stays put, so a rocking planted geta does not slide."""
    a = np.asarray(flat_ankle, float)
    h = J["ankle_z"]
    front, rear = geta_pivots(J)
    piv = a + np.array([0, front if pitch >= 0 else rear, -h])
    return piv + Rx(pitch) @ (a - piv)


def solve_frame(fk, ps):
    J = fk.J
    pose, _ = fk.solve(ps.root, ps.delta)
    absq = {}
    # legs
    for side, (A, pitch, yaw) in ps.feet.items():
        H = fk.head_if(pose, f"thigh_{side}")
        L1 = np.linalg.norm(J["bones"][f"thigh_{side}"][1] - J["bones"][f"thigh_{side}"][0])
        L2 = np.linalg.norm(J["bones"][f"shin_{side}"][1] - J["bones"][f"shin_{side}"][0])
        Ry_ = Rz(yaw)
        pole = Ry_ @ FWD + np.array([0.08 if side == "L" else -0.08, 0, 0])
        K, A2 = two_bone(H, np.asarray(A, float), L1, L2, pole)
        lat = np.cross(K - H, A2 - K)
        if np.linalg.norm(lat) < 1e-6:
            lat = Ry_ @ X
        lat = norm(lat)
        absq[f"thigh_{side}"] = align(DOWN, X, K - H, lat)
        absq[f"shin_{side}"] = align(DOWN, X, A2 - K, lat)
        F = Ry_ @ Rx(pitch)
        absq[f"foot_{side}"] = align(FWD, X, F @ FWD, F @ X)
    pose, _ = fk.solve(ps.root, ps.delta, absq)
    Qc = fk.Q(pose, "chest")
    for side, a in ps.arms.items():
        d0 = J[f"d0_{side}"]
        S = fk.head_if(pose, f"upperarm_{side}")
        P = J["P"]
        if "target" in a:
            W = np.asarray(a["target"], float)
            pole = Qc @ np.asarray(a.get("pole", (0.6 if side == "L" else -0.6, 0.4, -1.0)), float)
            E, W2 = two_bone(S, W, P["ua"], P["fa"], pole, reach=0.985)
            u = norm(E - S)
            f = norm(W2 - E)
            su = f - u * (f @ u)
            su = norm(su) if np.linalg.norm(su) > 1e-4 else norm(Qc @ FWD)
        else:
            u = norm(Qc @ np.asarray(a["u"], float))
            hint = Qc @ np.asarray(a.get("hint", FWD), float)
            su = norm(hint - u * (hint @ u))
            if a.get("tw"):
                su = rot(u, a["tw"]) @ su
            e = math.radians(a.get("e", 10.0))
            f = u * math.cos(e) + su * math.sin(e)
        sf = norm(-u - f * (-u @ f)) if np.linalg.norm(np.cross(u, f)) > 1e-3 else su
        if a.get("pro"):
            sf = rot(f, a["pro"]) @ sf
        Qu = align(d0, FWD, u, su)
        Qf = align(d0, FWD, f, sf)
        absq[f"upperarm_{side}"] = Qu
        absq[f"forearm_{side}"] = Qf
        # wrist: (flex toward the palm, radial deviation toward the thumb, twist), same sense both sides
        flex, rad, tw = a.get("wrist", (0.0, 0.0, 0.0))
        lat0 = norm(np.cross(d0, FWD))
        psg = 1.0 if side == "R" else -1.0
        Wr = rot(FWD, psg * flex) @ rot(lat0, rad) @ rot(d0, tw)
        absq[f"hand_{side}"] = Qf @ Wr
    pose, basis = fk.solve(ps.root, ps.delta, absq)
    return pose, absq


def sleeves(fk, frames_pose, frames_absq, frames_ps, loop=True):
    """Hanging sleeve bones: mostly gravity-down, lagging the forearm's motion (periodic)."""
    n = len(frames_pose)
    out = []
    for side in ("L", "R"):
        P = np.array([fk.head(frames_pose[i], f"sleeve_{side}1") for i in range(n)])
        if loop:
            # frames hold n+1 keys with the last == the first: difference the n unique ones cyclically
            P0 = P[:-1]
            vel = (np.roll(P0, -1, 0) - np.roll(P0, 1, 0)) * FPS / 2
            vel = np.vstack([vel, vel[:1]])
        else:
            vel = np.gradient(P, axis=0) * FPS
        for i in range(n):
            Qf = fk.Q(frames_pose[i], f"forearm_{side}")
            g = frames_ps[i].sleeve_g
            carried = Qf @ DOWN
            dirv = norm(g * (DOWN - 0.10 * vel[i] * np.array([1, 1, 0.3])) + (1 - g) * carried)
            l1 = Qf @ FWD
            frames_absq[i][f"sleeve_{side}1"] = align(DOWN, FWD, dirv, l1 if abs(norm(l1) @ dirv) < 0.95 else Qf @ X)
    return frames_absq


# ---------------------------------------------------------------- reach / root drop

def max_root_z(fk, ps, sides=("L", "R"), margin=0.99):
    J = fk.J
    ps0 = Pose()
    ps0.delta = ps.delta
    ps0.root = np.array([ps.root[0], ps.root[1], 0.0])
    pose, _ = fk.solve(ps0.root, ps0.delta)
    best = 1e9
    for side in sides:
        if side not in ps.feet:
            continue
        A = np.asarray(ps.feet[side][0], float)
        H = fk.head_if(pose, f"thigh_{side}")
        L = np.linalg.norm(J["bones"][f"thigh_{side}"][1] - J["bones"][f"thigh_{side}"][0]) + \
            np.linalg.norm(J["bones"][f"shin_{side}"][1] - J["bones"][f"shin_{side}"][0])
        dxy2 = (A[0] - H[0]) ** 2 + (A[1] - H[1]) ** 2
        r2 = (L * margin) ** 2 - dxy2
        if r2 <= 0:
            best = min(best, -1.0)
            continue
        best = min(best, A[2] + math.sqrt(r2) - H[2])
    return best


def lowpass(x, k):
    F = np.fft.rfft(x)
    F[k + 1:] = 0
    return np.fft.irfft(F, len(x))


# ---------------------------------------------------------------- gait

class Gait:
    LIFT, LAND = 0.12, 0.16

    def __init__(self, J, v, T, duty, clear, toe_off=20.0, strike=-8.0, kick=0.0, width=1.0, swing_back=0.0):
        self.J, self.v, self.T, self.duty = J, v, T, duty
        self.D = v * T * duty
        self.clear, self.toe_off, self.strike, self.kick = clear, toe_off, strike, kick
        self.width = width
        self.swing_back = swing_back

    def foot(self, side, phi):
        """(ankle, pitch) for a foot; left foot strikes at phi = 0, right at 0.5."""
        J = self.J
        ph = (phi + (0.0 if side == "L" else 0.5)) % 1.0
        x = J[f"an_{side}"][0] * self.width
        D, du = self.D, self.duty
        h0 = J["ankle_z"]
        if ph < du:
            s = ph / du
            y = -D / 2 + D * s
            pitch = self.strike * (1 - smooth(0.0, 0.18, s)) + self.toe_off * smooth(0.70, 1.0, s) ** 1.5
            lift = 0.0
        else:
            s = (ph - du) / (1 - du)
            # swing: the first LIFT and last LAND fractions only raise / lower the foot while it keeps
            # drifting back at the ground speed (stationary on the ground: no skate at toe-off or
            # strike); the forward travel happens in between on a Hermite curve that matches that
            # drift velocity at both ends.
            Ts = (1 - du) * self.T
            a_, b_ = self.LIFT, self.LAND
            if s < a_:
                y = D / 2 + self.v * Ts * s
            elif s > 1 - b_:
                y = -D / 2 - self.v * Ts * (1 - s)
            else:
                u = (s - a_) / (1 - a_ - b_)
                y0_, y1_ = D / 2 + self.v * Ts * a_, -D / 2 - self.v * Ts * b_
                m = self.v * Ts * (1 - a_ - b_)
                h00, h10, h01, h11 = 2 * u ** 3 - 3 * u ** 2 + 1, u ** 3 - 2 * u ** 2 + u, -2 * u ** 3 + 3 * u ** 2, u ** 3 - u ** 2
                y = h00 * y0_ + h10 * m + h01 * y1_ + h11 * m
                y += self.swing_back * math.sin(math.pi * u) * (1 - u) ** 1.5
            pitch = self.toe_off * (1 - smooth(0.0, 0.45, s)) + self.kick * math.sin(math.pi * min(s * 1.6, 1.0)) * (1 - s) +                 self.strike * smooth(0.60, 1.0, s)
            lift = self.clear * math.sin(math.pi * s) ** 1.2 * (1 + 0.6 * self.kick / 40 * math.sin(math.pi * s) * (1 - s))
        flat = np.array([x, y, h0 + lift])
        return foot_ankle(J, flat, pitch), pitch


# ---------------------------------------------------------------- clip builders

# Relaxed arm (all clips): the upper arm hangs a little away from the body (out, deg from vertical) and a
# little forward (fwd), the elbow is softly bent (e, 15-35 deg), the wrist flexes slightly toward the
# palm with a touch of ulnar deviation. Positive swing = upper arm back.
ARM_E, ARM_OUT, ARM_FWD = 24.0, 13.0, 7.0
WRIST_RELAXED = (12.0, -4.0, 0.0)


def relaxed(side, swing=0.0, e=ARM_E, out=ARM_OUT, fwd=ARM_FWD, wrist=WRIST_RELAXED, pro=0.0):
    sg = 1.0 if side == "L" else -1.0
    u = Rx(swing) @ rot(Y, -sg * out) @ Rx(-fwd) @ DOWN
    a = dict(u=u, e=e, hint=FWD, wrist=tuple(wrist))
    if pro:
        a["pro"] = pro
    return a


def swing_arm(side, phi, ph0, amp, lag, e0, follow=0.07, gain=1.15, fwd_bend=6.0, e_lim=(15.0, 36.0)):
    """Pendular arm swing with follow-through: the forearm's own swing lags the upper arm's by
    `follow` of a cycle, so the elbow opens on the back-swing and closes on the forward swing."""
    sw = -amp * math.cos(2 * math.pi * (phi - ph0 - lag))                  # upper arm (+ = back)
    swf = -amp * gain * math.cos(2 * math.pi * (phi - ph0 - lag - follow))  # forearm, lagging
    e = e0 + (sw - swf) + fwd_bend * max(0.0, -sw) / amp
    return sw, float(np.clip(e, *e_lim))


def frames(fn, n, fk, loop=True):
    """Sample fn(phase) -> Pose for i in 0..n (n+1 keys, the last equal to the first when looping),
    choose the root drop, solve, add sleeves."""
    ts = [i / n for i in range(n + 1)]
    pss = [fn(t) for t in ts]
    return pss


def finish(fk, pss, root_mode="lowpass", k=4, margin=0.985, loop=True):
    """Root height: either the low-passed reach limit (walk) or the given design curve, shifted
    down so the planted legs never over-extend."""
    n = len(pss)
    lim = np.array([max_root_z(fk, ps, margin=margin) for ps in pss])
    lim = np.minimum(lim, 0.0)
    design = np.array([ps.root[2] for ps in pss])
    if root_mode == "lowpass":
        base = lowpass(lim[:-1] if loop else lim, k)
        if loop:
            base = np.append(base, base[0])
        design = base + design
    over = np.max(design - lim)
    z = design - max(over, 0.0) - 0.002
    for ps, zz in zip(pss, z):
        ps.root = np.array([ps.root[0], ps.root[1], zz])
    poses, absqs = [], []
    for ps in pss:
        pose, absq = solve_frame(fk, ps)
        poses.append(pose)
        absqs.append(absq)
    absqs = sleeves(fk, poses, absqs, pss, loop)
    out = []
    for ps, absq in zip(pss, absqs):
        pose, basis = fk.solve(ps.root, ps.delta, absq)
        out.append((pose, basis, ps.root.copy()))
    return out


def walk_pose(fk, g, phi, sparkler=False):
    J = fk.J
    ps = Pose()
    c = math.cos(2 * math.pi * phi)
    ps.root = np.zeros(3)
    yaw = -4.5 * c
    roll = -2.5 * math.cos(2 * math.pi * (phi - g.duty / 2))
    ps.delta["hips"] = Rz(yaw) @ Ry(roll) @ Rx(2.0)
    ps.delta["spine"] = Rz(-yaw * 0.45) @ Ry(-roll * 0.5) @ Rx(1.5)
    ps.delta["chest"] = Rz(-yaw * 0.45) @ Ry(-roll * 0.3) @ Rx(-1.0 + 0.6 * math.cos(4 * math.pi * phi))
    ps.delta["neck"] = Rx(1.0)
    ps.delta["head"] = Rz(-yaw * 0.15) @ Rx(-1.5 + 1.2 * math.cos(4 * math.pi * (phi - 0.08)))
    for side in ("L", "R"):
        A, pitch = g.foot(side, phi)
        ps.feet[side] = (A, pitch, 0.0)
    for side, ph0 in (("L", 0.5), ("R", 0.0)):
        sw, e = swing_arm(side, phi, ph0, 22.0, 0.04, ARM_E - 2.0, follow=0.08)
        # wrist trails the forearm a little more (flicks back at the end of the forward swing)
        wl = 12.0 + 6.0 * math.sin(2 * math.pi * (phi - ph0 - 0.18))
        ps.arms[side] = relaxed(side, sw, e=e, wrist=(wl, -4.0, 0.0))
    if sparkler:
        w = 2 * math.pi * 2 * phi
        u = Rz(-6 * math.cos(w)) @ Rx(5 * math.sin(w)) @ norm(np.array([-0.18, -0.86, -0.30]))
        ps.arms["R"] = dict(u=u, e=58.0 + 6 * math.sin(w), hint=FWD, wrist=(-14.0 + 8 * math.cos(w), 10 * math.sin(w), 0.0))
        ps.delta["shoulder_R"] = Rx(-4.0)
    ps.delta.setdefault("shoulder_L", np.eye(3))
    return ps


def run_pose(fk, g, phi):
    J = fk.J
    ps = Pose()
    c = math.cos(2 * math.pi * phi)
    ms = g.duty / 2
    ps.root = np.array([0.0, 0.0,
                        -0.026 * J["lk"] * math.cos(4 * math.pi * (phi - ms))])
    yaw = -8.0 * c
    ps.delta["hips"] = Rz(yaw) @ Ry(-3.0 * math.cos(2 * math.pi * (phi - ms))) @ Rx(6.0)
    ps.delta["spine"] = Rz(-yaw * 0.5) @ Rx(4.0)
    ps.delta["chest"] = Rz(-yaw * 0.5) @ Rx(2.0 + 2.0 * math.cos(4 * math.pi * (phi - ms - 0.1)))
    ps.delta["neck"] = Rx(-3.0)
    ps.delta["head"] = Rz(-yaw * 0.2) @ Rx(-6.0 + 3.0 * math.cos(4 * math.pi * (phi - ms - 0.15)))
    for side in ("L", "R"):
        A, pitch = g.foot(side, phi)
        ps.feet[side] = (A, pitch, 0.0)
    for side, ph0 in (("L", 0.5), ("R", 0.0)):
        sg = 1.0 if side == "L" else -1.0
        sw, e = swing_arm(side, phi, ph0, 38.0, 0.03, 82.0, follow=0.06, gain=1.08, fwd_bend=14.0, e_lim=(70.0, 104.0))
        u = Rx(sw) @ rot(Y, -sg * 18) @ DOWN
        wl = 10.0 + 8.0 * math.sin(2 * math.pi * (phi - ph0 - 0.2))
        ps.arms[side] = dict(u=u, e=e, hint=norm(FWD + np.array([-sg * 0.25, 0, 0.0])), wrist=(wl, -3.0, 0.0))
        ps.delta[f"shoulder_{side}"] = Rz(sg * 3.0 * math.sin(2 * math.pi * (phi - ph0)))
    ps.sleeve_g = 0.7
    return ps


def stance(fk, ps, width=1.0, toe_out=6.0, fwd=(0.0, 0.0)):
    J = fk.J
    for i, side in enumerate(("L", "R")):
        sg = 1.0 if side == "L" else -1.0
        an = J[f"an_{side}"]
        ps.feet[side] = (np.array([an[0] * width, an[1] + fwd[i], J["ankle_z"]]), 0.0, sg * toe_out)


def idle_pose(fk, t, T):
    J = fk.J
    ps = Pose()
    w = 2 * math.pi * t / T
    ps.root = np.array([0.014 * math.sin(w), 0.003 * math.sin(2 * w), -0.012])
    roll = 2.2 * math.sin(w)
    ps.delta["hips"] = Ry(roll) @ Rz(1.5 * math.sin(w + 0.6))
    ps.delta["spine"] = Ry(-roll * 0.6) @ Rx(0.6 * math.sin(2 * w))
    br = math.sin(2 * w + 0.3)
    ps.delta["chest"] = Ry(-roll * 0.5) @ Rx(-0.9 * br)
    ps.delta["neck"] = Rx(1.0)
    ps.delta["head"] = Rz(9.0 * math.sin(w + 1.2)) @ Rx(2.5 * math.sin(2 * w + 0.8)) @ Ry(2.0 * math.sin(w + 2.0))
    for side in ("L", "R"):
        sg = 1.0 if side == "L" else -1.0
        ph = 0.0 if side == "L" else 1.7
        ps.delta[f"shoulder_{side}"] = Rx(0.0) @ Ry(-sg * 0.8 * (br + 1))
        # slow sway and weight-shift drift: never two identical arms, never a locked elbow
        ps.arms[side] = relaxed(side, swing=-1.0 + 2.5 * math.sin(w + ph),
                                e=ARM_E + 1.5 * sg + 4.0 * math.sin(w + ph + 0.8),
                                out=ARM_OUT + 1.5 * math.sin(w + ph + 2.0) + 1.2 * sg * math.sin(w),
                                wrist=(12.0 + 4.0 * math.sin(2 * w + ph), -4.0 + 2.0 * math.sin(w + ph), 3.0 * math.sin(w + ph + 1.0)))
    stance(fk, ps, 1.0, 7.0, (-0.03, 0.03))
    return ps


def keyed(keys, t, T):
    """Periodic Catmull-Rom over {time: value-array} keys."""
    ts = sorted(keys)
    vals = [np.asarray(keys[k], float) for k in ts]
    n = len(ts)
    t = t % T
    i = max(j for j in range(n) if ts[j] <= t) if t >= ts[0] else n - 1
    t0 = ts[i]
    t1 = ts[(i + 1) % n] + (T if i + 1 >= n else 0)
    tt = t if t >= t0 else t + T
    s = (tt - t0) / max(t1 - t0, 1e-9)
    p0, p1, p2, p3 = vals[(i - 1) % n], vals[i], vals[(i + 1) % n], vals[(i + 2) % n]
    s2, s3 = s * s, s * s * s
    return 0.5 * ((2 * p1) + (-p0 + p2) * s + (2 * p0 - 5 * p1 + 4 * p2 - p3) * s2 + (-p0 + 3 * p1 - 3 * p2 + p3) * s3)


def wave_pose(fk, t, T):
    ps = idle_pose(fk, t * 2, T * 2)
    w = 2 * math.pi * t / T
    ps.root = ps.root * 0.6
    osc = math.sin(3 * w)
    u = norm(np.array([-0.86, -0.22, 0.30]))
    ps.arms["R"] = dict(u=u, e=92.0 + 6 * math.sin(3 * w + 0.6), hint=np.array([0.0, 0.0, 1.0]), tw=-24.0 * osc,
                        wrist=(-6.0, 12.0 * math.sin(3 * w - 0.8), 0.0), pro=-10.0)
    ps.delta["shoulder_R"] = Ry(8.0) @ Rx(-3.0)
    ps.delta["chest"] = ps.delta["chest"] @ Ry(3.0) @ Rz(-5.0)
    ps.delta["head"] = Rz(-6.0) @ Ry(5.0 + 2.0 * math.sin(w)) @ Rx(-2.0)
    ps.sleeve_g = 0.85
    return ps


def call_pose(fk, t, T, cupped_cache):
    ps = idle_pose(fk, t * 1.333, T * 1.333)
    k = float(np.clip(keyed({0.0: [1.0], 1.15: [1.0], 1.55: [0.0], 2.55: [0.0]}, t, T)[0], 0, 1))
    lean = 9.0 * k
    pump = math.sin(2 * math.pi * t / T * 4) * k
    ps.delta["spine"] = Rx(lean * 0.5 + 1.5 * pump)
    ps.delta["chest"] = Rx(lean * 0.5 + 1.0 * pump) @ Rz(-4.0 * (1 - k))
    ps.delta["head"] = Rx(-6.0 * k - 2.0 * pump) @ Rz(-12.0 * (1 - k)) @ Ry(3.0 * (1 - k))
    ps.root = ps.root * 0.5
    # A: hand cupped at the right side of the mouth (IK target relative to the head);
    # B: arm open to the side and a little forward, palm up, "this way!"
    uA, eA, hA = cupped_cache
    uB = norm(np.array([-0.80, -0.50, -0.32]))
    gB = 0.5 + 0.5 * math.sin(2 * math.pi * t / T * 3)
    u = norm(lerp(uB, uA, k))
    e = lerp(28.0 + 6 * gB, eA, k)
    hint = norm(lerp(np.array([0.0, -0.3, 1.0]), hA, k))
    ps.arms["R"] = dict(u=u, e=e, hint=hint, wrist=(lerp(-20.0, 0.0, k), 0.0, 0.0), pro=lerp(-80.0, 0.0, k))
    ps.arms["L"] = relaxed("L", swing=-4.0 * k, e=lerp(ARM_E, 32.0, k))
    ps.delta["shoulder_R"] = Ry(6.0 * k) @ Rx(-4.0 * k)
    ps.sleeve_g = 0.85
    return ps


def talk_pose(fk, t, T):
    ps = idle_pose(fk, t, T)
    ps.root = ps.root * 0.7
    # right/left forearm gestures, nods
    gR = keyed({0.0: [0, 0], 0.7: [1, 0.2], 1.4: [0.3, 0], 2.2: [0.1, 0], 2.9: [0.8, 0.6], 3.5: [0.2, 0]}, t, T)
    gL = keyed({0.0: [0.2], 1.0: [0.0], 1.9: [1.0], 2.6: [0.3], 3.4: [0.6]}, t, T)
    nod = keyed({0.0: [0], 0.45: [7], 0.8: [0], 1.85: [6], 2.2: [0], 3.1: [8], 3.5: [0]}, t, T)[0]
    for side, g, tw in (("R", gR[0], gR[1]), ("L", gL[0], 0.0)):
        sg = 1.0 if side == "L" else -1.0
        u = Rx(-12.0 - 14.0 * g) @ rot(Y, -sg * (10.0 + 6 * g)) @ DOWN
        ps.arms[side] = dict(u=u, e=55.0 + 35.0 * g, hint=FWD, wrist=(8.0 - 18.0 * g, -3.0, 0.0), pro=-50.0 * g - 30 * tw)
    ps.delta["head"] = ps.delta["head"] @ Rx(nod)
    return ps


def fan_pose(fk, t, T):
    ps = idle_pose(fk, t, T)
    w = 2 * math.pi * t / T
    flap = math.sin(4 * w)
    u = norm(np.array([-0.32, -0.40, -0.86]))
    ps.arms["R"] = dict(u=u, e=118.0 + 3 * flap, hint=FWD, tw=8.0, wrist=(-10.0 + 30.0 * flap, 0.0, 0.0), pro=-20.0)
    ps.delta["head"] = ps.delta["head"] @ Rz(-5.0) @ Ry(-3.0)
    return ps


def lookup_pose(fk, t, T):
    ps = idle_pose(fk, t, T)
    w = 2 * math.pi * t / T
    ps.root = ps.root * 0.6
    ps.delta["spine"] = ps.delta["spine"] @ Rx(-3.0)
    ps.delta["chest"] = ps.delta["chest"] @ Rx(-5.0)
    ps.delta["neck"] = Rx(-12.0)
    ps.delta["head"] = Rx(-22.0 + 2.0 * math.sin(2 * w)) @ Rz(8.0 * math.sin(w + 0.5)) @ Ry(2.5 * math.sin(w))
    for side in ("L", "R"):
        sg = 1.0 if side == "L" else -1.0
        ph = 0.0 if side == "L" else 2.1
        ps.arms[side] = relaxed(side, swing=-0.5 + 2.0 * math.sin(w + ph), e=ARM_E - 2.0 + 3.0 * math.sin(w + ph + 1.1),
                                out=ARM_OUT - 1.0 + 1.0 * math.sin(w + ph), wrist=(12.0 + 3.0 * math.sin(2 * w + ph), -4.0, 0.0))
    return ps


def cupped_params(fk):
    """Solve the 'hand at mouth' arm once (IK to a point by the mouth), express it in chest space as
    (u, e, hint) so it can be blended like the other key poses."""
    J = fk.J
    ps = Pose()
    ps.delta["spine"] = Rx(4.5)
    ps.delta["chest"] = Rx(4.5)
    ps.delta["head"] = Rx(-6.0)
    stance(fk, ps)
    pose, _ = fk.solve(None, ps.delta)
    hh = J["P"]["head"]
    head = fk.head(pose, "head")
    Qh = fk.Q(pose, "head")
    mouth = head + Qh @ np.array([-0.012, -0.112 * hh / 0.235, 0.024])
    hc_target = mouth + Qh @ np.array([-0.06, -0.025, -0.045])   # cupped hand beside the mouth (centre sits low: fingers rise past the cheek)
    hl = J["P"]["hand"]
    S = fk.head_if(pose, "upperarm_R")
    pole = np.array([-1.0, 0.15, -0.55])
    wrist = hc_target - np.array([0, 0, hl * 0.45])
    for _ in range(4):
        E, W2 = two_bone(S, wrist, J["P"]["ua"], J["P"]["fa"], pole, reach=0.97)
        fdir = norm(W2 - E)
        wrist = hc_target - fdir * hl * 0.42
    Qc = fk.Q(pose, "chest")
    u = Qc.T @ norm(E - S)
    f = Qc.T @ norm(W2 - E)
    e = math.degrees(math.acos(np.clip(u @ f, -1, 1)))
    hint = norm(f - u * (u @ f))
    return u, e, hint


CLIPS = [  # name, frames, ref skeleton, loop
    ("idle", 120, "woman"), ("walk", 30, "woman"), ("run", 14, "kid"), ("sparkler", 30, "woman"),
    ("wave", 60, "woman"), ("call", 90, "woman"), ("talk", 120, "woman"), ("fan", 120, "woman"),
    ("lookup", 120, "woman"),
]
WALK_V = 0.90
WALK_DUTY = 0.56
RUN_V = 2.6
RUN_DUTY = 0.28


def build_clip(name, n, fk):
    J = fk.J
    T = n / FPS
    meta = dict(frames=n, duration=round(T, 4), loop=True, fps=FPS)
    if name in ("walk", "sparkler"):
        du = WALK_DUTY
        g = Gait(J, WALK_V, T, du, clear=0.050 * J["lk"], toe_off=16.0, strike=-7.0, width=0.92)
        pss = [walk_pose(fk, g, i / n, sparkler=(name == "sparkler")) for i in range(n + 1)]
        out = finish(fk, pss, "lowpass", k=6)
        meta.update(speed=WALK_V, stride=round(WALK_V * T, 4),
                    contacts={"L": [0.0, round(du * T, 4)], "R": [round(0.5 * T, 4), round((du - 0.5) * T, 4)]},
                    events={"strikeL": 0.0, "toeOffL": round(du * T, 4), "strikeR": round(0.5 * T, 4), "toeOffR": round((du - 0.5) * T, 4)})
    elif name == "run":
        du = RUN_DUTY
        g = Gait(J, RUN_V, T, du, clear=0.20 * J["lk"], toe_off=30.0, strike=-12.0, kick=40.0, width=0.85,
                 swing_back=0.10 * J["lk"])
        pss = [run_pose(fk, g, i / n) for i in range(n + 1)]
        out = finish(fk, pss, "design", margin=0.985)
        meta.update(speed=RUN_V, stride=round(RUN_V * T, 4),
                    contacts={"L": [0.0, round(du * T, 4)], "R": [round(0.5 * T, 4), round((0.5 + du) * T, 4)]},
                    events={"strikeL": 0.0, "toeOffL": round(du * T, 4), "strikeR": round(0.5 * T, 4), "toeOffR": round((0.5 + du) * T, 4)})
    else:
        if name == "call":
            cc = cupped_params(fk)
            fn = lambda t: call_pose(fk, t, T, cc)
        else:
            fn = {"idle": lambda t: idle_pose(fk, t, T), "wave": lambda t: wave_pose(fk, t, T),
                  "talk": lambda t: talk_pose(fk, t, T), "fan": lambda t: fan_pose(fk, t, T),
                  "lookup": lambda t: lookup_pose(fk, t, T)}[name]
        pss = [fn(T * i / n) for i in range(n + 1)]
        out = finish(fk, pss, "design")
        meta.update(contacts={"L": [0.0, round(T, 4)], "R": [0.0, round(T, 4)]})
    rz = np.array([o[2][2] for o in out])
    rx = np.array([o[2][0] for o in out])
    meta["rootZ"] = [round(float(rz.min()), 4), round(float(rz.max()), 4)]
    meta["rootX"] = [round(float(rx.min()), 4), round(float(rx.max()), 4)]
    meta["refSkeleton"] = None
    return out, meta


def bake(arm, fk, name, out):
    import bpy
    act = bpy.data.actions.new(name)
    act.use_fake_user = True
    slot = act.slots.new(id_type="OBJECT", name=arm.name)
    layer = act.layers.new("Layer")
    strip = layer.strips.new(type="KEYFRAME")
    cb = strip.channelbag(slot, ensure=True)
    n = len(out)
    rots = {b: np.zeros((n, 4)) for b in fk.order}
    locs = np.zeros((n, 3))
    for i, (pose, basis, root) in enumerate(out):
        for b in fk.order:
            t, Rb = basis[b]
            q = Matrix(Rb.tolist()).to_quaternion()
            v = np.array([q.w, q.x, q.y, q.z])
            if i > 0 and v @ rots[b][i - 1] < 0:
                v = -v
            rots[b][i] = v
        locs[i] = basis["root"][0]
    fr = np.arange(n, dtype=float)
    for b in fk.order:
        if b.startswith("finger_"):
            continue            # fingers stay in their relaxed rest curl (not keyed by these clips)
        grp = cb.groups.new(b)
        for k in range(4):
            fc = cb.fcurves.new(f'pose.bones["{b}"].rotation_quaternion', index=k)
            fc.group = grp
            fc.keyframe_points.add(n)
            fc.keyframe_points.foreach_set("co", np.stack([fr, rots[b][:, k]], 1).ravel())
            fc.keyframe_points.foreach_set("interpolation", [1] * n)
            fc.update()
        if b == "root":
            for k in range(3):
                fc = cb.fcurves.new('pose.bones["root"].location', index=k)
                fc.group = grp
                fc.keyframe_points.add(n)
                fc.keyframe_points.foreach_set("co", np.stack([fr, locs[:, k]], 1).ravel())
                fc.keyframe_points.foreach_set("interpolation", [1] * n)
                fc.update()
    act.use_frame_range = True
    act.frame_start, act.frame_end = 0, n - 1
    act.use_cyclic = True
    return act, slot
