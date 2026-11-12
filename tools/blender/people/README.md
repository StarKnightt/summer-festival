# people.glb: festival townsfolk NPCs

Five original background characters for the street, built procedurally. The script is deterministic and nothing is downloaded. Output: `public/models/people.glb` (1 607 000 bytes, about 1.53 MiB; the budget is 2.5 MB).

## Rebuild

```
E:\blender\blender-5.1.2-windows-x64\blender.exe --background --factory-startup ^
  --python tools/blender/people/build.py -- --out public/models/people.glb
```

- Add `--no-previews` to skip the Eevee stills.
- The script lowers its own priority to below-normal. A run takes about 5 s, plus about 10 s for the previews.
- It writes `people_summary.json`, the re-import summary.
- It writes `previews/*.png`: lineups front, 3/4 and back; the game camera; clip frames from a street camera about 4 m away; face close-ups. Previews render on Eevee, and the GPU is asserted (`NVIDIA GeForce RTX 4060`).
- Code layout: `npc/geo.py` (mesh helpers), `npc/rig.py` (skeleton and weights), `npc/body.py` (body parts and garments), `npc/outfits.py` (the five designs), `npc/anim.py` (procedural clips), `npc/bl.py` (Blender objects and materials), `npc/glbtools.py` (GLB post-process), `npc/preview.py`.

## Nodes

Each variant is its own top-level skinned armature node. Its skinned mesh is its child.

| node | mesh | look | tris | height (m) | head top | hip | bbox min → max (glTF, m) |
|---|---|---|---|---|---|---|---|
| `npc_woman` | `npc_woman_body` | yukata, obi with small bow, hair bun with kanzashi | 6298 | 1.636 (bun) | 1.60 | 0.80 | (-0.338, 0, -0.151) → (0.338, 1.636, 0.180) |
| `npc_man` | `npc_man_body` | dark yukata, narrow kaku obi | 5356 | 1.75 | 1.74 | 0.875 | (-0.386, 0, -0.148) → (0.386, 1.75, 0.197) |
| `npc_kid` | `npc_kid_body` | jinbei (top and shorts), short hair | 4696 | 1.206 (cowlick) | 1.15 | 0.50 | (-0.232, 0, -0.111) → (0.232, 1.206, 0.112) |
| `npc_keeper` | `npc_keeper_body` | happi over dark clothes, twisted hachimaki, neck towel, apron, jika-tabi | 5204 | 1.707 | 1.70 | 0.85 | (-0.372, 0, -0.122) → (0.372, 1.707, 0.186) |
| `npc_elder` | `npc_elder_body` | stooped, light yukata, grey bun, uchiwa fan in the right hand | 5748 | 1.529 | 1.52 | 0.76 | (-0.341, 0, -0.151) → (0.319, 1.529, 0.313) |

- The origin is between the feet on the ground. Characters face +Z. There are no morph targets.
- The uchiwa is part of `npc_elder_body` and is 100% weighted to `hand_R`, so it follows every clip.
- The kid is intended to be scaled 0.9–1.05 in game. Scale the node uniformly; clips are scale-agnostic, apart from the root-translation note below.

### Loading: duplicate names

All five armatures use the same bone names, so three.js `GLTFLoader` makes them unique (`hips`, `hips_1`, …). It keeps the original name in `userData.name`, and the clips target the `npc_woman` bones. Restore the names before you bind a mixer:

```js
const gltf = await loader.loadAsync('/models/people.glb');
// 1) clip tracks were written with the loader's uniquified names (e.g. "hips_3.quaternion"): map them back
const orig = new Map();
gltf.scene.traverse(o => { if (o.userData.name) orig.set(o.name, o.userData.name); });
for (const clip of gltf.animations)
  for (const t of clip.tracks) {
    const i = t.name.lastIndexOf('.');
    const node = t.name.slice(0, i);
    t.name = (orig.get(node) ?? node) + t.name.slice(i);
  }
// 2) restore the object names
gltf.scene.traverse(o => { if (o.userData.name) o.name = o.userData.name; });
// 3) clone any variant and play any clip on it
const npc = SkeletonUtils.clone(gltf.scene.getObjectByName('npc_kid'));   // three/addons/utils/SkeletonUtils.js
const mixer = new THREE.AnimationMixer(npc);
mixer.clipAction(THREE.AnimationClip.findByName(gltf.animations, 'walk')).play();
```

## Skeleton (22 bones, identical on all variants)

```
root
└ hips
  ├ spine > chest
  │   ├ neck > head
  │   ├ shoulder_L > upperarm_L > forearm_L > hand_L   (+ forearm_L > sleeve_L1)
  │   └ shoulder_R > upperarm_R > forearm_R > hand_R   (+ forearm_R > sleeve_R1)
  ├ thigh_L > shin_L > foot_L
  └ thigh_R > shin_R > foot_R
```

- Names, hierarchy, rest directions and rolls are identical across variants (asserted by the build). Only joint positions differ, so every rotation clip plays on every variant.
- Rest pose: an A-pose with the arms 74° below horizontal.
- `sleeve_L1` and `sleeve_R1` drive the hanging yukata sleeve (tamoto). The clips animate them to hang under gravity with a little lag. They can be left alone or driven procedurally.

## Clips (30 fps, all loop seamlessly, in place)

Each clip has 22 rotation channels plus `root.position`. There are no scale keys and no other translations.

`root.position` is only a small bob and sway, in metres, for the reference skeleton (`refSkeleton` / `refHip`). It is not forward travel: move the NPC yourself at the clip speed. On another variant, multiply it by `nodes[npc_X].extras.npc.rootScale[clip]` (= hipHeight / refHip). Without the scaling, the kid sinks a few cm in the adult clips and adults barely bob in `run`. The game can also simply ignore root translation.

| clip | dur (s) | ref | speed (m/s, ref) | stride (m) | foot contacts (s, ground in → out) | notes |
|---|---|---|---|---|---|---|
| `idle` | 4.0 | woman | – | – | both planted | breathing, weight shift, glances |
| `walk` | 1.0 | woman | 0.90 | 0.90 | L 0.00→0.56, R 0.50→0.06 (wraps) | strikeL 0.00, toeOffR 0.06, strikeR 0.50, toeOffL 0.56 |
| `run` | 0.4667 | **kid** | 2.6 | 1.213 | L 0.000→0.131, R 0.233→0.364 | childlike skip-run; meant for kids |
| `sparkler` | 1.0 | woman | 0.90 | 0.90 | same as walk | walk, right arm up and forward drawing small circles; attach the sparkler to `hand_R` |
| `wave` | 2.0 | woman | – | – | planted | right hand waving overhead |
| `call` | 3.0 | woman | – | – | planted | lean, cupped right hand at the mouth (≈0.2–1.2 s), then gestures out to the side (the stall), back to rest |
| `talk` | 4.0 | woman | – | – | planted | conversational hand gestures and nods |
| `fan` | 4.0 | woman | – | – | planted | idle while fanning with the right hand (elder holds an uchiwa; others can be given one on `hand_R`) |
| `lookup` | 4.0 | woman | – | – | planted | looking up at the sky (fireworks), slight sway |

### Locomotion speed per variant

Play the clip at timeScale 1 and move the node at the speed below. The speed is linear in hip height: walk = 0.9·hip/0.80, run = 2.6·hip/0.50. If the game scales a node by `s`, multiply its speed by `s`. Both values are also in `extras.npc.walkSpeed` and `runSpeed`.

| variant | walk / sparkler | run |
|---|---|---|
| woman | 0.90 | (4.16, not intended) |
| man | 0.984 | (4.55, not intended) |
| kid | 0.562 | **2.60** |
| keeper | 0.956 | (4.42, not intended) |
| elder | 0.855 | (3.95, not intended) |

Kid walk is slower than adult walk because of shorter legs. To make a kid keep pace with an adult, raise its walk `timeScale` (≈1.5) and move it at 0.562 × timeScale.

## Materials

There is one material set, shared by all meshes. Metallic is 0 and roughness is 1. Every surface also has `COLOR_0` (vertex colour). It is mostly white, with baked detail such as collar-band and ring stripes, shading on the face features, and the fan rim. The game multiplies it into the albedo as per the contract.

| material | used for | base colour factor (default) |
|---|---|---|
| `skin` | skin | `#f4d3bf` |
| `face` | eyes, lashes, highlights, brows, blush, mouth (geometry projected onto the head) | white; colours come from COLOR_0. Do not tint. |
| `hair` | hair, buns | `#3b2b26` |
| `cloth_main` | main garment (yukata, jinbei, happi) | white × `people_cloth_pattern` texture |
| `cloth_accent` | obi, bow, collar bands, hachimaki, towel, geta straps (hanao), fan disc | `#e8c35a` |
| `cloth_dark` | under-layers, keeper trousers and apron, kid shorts | `#2c3346` |
| `wood_geta` | geta sandals, fan handle | `#c79a68` |
| `cloth_shoe` | keeper's jika-tabi | `#30323a` |

**Tinting.**
- `people_cloth_pattern` is a 1000×500 PNG with five 200 px columns, one per variant: woman blossoms, man stripes and kasuri dashes, kid polka dots, keeper lozenges, elder koshi grid.
- Each column tiles vertically. Motifs are 0.64 grey on white, so `albedo = tint × texture × COLOR_0` keeps the pattern readable in any colour.
- For crowd variety, set a per-instance tint as the base colour of each material, keeping the texture and COLOR_0. This works for `cloth_main` especially, and also for hair, accent, dark and skin.
- Suggested palettes per variant are in `extras.npc.tints`, which the previews use. Examples: woman `cloth_main #f19aa6` and `cloth_accent #f3c74f`; man `#40507a`; kid `#7cc3ea`; keeper `#d8423a`; elder `#cfc6e6`.

## Attachments (bone-local offsets, glTF coords, metres; also in `extras.npc`)

**`handR_palm`.** Palm centre on bone `hand_R`.
- `gripAxis` = (-0.2756, 0, -0.9613): the direction a held stick runs through the fist, toward the thumb side.
- `palmNormal` = (0.9613, 0, -0.2756).
- Offset per variant:

| variant | offset |
|---|---|
| woman | (0.0115, 0.0675, -0.0033) |
| man | (0.0131, 0.0765, -0.0037) |
| kid | (0.0083, 0.0486, -0.0024) |
| keeper | (0.0129, 0.0756, -0.0037) |
| elder | (0.0109, 0.0639, -0.0031) |

Use it for the sparkler, a held fan, a goldfish bag or a candy apple.

**`headTopOffset`.** Top of the scalp on bone `head`, for name tags and emote bubbles.

| variant | offset |
|---|---|
| woman | (0, 0.2378, 0.004), bun top |
| man | (0, 0.221, 0.004) |
| kid | (0, 0.2405, 0.004), cowlick |
| keeper | (0, 0.2131, 0.004) |
| elder | (0, 0.2026, 0.004) |

## Extras

- `nodes[npc_X].extras.npc` holds height, headTop, hipHeight, tris, walkSpeed, runSpeed, rootScale, handR_palm, headTopOffset, bbox and tints.
- `scenes[0].extras.people` holds clip metadata: frames, duration, loop, speed, stride, contacts, events, refSkeleton, refHip and the rootZ/rootX ranges.

## Re-import check (Blender glTF importer)

| item | result |
|---|---|
| armatures | 5, with 22 bones each |
| skinned meshes | 5, with tris as above |
| actions | 9 |
| texture | 1 PNG |
| vertex influences | max 4 (normalized) |

The importer also adds five 80-tri `Icosphere` objects. These are its own bone-display shapes and are not in the file.
