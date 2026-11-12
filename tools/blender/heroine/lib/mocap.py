"""Her motion-captured clips: Mixamo clips retargeted onto her own rig (tools/blender/mixamo).

  idle   loop      idle_f.fbx   (Female Idle)
  walk   loop      walk_f.fbx   (Female Normal Walk, in place)   -> clipSpeed.walk
  run    loop      run_f.fbx    (Female Run Forward, in place)   -> clipSpeed.run
  talk   loop      talk.fbx     look   loop  look.fbx
  wave / bow / eat / cheer / point   one-shots that start and end on the idle's first pose
  add_ref, add_nod, add_shake, add_look_l, add_look_r   additive layer clips (spine/neck/head only)

Only the motion is taken. The raw FBX files live in assets/mixamo (gitignored, never shipped);
retarget.load_fbx() samples a clip and deletes the import, so no Mixamo bone, mesh or action
reaches the GLB. The rotation retarget, the foot-contact pass and the arm clearance are generic
(retarget.py); this file holds what is hers: the clip table, the yukata stride and stance, the
body cross-section her arms and sleeves must stay out of, and the hanging sleeves / skirt panels.
"""
import math
import os
import sys

import bpy
import numpy as np

from . import shape as S
from . import anim as A
from .common import smooth

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
MIXAMO_PY = os.path.join(REPO, "tools", "blender", "mixamo")
MIXAMO_FBX = os.path.join(REPO, "assets", "mixamo")
if MIXAMO_PY not in sys.path:
    sys.path.insert(0, MIXAMO_PY)

X, Y, Z = np.eye(3)

# Narrow standing stance for every standing clip (offsets from the rest foot position, yaw deg):
# feet together under the hips, toes a touch out, as the yukata hem allows.
STANCE = {"L": (0.004, -0.010, 4.0), "R": (-0.004, 0.012, -6.0)}

# Yukata gait. The hem is narrow and geta are rigid, so the Mixamo stride (made for trousers) is
# shortened and the cycle quickened: short quick steps, feet landing under the body, knees in.
#   frames       cycle length at 30 fps (the source cycle is time-scaled to it)
#   stride_scale share of the (leg-length-scaled) source stride that is kept
#   stance_x     sideways distance of a planted foot from the centre line (m)
#   key_rate     the run is keyed at 60 Hz (see retarget.transfer); everything else at 30
CLIPS = {
    "idle": dict(src="idle_f", mode="planted", loop=True, gains={"hips": 0.6}, hips_gain=(0.5, 0.5, 1.0)),
    "walk": dict(src="walk_f", mode="locomotion", loop=True, frames=26, stride_scale=0.72, stance_x=0.050,
                 toe_yaw=3.0, swing_scale=0.45, min_lift=0.03, max_lift=0.06, pitch_gain=0.2, knee_spread=0.25, hips_drop=-0.025, stance_fwd=-0.02,
                 knee_out=0.02, reach=0.985, level=0.5,
                 gains={"hips": 0.55, "spine": 0.5, "spine1": 0.5, "spine2": 0.55},
                 hips_gain=(0.45, 0.6, 0.7), lateral_scale=0.25, clear_thr=0.045, vel_tol=0.6),
    # Run: a light upright jog. The hem limits the stride, so the cadence goes up (5 steps/s) and
    # the hips stay near standing height with the stance leg almost straight; never a crouch.
    "run": dict(src="run_f", mode="locomotion", loop=True, frames=12, key_rate=60, extend=2, pitch_ramp=5,
                stride_scale=0.42, stance_x=0.045, toe_yaw=2.0, swing_scale=0.75, min_lift=0.02, max_lift=0.12,
                pitch_gain=0.6, knee_spread=0.2, hips_drop=-0.05, stance_fwd=0.05, knee_out=0.02, reach=0.992,
                level=0.0, hips_gain=(0.4, 0.5, 0.6),
                gains={"hips": 0.25, "spine": 0.3, "spine1": 0.3, "spine2": 0.33, "neck": 0.6},
                lift_late=0.1, lift_fade=(0.15, 0.5), toe_pivot=True,
                amp={"upperarm_L": 0.4, "upperarm_R": 0.4, "forearm_L": 0.5, "forearm_R": 0.5},
                lateral_scale=0.2, pitch_limits=(-55.0, 6.0)),
    "talk": dict(src="talk", mode="planted", loop=True, trim=(20, 225), close=14, gains={"hips": 0.6},
                 hips_gain=(0.5, 0.5, 1.0), amp={"upperarm_L": 0.8, "upperarm_R": 0.8}),
    # The source turns the whole mannequin round; with planted feet she only looks over a shoulder.
    "look": dict(src="look", mode="planted", loop=True, gains={"hips": 0.45}, hips_gain=(0.4, 0.3, 0.3),
                 turn={"hips": 8.0, "spine": 15.0, "spine1": 22.0, "spine2": 28.0, "neck": 50.0, "head": 69.0},
                 tilt={"head": 0.7}),
    "wave": dict(src="wave", mode="planted", loop=False, repeat=3.5, edge=(9, 11), gains={"hips": 0.6}),
    "bow": dict(src="bow", mode="planted", loop=False, trim=(10, 78), edge=(6, 8), hips_gain=(0.5, 0.6, 1.0)),
    # The source drinks from a cup held at the chest; her arms are shorter and her head larger than
    # the mannequin's, so the lift is eased a little to bring the hand to her mouth, not her brow.
    "eat": dict(src="eat", mode="planted", loop=False, trim=(56, 174), edge=(10, 10), gains={"hips": 0.6},
                hips_gain=(0.5, 0.5, 1.0), amp={"upperarm_L": 0.8, "forearm_L": 0.85}),
    "cheer": dict(src="cheer", mode="planted", loop=False, edge=(8, 10), hips_gain=(0.4, 0.4, 0.8),
                  gains={"hips": 0.6, "spine": 0.7, "spine1": 0.7, "spine2": 0.8}),
    "point": dict(src="point", mode="planted", loop=False, trim=(6, 74), edge=(6, 7), gains={"hips": 0.6},
                  hips_gain=(0.5, 0.5, 1.0)),
}
ORDER = ("idle", "walk", "run", "talk", "look", "wave", "bow", "eat", "cheer", "point")
ADD_BONES = ("spine", "spine1", "spine2", "neck", "head")
IDLE0 = []       # the idle's first frame (anim.bake tuple): what one-shots start from and return to


def body_section(z):
    """Half-width, half-depth and centre y of her clothed body at armature height z (the yukata
    shell plus the obi), fading out toward the shoulders where arms are free."""
    zb = z - S.SOLE
    if zb < 0.25 or zb > 1.20:
        return None
    a, b, yc = S.yukata_ring(zb)
    f = float(1 - smooth(1.10, 1.20, zb))
    obi = 0.012 * float(smooth(0.90, 0.95, zb) * (1 - smooth(1.08, 1.12, zb)))
    return (float(a[0]) + obi) * f, (float(b[0]) + obi) * f, float(yc[0])


def _spec(arm, rt):
    spec = rt.load_spec(os.path.join(MIXAMO_PY, "maps", "heroine.json"))
    spec["sole"] = rt.sole_from_mesh(bpy.data.objects["heroine_geta"], {"L": "foot_L", "R": "foot_R"})
    return spec


def _sleeve_clear(fk, fr, lengths, margin=0.035):
    """Keep the hanging sleeve bags out of the body: where a sleeve chain joint would hang inside
    her (arm across the body), swing that sleeve bone outward about its head."""
    import retarget as rt
    delta, absr, local, loc, grav = fr
    absr = dict(absr)
    for sf in ("L", "R"):
        for bone in (f"sleeve_{sf}1", f"sleeve_{sf}2"):
            pose, _ = fk.solve(delta, absr, {k: v for k, v in local.items() if not k.startswith("skirt")}, loc, grav)
            Mb = pose[bone]
            h, t = Mb[:3, 3], Mb[:3, 3] + Mb[:3, 1] * lengths[bone]
            e = body_section(t[2])
            if e is None:
                continue
            a, b, yc = e
            q = np.array([t[0] / (a + margin), (t[1] - yc) / (b + margin)])
            r = float(np.linalg.norm(q))
            if r >= 1.3:
                continue
            if r < 1e-4:
                q, r = np.array([1e-4 if sf == "L" else -1e-4, 0.0]), 1e-4
            r2 = (r ** 8 + 1.0) ** (1.0 / 8)
            t2 = np.array([q[0] * r2 / r * (a + margin), yc + q[1] * r2 / r * (b + margin), t[2]])
            # Undo the bone's own `local` sway before overriding (it is re-applied by fk.solve).
            Rb = Mb[:3, :3] @ local[bone].T if bone in local else Mb[:3, :3]
            absr[bone] = rt.rot_between(t - h, t2 - h) @ Rb
    return delta, absr, local, loc, grav


def _frames(fk, mo, cfg, lengths):
    """Per-frame tuples for anim.bake: the retargeted world orientations, plus her gravity-hung
    helper chains (anim.FK), a light periodic sway, sleeves kept out of the body and the skirt
    panels following the legs."""
    n = mo.n
    T = n / mo.fps
    loco = cfg["mode"] == "locomotion"
    out = []
    for i in range(n + 1):
        t = i / mo.fps
        absr = {b: R[i] for b, R in mo.R.items()}
        loc = {"hips": mo.hips[i]}
        grav = None
        if cfg["src"] == "walk_f":
            local = A.secondary(fk, t, T / 2, 2.0, -3.0, scale={"sleeve_L": 1.6, "sleeve_R": 1.6, "skirtF": 1.5, "skirtB": 1.5})
        elif cfg["src"] == "run_f":
            local = A.secondary(fk, t, T / 2, 4.0, -10.0, scale={"sleeve_L": 1.2, "sleeve_R": 1.2, "skirtF": 1.2, "skirtB": 1.2})
            grav = {"sleeve_L": 0.65, "sleeve_R": 0.65}
        else:
            per = T / max(1, round(T / 2.0))
            amp = 1.0 if cfg["loop"] else 1.0 * float(smooth(0, 0.3, t) * (1 - smooth(T - 0.3, T, t)))
            local = A.secondary(fk, t, per, amp, 0.0)
        fr = ({}, absr, local, loc, grav)
        fr = _sleeve_clear(fk, fr, lengths)
        out.append(A.skirt_follow(fk, fr, "gait" if loco else "avg"))
    if cfg["loop"]:
        out[-1] = out[0]
    return out


def retarget_clip(name, rig, spec, cache, idle_pose=None):
    """One clip: load -> rotation retarget -> (loop / one-shot shaping) -> feet -> arms."""
    import retarget as rt
    cfg = CLIPS[name]
    path = os.path.join(MIXAMO_FBX, cfg["src"] + ".fbx")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"{path} is missing. The raw Mixamo clips are not in the repository; "
                                f"download them again as listed in assets/mixamo/MANIFEST.md.")
    if cfg["src"] not in cache:
        cache[cfg["src"]] = rt.load_fbx(path)
    src = cache[cfg["src"]]
    trim = cfg.get("trim")
    if cfg.get("repeat"):
        # A short source loop played several times (the wave): tile it by resampling cyclically.
        L = src.n - 1
        m = int(round(L * cfg["repeat"]))
        src = src.resampled(np.arange(m + 1) % L)
        trim = None
    mo = rt.transfer(src, rig, spec, frames=cfg.get("frames"), trim=trim, gains=cfg.get("gains"),
                     hips_gain=cfg.get("hips_gain", (1.0, 1.0, 1.0)), name=name, amp=cfg.get("amp"), key_rate=cfg.get("key_rate", A.FPS),
                     hips_origin="mean" if cfg["loop"] else "ends")
    if cfg["mode"] == "locomotion":
        info = rt.plant_feet(mo, rig, spec, mode="locomotion",
                             **{k: cfg[k] for k in ("stride_scale", "stance_x", "toe_yaw", "swing_scale", "min_lift", "max_lift",
                                                    "pitch_gain", "knee_spread", "knee_out", "reach", "level", "lateral_scale",
                                                    "pitch_limits", "clear_thr", "vel_tol", "extend", "pitch_ramp", "hips_drop", "stance_fwd", "lift_late", "lift_fade", "toe_pivot") if k in cfg})
        moved = rt.clear_arms(mo, rig, spec, body_section)
    else:
        if cfg.get("turn"):
            info_turn = rt.limit_turn(mo, rig, cfg["turn"], tilt=cfg.get("tilt"))
        if cfg["loop"] and cfg.get("close"):
            mo.close_loop(cfg["close"])
        if not cfg["loop"]:
            mo.blend_edges(idle_pose, cfg["edge"][0], idle_pose, cfg["edge"][1])
        pose0 = mo.pose(0)
        info = rt.plant_feet(mo, rig, spec, mode="planted", stance=STANCE, reach=0.99, cyclic=cfg["loop"], knee_out=0.05)
        moved = rt.clear_arms(mo, rig, spec, body_section)
        mo.pose0 = pose0
    info["armPushMaxCm"] = round(moved * 100, 1)
    if cfg.get("turn"):
        info["turnDegBeforeAfter"] = info_turn
    info["loop"] = cfg["loop"]
    return mo, info


def _bake_add(arm, fk, name, frames):
    """An additive-layer clip: keys ONLY on spine/neck/head, each frame = reference pose (rest)
    turned by the given world-space deltas."""
    import retarget as rt
    act, slot, cb = rt.new_action(arm, name, False)
    n = len(frames)
    rots = {b: np.zeros((n, 4)) for b in ADD_BONES}
    for i, delta in enumerate(frames):
        _, basis = fk.solve(delta)
        for b in ADD_BONES:
            q = rt._q(basis[b][1])
            q = np.array([q.w, q.x, q.y, q.z])
            if i > 0 and rots[b][i - 1] @ q < 0:
                q = -q
            rots[b][i] = q
    for b in ADD_BONES:
        rt.write_keys(cb, b, rots[b])
    act.use_frame_range = True
    act.frame_start, act.frame_end = 1, n
    return act, slot


def build_additive(arm, fk, acts, clips):
    """add_ref (the neutral reference: her rest pose, 1 frame) and the layers authored as
    differences from it. In the game: THREE.AnimationUtils.makeClipAdditive(clip, 0, add_ref)."""
    rot = A.rot
    I = {b: np.eye(3) for b in ADD_BONES}
    acts["add_ref"] = _bake_add(arm, fk, "add_ref", [I, I])
    clips["add_ref"] = {"duration": 0.0, "loop": False, "additive": "reference", "bones": list(ADD_BONES)}
    n = 18                                               # nod: down and back up, 0.6 s
    fr = []
    for i in range(n + 1):
        u = i / n
        a = 12.0 * math.sin(math.pi * u) ** 2 * (1 - 0.25 * math.sin(2 * math.pi * u))
        fr.append({**I, "spine2": rot(X, 0.12 * a), "neck": rot(X, 0.33 * a), "head": rot(X, 0.55 * a)})
    acts["add_nod"] = _bake_add(arm, fk, "add_nod", fr)
    clips["add_nod"] = {"duration": round(n / A.FPS, 4), "loop": False, "additive": True, "peakDeg": 12.0}
    n = 24                                               # shake: left-right-left-right, 0.8 s
    fr = []
    for i in range(n + 1):
        u = i / n
        a = 11.0 * math.sin(2 * math.pi * 2 * u) * math.sin(math.pi * u) ** 0.8
        fr.append({**I, "neck": rot(Z, 0.3 * a), "head": rot(Z, 0.7 * a)})
    acts["add_shake"] = _bake_add(arm, fk, "add_shake", fr)
    clips["add_shake"] = {"duration": round(n / A.FPS, 4), "loop": False, "additive": True, "peakDeg": 11.0}
    n = 12                                               # look: eases to the full turn in 0.4 s and ends there
    for nm, sgn in (("add_look_l", 1.0), ("add_look_r", -1.0)):
        fr = []
        for i in range(n + 1):
            k = float(smooth(0, n, i))
            fr.append({**I, "spine1": rot(Z, sgn * 4.0 * k), "spine2": rot(Z, sgn * 6.0 * k),
                       "neck": rot(Z, sgn * 8.0 * k) @ rot(Y, sgn * 1.0 * k),
                       "head": rot(Z, sgn * 17.0 * k) @ rot(Y, sgn * 1.5 * k)})
        acts[nm] = _bake_add(arm, fk, nm, fr)
        clips[nm] = {"duration": round(n / A.FPS, 4), "loop": False, "additive": True, "turnDeg": 35.0,
                     "note": "eases from the reference to the full turn and ends there: clamp it and fade its weight"}


def build(arm, fk, acts, clips):
    """Retarget and bake every Mixamo-driven clip plus the additive layers. Fills acts (name ->
    (action, slot)) and clips (metadata). Returns {"walk": m/s, "run": m/s}."""
    import importlib
    import retarget as rt
    importlib.reload(rt)
    rig = rt.Rig(arm)
    spec = _spec(arm, rt)
    lengths = {b.name: b.length for b in arm.data.bones if b.name.startswith("sleeve_")}
    cache, speed, idle_pose = {}, {}, None
    for name in ORDER:
        mo, info = retarget_clip(name, rig, spec, cache, idle_pose)
        if name == "idle":
            idle_pose = mo.pose0
        frames = _frames(fk, mo, CLIPS[name], lengths)
        if name == "idle":
            IDLE0[:] = [frames[0]]
        acts[name] = A.bake(arm, fk, name, frames, loop=CLIPS[name]["loop"])
        c = {"duration": round(mo.duration, 4), "loop": CLIPS[name]["loop"], "source": CLIPS[name]["src"] + ".fbx"}
        if "speed" in info:
            c.update({"speed": round(info["speed"], 3), "stride": round(info["stride"], 3), "step": round(info["step"], 3),
                      "events": info["events"], "keys": mo.n, "keyRate": mo.fps})
            speed[name] = round(info["speed"], 3)
        clips[name] = c
        print(f"[mocap] {name}: {mo.n} frames, {info}")
    build_additive(arm, fk, acts, clips)
    left = [o.name for o in bpy.data.objects if "mixamo" in o.name.lower()] + \
           [b.name for b in arm.data.bones if "mixamo" in b.name.lower()]
    if left:
        raise RuntimeError(f"Mixamo data left in the scene: {left}")
    return speed
