"""The townspeople's shared clips: Mixamo motion retargeted with tools/blender/mixamo/retarget.py.

One clip set for all five variants. Everything is solved ONCE on the carrier rig (the woman) and
baked as rotations plus a hips translation. That plays on every variant because

  - bone names, parents, rest directions and rolls are identical (asserted in build.py), and
  - each variant's legs and pelvis height are the woman's scaled by one number, lk = hip / 0.80
    (rig.skeleton), so a hips translation of t metres on the woman must be t * lk on a variant.
    The GLB carries that factor in the rest pose (root bone scale lk, hips bone scale 1 / lk, see
    glbtools.leg_units), so the game needs to do nothing: the same hips track puts every
    variant's soles on the floor.

What is per variant is checked per variant: arms are pushed out of each variant's own body
(clear_arms on each rig), and glbcheck.py measures feet and slip on the exported GLB.

  idle      loop      idle.fbx    (Breathing Idle)
  walk      loop      walk.fbx    (Standard Walk, in place)        -> clipSpeed.walk
  walk_f    loop      walk_f.fbx  (Female Normal Walk, in place)   -> clipSpeed.walk_f
  run       loop      run.fbx     (Jogging, in place), 60 Hz keys  -> clipSpeed.run
  talk      loop      talk.fbx    gestures kept inside the shoulders
  look      loop      look.fbx    turn limited to about 68 degrees at the head
  wave / bow / eat / cheer / point   one-shots that start and end on the idle's first pose
  call / fan / lookup               the existing hand-made loops (npc/anim.py), re-baked: their
                                    root bob is now the hips translation
  sparkler                          the new walk with the hand-made sparkler arm
  sit / sit_fan / sit_sleep / yawn / cry / pick_up / peace   hand-made (npc/handmade.py)

The raw FBX files live in assets/mixamo (gitignored, never shipped); retarget.load_fbx() samples a
clip and deletes the import, so no Mixamo bone, mesh or action reaches the GLB.
"""
import math
import os
import sys

import bpy
import numpy as np

from . import anim as A
from . import rig as RIG
from .geo import smooth

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
MIXAMO_PY = os.path.join(REPO, "tools", "blender", "mixamo")
MIXAMO_FBX = os.path.join(REPO, "assets", "mixamo")
if MIXAMO_PY not in sys.path:
    sys.path.insert(0, MIXAMO_PY)

REF = "woman"
# Standing stance of every standing clip (offsets from the rest foot position, toe-out in degrees).
# It is the stance of the hand-made clips (anim.stance), so crossfades never slide a foot.
STANCE = {"L": (0.0, -0.03, 7.0), "R": (0.0, 0.03, -7.0)}
HANG = {"sleeve_L1": 0.85, "sleeve_R1": 0.85}
# Ground speed of the walk clips on the woman (m/s at rate 1); other variants get lk times that.
# 0.90 is what the hand-made walk had, so the game's speed table stays valid.
WALK_SPEED = 0.90
RUN_SPEED = 1.85

# frames: cycle length at 30 fps. speed: target ground speed on the woman; the stride scale that
# gives it is solved (yukata hems are narrow: the Mixamo stride, made for trousers, is shortened).
CLIPS = {
    "idle": dict(src="idle", mode="planted", loop=True, gains={"hips": 0.6}, hips_gain=(0.18, 0.4, 1.0)),
    "walk": dict(src="walk", mode="locomotion", loop=True, frames=28, speed=WALK_SPEED, stance_x=0.062,
                 toe_yaw=4.0, swing_scale=0.45, min_lift=0.03, max_lift=0.06, pitch_gain=0.2, knee_spread=0.25,
                 hips_drop=-0.02, stance_fwd=-0.02, knee_out=0.02, reach=0.985, level=0.5,
                 gains={"hips": 0.55, "spine": 0.55, "chest": 0.6}, hips_gain=(0.45, 0.6, 0.7),
                 amp={"upperarm_L": 0.75, "upperarm_R": 0.75}, lateral_scale=0.25, clear_thr=0.045, vel_tol=0.6),
    "walk_f": dict(src="walk_f", mode="locomotion", loop=True, frames=26, speed=WALK_SPEED, stance_x=0.050,
                   toe_yaw=3.0, swing_scale=0.45, min_lift=0.03, max_lift=0.06, pitch_gain=0.2, knee_spread=0.25,
                   hips_drop=-0.02, stance_fwd=-0.02, knee_out=0.02, reach=0.985, level=0.5,
                   gains={"hips": 0.55, "spine": 0.5, "chest": 0.55}, hips_gain=(0.45, 0.6, 0.7),
                   lateral_scale=0.25, clear_thr=0.045, vel_tol=0.6),
    # run.fbx (Jogging) holds three strides: one is cut out (cycles=3) and its ends closed.
    "run": dict(src="run", mode="locomotion", loop=True, cycles=3, frames=12, key_rate=60, extend=2, pitch_ramp=6,
                speed=RUN_SPEED, stance_x=0.050, toe_yaw=2.0, swing_scale=0.40, min_lift=0.045, max_lift=0.09,
                pitch_gain=0.2, knee_spread=0.2, hips_drop=-0.03, stance_fwd=0.08, knee_out=0.02, reach=0.965,
                level=0.3, hips_gain=(0.4, 0.5, 0.6), gains={"hips": 0.6, "spine": 0.6, "chest": 0.65, "neck": 0.8},
                amp={"upperarm_L": 0.6, "upperarm_R": 0.6, "forearm_L": 0.7, "forearm_R": 0.7},
                lateral_scale=0.2, pitch_limits=(-30.0, 8.0)),
    "talk": dict(src="talk", mode="planted", loop=True, trim=(20, 225), close=14, gains={"hips": 0.6},
                 hips_gain=(0.5, 0.5, 1.0), amp={"upperarm_L": 0.6, "upperarm_R": 0.6, "forearm_L": 0.8, "forearm_R": 0.8},
                 inside_shoulders=True),
    "look": dict(src="look", mode="planted", loop=True, gains={"hips": 0.45}, hips_gain=(0.4, 0.3, 0.3),
                 turn={"hips": 6.0, "spine": 16.0, "chest": 28.0, "neck": 48.0, "head": 68.0},
                 tilt={"spine": 0.8, "chest": 0.7, "neck": 0.5, "head": 0.45}),
    "wave": dict(src="wave", mode="planted", loop=False, repeat=3.5, edge=(9, 11), gains={"hips": 0.6}),
    "bow": dict(src="bow", mode="planted", loop=False, trim=(10, 78), edge=(6, 8), hips_gain=(0.5, 0.6, 1.0)),
    # The source drinks from a cup and lifts the hand to the brow of our larger heads: while the hand
    # is up, the arm is steered to each variant's own mouth (to_mouth).
    "eat": dict(src="eat", mode="planted", loop=False, trim=(56, 174), edge=(10, 10), gains={"hips": 0.6},
                hips_gain=(0.5, 0.5, 1.0), to_mouth="L"),
    "cheer": dict(src="cheer", mode="planted", loop=False, edge=(8, 10), hips_gain=(0.4, 0.4, 0.8),
                  gains={"hips": 0.6, "spine": 0.7, "chest": 0.8}),
    "point": dict(src="point", mode="planted", loop=False, trim=(6, 74), edge=(6, 7), gains={"hips": 0.6},
                  hips_gain=(0.5, 0.5, 1.0)),
}
MOCAP_ORDER = ("idle", "walk", "walk_f", "run", "talk", "look", "wave", "bow", "eat", "cheer", "point")
LEGACY = (("call", 90), ("fan", 120), ("lookup", 120))     # anim.py clips kept as they were
LOCO = ("walk", "walk_f", "run", "sparkler")


def require_fbx():
    """Stop before anything is built if a raw clip is missing."""
    need = sorted({c["src"] + ".fbx" for c in CLIPS.values()})
    missing = [f for f in need if not os.path.isfile(os.path.join(MIXAMO_FBX, f))]
    if missing:
        raise SystemExit(
            "[people] cannot build the clips: missing Mixamo FBX file(s) in " + MIXAMO_FBX + ":\n    "
            + ", ".join(missing) + "\n  The raw clips are not in the repository (Adobe's terms). Download them again "
            "as listed in assets/mixamo/MANIFEST.md (FBX Binary, Without Skin, 30 fps), then rebuild.")


class View:
    """A Motion as another variant plays it: the same rotations (shared arrays, so edits made
    through the view stay in the motion) and the hips travel scaled by that variant's legs."""

    def __init__(self, mo, k):
        self.mo, self.R, self.n, self.fps, self.name = mo, mo.R, mo.n, mo.fps, mo.name
        self.hips = mo.hips * k


def body_section_fn(ob, J):
    """body(z) -> (half-width, half-depth, centre y) of a variant's clothed trunk and skirt at
    height z, measured on its near mesh (vertices owned by hips / spine / chest / thighs); None
    above the armpits and below the knees, where arms are free."""
    me = ob.data
    own = {"hips", "spine", "chest", "thigh_L", "thigh_R"}
    gname = {g.index: g.name for g in ob.vertex_groups}
    pts = []
    for v in me.vertices:
        best, bw = None, 0.0
        for e in v.groups:
            if e.weight > bw:
                best, bw = gname[e.group], e.weight
        if best in own:
            pts.append(tuple(v.co))
    P = np.array(pts)
    lk = J["lk"]
    z0, z1 = J["knee_z"], J["shoulder_z"] - 0.05 * lk
    zs = np.arange(z0, z1 + 0.02, 0.02)
    rows = []
    for z in zs:
        s = P[np.abs(P[:, 2] - z) < 0.025]
        if len(s) < 6:
            rows.append(rows[-1] if rows else (0.1 * lk, 0.08 * lk, 0.0))
            continue
        rows.append((float(np.abs(s[:, 0]).max()), float((s[:, 1].max() - s[:, 1].min()) / 2),
                     float((s[:, 1].max() + s[:, 1].min()) / 2)))
    rows = np.array(rows)
    fade0 = z1 - 0.10 * lk

    def body(z):
        if z < z0 or z > z1:
            return None
        f = float(1 - smooth(fade0, z1, z))
        a, b, yc = (float(np.interp(z, zs, rows[:, k])) for k in range(3))
        return a * f, b * f, yc
    return body


class Ctx:
    """Everything the clip builders share: one retarget Rig per variant, the bone map, the leg
    scale per variant, each variant's body cross-section."""

    def __init__(self, arms, bodies, nears, getas):
        import importlib
        import retarget as rt
        importlib.reload(rt)
        self.rt = rt
        self.arms, self.J = arms, {v: bodies[v].J for v in arms}
        self.order = list(arms)
        self.rigs = {v: rt.Rig(arms[v]) for v in arms}
        self.rig = self.rigs[REF]
        self.arm = arms[REF]
        self.lk = {v: self.J[v]["lk"] / self.J[REF]["lk"] for v in arms}
        self.spec = rt.load_spec(os.path.join(MIXAMO_PY, "maps", "people.json"))
        sole = rt.sole_from_mesh(getas[REF], {"R": "foot_R"})["R"]
        # The left geta is part of the body mesh and is the right one mirrored.
        self.spec["sole"] = {"R": sole, "L": [[-p[0], p[1], p[2]] for p in sole]}
        self.body = {v: body_section_fn(nears[v], self.J[v]) for v in arms}
        self.cache = {}
        self.idle_pose = None
        self.report = {}

    def view(self, mo, v):
        return View(mo, self.lk[v])

    def source(self, name):
        if name not in self.cache:
            self.cache[name] = self.rt.load_fbx(os.path.join(MIXAMO_FBX, name + ".fbx"))
        return self.cache[name]

    # ------------------------------------------------------------ passes shared by every clip
    def clear_arms(self, mo):
        """Arms out of every variant's own body: the same rotations put a wrist somewhere else
        on each of them, so each rig pushes in turn (a push only ever moves an arm outward)."""
        moved = {}
        for _ in range(2):
            for v in self.order:
                m = self.rt.clear_arms(self.view(mo, v), self.rigs[v], self.spec, self.body[v])
                moved[v] = round(max(moved.get(v, 0.0), m * 100), 1)
        return moved

    def inside_shoulders(self, mo, floor=0.55):
        """Talk: keep the wrists inside the shoulders' width (soft limit), on every variant."""
        rt = self.rt
        worst = 0.0
        for v in self.order:
            rig, J = self.rigs[v], self.J[v]
            lim = J["P"]["shw"]
            vw = self.view(mo, v)
            for i in range(mo.n + 1):
                pose, _ = rig.solve({b: R[i] for b, R in mo.R.items()}, {"hips": vw.hips[i]})
                for sf, a in self.spec["arms"].items():
                    S, E, W = (pose[a[k]][:3, 3] for k in ("upper", "fore", "hand"))
                    x = abs(W[0])
                    knee = floor * lim
                    if x <= knee:
                        continue
                    x2 = knee + (lim - knee) * math.tanh((x - knee) / (lim - knee))
                    worst = max(worst, x - x2)
                    W2 = np.array([math.copysign(x2, W[0]), W[1], W[2]])
                    L1, L2 = np.linalg.norm(E - S), np.linalg.norm(W - E)
                    E2, W2 = rt.two_bone(S, W2, L1, L2, E - S, reach=0.98)
                    mo.R[a["upper"]][i] = rt.rot_between(E - S, E2 - S) @ mo.R[a["upper"]][i]
                    mo.R[a["fore"]][i] = rt.rot_between(W - E, W2 - E2) @ mo.R[a["fore"]][i]
        return round(worst * 100, 1)

    def finish_standing(self, mo, loop, clear=True):
        """Feet planted on the common stance, then the arm clearance. Returns the clip facts."""
        info = self.rt.plant_feet(mo, self.rig, self.spec, mode="planted", stance=STANCE, reach=0.99, cyclic=loop,
                                  knee_out=0.05)
        if clear:
            info["armPushCm"] = self.clear_arms(mo)
        return info

    def pin_ends(self, mo, k=4):
        """One-shots: the first and last key become exactly the idle's finished first pose (legs,
        hips and cleared arms included); the few keys next to them ease into it. The difference
        being removed is under a millimetre (the hip-height smoothing looks at neighbours)."""
        ref = self.idle_final
        for i in list(range(k)) + list(range(mo.n - k + 1, mo.n + 1)):
            w = float(smooth(0, k, min(i, mo.n - i)))
            for b in mo.R:
                if b in ref["R"]:
                    mo.R[b][i] = self.rt.slerp_m(ref["R"][b], mo.R[b][i], w)
            mo.hips[i] = ref["hips"] * (1 - w) + mo.hips[i] * w

    def blank(self, name, n, fps=A.FPS):
        """An empty Motion with what plant_feet(mode="planted") needs."""
        rt = self.rt
        mo = rt.Motion(name, n, fps)
        legs = self.spec["legs"]
        mo.k = 1.0
        for sf in legs:
            mo.foot[sf] = {"pole": np.zeros((n + 1, 3))}
        return mo

    def bake(self, name, mo, loop, hang=HANG):
        return self.rt.bake_action(self.arm, name, mo, self.rig, self.spec, loop=loop, hang=hang)


# ---------------------------------------------------------------- Mixamo clips


def retarget_clip(ctx, name):
    """One clip: load -> rotation retarget -> (loop / one-shot shaping) -> feet -> arms."""
    rt, rig, spec = ctx.rt, ctx.rig, ctx.spec
    cfg = CLIPS[name]
    src = ctx.source(cfg["src"])
    trim = cfg.get("trim")
    if cfg.get("repeat"):
        L = src.n - 1                                   # a short source loop played several times
        m = int(round(L * cfg["repeat"]))
        src = src.resampled(np.arange(m + 1) % L)
        trim = None
    if cfg.get("cycles"):
        # The source holds several strides: take the one whose two ends match best.
        L = (src.n - 1) / cfg["cycles"]
        best = (1e9, 0)
        for a in range(0, int(src.n - 1 - L) + 1):
            two = src.resampled(np.array([a, a + L, a + 1, a + L + 1.0]))
            d = two.pose_distance(0, 1) + 0.6 * two.pose_distance(2, 3)
            if d < best[0]:
                best = (d, a)
        trim = (best[1], best[1] + L)
    mo = rt.transfer(src, rig, spec, frames=cfg.get("frames"), trim=trim, gains=cfg.get("gains"),
                     hips_gain=cfg.get("hips_gain", (1.0, 1.0, 1.0)), name=name, amp=cfg.get("amp"),
                     key_rate=cfg.get("key_rate", A.FPS), hips_origin="mean" if cfg["loop"] else "ends")
    if cfg.get("cycles"):
        mo.close_loop(max(2, mo.n // 3))
    if cfg["mode"] == "locomotion":
        keys = ("stance_x", "toe_yaw", "swing_scale", "min_lift", "max_lift", "pitch_gain", "knee_spread", "knee_out",
                "reach", "level", "lateral_scale", "pitch_limits", "clear_thr", "vel_tol", "extend", "pitch_ramp",
                "hips_drop", "stance_fwd")
        kw = {k: cfg[k] for k in keys if k in cfg}
        # The stride scale that gives the wanted ground speed on the carrier.
        _, v_src = rt.detect_stance(mo, kw.get("clear_thr", 0.03), kw.get("vel_tol", 0.45))
        stride = cfg["speed"] / (v_src * mo.k)
        info = rt.plant_feet(mo, rig, spec, mode="locomotion", stride_scale=stride, **kw)
        info["strideScale"] = round(stride, 3)
        info["armPushCm"] = ctx.clear_arms(mo)
    else:
        if cfg.get("turn"):
            info_turn = rt.limit_turn(mo, rig, cfg["turn"], tilt=cfg.get("tilt"))
        if cfg["loop"] and cfg.get("close"):
            mo.close_loop(cfg["close"])
        if not cfg["loop"]:
            mo.blend_edges(ctx.idle_pose, cfg["edge"][0], ctx.idle_pose, cfg["edge"][1])
        if name == "idle":
            ctx.idle_pose = mo.pose(0)
        if cfg.get("to_mouth"):
            to_mouth(ctx, mo, cfg["to_mouth"])
        if cfg.get("inside_shoulders"):
            pulled = ctx.inside_shoulders(mo)
        info = ctx.finish_standing(mo, cfg["loop"])
        if cfg.get("inside_shoulders"):
            info["wristPullCm"] = max(pulled, ctx.inside_shoulders(mo))
        if name == "idle":
            ctx.idle_final = mo.pose(0)
        if not cfg["loop"]:
            ctx.pin_ends(mo)
        if cfg.get("turn"):
            info["turnDeg"] = info_turn
    info["loop"] = cfg["loop"]
    return mo, info


def to_mouth(ctx, mo, side):
    """Eat: wherever the source lifts the hand above the chest, steer the wrist to a point just in
    front of and below the mouth, solved on every variant (handmade.Kit.reach). The hand keeps the
    source's orientation and fingers; the blend follows how high the source hand is."""
    from . import handmade
    kit = handmade.Kit(ctx)
    rig = ctx.rig
    up, fo, hb = f"upperarm_{side}", f"forearm_{side}", f"hand_{side}"
    sx = 1.0 if side == "L" else -1.0
    z0 = rig.head("chest")[2] + 0.10
    z1 = rig.head("neck")[2] - 0.02
    keep = [b for b in mo.R if b == hb or (b.startswith("finger_") and b.endswith("_" + side))]
    for i in range(mo.n + 1):
        p = mo.pose(i)
        z = rig.solve(p["R"], {"hips": p["hips"]})[0][hb][2, 3]
        w = float(smooth(z0, z1, z))
        if w <= 0:
            continue
        q = handmade.copy(p)
        kit.reach(q, side, lambda v, P: kit.face(v, P, 0.12 * sx, -0.66, -0.24), (0.9 * sx, 0.3, -0.5), tag="eat hand to mouth")
        for b in (up, fo):
            mo.R[b][i] = ctx.rt.slerp_m(p["R"][b], q["R"][b], w)
        for b in keep:
            mo.R[b][i] = p["R"][b]


# ---------------------------------------------------------------- the hand-made clips of anim.py


def legacy_motion(ctx, name, n, fk):
    """A clip of npc/anim.py as a Motion: every bone's world orientation, and its root bob as the
    hips translation (the root bone is no longer keyed)."""
    out, meta = A.build_clip(name, n, fk)
    mo = ctx.rt.Motion(name, n)
    names = [b for b in ctx.rig.order if b != "root"]
    for b in names:
        mo.R[b] = np.array([o[0][b][:3, :3] for o in out])
    mo.hips = np.array([o[2] for o in out], float)
    mo.hips[n] = mo.hips[0]
    return mo, meta


def sparkler_motion(ctx, walk, fk):
    """The new walk with the hand-made sparkler arm: right shoulder, arm and hand keep the pose
    they had relative to the chest in anim.walk_pose(sparkler=True); the fingers close on the
    stick."""
    rt = ctx.rt
    n30 = int(round(walk.n * A.FPS / walk.fps))
    out, _ = A.build_clip("sparkler", n30, fk)
    mo = rt.Motion("sparkler", walk.n, walk.fps)
    mo.R = {b: R.copy() for b, R in walk.R.items()}
    mo.hips, mo.k, mo.foot, mo.info = walk.hips.copy(), walk.k, walk.foot, dict(walk.info)
    arm_bones = ["shoulder_R", "upperarm_R", "forearm_R", "hand_R"] + [b for b in ctx.rig.order if b.startswith("finger_") and b.endswith("_R")]
    for b in arm_bones:
        mo.R[b] = np.zeros((walk.n + 1, 3, 3))
    for i in range(walk.n + 1):
        pose = out[int(round(i * n30 / walk.n)) % n30][0]
        C = walk.R["chest"][i] @ pose["chest"][:3, :3].T
        for b in arm_bones:
            mo.R[b][i] = C @ pose[b][:3, :3]
    from . import handmade
    handmade.grip(ctx, mo, "R", 0.75)
    for b in arm_bones:
        mo.R[b][walk.n] = mo.R[b][0]
    return mo


# ---------------------------------------------------------------- everything, in GLB order

ORDER = ("idle", "walk", "walk_f", "run", "sparkler", "talk", "look", "wave", "bow", "eat", "cheer", "point",
         "call", "fan", "lookup", "sit", "sit_fan", "sit_sleep", "yawn", "cry", "pick_up", "peace")
NOTES = {
    "idle": "breathing idle", "walk": "standard walk", "walk_f": "female walk (women)", "run": "jog; keyed at 60 Hz",
    "sparkler": "the walk with the right arm up drawing small circles (attach the sparkler to hand_R)",
    "talk": "conversation, gestures inside the shoulders", "look": "looking around, head turn limited to about 68 deg",
    "wave": "right hand", "bow": "quick informal bow", "eat": "hand to mouth", "cheer": "two fists pumping",
    "point": "pointing with a bent arm", "call": "cupped hand at the mouth, then a gesture to the side",
    "fan": "idle while fanning with the right hand", "lookup": "looking up at the sky",
    "sit": "seated, hands on knees", "sit_fan": "seated, right hand fanning slowly", "sit_sleep": "seated asleep, nodding",
    "yawn": "stretch, hand to mouth", "cry": "fists at the eyes, shoulders bobbing", "pick_up": "crouch, right hand to the ground",
    "peace": "V sign beside the face, held about a second",
}


def arm_clearance(ctx, mo, step=2):
    """How close elbows, wrists, knuckles and fingertips come to each variant's own trunk/skirt
    (cm; negative = inside the cross-section ellipse) and to its head (cm from a sphere of the
    head's half-width; negative = inside). The smallest value over the clip, per variant."""
    out = {}
    for v in ctx.order:
        rig, body, J = ctx.rigs[v], ctx.body[v], ctx.J[v]
        vw = ctx.view(mo, v)
        hd = J["P"]["head"]
        tip = {}
        for s in ("L", "R"):
            h, t = J["bones"][f"finger_middle_2_{s}"]
            tip[s] = (f"finger_middle_2_{s}", float(np.linalg.norm(np.asarray(t) - np.asarray(h))))
        cb, ch = 1e9, 1e9
        for i in range(0, mo.n + 1, step):
            pose, _ = rig.solve({b: R[i] for b, R in mo.R.items()}, {"hips": vw.hips[i]})
            Qh = pose["head"][:3, :3] @ rig.axes("head").T
            C = pose["head"][:3, 3] + Qh @ np.array([0.0, -0.02 * hd, 0.36 * hd])
            for s in ("L", "R"):
                pts = [pose[f"forearm_{s}"][:3, 3], pose[f"hand_{s}"][:3, 3], pose[f"finger_middle_1_{s}"][:3, 3],
                       pose[tip[s][0]][:3, 3] + pose[tip[s][0]][:3, 1] * tip[s][1]]
                for k, P in enumerate(pts):
                    e = body(P[2])
                    if e is not None and e[0] > 0.02:
                        a, b, yc = e
                        r = math.hypot(P[0] / a, (P[1] - yc) / b)
                        cb = min(cb, (r - 1.0) * min(a, b))
                    if k > 0:
                        ch = min(ch, float(np.linalg.norm(P - C)) - 0.40 * hd)
        out[v] = dict(body_cm=round(cb * 100, 1), head_cm=round(ch * 100, 1))
    return out


def variant_action(action, k, tag):
    """A copy of a clip as a variant with leg scale k plays it in Blender (previews, seat
    measurement): the hips translation times k. In the GLB the rest scales do this."""
    if action is None or abs(k - 1.0) < 1e-6:
        return action
    name = f"_{tag}_{action.name}"
    if name in bpy.data.actions:
        return bpy.data.actions[name]
    a2 = action.copy()
    a2.name = name
    a2.use_fake_user = False
    for layer in a2.layers:
        for st in layer.strips:
            for cb in st.channelbags:
                for fc in cb.fcurves:
                    if fc.data_path == 'pose.bones["hips"].location':
                        for kp in fc.keyframe_points:
                            kp.co[1] *= k
                        fc.update()
    return a2


def drop_variant_actions():
    for a in [a for a in bpy.data.actions if a.name.startswith("_")]:
        bpy.data.actions.remove(a)


def set_action(arm, action, frame=1):
    ad = arm.animation_data or arm.animation_data_create()
    ad.action = action
    if action is not None:
        try:
            ad.action_slot = action.slots[0]
        except Exception:
            pass
    else:
        for pb in arm.pose.bones:
            pb.rotation_quaternion = (1, 0, 0, 0)
            pb.location = (0, 0, 0)
    bpy.context.scene.frame_set(frame)


def seat_heights(ctx, nears, action):
    """Seat height each variant's seated pose implies: the lowest point of the skinned near mesh
    under the hips and the back half of the thighs (m above the root, at scale 1), and how far the
    hip joints sit behind the root."""
    out = {}
    for v in ctx.order:
        arm, ob = ctx.arms[v], nears[v]
        loc0 = tuple(arm.location)
        arm.location = (0, 0, 0)
        set_action(arm, variant_action(action, ctx.lk[v], v), 1)
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        gname = {g.index: g.name for g in ob.vertex_groups}
        own = np.zeros(len(ob.data.vertices), bool)
        for vert in ob.data.vertices:
            best, bw = None, 0.0
            for e in vert.groups:
                if e.weight > bw:
                    best, bw = gname[e.group], e.weight
            own[vert.index] = best in ("hips", "thigh_L", "thigh_R")
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        co = np.zeros(len(me.vertices) * 3)
        me.vertices.foreach_get("co", co)
        ev.to_mesh_clear()
        M = np.array(ob.matrix_world)
        co = co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3]
        pb = arm.pose.bones
        hip = np.array(pb["thigh_L"].head)
        knee = np.array(pb["shin_L"].head)
        sel = own & (co[:, 1] > 0.5 * (hip[1] + knee[1]))
        out[v] = dict(seatHeight=round(float(co[sel, 2].min()), 3), hipsBack=round(float(hip[1]), 3),
                      hipJointHeight=round(float(hip[2]), 3))
        set_action(arm, None)
        arm.location = loc0
    return out


def build(arms, bodies, nears, getas):
    """Retarget, author and bake every clip on the carrier armature. Returns (ctx, actions, clip
    metadata, motions)."""
    import importlib
    from . import handmade
    importlib.reload(handmade)
    ctx = Ctx(arms, bodies, nears, getas)
    fk = A.FK(arms[REF], bodies[REF].J)
    motions, clips = {}, {}
    for name in MOCAP_ORDER:
        mo, info = retarget_clip(ctx, name)
        motions[name] = mo
        c = dict(duration=round(mo.duration, 4), loop=CLIPS[name]["loop"], kind="mocap", source=CLIPS[name]["src"] + ".fbx",
                 keys=mo.n + 1, keyRate=mo.fps)
        if "speed" in info:
            c.update(refSpeed=info["speed"], refStride=info["stride"], strideScale=info["strideScale"], events=info["events"],
                     duty=info["duty"])
        clips[name] = c
        print(f"[mocap] {name}: {mo.n} keys at {mo.fps} Hz, {info}")
    for name, n in LEGACY:
        mo, meta = legacy_motion(ctx, name, n, fk)
        motions[name] = mo
        clips[name] = dict(duration=round(n / A.FPS, 4), loop=True, kind="hand-made (npc/anim.py)", keys=n + 1, keyRate=A.FPS)
    motions["sparkler"] = sparkler_motion(ctx, motions["walk"], fk)
    clips["sparkler"] = dict(clips["walk"], kind="mocap walk + hand-made arm", source="walk.fbx")
    hm, err = handmade.build(ctx)
    for name, (mo, meta) in hm.items():
        motions[name] = mo
        clips[name] = dict(duration=round(mo.duration, 4), loop=meta["loop"], kind="hand-made (npc/handmade.py)", keys=mo.n + 1,
                           keyRate=mo.fps, **{k: v for k, v in meta.items() if k in ("hold", "touch", "seated")})
    ctx.report["reachMissCm"] = err
    ctx.report["armClearance"] = {name: arm_clearance(ctx, motions[name]) for name in ORDER}
    actions = {}
    for name in ORDER:
        clips[name]["note"] = NOTES[name]
        act, slot = ctx.bake(name, motions[name], clips[name]["loop"])
        actions[name] = act
    clips = {name: clips[name] for name in ORDER}
    left = [o.name for o in bpy.data.objects if "mixamo" in o.name.lower()] + \
           [b.name for a in arms.values() for b in a.data.bones if "mixamo" in b.name.lower()] + \
           [a.name for a in bpy.data.actions if "mixamo" in a.name.lower()]
    if left:
        raise RuntimeError(f"Mixamo data left in the scene: {left}")
    return ctx, actions, clips, motions
