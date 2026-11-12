"""Mixamo motion -> our own rigs (Blender, headless or interactive). Only the motion is taken.

    import retarget as rt
    src   = rt.load_fbx(r"assets/mixamo/walk_f.fbx")          # samples the clip, then deletes the import
    rig   = rt.Rig(arm_object)                                # the TARGET armature (rest pose is read)
    spec  = rt.load_spec("tools/blender/mixamo/maps/heroine.json")
    spec["sole"] = rt.sole_from_mesh(geta_object, {"L": "foot_L", "R": "foot_R"})
    mo    = rt.transfer(src, rig, spec, frames=28)            # rotation retarget (world space)
    info  = rt.plant_feet(mo, rig, spec, mode="locomotion", stride_scale=0.8)   # contact pass + leg IK
    rt.clear_arms(mo, rig, spec, body_fn)                     # optional: keep arms out of the body
    act, slot = rt.bake_action(arm_object, "walk", mo, rig)   # keys on the target's own bones, 30 fps

Conventions (Blender armature space): metres, +Z up, the character faces -Y, +X is its left.
Mixamo FBX files import facing -Y too (armature object scaled 0.01 and turned +90 deg about X);
everything is sampled in world space, so that object transform never matters.

How the rotation retarget works. For every mapped pair (Mixamo bone s -> target bone t):

    D(f)  = Rs(f) @ Rs0^T            world-space rotation of the source bone away from ITS rest pose
    Rt(f) = D(f)^gain @ C @ Rt0      target world rotation; Rt0 = target rest orientation

C is the rest-pose difference, per bone and constant:
  "delta" bones (hips, spine, neck, head, clavicles, feet): C = 1. Both rests are upright.
  "aim" bones (upper arm, forearm, thigh, shin, fingers): C = M @ C_parent, where M is the smallest
      rotation that takes the (parent-corrected) target rest direction onto the source rest
      direction. This is what turns an A-pose (or relaxed-curl fingers) into Mixamo's T-pose
      without adding twist, so the limb then points where the source limb points.
  "frame" bones (hands): C aligns a full frame (aim = wrist -> middle knuckle, side = index ->
      pinky), so the palm faces where the source palm faces.
Because the deltas are taken in world space, bones the target lacks (Spine1 on a two-bone spine)
are absorbed by the next mapped bone, and no twist can accumulate down a chain.

Legs are NOT copied: plant_feet() rebuilds them with two-bone IK from foot targets (see there).
No Mixamo object, bone, mesh or action is left in the file after load_fbx().
"""
import json
import math
import os
import re

import bpy
import numpy as np
from mathutils import Matrix, Quaternion

FPS = 30
UP = np.array([0.0, 0.0, 1.0])
FWD = np.array([0.0, -1.0, 0.0])
PREFIX = re.compile(r"^(?:.*\|)?mixamorig\d*[:_]?")

# ---------------------------------------------------------------- small maths


def _n(v):
    v = np.asarray(v, float)
    return v / max(np.linalg.norm(v), 1e-12)


def _smooth(e0, e1, x):
    t = np.clip((np.asarray(x, float) - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def _q(R):
    q = Matrix(np.asarray(R).tolist()).to_quaternion()
    return q


def _m(q):
    return np.array(q.to_matrix())


def slerp_m(Ra, Rb, t):
    qa, qb = _q(Ra), _q(Rb)
    if qa.dot(qb) < 0:
        qb.negate()
    return _m(qa.slerp(qb, float(t)))


def scale_rot(R, g):
    """R^g: the same axis, g times the angle."""
    if g == 1.0:
        return R
    return _m(Quaternion().slerp(_q(R), float(g)))


def rot_axis(axis, deg):
    return _m(Quaternion(tuple(_n(axis)), math.radians(deg)))


def rot_between(a, b):
    """Smallest rotation taking direction a onto direction b."""
    a, b = _n(a), _n(b)
    c = float(np.clip(a @ b, -1, 1))
    ax = np.cross(a, b)
    s = np.linalg.norm(ax)
    if s < 1e-9:
        if c > 0:
            return np.eye(3)
        ax = np.cross(a, [1.0, 0, 0])
        if np.linalg.norm(ax) < 1e-6:
            ax = np.cross(a, [0, 1.0, 0])
        return _m(Quaternion(tuple(_n(ax)), math.pi))
    return _m(Quaternion(tuple(ax / s), math.atan2(s, c)))


def frame(aim, side):
    """Orthonormal frame, columns (x, y = aim, z) with x as close to `side` as possible."""
    y = _n(aim)
    x = np.asarray(side, float)
    x = _n(x - y * (x @ y))
    return np.stack([x, y, np.cross(x, y)], axis=1)


def two_bone(H, A, L1, L2, pole, reach=0.995):
    """Knee/elbow position K and the reachable end point for a two-bone chain from H toward A."""
    d = A - H
    dist = np.linalg.norm(d)
    u = d / max(dist, 1e-9)
    dist = float(np.clip(dist, abs(L1 - L2) + 1e-4, (L1 + L2) * reach))
    ca = float(np.clip((L1 * L1 + dist * dist - L2 * L2) / (2 * L1 * dist), -1, 1))
    sa = math.sqrt(1 - ca * ca)
    v = pole - u * (pole @ u)
    if np.linalg.norm(v) < 1e-6:
        v = FWD - u * (FWD @ u)
    v = _n(v)
    return H + L1 * (ca * u + sa * v), H + u * dist


def _cyc_smooth_max(need, k=3, sigma=1.5, cyclic=True):
    """Smooth envelope that is never below `need` (so a leg never over-reaches)."""
    n = len(need)
    idx = (lambda i: i % n) if cyclic else (lambda i: min(max(i, 0), n - 1))
    mx = np.array([max(need[idx(i + j)] for j in range(-k, k + 1)) for i in range(n)])
    g = np.exp(-0.5 * (np.arange(-k, k + 1) / sigma) ** 2)
    g /= g.sum()
    sm = np.array([sum(g[j + k] * mx[idx(i + j)] for j in range(-k, k + 1)) for i in range(n)])
    return np.maximum(sm, need)


# ---------------------------------------------------------------- source clip


class Source:
    """A sampled Mixamo clip: world-space joint positions (m) and orientations per frame at 30 fps.
    Bone names have the mixamorig prefix removed (Hips, LeftArm, ...). `n` samples; in a looping
    Mixamo clip the last sample repeats the first."""

    def __init__(self, name, parent, rest_pos, rest_rot, pos, rot):
        self.name, self.parent = name, parent
        self.rest_pos, self.rest_rot, self.pos, self.rot = rest_pos, rest_rot, pos, rot
        self.n = len(next(iter(pos.values())))

    def resampled(self, xs):
        """New Source sampled at the fractional frame indices xs (linear / slerp)."""
        xs = np.clip(np.asarray(xs, float), 0, self.n - 1)
        i0 = np.minimum(np.floor(xs).astype(int), self.n - 2) if self.n > 1 else np.zeros(len(xs), int)
        t = xs - i0
        pos, rot = {}, {}
        for b in self.pos:
            P, R = self.pos[b], self.rot[b]
            pos[b] = P[i0] * (1 - t[:, None]) + P[np.minimum(i0 + 1, self.n - 1)] * t[:, None]
            rot[b] = np.array([R[i] if tt < 1e-6 else slerp_m(R[i], R[min(i + 1, self.n - 1)], tt) for i, tt in zip(i0, t)])
        return Source(self.name, self.parent, self.rest_pos, self.rest_rot, pos, rot)

    def pose_distance(self, i, j, bones=None):
        """Mean angle (deg) between two frames' world orientations plus hips offset (cm)."""
        bones = bones or [b for b in self.rot if "Hand" not in b or b.endswith("Hand")]
        a = 0.0
        for b in bones:
            c = (np.trace(self.rot[b][i].T @ self.rot[b][j]) - 1) / 2
            a += math.degrees(math.acos(float(np.clip(c, -1, 1))))
        return a / len(bones) + 100 * np.linalg.norm(self.pos["Hips"][i] - self.pos["Hips"][j])

    def find_loop(self, min_len, max_len, start=(0, None), step=1):
        """Best (a, b) with min_len <= b - a <= max_len so that playing a..b loops with the least
        pose and velocity mismatch. For trimming a long Mixamo loop to a shorter one."""
        hi = self.n - 2 if start[1] is None else start[1]
        best = (1e18, 0, self.n - 1)
        for a in range(start[0], hi + 1, step):
            for b in range(a + min_len, min(a + max_len, self.n - 2) + 1, step):
                c = self.pose_distance(a, b) + 0.6 * self.pose_distance(a + 1, b + 1)
                if c < best[0]:
                    best = (c, a, b)
        return best[1], best[2], best[0]


def load_fbx(path, name=None):
    """Import a Mixamo FBX, sample every bone in world space at 30 fps, then remove everything the
    import created (objects, armature, actions, any mesh/material), so nothing of Mixamo stays."""
    sc = bpy.context.scene
    sc.render.fps, sc.render.fps_base = FPS, 1.0
    before = {k: set(getattr(bpy.data, k)) for k in ("objects", "armatures", "actions", "meshes", "materials", "images")}
    props = bpy.ops.import_scene.fbx.get_rna_type().properties.keys()
    kw = dict(filepath=path, use_anim=True, ignore_leaf_bones=True, automatic_bone_orientation=False)
    bpy.ops.import_scene.fbx(**{k: v for k, v in kw.items() if k in props or k == "filepath"})
    new = [o for o in bpy.data.objects if o not in before["objects"]]
    arm = next((o for o in new if o.type == "ARMATURE"), None)
    try:
        if arm is None or not arm.animation_data or not arm.animation_data.action:
            raise RuntimeError(f"{path}: no animated armature in the FBX")
        act = arm.animation_data.action
        f0, f1 = int(round(act.frame_range[0])), int(round(act.frame_range[1]))
        W = np.array(arm.matrix_world)
        clean = lambda nm: PREFIX.sub("", nm)
        parent, rest_pos, rest_rot = {}, {}, {}
        for b in arm.data.bones:
            M = W @ np.array(b.matrix_local)
            R = M[:3, :3]
            parent[clean(b.name)] = clean(b.parent.name) if b.parent else None
            rest_pos[clean(b.name)] = M[:3, 3].copy()
            rest_rot[clean(b.name)] = R / np.linalg.norm(R, axis=0)
        pos = {b: [] for b in parent}
        rot = {b: [] for b in parent}
        for f in range(f0, f1 + 1):
            sc.frame_set(f)
            for pb in arm.pose.bones:
                M = W @ np.array(pb.matrix)
                R = M[:3, :3]
                pos[clean(pb.name)].append(M[:3, 3].copy())
                rot[clean(pb.name)].append(R / np.linalg.norm(R, axis=0))
        src = Source(name or os.path.splitext(os.path.basename(path))[0], parent, rest_pos, rest_rot,
                     {b: np.array(v) for b, v in pos.items()}, {b: np.array(v) for b, v in rot.items()})
    finally:
        for o in new:
            if o.name in bpy.data.objects:
                bpy.data.objects.remove(o, do_unlink=True)
        for k in ("armatures", "actions", "meshes", "materials", "images"):
            coll = getattr(bpy.data, k)
            for d in list(coll):
                if d not in before[k]:
                    coll.remove(d)
        sc.frame_set(1)
    if "Hips" not in src.pos:
        raise RuntimeError(f"{path}: no Mixamo Hips bone (bones: {sorted(src.pos)[:6]}...)")
    return src


# ---------------------------------------------------------------- target rig


class Rig:
    """Rest pose and hierarchy of the target armature, plus forward kinematics on world rotations."""

    def __init__(self, arm):
        bones = arm.data.bones
        self.rest = {b.name: np.array(b.matrix_local, dtype=float) for b in bones}
        self.parent = {b.name: (b.parent.name if b.parent else None) for b in bones}
        self.order, seen = [], set()

        def visit(n):
            if n in seen:
                return
            if self.parent[n]:
                visit(self.parent[n])
            seen.add(n)
            self.order.append(n)

        for b in bones:
            visit(b.name)
        self.inv = {n: np.linalg.inv(m) for n, m in self.rest.items()}

    def head(self, n):
        return self.rest[n][:3, 3]

    def axes(self, n):
        return self.rest[n][:3, :3]

    def solve(self, absr=None, loc=None, hang=None):
        """absr: bone -> world 3x3 (others keep their rest orientation relative to the parent);
        loc: bone -> world-space offset of the bone head from where its parent puts it;
        hang: bone -> k in 0..1, share of the bone's REST world orientation it keeps (gravity) for
        unmapped helper bones such as hanging sleeves. Returns (pose 4x4, basis (loc, rot))."""
        absr, loc, hang = absr or {}, loc or {}, hang or {}
        pose, basis = {}, {}
        for n in self.order:
            Rr, p = self.rest[n], self.parent[n]
            M0 = pose[p] @ self.inv[p] @ Rr if p else Rr.copy()
            R0 = M0[:3, :3]
            if n in absr:
                Rp = absr[n]
            elif n in hang:
                Rp = slerp_m(R0, Rr[:3, :3], hang[n])
            else:
                Rp = R0
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


# ---------------------------------------------------------------- spec (the data that drives it)

_AIM_CHILD = {"Arm": "ForeArm", "ForeArm": "Hand", "Hand": "HandMiddle1", "UpLeg": "Leg", "Leg": "Foot"}


def _src_mode(s):
    if re.search(r"(Left|Right)Hand$", s):
        return "frame"
    if re.search(r"(Arm|ForeArm|UpLeg|Leg)$", s) or re.search(r"Hand(Thumb|Index|Middle|Ring|Pinky)\d$", s):
        return "aim"
    return "delta"


def _src_aim(src, s):
    """Rest direction of a Mixamo bone: toward its chain child (or along parent -> self at a tip)."""
    m = re.match(r"(Left|Right)(.*)$", s)
    if m and m.group(2) in _AIM_CHILD:
        c = m.group(1) + _AIM_CHILD[m.group(2)]
        return _n(src.rest_pos[c] - src.rest_pos[s])
    m = re.match(r"(.*Hand(?:Thumb|Index|Middle|Ring|Pinky))(\d)$", s)
    if m:
        c = f"{m.group(1)}{int(m.group(2)) + 1}"
        if c in src.rest_pos:
            return _n(src.rest_pos[c] - src.rest_pos[s])
        return _n(src.rest_pos[s] - src.rest_pos[src.parent[s]])
    raise KeyError(s)


def load_spec(path):
    with open(path, "r", encoding="utf8") as f:
        spec = json.load(f)
    return spec


def default_spec(bone_names):
    """Bone map for rigs that follow this project's naming (heroine, townspeople). Mixamo name ->
    target bone; bones the target lacks are simply left out."""
    have = set(bone_names)
    m = {"Hips": "hips", "Spine": "spine", "Neck": "neck", "Head": "head"}
    if "spine1" in have:
        m.update({"Spine1": "spine1", "Spine2": "spine2"})
    elif "chest" in have:
        m["Spine2"] = "chest"
    spec = {"bones": {}, "blend": {}, "hand_side": {}, "legs": {}, "arms": {}, "hips": "hips", "ground": 0.0}
    for S, s in (("Left", "L"), ("Right", "R")):
        m.update({f"{S}Shoulder": f"shoulder_{s}", f"{S}Arm": f"upperarm_{s}", f"{S}ForeArm": f"forearm_{s}",
                  f"{S}Hand": f"hand_{s}", f"{S}UpLeg": f"thigh_{s}", f"{S}Leg": f"shin_{s}", f"{S}Foot": f"foot_{s}",
                  f"{S}ToeBase": f"toe_{s}"})
        for F, f in (("Thumb", "thumb"), ("Index", "index"), ("Middle", "middle"), ("Ring", "ring"), ("Pinky", "pinky")):
            m[f"{S}Hand{F}1"] = f"finger_{f}_1_{s}"
            m[f"{S}Hand{F}2"] = f"finger_{f}_2_{s}"
            if f"finger_{f}_2_{s}" in have:
                # Our second finger bone spans Mixamo's 2nd and 3rd joints: take half of each.
                spec["blend"][f"finger_{f}_2_{s}"] = [f"{S}Hand{F}3", 0.5]
        if f"finger_index_1_{s}" in have and f"finger_pinky_1_{s}" in have:
            spec["hand_side"][f"hand_{s}"] = [f"finger_index_1_{s}", f"finger_pinky_1_{s}"]
        spec["legs"][s] = {"thigh": f"thigh_{s}", "shin": f"shin_{s}", "foot": f"foot_{s}",
                           "toe": f"toe_{s}" if f"toe_{s}" in have else None,
                           "src": [f"{S}UpLeg", f"{S}Leg", f"{S}Foot", f"{S}ToeBase"]}
        spec["arms"][s] = {"upper": f"upperarm_{s}", "fore": f"forearm_{s}", "hand": f"hand_{s}"}
    spec["bones"] = {k: v for k, v in m.items() if v in have}
    return spec


def sole_from_mesh(ob, foot_groups, ground=0.0, tol=0.003):
    """Rest positions (armature space) of the vertices that form the bottom of each foot/shoe:
    those weighted to the side's foot bone that lie within `tol` of the floor. plant_feet() keeps
    the lowest of these exactly on the floor. foot_groups: {"L": "foot_L", "R": "foot_R"}."""
    out = {}
    M = np.array(ob.matrix_world)
    for sf, g in foot_groups.items():
        gi = ob.vertex_groups[g].index
        pts = []
        for v in ob.data.vertices:
            if any(e.group == gi and e.weight > 0.5 for e in v.groups):
                p = M[:3, :3] @ np.array(v.co) + M[:3, 3]
                pts.append(p)
        pts = np.array(pts)
        low = pts[pts[:, 2] < pts[:, 2].min() + tol]
        low[:, 2] = pts[:, 2].min()
        out[sf] = np.unique(np.round(low, 5), axis=0).tolist()
        if abs(pts[:, 2].min() - ground) > 0.004:
            print(f"[retarget] note: {ob.name} {g} sole is at z={pts[:, 2].min():.4f}, ground={ground}")
    return out


# ---------------------------------------------------------------- motion (retargeted, editable)


class Motion:
    """Retargeted motion in the TARGET's armature space, n+1 samples at `fps` (30 unless
    transfer(key_rate=...) asked for denser keys; sample n closes the clip; for a loop it equals
    sample 0).
      R[bone]   (n+1, 3, 3) world orientations of the mapped bones
      hips      (n+1, 3)    offset of the hips bone head from its rest position
      foot[sf]  source-derived data for the contact pass (scaled to the target)"""

    def __init__(self, name, n, fps=FPS):
        self.name, self.n, self.fps = name, n, fps
        self.R, self.hips, self.foot = {}, np.zeros((n + 1, 3)), {}
        self.k = 1.0
        self.info = {}

    @property
    def duration(self):
        return self.n / self.fps

    def pose(self, i):
        return {"R": {b: v[i].copy() for b, v in self.R.items()}, "hips": self.hips[i].copy()}

    def blend_edges(self, ref_in, n_in, ref_out=None, n_out=None, skip=()):
        """One-shots: ease from the pose ref_in over the first n_in frames and back to ref_out over
        the last n_out (poses from Motion.pose(), normally the idle's first frame)."""
        ref_out = ref_out or ref_in
        n_out = n_in if n_out is None else n_out
        for i in range(self.n + 1):
            w = 1.0
            ref = ref_in
            if i < n_in:
                w = float(_smooth(0, n_in, i))
            if i > self.n - n_out:
                w2 = float(_smooth(0, n_out, self.n - i))
                if w2 < w:
                    w, ref = w2, ref_out
            if w >= 1.0:
                continue
            for b in self.R:
                if b in ref["R"] and b not in skip:
                    self.R[b][i] = slerp_m(ref["R"][b], self.R[b][i], w)
            self.hips[i] = ref["hips"] * (1 - w) + self.hips[i] * w

    def close_loop(self, blend):
        """Make sample n equal sample 0 by spreading the mismatch over the last `blend` frames."""
        n = self.n
        for b, R in self.R.items():
            Dq = R[0] @ R[n].T
            for i in range(n - blend, n + 1):
                w = float(_smooth(n - blend, n, i))
                R[i] = scale_rot(Dq, w) @ R[i]
        d = self.hips[0] - self.hips[n]
        for i in range(n - blend, n + 1):
            self.hips[i] += d * float(_smooth(n - blend, n, i))


def transfer(src, rig, spec, frames=None, trim=None, gains=None, hips_gain=(1.0, 1.0, 1.0), name=None,
             hips_origin="mean", amp=None, key_rate=FPS):
    """Rotation retarget (see the module docstring) + hips translation scaled by the leg-length
    ratio. trim=(a, b): source frame range to use. frames: number of 30 fps frames of the result
    (time-stretches the range; default: unchanged). gains: target bone -> scale of its world delta
    (e.g. {"hips": 0.6} for a calmer pelvis). hips_gain: (sideways, fore-aft, vertical) scale of
    the hips' travel about its origin. hips_origin: "mean" (loops: the clip's mean hips position
    sits over the target's rest position) or "ends" (one-shots: the first/last frame does).
    amp: target bone -> scale of its swing about its own mean orientation over the clip (e.g.
    {"upperarm_L": 0.6} for a smaller arm swing with the same carriage).
    key_rate: keys per second of the result. 30 everywhere, except that a fast run may be keyed
    at 60: `frames` stays the length in 30 fps frames, the Motion just has twice the samples.
    (Joint rotations are interpolated linearly between keys, so a planted foot wanders a little
    between them; at running speed that needs the denser keys to stay under 3 cm/s.) An action
    baked from such a Motion is twice as long in Blender frames: scale its key times by
    30 / key_rate when exporting (heroine/lib/glbpost.py: scale_clip_times)."""
    a, b = trim or (0, src.n - 1)
    n = int(frames) if frames else (b - a)
    n = int(round(n * key_rate / FPS))
    s = src.resampled(np.linspace(a, b, n + 1))
    gains = gains or {}
    mo = Motion(name or src.name, n, key_rate)
    t2s = {t: sname for sname, t in spec["bones"].items()}
    for sname in spec["bones"]:
        if sname not in src.rest_rot:
            raise KeyError(f"bone map: the source clip has no bone '{sname}'")
    for t in t2s:
        if t not in rig.rest:
            raise KeyError(f"bone map: the target rig has no bone '{t}'")
    legs = spec["legs"]
    leg_bones = {v for L in legs.values() for k, v in L.items() if k in ("thigh", "shin", "foot", "toe") and v}
    # Rest-pose corrections, parents first.
    C = {}

    def mapped_parent(t):
        p = rig.parent[t]
        while p and p not in t2s:
            p = rig.parent[p]
        return p

    for t in rig.order:
        if t not in t2s:
            continue
        sname = t2s[t]
        mode = spec.get("modes", {}).get(t) or _src_mode(sname)
        if mode == "delta":
            C[t] = np.eye(3)
            continue
        ds0 = _src_aim(src, sname)
        dt0 = rig.axes(t)[:, 1]
        if mode == "frame" and t in spec.get("hand_side", {}):
            ti, tp = spec["hand_side"][t]
            S = sname[:-4]                                      # "Left" / "Right"
            Fs = frame(ds0, src.rest_pos[f"{S}HandPinky1"] - src.rest_pos[f"{S}HandIndex1"])
            Ft = frame(dt0, rig.head(tp) - rig.head(ti))
            C[t] = Fs @ Ft.T
        else:
            p = mapped_parent(t)
            Cp = C.get(p, np.eye(3)) if p else np.eye(3)
            C[t] = rot_between(Cp @ dt0, ds0) @ Cp
    mo.C = C
    # World orientations.
    for t, sname in t2s.items():
        if t in leg_bones:
            continue
        Rs0T = src.rest_rot[sname].T
        Rt0 = C[t] @ rig.axes(t)
        g = gains.get(t, 1.0)
        bl = spec.get("blend", {}).get(t)
        out = np.zeros((n + 1, 3, 3))
        for i in range(n + 1):
            D = s.rot[sname][i] @ Rs0T
            if bl and bl[0] in s.rot:
                D = slerp_m(D, s.rot[bl[0]][i] @ src.rest_rot[bl[0]].T, bl[1])
            out[i] = scale_rot(D, g) @ Rt0
        if amp and t in amp:
            qs = np.array([[q.w, q.x, q.y, q.z] for q in (_q(R) for R in out[:max(n, 1)])])
            qs[qs @ qs[0] < 0] *= -1
            Rm = _m(Quaternion(tuple(_n(qs.sum(axis=0)))))
            for i in range(n + 1):
                out[i] = slerp_m(Rm, out[i], amp[t])
        mo.R[t] = out
    # Leg-length ratio and hips travel.
    k_num = k_den = 0.0
    for sf, L in legs.items():
        up, lo, ft, toe = L["src"]
        k_num += np.linalg.norm(rig.head(L["shin"]) - rig.head(L["thigh"])) + np.linalg.norm(rig.head(L["foot"]) - rig.head(L["shin"]))
        k_den += np.linalg.norm(src.rest_pos[lo] - src.rest_pos[up]) + np.linalg.norm(src.rest_pos[ft] - src.rest_pos[lo])
    k = mo.k = k_num / k_den
    H = s.pos["Hips"]
    mean = H[:n].mean(axis=0) if (n > 0 and hips_origin == "mean") else 0.5 * (H[0] + H[n])
    mo.src_hips = H.copy()
    mo.src_hips_rest = src.rest_pos["Hips"].copy()
    hz = (H[:, 2] - src.rest_pos["Hips"][2]) * k
    mo.hips = np.stack([(H[:, 0] - mean[0]) * k * hips_gain[0], (H[:, 1] - mean[1]) * k * hips_gain[1],
                        (hz - hz.mean()) * hips_gain[2] + hz.mean()], axis=1)
    mo.hips_gain = hips_gain
    for sf, L in legs.items():
        up, lo, ft, toe = L["src"]
        A, T, K, U = s.pos[ft], s.pos[toe], s.pos[lo], s.pos[up]
        A0, T0 = src.rest_pos[ft], src.rest_pos[toe]
        # Clearance of the source sole: how far heel (ankle) or toe, whichever is lower, is above
        # its standing height.
        za = A[:, 2] - min(A0[2], A[:, 2].min())
        zt = T[:, 2] - min(T0[2], T[:, 2].min())
        v, v0 = T - A, T0 - A0
        pitch = np.degrees(np.arctan2(v[:, 2], np.linalg.norm(v[:, :2], axis=1)) - math.atan2(v0[2], np.linalg.norm(v0[:2])))
        yaw = np.degrees(np.arctan2(v[:, 0], -v[:, 1]) - math.atan2(v0[0], -v0[1]))
        yaw = (yaw + 180) % 360 - 180
        # Knee direction: the part of hip -> knee that is perpendicular to hip -> ankle.
        pole = np.zeros((n + 1, 3))
        for i in range(n + 1):
            u = _n(A[i] - U[i])
            w = (K[i] - U[i]) - u * ((K[i] - U[i]) @ u)
            pole[i] = w
        mo.foot[sf] = {"ankle": A.copy(), "toe": T.copy(), "ankle_rest": A0.copy(), "clear": np.minimum(za, zt),
                       "heel_clear": za, "toe_clear": zt, "pitch": pitch, "yaw": yaw, "pole": pole}
    return mo


# ---------------------------------------------------------------- foot contact pass


def _runs(flag):
    """Cyclic runs of True in a boolean array: [(start, length)]."""
    n = len(flag)
    if flag.all():
        return [(0, n)]
    out, i = [], 0
    while i < n:
        if flag[i] and not flag[i - 1]:
            L = 0
            while flag[(i + L) % n]:
                L += 1
            out.append((i, L))
        i += 1
    return out


def detect_stance(mo, clear_thr=0.03, vel_tol=0.45):
    """Stance flags per foot for an IN-PLACE locomotion loop, from the source: the sole is low
    and the foot travels backward at about the ground speed. Returns (flags, v_src in m/s)."""
    n = mo.n
    vy, low = {}, {}
    for sf, F in mo.foot.items():
        y = F["ankle"][:n, 1]
        vy[sf] = (np.roll(y, -1) - np.roll(y, 1)) * mo.fps / 2
        low[sf] = F["clear"][:n] < clear_thr
    samples = np.concatenate([vy[sf][low[sf]] for sf in vy])
    samples = samples[samples > 0.2 * max(samples.max(), 1e-6)]
    v = float(np.median(samples))
    flags = {}
    for sf in vy:
        f = low[sf] & (np.abs(vy[sf] - v) < vel_tol * v)
        for i in range(n):                                  # close 1-frame holes
            if not f[i] and f[i - 1] and f[(i + 1) % n]:
                f[i] = True
        runs = _runs(f)
        if not runs:
            raise RuntimeError(f"{mo.name}: no stance phase found for foot {sf}")
        s0, L = max(runs, key=lambda r: r[1])               # one stance per foot per cycle
        g = np.zeros(n, bool)
        g[[(s0 + j) % n for j in range(L)]] = True
        flags[sf] = g
    # Refine the ground speed on the stance frames only.
    v = float(np.mean(np.concatenate([vy[sf][flags[sf]] for sf in vy])))
    return flags, v


def plant_feet(mo, rig, spec, mode="planted", stride_scale=1.0, stance_x=None, stance=None, toe_yaw=0.0,
               lateral_scale=0.3, swing_scale=1.0, min_lift=0.03, max_lift=0.25, pitch_gain=0.6,
               pitch_limits=(-35.0, 12.0), knee_spread=0.4, knee_out=0.05, reach=0.985, level=0.0,
               hips_drop=0.0, extend=1, cyclic=None, clear_thr=0.03, vel_tol=0.45, hips_y=0.0, pitch_ramp=3, stance_fwd=0.0, lift_late=1.0,
               lift_fade=(0.4, 0.7), toe_pivot=False):
    """Rebuild the legs so the feet behave. Fills mo.R for thigh/shin/foot/toe, lowers the hips
    where a leg would over-reach, and returns the clip facts (speed, contacts).

    mode="locomotion" (an in-place walk/run loop):
      - stance phases come from the source (detect_stance);
      - the ground speed the clip implies is v = v_source * leg_ratio * stride_scale, and every
        planted foot is pinned to a straight line: it moves back at exactly v, at a fixed
        sideways position (stance_x: metres from the centre line; default the rest position),
        flat, the lowest sole point on the floor. The horizontal pin lasts `extend` frames beyond
        the stance at both ends, so a foot leaving or meeting the floor never skates;
      - in swing the foot follows the source's path about the straight chord between the pinned
        ends (scaled), lifted by the source clearance (x swing_scale, at least min_lift, softly
        capped at max_lift), pitched by pitch_gain x the source pitch;
      - knees follow the source knee direction, with its sideways part scaled by knee_spread.
    mode="planted" (standing clips): both feet stay flat at `stance` = {"L": (dx, dy, yaw_deg),
      "R": ...} offsets from their rest position for the whole clip.
    Common: toe_yaw (deg, + = toes out), reach = max leg extension (knees stay soft),
    level in 0..1 = how much of the reach-driven hip dip is held through the cycle,
    hips_drop = constant extra lowering (m), stance_fwd = shift of the whole stance forward (m;
    Mixamo runs push off far behind the body, which a narrow skirt cannot follow).
    lift_late (locomotion): scale of the swing lift late in the swing (it fades in over the
    swing fractions lift_fade); below 1 the
    heel still kicks up behind but the foot comes through low, so the knee is not driven up in
    front (a long skirt). toe_pivot: while a pitched foot is still within a few cm of the floor,
    rotate it about its lowest sole point instead of the point under the ankle, so the edge it
    rocks on stays put (no skate during a strong toe-off). Both default to the old behaviour."""
    n = mo.n
    FPS = mo.fps                    # extend / pitch_ramp are in keys of the motion
    legs = spec["legs"]
    ground = spec.get("ground", 0.0)
    hips = spec.get("hips", "hips")
    cyclic = (mode == "locomotion") if cyclic is None else cyclic
    sole = spec.get("sole") or {}
    k = mo.k
    info = {"duration": round(mo.duration, 4), "legRatio": round(k, 4)}
    N = n if cyclic else n + 1      # samples solved (a loop's sample n is a copy of sample 0)
    G = {}          # per foot: ground reference path (N, 3), lift (N), Q (N, 3, 3)
    QF = {}         # per foot: its flat (yaw only) orientation
    sgn = {"L": 1.0, "R": -1.0}
    if mode == "locomotion":
        flags, v_src = detect_stance(mo, clear_thr, vel_tol)
        v = v_src * k * stride_scale
        info.update({"speed": round(v, 4), "sourceSpeed": round(v_src, 4), "stride": round(v * mo.duration, 4),
                     "step": round(v * mo.duration / 2, 4), "events": {}, "duty": {}})
        for sf, L in legs.items():
            F = mo.foot[sf]
            A0 = rig.head(L["foot"])
            st = flags[sf]
            (s0, SL), = _runs(st)
            a, b = s0 - extend, s0 + SL - 1 + extend            # pinned frames a..b (cyclic)
            NP = b - a                                          # intervals pinned
            NS = n - NP                                         # swing intervals
            if NS < 2:
                raise RuntimeError(f"{mo.name}: foot {sf} has no swing phase")
            xs = sgn[sf] * stance_x if stance_x is not None else A0[0]
            src_y = F["ankle"][:n, 1] - mo.src_hips[:n, 1].mean()
            rest_rel = F["ankle_rest"][1] - mo.src_hips_rest[1]
            mid = s0 + (SL - 1) / 2.0
            yc = A0[1] + hips_y - stance_fwd + stride_scale * k * (float(np.mean(src_y[[(s0 + j) % n for j in range(SL)]])) - rest_rel)
            g = np.zeros((n, 3))
            lift = np.zeros(n)
            pit = np.zeros(n)
            g[:, 2] = ground
            ya, yb = yc + v * (a - mid) / FPS, yc + v * (b - mid) / FPS
            sx = F["ankle"][:n, 0]
            for j in range(NP + 1):
                i = (a + j) % n
                g[i, 0], g[i, 1] = xs, yc + v * (a + j - mid) / FPS
            ia, ib = a % n, b % n
            for j in range(1, NS):
                i = (b + j) % n
                u = j / NS
                dev_y = src_y[i] - (src_y[ib] * (1 - u) + src_y[ia] * u)
                dev_x = sx[i] - (sx[ib] * (1 - u) + sx[ia] * u)
                g[i, 0] = xs + lateral_scale * k * dev_x
                g[i, 1] = yb * (1 - u) + ya * u + stride_scale * k * dev_y
            # Lift: zero in stance; outside it the scaled source clearance with a floor and a cap.
            NSW = n - SL                                         # frames off the floor + 1
            for j in range(1, NSW + 1):
                i = (s0 + SL - 1 + j) % n
                u = j / (NSW + 1)
                h = swing_scale * k * F["clear"][i] * (1 - (1 - lift_late) * float(_smooth(lift_fade[0], lift_fade[1], u)))
                h = max(h, min_lift * math.sin(math.pi * u) ** 0.8)
                lift[i] = max_lift * math.tanh(h / max_lift)
                w = min(1.0, j / pitch_ramp, (NSW + 1 - j) / pitch_ramp)
                pit[i] = float(np.clip(pitch_gain * F["pitch"][i], *pitch_limits)) * _smooth(0, 1, w)
            yaw = sgn[sf] * toe_yaw
            Q = np.array([rot_axis(UP, yaw) @ rot_axis([1, 0, 0], -p) for p in pit])
            G[sf] = (g, lift, Q)
            QF[sf] = rot_axis(UP, yaw)
            t_down, t_up = (s0 % n) / FPS, ((s0 + SL - 1) % n) / FPS
            info["events"][f"footDown{sf}"] = round(t_down, 4)
            info["events"][f"footUp{sf}"] = round(t_up, 4)
            info["duty"][sf] = round(SL / n, 3)
    else:
        stance = stance or {}
        for sf, L in legs.items():
            A0 = rig.head(L["foot"])
            dx, dy, yw = stance.get(sf, (0.0, 0.0, 0.0))
            g = np.tile(np.array([A0[0] + dx, A0[1] + dy, ground]), (N, 1))
            Q = np.tile(rot_axis(UP, yw + sgn[sf] * toe_yaw), (N, 1, 1))
            G[sf] = (g, np.zeros(N), Q)
    # Ankle targets from the sole: lowest sole point exactly `lift` above the floor.
    ankle = {}
    if mode != "locomotion":
        toe_pivot = False
    for sf, L in legs.items():
        g, lift, Q = G[sf]
        A0 = rig.head(L["foot"])
        g0 = np.array([A0[0], A0[1], ground])
        pts = np.array(sole.get(sf) or [g0]) - g0
        A = np.zeros((N, 3))
        for i in range(N):
            pr = pts @ Q[i].T
            j = int(np.argmin(pr[:, 2]))
            low = float(pr[j, 2])
            A[i] = g[i] + Q[i] @ (A0 - g0) + np.array([0, 0, lift[i] - low])
            if toe_pivot:
                d = pr[j] - QF[sf] @ pts[j]
                A[i, :2] -= d[:2] * float(1 - _smooth(0.03, 0.08, lift[i]))
        ankle[sf] = A
    # Hips: lower them where a leg would be straighter than `reach`.
    rest_h = rig.head(hips)
    Lsum = {sf: (np.linalg.norm(rig.head(L["shin"]) - rig.head(L["thigh"])), np.linalg.norm(rig.head(L["foot"]) - rig.head(L["shin"])))
            for sf, L in legs.items()}
    hip_off = {sf: rig.axes(hips).T @ (rig.head(L["thigh"]) - rest_h) for sf, L in legs.items()}
    need = np.zeros(N)
    for i in range(N):
        Rh = mo.R[hips][i]
        dz = 0.0
        for _ in range(10):
            hp = rest_h + mo.hips[i] + np.array([0, hips_y, -hips_drop - dz])
            worst = max(np.linalg.norm(ankle[sf][i] - (hp + Rh @ hip_off[sf])) / sum(Lsum[sf]) for sf in legs)
            if worst <= reach:
                break
            dz += (worst - reach + 0.002) * sum(Lsum["L" if "L" in Lsum else sf])
        need[i] = dz
    sm = _cyc_smooth_max(need, cyclic=cyclic)
    sm = (1 - level) * sm + level * sm.max()
    info["hipDropMm"] = [round(float(sm.min() * 1000), 1), round(float(sm.max() * 1000), 1)]
    mo.hips[:N, 1] += hips_y
    mo.hips[:N, 2] -= hips_drop + sm
    if cyclic:
        mo.hips[n] = mo.hips[0]
    # Legs.
    for sf, L in legs.items():
        g, lift, Q = G[sf]
        F = mo.foot[sf]
        out = {key: np.zeros((n + 1, 3, 3)) for key in ("thigh", "shin", "foot", "toe") if L.get(key)}
        d_th0 = _n(rig.head(L["shin"]) - rig.head(L["thigh"]))
        d_sh0 = _n(rig.head(L["foot"]) - rig.head(L["shin"]))
        F_th0, F_sh0 = frame(d_th0, np.cross(d_th0, FWD)), frame(d_sh0, np.cross(d_sh0, FWD))
        for i in range(N):
            hp = rest_h + mo.hips[i]
            H = hp + mo.R[hips][i] @ hip_off[sf]
            pd = F["pole"][i] * k
            w = float(np.clip(np.linalg.norm(pd) / 0.04, 0, 1)) if mode == "locomotion" else 0.0
            pole = _n(pd) * w * np.array([knee_spread, 1.0, 1.0]) + FWD * (1 - w)
            pole = pole + np.array([sgn[sf] * knee_out, 0, 0])
            if pole @ FWD < 0.15:                                # never let a knee point backwards
                pole = pole + FWD * (0.15 - pole @ FWD) * 2
            Kp, A2 = two_bone(H, ankle[sf][i], Lsum[sf][0], Lsum[sf][1], _n(pole), reach=0.999)
            d1, d2 = _n(Kp - H), _n(A2 - Kp)
            # Bend plane normal as the frame's side axis keeps the knee hinge untwisted.
            side = np.cross(d1, d2)
            if np.linalg.norm(side) < 1e-4:
                side = np.cross(d1, _n(pole))
            if side @ np.cross(d1, _n(pole)) < 0:
                side = -side
            out["thigh"][i] = frame(d1, side) @ F_th0.T @ rig.axes(L["thigh"])
            out["shin"][i] = frame(d2, side) @ F_sh0.T @ rig.axes(L["shin"])
            out["foot"][i] = Q[i] @ rig.axes(L["foot"])
            if "toe" in out:
                out["toe"][i] = Q[i] @ rig.axes(L["toe"])
        for key, arr in out.items():
            if cyclic:
                arr[n] = arr[0]
            mo.R[L[key]] = arr
        mo.foot[sf]["target_ankle"] = ankle[sf]
    mo.info.update(info)
    return info


# ---------------------------------------------------------------- arms out of the body


def clear_arms(mo, rig, spec, body, wrist_margin=0.035, elbow_margin=0.03, sharp=8.0):
    """Push elbows and wrists out of the body so arms (and sleeves) do not pass through clothes
    that are wider than the Mixamo mannequin. body(z) -> (a, b, yc): half-width, half-depth and
    centre y of the body's cross-section (an ellipse) at height z, or None where arms are free
    (e.g. above the shoulders). Upper arm and forearm are re-aimed with the smallest rotations;
    the hand keeps its world orientation."""
    hips = spec.get("hips", "hips")
    moved = 0.0

    def push(P, margin):
        e = body(P[2])
        if e is None:
            return P
        a, b, yc = e
        q = np.array([P[0] / (a + margin), (P[1] - yc) / (b + margin)])
        r = float(np.linalg.norm(q))
        if r > 1.6:
            return P
        if r < 1e-4:
            q, r = np.array([1e-4, 0.0]), 1e-4
        r2 = (r ** sharp + 1.0) ** (1.0 / sharp)
        q = q * (r2 / r)
        return np.array([q[0] * (a + margin), yc + q[1] * (b + margin), P[2]])

    for i in range(mo.n + 1):
        absr = {b: R[i] for b, R in mo.R.items()}
        pose, _ = rig.solve(absr, {hips: mo.hips[i]})
        for sf, A in spec["arms"].items():
            S = pose[A["upper"]][:3, 3]
            E = pose[A["fore"]][:3, 3]
            W = pose[A["hand"]][:3, 3]
            L1, L2 = np.linalg.norm(E - S), np.linalg.norm(W - E)
            E2 = S + L1 * _n(push(E, elbow_margin) - S)
            W2 = E2 + L2 * _n((W - E) + (E2 - E) * 0.0)
            W2 = E2 + L2 * _n(push(W2, wrist_margin) - E2)
            moved = max(moved, float(np.linalg.norm(W2 - W)))
            mo.R[A["upper"]][i] = rot_between(E - S, E2 - S) @ mo.R[A["upper"]][i]
            mo.R[A["fore"]][i] = rot_between(W - E, W2 - E2) @ mo.R[A["fore"]][i]
    return moved


# ---------------------------------------------------------------- bake


def new_action(arm, name, loop=True):
    act = bpy.data.actions.new(name)
    act.use_fake_user = True
    slot = act.slots.new(id_type="OBJECT", name=arm.name)
    layer = act.layers.new("Layer")
    strip = layer.strips.new(type="KEYFRAME")
    cb = strip.channelbag(slot, ensure=True)
    return act, slot, cb


def write_keys(cb, bone, rots, locs=None):
    """rots: (n, 4) wxyz local rotations; locs: (n, 3) local translations or None. Linear keys on
    frames 1..n."""
    n = len(rots)
    fr = np.arange(n, dtype=float) + 1
    grp = cb.groups.new(bone)
    for kq in range(4):
        fc = cb.fcurves.new(f'pose.bones["{bone}"].rotation_quaternion', index=kq)
        fc.group = grp
        fc.keyframe_points.add(n)
        fc.keyframe_points.foreach_set("co", np.stack([fr, rots[:, kq]], axis=1).ravel())
        fc.keyframe_points.foreach_set("interpolation", [1] * n)
        fc.update()
    if locs is not None and np.abs(locs).max() > 1e-7:
        for kq in range(3):
            fc = cb.fcurves.new(f'pose.bones["{bone}"].location', index=kq)
            fc.group = grp
            fc.keyframe_points.add(n)
            fc.keyframe_points.foreach_set("co", np.stack([fr, locs[:, kq]], axis=1).ravel())
            fc.keyframe_points.foreach_set("interpolation", [1] * n)
            fc.update()


def bake_action(arm, name, mo, rig, spec=None, loop=True, hang=None, bones=None):
    """Write the motion as an action on the target's own bones: one key per frame at 30 fps
    (frames 1..n+1), rotation on every bone (or just `bones`), location where it is non-zero (the
    hips). hang: see Rig.solve. Returns (action, slot)."""
    hips = (spec or {}).get("hips", "hips")
    act, slot, cb = new_action(arm, name, loop)
    n = mo.n + 1
    names = [b for b in rig.order if bones is None or b in bones]
    rots = {b: np.zeros((n, 4)) for b in names}
    locs = {b: np.zeros((n, 3)) for b in names}
    for i in range(n):
        pose, basis = rig.solve({b: R[i] for b, R in mo.R.items()}, {hips: mo.hips[i]}, hang)
        for b in names:
            t, Rb = basis[b]
            q = _q(Rb)
            q = np.array([q.w, q.x, q.y, q.z])
            if i > 0 and rots[b][i - 1] @ q < 0:
                q = -q
            rots[b][i] = q
            locs[b][i] = t
    for b in names:
        write_keys(cb, b, rots[b], locs[b])
    act.use_frame_range = True
    act.frame_start, act.frame_end = 1, n
    act.use_cyclic = loop
    return act, slot


# ---------------------------------------------------------------- measurement


def slip_report(arm, shoe, side_idx, action, slot, speed, n_frames, sub=4, contact=0.003, ground=0.0, fps=FPS):
    """Foot slip of a baked in-place locomotion loop, measured on the SKINNED shoe mesh the way
    the game will show it: the action is evaluated `sub` times per frame (linear keys in between),
    and whenever a shoe's lowest vertex is within `contact` of the floor its horizontal velocity
    is compared with the ground's (0, +speed in Blender Y: the floor moves back under a character
    walking toward -Y). side_idx: {"L": vertex indices, "R": ...} of the shoe mesh. n_frames:
    keys in the cycle; fps: their rate (the Motion's fps).
    Returns max / p95 slip in cm/s and the contact height range in mm."""
    sc = bpy.context.scene
    ad = arm.animation_data or arm.animation_data_create()
    ad.action = action
    try:
        ad.action_slot = slot
    except Exception:
        pass
    m = n_frames * sub
    dt = n_frames / fps / m
    P = {sf: [] for sf in side_idx}
    M = np.array(shoe.matrix_world)
    for i in range(m):
        fr = i / sub
        sc.frame_set(1 + int(fr), subframe=fr - int(fr))
        dg = bpy.context.evaluated_depsgraph_get()
        ev = shoe.evaluated_get(dg)
        me = ev.to_mesh()
        co = np.zeros(len(me.vertices) * 3)
        me.vertices.foreach_get("co", co)
        ev.to_mesh_clear()
        co = co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3]
        for sf, idx in side_idx.items():
            P[sf].append(co[idx])
    slips, zr, worst, worst_at, bad = [], [1e9, -1e9], 0.0, None, []
    for sf in P:
        A = np.array(P[sf])
        for i in range(m):
            kk = int(np.argmin(A[i, :, 2]))
            z = A[i, kk, 2] - ground
            if z > contact:
                continue
            vel = (A[(i + 1) % m, kk] - A[(i - 1) % m, kk]) / (2 * dt)
            s = math.hypot(vel[0], vel[1] - speed)
            slips.append(s)
            zr = [min(zr[0], z), max(zr[1], z)]
            if s > 0.03:
                bad.append((sf, round(i / sub, 2), round(z * 1000, 1), round(s * 100, 1)))
            if s > worst:
                worst, worst_at = s, f"{sf} frame {i / sub:.2f}"
    slips = np.array(slips) if slips else np.zeros(1)
    return {"speed": round(speed, 4), "stance_samples": int(len(slips)), "max_stance_slip_cm_s": round(float(slips.max()) * 100, 2),
            "p95_stance_slip_cm_s": round(float(np.percentile(slips, 95)) * 100, 2), "worst_at": worst_at,
            "stance_contact_z_mm": [round(zr[0] * 1000, 1), round(zr[1] * 1000, 1)], "over_3cm_s": bad[:40]}


# ---------------------------------------------------------------- turn limit (looking around)


def limit_turn(mo, rig, caps, chain=("hips", "spine", "spine1", "spine2", "chest", "neck", "head"), tilt=None):
    """Soft-limit how far the trunk and head turn about the vertical (a Mixamo "looking around"
    clip turns the whole mannequin, which a character with planted feet cannot follow).
    caps: {bone: max heading in degrees away from straight ahead}, for bones of `chain` (root to
    head). Each capped bone's heading psi becomes cap * tanh(psi / cap); every other bone (arms,
    fingers) turns with its nearest capped ancestor, so limbs stay attached the way they were.
    tilt: {bone: gain} scales what is left of a capped bone's rotation once its heading is taken
    out (its nod and lean), e.g. 0.6 for a head that looks at the ground behind it in the source.
    Call it after transfer() and before plant_feet(). Returns {bone: (max |heading| before, after)}."""
    n = mo.n
    fwd0 = {}
    psi, corr, out = {}, {}, {}
    for b in chain:
        if b not in mo.R or b not in caps:
            continue
        f = np.einsum("nij,j->ni", mo.R[b] @ rig.axes(b).T, FWD)
        p = np.unwrap(np.arctan2(f[:, 0], -f[:, 1]))
        p -= 2 * math.pi * round(float(np.median(p)) / (2 * math.pi))
        cap = math.radians(caps[b])
        p2 = cap * np.tanh(p / cap)
        corr[b] = np.degrees(p2 - p)
        psi[b] = np.degrees(p2)
        out[b] = (round(float(np.degrees(np.abs(p)).max()), 1), round(float(np.degrees(np.abs(p2)).max()), 1))

    def owner(b):
        while b and b not in corr:
            b = rig.parent.get(b)
        return b

    for b in list(mo.R):
        o = owner(b)
        if o is None:
            continue
        for i in range(n + 1):
            if abs(corr[o][i]) > 1e-6:
                mo.R[b][i] = rot_axis(UP, corr[o][i]) @ mo.R[b][i]
    for b, g in (tilt or {}).items():
        if b not in psi:
            continue
        R0 = rig.axes(b)
        for i in range(n + 1):
            Y = rot_axis(UP, psi[b][i])
            T = Y.T @ mo.R[b][i] @ R0.T                   # nod and lean, heading removed
            mo.R[b][i] = Y @ scale_rot(T, g) @ R0
    return out
