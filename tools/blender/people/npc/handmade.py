"""Hand-made clips built from the new idle pose: sit, sit_fan, sit_sleep, yawn, cry, pick_up, peace.

These are poses with a little life, not mocap. A pose is {"R": {bone: world 3x3}, "hips": offset}
(the same thing retarget.Motion.pose() returns), so it starts as a copy of the idle's first pose
and is edited with a few verbs:

  bend(pose, bone, axis, deg)      turn a bone and everything below it about a world axis
  arm(pose, side, u, f, ...)       upper arm along u, forearm along f (world directions)
  reach(pose, side, wrist_fn, ...) two-bone IK to a point that is given PER VARIANT (a mouth, a
                                   knee, the ground): each rig is solved and the directions are
                                   averaged, because the clip is one set of rotations for all five
  fingers(pose, side, {...})       extra curl / splay per finger on top of the relaxed rest curl

Standing clips then go through the same foot planting and arm clearance as the Mixamo clips
(mocap.Ctx.finish_standing), so one-shots start and end exactly on the idle. Seated clips set the
legs directly; the root stays at the feet and the hips sit back and down.
"""
import math

import numpy as np

from . import anim as A
from .geo import norm, rot, smooth
from .rig import FINGERS, hand_frame

X, Y, Z = np.eye(3)
FWD, DOWN, UP = -Y, -Z, Z
FPS = A.FPS
# Seated: the thighs slope down toward the knees by this many degrees (0 = level). It sets the seat
# height the pose implies; build.py measures that per variant (extras.people.seat).
SIT_SLOPE = 12.0


def sgn(side):
    return 1.0 if side == "L" else -1.0


def copy(p):
    return {"R": {b: r.copy() for b, r in p["R"].items()}, "hips": np.array(p["hips"], float)}


class Kit:
    def __init__(self, ctx):
        self.ctx, self.rt = ctx, ctx.rt
        self.rig, self.rigs, self.J = ctx.rig, ctx.rigs, ctx.J
        self.Jr = ctx.J[ctx.order[0] if "woman" not in ctx.J else "woman"]
        self.kids = {}
        for b in self.rig.order:
            p = self.rig.parent[b]
            if p:
                self.kids.setdefault(p, []).append(b)
        self._sub = {}
        self.err = {}

    def ax(self, b):
        return self.rig.axes(b)

    def sub(self, bone):
        if bone not in self._sub:
            out, st = [], [bone]
            while st:
                b = st.pop()
                out.append(b)
                st += self.kids.get(b, [])
            self._sub[bone] = out
        return self._sub[bone]

    def mix(self, a, b, w):
        if w <= 0:
            return copy(a)
        if w >= 1:
            return copy(b)
        R = {}
        for k in a["R"]:
            R[k] = self.rt.slerp_m(a["R"][k], b["R"][k], w) if k in b["R"] else a["R"][k].copy()
        for k in b["R"]:
            if k not in R:
                R[k] = b["R"][k].copy()
        return {"R": R, "hips": a["hips"] * (1 - w) + b["hips"] * w}

    def fk(self, v, pose):
        return self.rigs[v].solve(pose["R"], {"hips": pose["hips"] * self.ctx.lk[v]})[0]

    def Q(self, pose, bone):
        """World rotation of a bone away from rest."""
        return pose["R"][bone] @ self.ax(bone).T if bone in pose["R"] else np.eye(3)

    # ------------------------------------------------------------ verbs
    def bend(self, pose, bone, axis, deg):
        D = rot(axis, deg)
        for b in self.sub(bone):
            if b in pose["R"]:
                pose["R"][b] = D @ pose["R"][b]
            elif b == bone:
                pose["R"][b] = D @ self.ax(b)
        return pose

    def finger_set(self, pose, side, Qh, spec=None):
        """Finger bones for a hand turned by Qh from rest. spec: {finger: (curl1, curl2, splay)}
        in degrees ON TOP of the relaxed rest curl (negative straightens)."""
        spec = spec or {}
        _, _, n0 = hand_frame(self.Jr, side)
        for f in FINGERS:
            b1, b2 = f"finger_{f}_1_{side}", f"finger_{f}_2_{side}"
            y1, y2 = self.ax(b1)[:, 1], self.ax(b2)[:, 1]
            if f == "thumb":
                h = np.cross(y1, y2)
                h = norm(h) if np.linalg.norm(h) > 1e-4 else norm(np.cross(y1, n0))
            else:
                h = norm(np.cross(y1, n0))                # + curls toward the palm
            c1, c2, sp = (tuple(spec.get(f, (0.0, 0.0, 0.0))) + (0.0,))[:3]
            S = rot(n0, sp * sgn(side)) if sp else np.eye(3)
            pose["R"][b1] = Qh @ S @ rot(h, c1) @ self.ax(b1)
            pose["R"][b2] = Qh @ S @ rot(h, c1 + c2) @ self.ax(b2)

    def arm(self, pose, side, u, f, hand=None, wrist=A.WRIST_RELAXED, pro=0.0, hint=None, fingers=None):
        """Upper arm along u, forearm along f (world). hand: (finger direction, palm normal) in
        world, or None for the forearm's line with `wrist` = (flex, radial deviation, twist)."""
        d0 = self.Jr[f"d0_{side}"]
        u, f = norm(u), norm(f)
        su = f - u * (f @ u)
        if np.linalg.norm(su) < 1e-3:
            su = np.asarray(hint if hint is not None else FWD, float)
            su = su - u * (su @ u)
        su = norm(su)
        sf = -u - f * (-u @ f)
        sf = norm(sf) if np.linalg.norm(sf) > 1e-3 else su
        if pro:
            sf = rot(f, pro) @ sf
        Qu = A.align(d0, FWD, u, su)
        Qf = A.align(d0, FWD, f, sf)
        if hand is None:
            flex, rad, tw = wrist
            lat0 = norm(np.cross(d0, FWD))
            psg = 1.0 if side == "R" else -1.0
            Qh = Qf @ rot(FWD, psg * flex) @ rot(lat0, rad) @ rot(d0, tw)
        else:
            _, _, n0 = hand_frame(self.Jr, side)
            Qh = A.align(d0, n0, hand[0], hand[1])
        pose["R"][f"upperarm_{side}"] = Qu @ self.ax(f"upperarm_{side}")
        pose["R"][f"forearm_{side}"] = Qf @ self.ax(f"forearm_{side}")
        pose["R"][f"hand_{side}"] = Qh @ self.ax(f"hand_{side}")
        self.finger_set(pose, side, Qh, fingers)
        return pose

    def arm_chest(self, pose, side, a, fingers=None):
        """An arm written the way npc/anim.py writes them (u, e, hint, tw, wrist, pro in chest
        space): the fanning arm of `fan`, the relaxed arm."""
        Qc = self.Q(pose, "chest")
        u = norm(Qc @ np.asarray(a["u"], float))
        hint = Qc @ np.asarray(a.get("hint", FWD), float)
        su = norm(hint - u * (hint @ u))
        if a.get("tw"):
            su = rot(u, a["tw"]) @ su
        e = math.radians(a.get("e", 10.0))
        f = u * math.cos(e) + su * math.sin(e)
        return self.arm(pose, side, u, f, wrist=a.get("wrist", (0.0, 0.0, 0.0)), pro=a.get("pro", 0.0), hint=hint,
                        fingers=fingers)

    def reach(self, pose, side, wrist_fn, pole, hand=None, tag=None, **kw):
        """Arm IK to wrist_fn(variant, fk pose) -> world point, solved on every rig; the upper-arm
        and forearm directions are averaged (one set of rotations serves all five). `pole`: the
        way the elbow points (world). Records the worst miss per variant under `tag`."""
        up, fo = f"upperarm_{side}", f"forearm_{side}"
        us, fs, data = [], [], {}
        for v in self.ctx.order:
            P = self.fk(v, pose)
            S = P[up][:3, 3]
            W = np.asarray(wrist_fn(v, P), float)
            rg = self.rigs[v]
            L1 = np.linalg.norm(rg.head(fo) - rg.head(up))
            L2 = np.linalg.norm(rg.head(f"hand_{side}") - rg.head(fo))
            E, W2 = self.rt.two_bone(S, W, L1, L2, np.asarray(pole, float), reach=0.985)
            us.append(norm(E - S))
            fs.append(norm(W2 - E))
            data[v] = (S, W, L1, L2)
        u, f = norm(np.mean(us, axis=0)), norm(np.mean(fs, axis=0))
        self.arm(pose, side, u, f, hand=hand, **kw)
        if tag:
            for v, (S, W, L1, L2) in data.items():
                e = float(np.linalg.norm(S + L1 * u + L2 * f - W)) * 100
                self.err.setdefault(tag, {})[v] = round(max(self.err.get(tag, {}).get(v, 0.0), e), 1)
        return pose

    def face(self, v, P, dx, dy, dz):
        """A point given in head lengths from the head joint (x to the character's left, y back,
        z up, in the head's own frame): the mouth is about (0, -0.48, 0.10), an eye
        (+-0.17, -0.47, 0.36)."""
        hd = self.J[v]["P"]["head"]
        Qh = P["head"][:3, :3] @ self.rigs[v].axes("head").T
        return P["head"][:3, 3] + Qh @ (np.array([dx, dy, dz]) * hd)

    def hand_len(self, v):
        return self.J[v]["P"]["hand"]

    # ------------------------------------------------------------ poses -> Motion
    def motion(self, name, poses, loop):
        n = len(poses) - 1
        mo = self.ctx.blank(name, n)
        if loop:
            poses[n] = poses[0]
        bones = set()
        for p in poses:
            bones |= set(p["R"])
        for b in bones:
            mo.R[b] = np.array([p["R"][b] if b in p["R"] else self.ax(b) for p in poses])
        mo.hips = np.array([p["hips"] for p in poses], float)
        return mo


def ease(keys, t):
    """keys: [(time, value)] with scalar values; smoothstep between neighbours, held outside."""
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, a), (t1, b) in zip(keys, keys[1:]):
        if t <= t1:
            return a + (b - a) * float(smooth(t0, t1, t))
    return keys[-1][1]


def grip(ctx, mo, side, amount=1.0):
    """Close the fingers of a Motion's hand round a stick (amount 0..1), whatever the hand does."""
    kit = Kit(ctx)
    spec = {f: (38.0 * amount, 34.0 * amount, 0.0) for f in FINGERS}
    spec["thumb"] = (22.0 * amount, 26.0 * amount, 0.0)
    hb = f"hand_{side}"
    for i in range(mo.n + 1):
        p = {"R": {}}
        kit.finger_set(p, side, mo.R[hb][i] @ kit.ax(hb).T, spec)
        for b, R in p["R"].items():
            mo.R[b][i] = R


RELAXED = {f: (0.0, 0.0, 0.0) for f in FINGERS}
FIST = {"thumb": (20.0, 30.0, 0.0), "index": (48.0, 42.0, 0.0), "middle": (46.0, 40.0, 0.0), "ring": (42.0, 38.0, 0.0),
        "pinky": (40.0, 36.0, 0.0)}
SOFT = {"thumb": (6.0, 8.0, 0.0), "index": (14.0, 10.0, 0.0), "middle": (16.0, 12.0, 0.0), "ring": (16.0, 12.0, 0.0),
        "pinky": (16.0, 12.0, 0.0)}
OPEN = {"thumb": (-6.0, -10.0, 0.0), "index": (-14.0, -22.0, 2.0), "middle": (-18.0, -26.0, 0.0), "ring": (-22.0, -28.0, -2.0),
        "pinky": (-26.0, -30.0, -4.0)}
# V sign: index and middle straight and spread, ring and little finger folded, thumb across them.
VSIGN = {"index": (-20.0, -36.0, 9.0), "middle": (-26.0, -42.0, -8.0), "ring": (52.0, 46.0, 0.0), "pinky": (48.0, 42.0, 0.0),
         "thumb": (34.0, 44.0, 0.0)}


# ---------------------------------------------------------------- standing clips


def yawn(kit, B, T=3.2):
    """One-shot: a stretch (chest back, left arm out and back), the right hand to the mouth."""
    def wrist(v, P):
        hl = kit.hand_len(v)
        m = kit.face(v, P, 0.0, -0.48, 0.05)
        return m + np.array([-0.02, -0.035, 0.0]) - hd * 0.50 * hl

    hd, hn = norm([0.55, -0.10, 0.83]), norm([0.10, 1.0, 0.05])
    K = copy(B)
    kit.bend(K, "spine", X, -4.0)
    kit.bend(K, "chest", X, -7.0)
    kit.bend(K, "neck", X, -6.0)
    kit.bend(K, "head", X, -9.0)
    kit.bend(K, "shoulder_R", Y, 6.0)
    kit.bend(K, "shoulder_L", Y, -8.0)
    kit.reach(K, "R", wrist, (-0.9, 0.2, -0.5), hand=(hd, hn), tag="yawn hand to mouth", fingers=SOFT)
    kit.arm(K, "L", norm([0.40, 0.30, -0.86]), norm([0.50, 0.10, -0.86]), wrist=(-28.0, 0.0, 0.0), fingers=OPEN)
    n = int(round(T * FPS))
    out = []
    for i in range(n + 1):
        t = i / FPS
        w = ease([(0.0, 0.0), (0.95, 1.0), (2.05, 1.0), (T - 0.05, 0.0)], t)
        p = kit.mix(B, K, w)
        s = math.sin(math.pi * float(np.clip((t - 0.6) / 1.7, 0, 1)))      # the yawn swells and fades
        kit.bend(p, "chest", X, -3.0 * s)
        kit.bend(p, "head", X, -5.0 * s)
        out.append(p)
    return kit.motion("yawn", out, False), dict(duration=T, loop=False)


def cry(kit, B, T=2.0):
    """Loop: head down, both fists at the eyes, shoulders bobbing with the sobs."""
    def wrist(side):
        hd = norm([0.42 * -sgn(side), -0.05, 0.90])

        def fn(v, P):
            hl = kit.hand_len(v)
            eye = kit.face(v, P, 0.17 * sgn(side), -0.50, 0.33)
            Qh = P["head"][:3, :3] @ kit.rigs[v].axes("head").T
            return eye + Qh @ np.array([0.0, -0.030, 0.0]) - (Qh @ hd) * 0.42 * hl
        return fn, hd

    K = copy(B)
    kit.bend(K, "spine", X, 5.0)
    kit.bend(K, "chest", X, 9.0)
    kit.bend(K, "neck", X, 10.0)
    kit.bend(K, "head", X, 14.0)
    Qh = kit.Q(K, "head")
    for side in ("L", "R"):
        kit.bend(K, f"shoulder_{side}", Y, -9.0 * sgn(side))
        fn, hd = wrist(side)
        kit.reach(K, side, fn, (0.8 * sgn(side), 0.25, -0.6), hand=(Qh @ hd, Qh @ norm([0.0, 1.0, 0.12])),
                  tag=f"cry fist to eye {side}", fingers=FIST)
    n = int(round(T * FPS))
    out = []
    for i in range(n + 1):
        w = 2 * math.pi * i / n
        p = copy(K)
        sob = max(0.0, math.sin(4 * w)) ** 1.5                # four sobs per loop
        kit.bend(p, "chest", X, 1.5 * math.sin(w) + 2.2 * sob)
        kit.bend(p, "head", X, 1.5 * math.sin(2 * w + 0.6))
        kit.bend(p, "head", Y, 2.0 * math.sin(w + 0.4))
        for side in ("L", "R"):
            kit.bend(p, f"shoulder_{side}", Y, -4.0 * sgn(side) * sob)
        out.append(p)
    return kit.motion("cry", out, True), dict(duration=T, loop=True)


def peace(kit, B, T=2.4):
    """One-shot: right hand up beside the face in a V sign, held about a second."""
    hd, hn = norm([-0.22, -0.06, 0.97]), norm([0.10, -1.0, 0.0])

    def wrist(v, P):
        return kit.face(v, P, -0.70, -0.16, -0.18)

    K = copy(B)
    kit.bend(K, "chest", Z, -4.0)
    kit.bend(K, "head", Y, -7.0)
    kit.bend(K, "head", Z, -3.0)
    kit.bend(K, "shoulder_R", Y, 5.0)
    kit.reach(K, "R", wrist, (-0.75, 0.35, -0.55), hand=(hd, hn), tag="peace hand beside face", fingers=VSIGN)
    n = int(round(T * FPS))
    out = []
    for i in range(n + 1):
        t = i / FPS
        w = ease([(0.0, 0.0), (0.5, 1.0), (1.7, 1.0), (T - 0.05, 0.0)], t)
        p = kit.mix(B, K, w)
        live = math.sin(2 * math.pi * (t - 0.5) / 0.6) * float(smooth(0.5, 0.7, t) * (1 - smooth(1.5, 1.7, t)))
        kit.bend(p, "forearm_R", Y, 2.5 * live)
        kit.bend(p, "head", Y, -1.0 * live)
        out.append(p)
    return kit.motion("peace", out, False), dict(duration=T, loop=False, hold=[0.5, 1.7])


def pick_up(kit, B, T=2.4):
    """One-shot: crouch, reach to the ground with the right hand, stand."""
    hd, hn = norm([0.0, -0.45, -0.89]), norm([0.0, 0.89, -0.45])

    def wrist(v, P):
        lk, hl = kit.J[v]["lk"], kit.hand_len(v)
        return np.array([-0.13 * lk, -0.40 * lk, 0.012 + 0.80 * hl * 0.89])

    K = copy(B)
    K["hips"] = B["hips"] + np.array([0.0, 0.13, -0.45])
    kit.bend(K, "hips", X, 30.0)
    kit.bend(K, "spine", X, 22.0)
    kit.bend(K, "chest", X, 14.0)
    kit.bend(K, "neck", X, -8.0)
    kit.bend(K, "head", X, -14.0)
    kit.bend(K, "chest", Z, 8.0)
    kit.reach(K, "R", wrist, (-0.9, 0.5, 0.2), hand=(hd, hn), tag="pick_up hand to ground", fingers=SOFT)
    kit.arm(K, "L", norm([0.30, -0.55, -0.78]), norm([-0.35, -0.90, 0.05]), wrist=(10.0, 0.0, 0.0), fingers=SOFT)
    n = int(round(T * FPS))
    out = []
    for i in range(n + 1):
        t = i / FPS
        w = ease([(0.0, 0.0), (0.95, 1.0), (1.25, 1.0), (T - 0.1, 0.0)], t)
        p = kit.mix(B, K, w)
        # the fingers close on the thing as the hand leaves the ground
        g = float(smooth(1.0, 1.3, t) * (1 - smooth(T - 0.5, T - 0.1, t)))
        if g > 0:
            Qh = kit.Q(p, "hand_R")
            kit.finger_set(p, "R", Qh, {f: tuple(np.array(SOFT[f]) * (1 - g) + np.array(FIST[f]) * 0.7 * g) for f in FINGERS})
        out.append(p)
    return kit.motion("pick_up", out, False), dict(duration=T, loop=False, touch=[0.95, 1.25])


# ---------------------------------------------------------------- seated clips


def seated(kit, B, slope=SIT_SLOPE, slump=0.0):
    """The seated base pose: thighs forward (sloping `slope` degrees down to the knees), shins
    down, feet flat at the root, hips back and down; a relaxed, slightly rounded back."""
    S = copy(B)
    # trunk: start from rest uprightness so the idle's weight shift does not tilt the sitter
    for b in ("hips", "spine", "chest", "neck", "head"):
        S["R"][b] = kit.ax(b).copy()
    for side in ("L", "R"):
        S["R"][f"shoulder_{side}"] = kit.ax(f"shoulder_{side}").copy()
    kit.bend(S, "hips", X, -8.0)
    kit.bend(S, "spine", X, 9.0 + 0.5 * slump)
    kit.bend(S, "chest", X, 4.0 + 0.5 * slump)
    kit.bend(S, "neck", X, 2.0)
    th = math.radians(slope)
    for side in ("L", "R"):
        sg = sgn(side)
        td = norm([0.045 * sg, -math.cos(th), -math.sin(th)])
        sd = norm([0.0, -0.035, -1.0])
        S["R"][f"thigh_{side}"] = A.align(DOWN, X, td, X) @ kit.ax(f"thigh_{side}")
        S["R"][f"shin_{side}"] = A.align(DOWN, X, sd, X) @ kit.ax(f"shin_{side}")
        S["R"][f"foot_{side}"] = rot(Z, 5.0 * sg) @ kit.ax(f"foot_{side}")
    # hips so that the ankles sit at their standing height, the feet where the root is
    S["hips"] = np.zeros(3)
    P = kit.fk("woman", S)
    an = 0.5 * (P["foot_L"][:3, 3] + P["foot_R"][:3, 3])
    rest = 0.5 * (kit.rig.head("foot_L") + kit.rig.head("foot_R"))
    S["hips"] = np.array([0.0, rest[1] - an[1], rest[2] - an[2]])
    return S


def hand_on_knee(kit, S, side, back=0.10, inward=0.0, tag=None, fingers=None):
    def wrist(v, P):
        lk = kit.J[v]["lk"]
        K = P[f"shin_{side}"][:3, 3]
        return K + np.array([-inward * sgn(side) * lk, (back + 0.07) * lk, 0.082 * lk])
    hd = norm([-0.10 * sgn(side), -1.0, -0.22])
    kit.reach(S, side, wrist, (0.9 * sgn(side), 0.5, -0.3), hand=(hd, norm([0.0, -0.22, -1.0])), tag=tag,
              fingers=fingers or SOFT)


def sit(kit, B, T=4.0):
    """Loop: seated, hands on the knees, breathing, a slow glance."""
    S = seated(kit, B)
    for side in ("L", "R"):
        hand_on_knee(kit, S, side, tag=f"sit hand on knee {side}")
    n = int(round(T * FPS))
    out = []
    for i in range(n + 1):
        w = 2 * math.pi * i / n
        p = copy(S)
        br = math.sin(2 * w)
        kit.bend(p, "chest", X, -0.9 * br)
        for side in ("L", "R"):
            kit.bend(p, f"upperarm_{side}", X, 0.9 * br)          # the hands stay on the knees
        kit.bend(p, "neck", Z, 3.0 * math.sin(w + 0.5))
        kit.bend(p, "head", Z, 5.0 * math.sin(w + 0.3))
        kit.bend(p, "head", X, 1.5 * math.sin(2 * w + 1.0))
        out.append(p)
    return kit.motion("sit", out, True), dict(duration=T, loop=True)


def sit_fan(kit, B, T=4.0):
    """Loop: seated, the right hand fanning slowly at chest height (the arm of `fan`)."""
    S = seated(kit, B)
    hand_on_knee(kit, S, "L", tag="sit_fan hand on knee L")
    n = int(round(T * FPS))
    out = []
    for i in range(n + 1):
        w = 2 * math.pi * i / n
        p = copy(S)
        br = math.sin(2 * w)
        kit.bend(p, "chest", X, -0.9 * br)
        kit.bend(p, "upperarm_L", X, 0.9 * br)
        kit.bend(p, "head", Z, -5.0 + 4.0 * math.sin(w + 0.3))
        kit.bend(p, "head", Y, -3.0)
        flap = math.sin(3 * w)                                    # 0.75 Hz: slow
        u = norm(np.array([-0.32, -0.40, -0.86]))
        kit.arm_chest(p, "R", dict(u=u, e=94.0 + 3 * flap, hint=FWD, tw=8.0, wrist=(-10.0 + 28.0 * flap, 0.0, 0.0), pro=-20.0),
                      fingers={f: (22.0, 18.0, 0.0) for f in FINGERS})
        out.append(p)
    return kit.motion("sit_fan", out, True), dict(duration=T, loop=True)


def sit_sleep(kit, B, T=6.0):
    """Loop: seated asleep, head dropped forward and nodding slowly, arms slack in the lap."""
    S = seated(kit, B, slump=14.0)
    kit.bend(S, "neck", X, 16.0)
    kit.bend(S, "head", X, 22.0)
    kit.bend(S, "head", Y, 5.0)
    for side in ("L", "R"):
        def wrist(v, P, side=side):
            lk = kit.J[v]["lk"]
            K, H = P[f"shin_{side}"][:3, 3], P[f"thigh_{side}"][:3, 3]
            m = H + (K - H) * 0.55
            return m + np.array([-0.035 * sgn(side) * lk, 0.0, 0.085 * lk])
        hd = norm([-0.55 * sgn(side), -0.80, -0.20])
        kit.reach(S, side, wrist, (0.9 * sgn(side), 0.6, -0.2), hand=(hd, norm([-0.2 * sgn(side), -0.1, -1.0])),
                  tag=f"sit_sleep hand in lap {side}", fingers={f: (10.0, 8.0, 0.0) for f in FINGERS})
    n = int(round(T * FPS))
    out = []
    for i in range(n + 1):
        w = 2 * math.pi * i / n
        p = copy(S)
        br = math.sin(2 * w)
        kit.bend(p, "chest", X, -1.4 * br)
        for side in ("L", "R"):
            kit.bend(p, f"upperarm_{side}", X, 1.4 * br)
        # the head sinks slowly, catches itself, sinks again (periodic)
        nod = 5.0 * (0.5 - 0.5 * math.cos(w)) ** 2 + 1.2 * math.sin(2 * w)
        kit.bend(p, "neck", X, 0.45 * nod)
        kit.bend(p, "head", X, 0.55 * nod)
        kit.bend(p, "head", Y, 1.5 * math.sin(w))
        out.append(p)
    return kit.motion("sit_sleep", out, True), dict(duration=T, loop=True)


STANDING = (("yawn", yawn), ("cry", cry), ("peace", peace), ("pick_up", pick_up))
SEATED = (("sit", sit), ("sit_fan", sit_fan), ("sit_sleep", sit_sleep))


def build(ctx):
    """All seven clips as Motions on the carrier rig. Returns {name: (motion, meta)} and the
    per-variant IK misses (cm) of the averaged reaches."""
    kit = Kit(ctx)
    B = ctx.idle_pose
    out = {}
    for name, fn in STANDING:
        mo, meta = fn(kit, B)
        info = ctx.finish_standing(mo, meta["loop"])
        if not meta["loop"]:
            ctx.pin_ends(mo)
        meta["hipDropMm"] = info.get("hipDropMm")
        out[name] = (mo, meta)
    for name, fn in SEATED:
        mo, meta = fn(kit, B)
        meta["seated"] = True
        out[name] = (mo, meta)
    return out, kit.err
