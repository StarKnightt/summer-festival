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
scene and writes `glb_summary.json`). The build takes about 20 s, plus about 1 min for previews.
It runs at below-normal priority and the Blender process exits when it is done.

Files: `build.py` is the entry point. `lib/` has `shape.py` (proportions and joints), `head.py`,
`hair.py`, `body.py`, `outfit.py`, `tex.py` (procedural textures), `rig.py` (armature and
analytic weights), `anim.py` (clips), `attach.py`, `export.py`, `glbpost.py` (removes the
exporter's constant scale tracks), `verify.py` and `preview.py`. `build_meta.json` holds the clip
metadata, and the same JSON is stored on the armature node as `extras.heroine`.

## Space, size and facing

- glTF Y-up, metres. **She faces +Z** (Blender −Y). Her left hand is on +X.
- Scene root node: `heroine_rig` (armature). Origin is on the ground between her feet.
- **The geta soles touch y = 0.** Her bare soles, standing on the geta, are at **y = 0.05**.
- Top of hair is at y = **1.566** (about 1.52 m barefoot body plus the geta). Eyes are at about 1.43.
- Bind-pose bounds (arms hang about 30° from the body, sleeves wide): x ±0.432, y 0…1.566,
  z −0.162…+0.174 (glTF).
- The bind pose is a relaxed A-pose (arms about 30° from the body), not a T-pose.

## Meshes (all skinned to one skin, 37,812 triangles)

| node | tris | | node | tris |
|---|---|---|---|---|
| heroine_head | 4828 | | heroine_yukata | 7844 |
| heroine_hair | 7016 | | heroine_sleeve_L | 1992 |
| heroine_kanzashi | 2148 | | heroine_sleeve_R | 1992 |
| heroine_neck | 1520 | | heroine_obi | 3216 |
| heroine_arms | 3728 | | heroine_legs | 2048 |
| heroine_geta | 1480 | | | |

The GLB is 2.29 MB, uncompressed (no Draco/Meshopt). Each vertex has at most 4 normalized influences.
It has two packed PNG textures: `T_heroine_yukata` (1024², tiling pattern) and `T_heroine_eye` (256²).

## Materials (base colour or texture = albedo, metallic 0, roughness 1)

`skin`, `hair`, `eye`, `face_line`, `face_brow`, `face_mouth`, `face_nose`, `face_blush`,
`cloth_yukata` (textured), `cloth_collar` (white han-eri), `cloth_obi`, `cloth_obijime`,
`cloth_hanao` (red geta thongs), `wood_geta`, `metal_kanzashi`, `plastic_flower_pink`,
`plastic_flower_white`, `plastic_bead`, `plastic_obidome`.

## Bones (47)

```
root > hips > spine > spine1 > spine2 > neck > head
head      > hairSideL1 > hairSideL2, hairSideR1 > hairSideR2,
            hairBack1 > hairBack2 > hairBack3, hairBun1 > kanzashi1 > kanzashi2
spine2    > shoulder_L > upperarm_L > forearm_L > hand_L > thumb_L, fingers_L
            forearm_L > sleeve_L1 > sleeve_L2         (same for _R)
spine     > obiTailL1 > obiTailL2, obiTailR1 > obiTailR2
hips      > thigh_L > shin_L > foot_L > toe_L          (same for _R)
hips      > skirtF1, skirtB1
```

Every clip keys all of these bones, including the secondary chains (sleeves, hair, kanzashi
dangles, obi tails, skirt). The game can play them as they are. If it adds its own sway, it
should add it on top of the clip.

## Clips (30 fps, in place, translation and rotation only, no scale keys)

| clip | duration s | loop | speed m/s | events (s from clip start) |
|---|---|---|---|---|
| idle | 4.0 | yes | – | – |
| walk | 0.7 | yes | **1.10** (stride 0.77 m) | footDownL 0.0, footUpR 0.07, footDownR 0.35, footUpL 0.42 |
| run | 0.4667 | yes | **2.70** (stride 1.26 m) | footDownL 0.0, footUpL 0.187, footDownR 0.233, footUpR 0.42 |
| crouch | 3.0 | yes | – | strokeForward 0.375, 1.875 (right hand reaches forward-low, e.g. stroking a cat) |
| reach | 3.0 | yes | – | right hand held out forward at chest height (wrist about 0.40 m in front) |
| throw | 1.2 | **no** | – | **release 0.62**; at release, hand_R palmCentre ≈ (−0.157, 0.881, 0.364), hand velocity ≈ (0.32, 2.3, 3.24) m/s (model space, she faces +Z) |
| lookup | 4.0 | yes | – | – |
| wave | 1.5 | **no** | – | – |

`throw` and `wave` start and end on the idle pose, so they cross-fade cleanly. To keep the feet
from sliding, scale the walk/run playback rate by `actualSpeed / clipSpeed`. In walk and run the
hips move up and down, but the root bone never moves.

## Morph targets (on `heroine_head`)

| name | effect |
|---|---|
| `blink` | both eyes closed into curved lash lines |
| `smile` | closed-mouth smile (corners up) |

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
`face`, `face_3q`, `face_blink`, `face_smile` and `face_at_3m`. Poses: `pose_idle`, `pose_walk_mid`,
`pose_walk_gamecam`, `pose_run_mid`, `pose_run_front`, `pose_crouch`, `pose_crouch_side`,
`pose_reach`, `pose_throw_release`, `pose_lookup`, `pose_wave`. They are Workbench renders, made
on the RTX 4060 (OpenGL backend).

## GLB summary (re-imported in Blender after export, see `glb_summary.json`)

- 11 meshes, 37,812 triangles, 47 bones, 2285.5 KiB
- Clips: crouch 3.0, idle 4.0, lookup 4.0, reach 3.0, run 0.4667, throw 1.2, walk 0.7, wave 1.5
- Animation channels: 376 translation and 376 rotation (8 clips × 47 bones), 0 scale
- Morphs: heroine_head [blink, smile]. Max influences 4. No extensions used.
