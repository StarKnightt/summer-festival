# Mixamo motion onto our own rigs (`retarget.py`)

Takes the motion of a Mixamo clip (FBX, "Without Skin", 30 fps) and bakes it onto one of the game's
own armatures in Blender. Only the motion is taken: the FBX is sampled in world space and its import
is deleted straight away, so no Mixamo bone, mesh or action reaches the output. The raw FBX files
stay in `assets/mixamo/` (gitignored; see `MANIFEST.md` there) and must never be copied into
`public/` or committed.

Used by the heroine build (`tools/blender/heroine/lib/mocap.py` is the worked example) and meant for
the townspeople rig too (`maps/people.json`).

## Calling it for another rig

Run inside Blender (headless is fine) with `tools/blender/mixamo` on `sys.path`:

```python
import retarget as rt

rig  = rt.Rig(arm)                                        # the target armature object (rest pose is read)
spec = rt.load_spec("tools/blender/mixamo/maps/people.json")       # bone map and chains (data)
spec["sole"] = rt.sole_from_mesh(shoe_mesh, {"L": "foot_L", "R": "foot_R"})   # bottom of each shoe

src  = rt.load_fbx("assets/mixamo/walk.fbx")              # sampled; nothing of the import is kept

# 1. rotation retarget (world space, rest-pose difference handled per bone, hips scaled by leg length)
mo   = rt.transfer(src, rig, spec, frames=30)             # frames: cycle length at 30 fps (time-stretch)

# 2. feet: stance detection from the source, planted feet pinned with leg IK
info = rt.plant_feet(mo, rig, spec, mode="locomotion", stride_scale=0.85, stance_x=0.07)
#    info["speed"] = ground speed in m/s at rate 1; info["events"] = foot down / up times

# 3. optional: keep elbows and wrists out of a body that is wider than the mannequin
rt.clear_arms(mo, rig, spec, body)                        # body(z) -> (half_width, half_depth, centre_y) or None

# 4. keys on the target's own bones, one per frame at 30 fps
act, slot = rt.bake_action(arm, "walk", mo, rig, spec, loop=True, hang={"sleeve_L1": 0.85, "sleeve_R1": 0.85})

# 5. measure the result on the skinned shoe mesh, as gait_report.json does
rep = rt.slip_report(arm, shoe_mesh, {"L": left_vertex_indices, "R": right_vertex_indices},
                     act, slot, info["speed"], mo.n, fps=mo.fps)
```

Standing clips use `mode="planted"`: `rt.plant_feet(mo, rig, spec, mode="planted", stance={"L": (dx, dy,
yaw_deg), "R": (...)}, cyclic=<clip loops>)` keeps both feet flat at those offsets from their rest
position. For a one-shot, `mo.blend_edges(idle_mo.pose(0), n_in, None, n_out)` (call it between
`transfer` and `plant_feet`, with `transfer(..., hips_origin="ends")`) makes it start and end on the
idle pose. `mo.close_loop(frames)` closes a loop cut out of a longer clip (`trim=(a, b)`;
`src.find_loop(min_len, max_len)` suggests where to cut). `src.resampled(np.arange(m + 1) % L)`
tiles a short loop.

## The data that drives it (`maps/*.json`)

| key | meaning |
|---|---|
| `bones` | Mixamo bone name (no `mixamorig:` prefix) → target bone. Bones the target lacks are left out; because the retarget works on world-space deltas, their motion is absorbed by the next mapped bone (the people rig maps `Spine`→`spine`, `Spine2`→`chest`). |
| `blend` | target bone → `[second Mixamo bone, weight]` mixed into its rotation (our second finger bone spans Mixamo's joints 2 and 3). |
| `hand_side` | hand → `[index knuckle bone, pinky knuckle bone]`: gives the palm direction for the hand's rest-frame alignment. |
| `legs`, `arms`, `hips`, `ground` | the chains the foot pass and the arm pass rebuild, and the floor height. |
| `modes` (optional) | target bone → `"delta"`, `"aim"` or `"frame"` to override the default below. |
| `sole` (set at run time) | per side, the rest positions of the shoe's bottom points (`sole_from_mesh`). |

`rt.default_spec(bone_names)` builds this for any rig that follows the project's naming.

## How it works

**Rotation.** For each mapped pair, `D(f) = Rs(f) · Rs0ᵀ` is the source bone's world rotation away
from its own rest pose, and the target gets `Rt(f) = D(f) · C · Rt0`. `C` is the rest-pose
difference, per bone:

- *delta* bones (hips, spine, neck, head, clavicles, feet): `C = 1`.
- *aim* bones (upper arm, forearm, thigh, shin, fingers): `C` is the smallest rotation that takes the
  target's rest direction (after its parent's correction) onto the source's rest direction. This is
  what reconciles an A-pose, or fingers whose rest is a relaxed curl, with Mixamo's T-pose.
- *frame* bones (hands): `C` aligns a full frame (wrist → middle knuckle, index → pinky).

Options on `transfer`: `gains={bone: g}` scales a bone's world delta (a calmer pelvis),
`amp={bone: a}` scales its swing about its own mean (a smaller arm swing), `hips_gain=(side,
fore-aft, vertical)`, `trim`, `frames`, `key_rate`.

**Hips.** The hips' travel is scaled by the leg-length ratio (target thigh + shin over source) and
taken about the clip's mean position, so there is no root motion: the hips keep their bob and sway
and nothing else. The root bone is never keyed.

**Feet (`plant_feet`, `mode="locomotion"`, for in-place walk/run loops).**

1. Stance per foot from the source: the sole is low (heel or toe within `clear_thr` of its standing
   height) and the foot is moving back at about the ground speed (the median of those velocities).
2. Clip speed = source ground speed × leg ratio × `stride_scale`. It is returned, not imposed: the
   game plays the clip at `actualSpeed / clipSpeed`.
3. A planted foot is pinned to a straight line: it moves back at exactly that speed, at a fixed
   sideways distance `stance_x`, flat, with the lowest sole point on the floor. The horizontal pin
   lasts `extend` keys beyond the stance at each end, so a foot leaving or meeting the floor moves
   with the floor.
4. In swing the foot follows the source's path about the chord between the pinned ends, lifted by
   the scaled source clearance (`swing_scale`, `min_lift`, `max_lift`) and pitched by `pitch_gain` ×
   the source pitch.
   `lift_late` / `lift_fade` scale the lift down late in the swing (heel kicks up behind, foot comes
   through low: for long skirts), and `toe_pivot=True` rocks a pitched foot about its lowest sole
   point while it is still near the floor.
5. Legs are two-bone IK; knees follow the source's knee direction with its sideways part scaled by
   `knee_spread`. The hips drop just enough that no leg is straighter than `reach`.

**Key rate.** Keys are 30 per second. Joint rotations are interpolated linearly between keys, so a
planted foot wanders slightly between them; at running speed that was 3-4.5 cm/s for the heroine.
`transfer(..., key_rate=60)` gives a Motion with twice the samples (the heroine's run uses it:
p95 1.4 cm/s). An action baked from it is twice as long in Blender frames, so scale that
clip's key times by `30 / key_rate` on export (`heroine/lib/glbpost.py` does this).

**Turn limit (`limit_turn`).** For "looking around" clips that turn the whole mannequin: `rt.limit_turn(mo, rig,
{"hips": 6, "spine": 16, "chest": 28, "neck": 48, "head": 68}, tilt={"head": 0.45})` soft-limits each trunk bone's
heading (cap x tanh), turns arms with their nearest capped ancestor, and optionally scales the nod and lean that is
left. Call it between `transfer` and `plant_feet`. The townspeople's `look` uses it; the heroine's does not yet.

## Notes for the townspeople

- `maps/people.json` is ready: 39 bones mapped (no toe bones, `chest` takes `Spine2`).
- All five variants share bone names but not proportions. The people build (`people/npc/mocap.py`) retargets once,
  on the woman, and shares the rotations; it builds a `Rig` per variant only to push arms out of each body, and scales
  the hips travel per variant through rest scales in the GLB (see the people README, Version 4).
- The rig's bones must point along the limb (head → tail); roll is free.
- `bake_action(..., hang={bone: k})` keeps a share `k` of a helper bone's rest world orientation
  (hanging sleeves) instead of letting it follow the arm rigidly.
- Assert afterwards that nothing of Mixamo is left (`"mixamo" in name` over objects and bones), as
  `heroine/lib/mocap.py` does.
