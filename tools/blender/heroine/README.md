# Heroine (`public/models/heroine.glb`)

An original anime-style young woman in an indigo morning-glory yukata, marigold obi with a
butterfly bow, chestnut updo with a flower kanzashi, wooden geta. Built entirely by script in
headless Blender (no hand edits, no external assets). The output is deterministic.

## Rebuild

```
E:\blender\blender-5.1.2-windows-x64\blender.exe --background --factory-startup ^
    --python tools/blender/heroine/build.py -- --previews --verify
```

Options after `--`: `--out <glb>` (default `public/models/heroine.glb`), `--no-export`,
`--no-anim`, `--previews` (PNG stills into `previews/`), `--verify` (re-imports the GLB in a clean
scene and writes `glb_summary.json`), `--only face` / `--only gait` / `--only anim` (quick iteration:
just the face stills; the clips with the idle/walk/run strips and foot-slip report; or the clips
with every pose still; no export). Every build with clips writes `gait_report.json` (see Walk and
run below). The build takes about 35 s, plus about 1 min for previews. It runs at below-normal
priority and the Blender process exits when it is done.

**The clips need the raw Mixamo FBX files** in `assets/mixamo/` (`idle_f`, `walk_f`, `run_f`, `wave`,
`bow`, `eat`, `talk`, `cheer`, `point`, `look`). They are gitignored (Adobe's terms) and never
copied anywhere; `assets/mixamo/MANIFEST.md` lists what to download again. The build stops with a
clear message if one is missing. Only the motion is used: each FBX is sampled and its import is
deleted before anything else happens, and the build asserts no Mixamo object or bone is left.

Files: `build.py` is the entry point. `lib/` has `shape.py` (proportions and joints), `head.py`,
`hair.py`, `body.py`, `outfit.py`, `tex.py` (procedural textures), `rig.py` (armature and
analytic weights), `anim.py` (hand-made task clips, baker, gait checks), `mocap.py` (the clip table
and her side of the Mixamo retarget; the generic part is `tools/blender/mixamo/retarget.py`),
`attach.py`, `export.py`, `glbpost.py` (GLB post-pass: scale tracks out, clip facts into extras, key
reduction), `verify.py` and `preview.py`. `build_meta.json` holds the clip
metadata, and the same JSON is stored on the armature node as `extras.heroine`.

## Space, size and facing

- glTF Y-up, metres. **She faces +Z** (Blender −Y). Her left hand is on +X.
- Scene root node: `heroine_rig` (armature). Origin is on the ground between her feet.
- **The geta soles touch y = 0.** Her bare soles, standing on the geta, are at **y = 0.05**.
- Top of hair is at y = **1.566** (about 1.52 m barefoot body plus the geta). Eyes are centred at about 1.436.
- Bind-pose bounds (arms hang about 30° from the body, sleeves wide): x ±0.432, y 0…1.566,
  z −0.162…+0.174 (glTF).
- The bind pose is a relaxed A-pose (arms about 30° from the body), not a T-pose.

## Meshes (all skinned to one skin, 39,136 triangles)

| node | tris | | node | tris |
|---|---|---|---|---|
| heroine_head | 4840 | | heroine_yukata | 7844 |
| heroine_hair | 8168 | | heroine_sleeve_L | 1992 |
| heroine_kanzashi | 2148 | | heroine_sleeve_R | 1992 |
| heroine_neck | 1520 | | heroine_obi | 3216 |
| heroine_arms | 3888 | | heroine_legs | 2048 |
| heroine_geta | 1480 | | | |

The GLB is 2.94 MB (2,943,244 bytes), uncompressed (no Draco/Meshopt). Each vertex has at most 4 normalized influences.
It has two packed PNG textures: `T_heroine_yukata` (1024², tiling pattern) and `T_heroine_eye` (256²).

## Materials (base colour or texture = albedo, metallic 0, roughness 1)

`skin`, `hair`, `eye`, `face_line`, `face_brow`, `face_mouth`, `face_nose`, `face_blush`,
`cloth_yukata` (textured), `cloth_collar` (white han-eri), `cloth_obi`, `cloth_obijime`,
`cloth_hanao` (red geta thongs), `wood_geta`, `metal_kanzashi`, `plastic_flower_pink`,
`plastic_flower_white`, `plastic_bead`, `plastic_obidome`.

## Bones (67)

```
root > hips > spine > spine1 > spine2 > neck > head
head      > hairSideL1 > hairSideL2, hairSideR1 > hairSideR2,
            hairBack1 > hairBack2 > hairBack3, hairBun1 > kanzashi1 > kanzashi2
spine2    > shoulder_L > upperarm_L > forearm_L > hand_L > thumb_L, fingers_L
            forearm_L > sleeve_L1 > sleeve_L2         (same for _R)
hand_L    > finger_thumb_1_L > finger_thumb_2_L, finger_index_1_L > finger_index_2_L,
            finger_middle_1_L > finger_middle_2_L, finger_ring_1_L > finger_ring_2_L,
            finger_pinky_1_L > finger_pinky_2_L       (same for _R)
spine     > obiTailL1 > obiTailL2, obiTailR1 > obiTailR2
hips      > thigh_L > shin_L > foot_L > toe_L          (same for _R)
hips      > skirtF1, skirtB1
```

The first 47 bones are unchanged (name, parent, rest pose). New: 20 finger bones,
`finger_<thumb|index|middle|ring|pinky>_<1|2>_<L|R>`, the same names as the townspeople's. Each `_1`
is a child of the hand, `_2` a child of `_1`; their rest pose is a relaxed curl. Each hand has five
separate fingers weighted to them. `thumb_L/R` and `fingers_L/R` (the old one-bone controls) are
still there for compatibility but no vertex is weighted to them and the clips leave them at rest.

Every full-body clip has a rotation track on every bone (head and neck included). Translation
tracks exist only where a bone really moves (hips, skirtF1, skirtB1). The game can play the
secondary chains (sleeves, hair, kanzashi dangles, obi tails, skirt) as they are; if it adds its own
sway, it should add it on top of the clip.

## Clips (in place, translation and rotation only, no scale keys)

| clip | duration s | loop | source | notes |
|---|---|---|---|---|
| idle | 10.0 | yes | Mixamo `idle_f` | arms at her sides, narrow stance |
| walk | 0.8667 | yes | Mixamo `walk_f` | **0.956 m/s** at rate 1 (stride 0.83 m); footDownL 0.20, footUpL 0.60, footDownR 0.60, footUpR 0.167 |
| run | 0.4 | yes | Mixamo `run_f` | **2.295 m/s** at rate 1 (stride 0.92 m); footDownL 0.133, footUpL 0.233, footDownR 0.35, footUpR 0.067; keyed at 60 Hz |
| talk | 6.8333 | yes | Mixamo `talk` | frames 20-225 of the source, ends closed over 14 frames |
| look | 6.3333 | yes | Mixamo `look` | looks around over both shoulders; turn limited to head 69°, chest 28° (`retarget.limit_turn`); feet stay planted |
| wave | 1.8667 | **no** | Mixamo `wave` | the 16-frame wave loop played 3.5 times, eased from/to the idle pose |
| bow | 2.2667 | **no** | Mixamo `bow` | source frames 10-78 |
| eat | 3.9333 | **no** | Mixamo `eat` | source frames 56-174 (the drink); LEFT hand to the mouth |
| cheer | 2.9 | **no** | Mixamo `cheer` | both fists pumping overhead |
| point | 2.2667 | **no** | Mixamo `point` | right arm, forward |
| crouch | 3.0 | yes | hand-made | strokeForward 0.375, 1.875 (right hand reaches forward-low, e.g. stroking a cat) |
| reach | 3.0 | yes | hand-made | right hand held out forward at chest height (wrist about 0.40 m in front) |
| throw | 1.2 | **no** | hand-made, ends re-based on the idle | **release 0.62**; at release, hand_R palmCentre ≈ (−0.157, 0.881, 0.364), hand velocity ≈ (0.32, 2.3, 3.24) m/s (model space, she faces +Z) |
| lookup | 4.0 | yes | hand-made | head and chest tilted up at fireworks |
| add_ref | 0 (1 key) | – | authored | additive reference: her rest pose on spine, spine1, spine2, neck, head |
| add_nod | 0.6 | no | authored | additive: one nod, 12° at the peak |
| add_shake | 0.8 | no | authored | additive: head shake, ±11° |
| add_look_l / add_look_r | 0.4 | no | authored | additive: head + upper spine turn 35° to her left / right; eases in and ENDS on the full turn |

- **Clip speeds for the game** are in the GLB: `scenes[0].extras.clipSpeed = { walk: 0.956, run: 2.295 }`
  (three.js: `gltf.scene.userData.clipSpeed`), repeated on the armature node
  (`nodes[heroine_rig].extras.clipSpeed`, next to the `heroine` JSON string). `scenes[0].extras.clips`
  has duration / loop / speed / stride / foot events per clip. Play walk and run at
  `rate = actualSpeed / clipSpeed`. (Her walk at 1.15 m/s is rate 1.20, her run at 2.75 m/s rate 1.20.)
- The one-shots `wave`, `bow`, `eat`, `cheer`, `point` and `throw` start and end exactly on the
  idle's first pose. `throw` is authored on the old hands-clasped standing pose; its first 0.25 s
  and last 0.25 s are eased from / to the idle pose (`anim.rebase`), and from 0.25 s to 0.95 s it is
  exactly as authored, so the release (0.62 s), release point and hand velocity are unchanged.
  `crouch`, `reach` and `lookup` are looping hold poses with no start or end of their own; the game
  cross-fades into them, and they are unchanged.
- **Additive layers**: the `add_*` clips have rotation tracks on spine, spine1, spine2, neck and head
  only. `THREE.AnimationUtils.makeClipAdditive(clip, 0, add_ref)` for each, then play them on top of
  anything. `add_look_l/r` are meant to be clamped (`clampWhenFinished`) and faded by weight.
- The root bone never moves and the hips never travel: over any clip the hips stay within a few cm
  of the origin horizontally (bob and sway only) and end where they started (`gait_report.json` →
  `clips`). The head's yaw at the last key equals the first on every clip.
- Keys: 30 per second, except the run (60 per second: joint rotations are interpolated linearly
  between keys, and at running speed a planted foot needs the denser keys to stay under 3 cm/s). In
  the GLB, keys of the retargeted standing clips that linear interpolation reproduces within 0.1° /
  0.2 mm are dropped; walk, run and the four hand-made clips keep every key.

### Walk and run

Both come from Mixamo's female walk / run and were reshaped for a yukata with a narrow hem and
rigid geta (`CLIPS` in `lib/mocap.py`):

- **Walk**: the 35-frame source cycle is played in 26 frames (2.3 steps/s) with 72% of the
  leg-scaled stride: 0.41 m steps. Feet land 5 cm either side of the centre line, toes 3° out, the
  swing foot clears the ground by at most 6 cm, knees follow the source at a quarter of its
  sideways spread. Pelvis and spine rotation are about half the source's, so the hips sway but the
  skirt is not thrown about and she does not lean back.
- **Run**: a light upright jog. The 18-frame source cycle is played in 12 frames (5 steps/s) with
  42% of the leg-scaled stride: 0.46 m steps, with a flight phase (each foot is down for about a
  third of the cycle). The torso leans 10.5° forward (8.7-11.7° over the cycle); the pelvis rides
  2.4-3.5 cm below its rest height (the idle stands about 1.1 cm below rest), and the stance leg is
  96-99% extended. The heel kicks up behind right after toe-off (up to 12 cm) and the foot then
  comes through low, so the knee is not driven up into the front of the skirt. Arm pump is 40-50%
  of the source's. The stance is moved 5 cm forward.
- A planted geta is flat, its lowest point exactly on the floor, and moves straight back at exactly
  the clip speed; it keeps moving with the ground for one more key while it lifts or lands.
- The skirt's front panel follows the forward leg and the back panel the rear leg. Checked on
  8-frame strips from the side, front and back: no leg comes through the skirt in either gait.
- `gait_report.json`: measured on the baked, skinned geta mesh, 4 samples per key with linear
  interpolation between keys. A foot counts as in contact while its lowest vertex is within 3 mm of
  the floor. Stance-foot slip at the clip speed: **walk max 1.13 cm/s (p95 1.06)**, **run p95
  1.37 cm/s**, with one sample of 60 at 11.1 cm/s (right foot, the instant it starts to roll onto
  its front tooth at lift-off: the measurement follows a heel vertex that is leaving the floor;
  every other sample is under 3 cm/s). Contact height stays between −0.6 and +2.3 mm. Loop seam is 0.

## Face

Proportions follow the usual modern-anime front-view construction, checked against reference
photos of young women in yukata at summer festivals (kept locally in `refs/heroine/`, never
committed). Heights below are glTF y (barefoot frame + 0.05).

- Head: crown 1.555, chin 1.341 (0.214 m). One broad, softly blended lower-face volume forms a
  continuous oval from the cheekbones to a small round chin, with no crease beside the nose. Head
  normals come from the analytic surface, not the tessellation, so a hard toon terminator crosses the
  face cleanly. They are kept in the GLB (exported normals are within 0.04° of the analytic ones).
  The ears keep their mesh normals and sit flush on the actual head surface.
- Eyes: centre 1.436, about the vertical middle of the head. 30 mm wide, 29 mm tall (about 1/6 of
  the hairline-to-chin face), one eye width (29 mm) apart. Warm brown iris with two highlights and a
  sparkle, a firm upper lash line with a small outer flick, and a thin lower lid on the outer half.
- Brows about 1.465, soft and arched, below the bang tips. The bangs end above the brows
  (tips 1.463 to 1.482), so the eyes and brows are always clear.
- A small nose tick (1.389), a small closed mouth with the corners slightly up (1.368), a faint
  lower-lip shade, and soft oval blush under the outer half of each eye. Ears 1.408 to 1.450.
- All 2,637 head vertices are weighted 100% to `head`. No bone or shape key enlarges the eyes:
  `blink` only closes them and `smile` only moves them. Measured on the exported GLB, the left eye
  is 30.3 × 29.6 mm at rest (29.7 with `smile`, which lifts the eye along an arc without opening it), and 30.3 × 13.4 mm (the closed arc) with `blink`
  or with `blink` + `smile`, which close cleanly together without overshoot.

Hair cap: the shell is a grid aligned to the hairline (112 columns). Its last ring lies on the
hairline curve, 1.2 mm under the skin, and it reaches full thickness within about 9 mm. The edge is
a clean curve: forehead, a soft sideburn in front of the ear, an arc over the ear, then down behind
the ear to the nape under the bun (`HAIRLINE` in `lib/hair.py`).

## Morph targets (on `heroine_head`)

| name | effect |
|---|---|
| `blink` | both lids meet on a soft arc 30% up from the lower lid; the lash line folds onto it |
| `smile` | closed-mouth smile (wider, corners up), eyes bow upward a little, brows and blush lift |

Both are 0 at rest, and no clip animates them. The game drives them, for example with a random blink every 2–6 s that lasts about 0.12 s.

## Attachment points (bone-local offsets, glTF metres)

| point | bone | local offset | notes |
|---|---|---|---|
| hand_R.palmCentre | hand_R | (0, 0.048, −0.013) | palm normal = local (0, 0, −1) |
| hand_R.gripCentre | hand_R | (0, 0.060, −0.022) | grip axis (stick/handle) = local (1, 0, 0) |
| head.maskCentre | head | (−0.097, 0.122, 0.016) | festival mask on her right temple; mask forward = local (−0.932, 0.233, 0.279), up = (0.148, 0.984, −0.098) |

The head bone's local axes match the glTF world axes in the bind pose. To attach an object,
make it a child of the bone and set its position to the local offset.

## Previews (`previews/`)

Turnaround: `front`, `three_quarter`, `side`, `back`. Also `game_camera` (3 m behind, 1.7 m up),
`face`, `face_3q`, `face_side`, `face_blink`, `face_smile`, `face_blink_smile` and `face_at_3m`.
Lit face checks (EEVEE on the GPU, skin swapped for a hard-terminator toon shader like the game's
cel step): `face_toon_key` and `face_toon_key_3q` (one sun from the upper front-left),
`face_toon_side` (sun from her left side) and `face_flat` (unshaded).
Strips (8 evenly spaced frames per cycle, side and front): `strip_idle_*`, `strip_walk_*`,
`strip_run_*`. Poses: `pose_idle`, `pose_walk_mid`, `pose_walk_gamecam`, `pose_run_mid`,
`pose_run_front`, `pose_crouch`, `pose_crouch_side`, `pose_reach`, `pose_throw_release`,
`pose_lookup`; a mid-pose still, front and `_side`, for `pose_wave`, `pose_bow`, `pose_eat`,
`pose_cheer`, `pose_point`, `pose_talk`, `pose_look` (at the frame of the largest head turn); hands: `pose_hand_idle`, `pose_hand_reach`,
`pose_hand_cheer`. They are Workbench renders, made
on the RTX 4060 (OpenGL backend). The build checks the GPU renderer string after the first render
and stops if it is not the NVIDIA GPU (`HEROINE_ALLOW_SOFTWARE=1` overrides that on a machine with no GPU).

## GLB summary (re-imported in Blender after export, see `glb_summary.json`)

- 11 meshes, 39,136 triangles, 67 bones, 2874.3 KiB (2,943,244 bytes)
- 19 clips: idle 10.0, walk 0.8667, run 0.4, talk 6.8333, look 6.3333, wave 1.8667, bow 2.2667,
  eat 3.9333, cheer 2.9, point 2.2667, crouch 3.0, reach 3.0, throw 1.2, lookup 4.0, add_ref 0,
  add_nod 0.6, add_shake 0.8, add_look_l 0.4, add_look_r 0.4
- Animation channels: 963 rotation and 42 translation, 0 scale
- Morphs: heroine_head [blink, smile]. Max influences 4. No extensions used.
