# people.glb: festival townsfolk NPCs

Five original background characters for the street, built procedurally. The script is deterministic and nothing is downloaded. Output: `public/models/people.glb` (3 167 868 bytes, about 3.02 MiB; the budget is 4 MB). Each character has two LODs on one skeleton: a detailed near mesh for close-ups and the original simple far mesh.

## Rebuild

```
E:\blender\blender-5.1.2-windows-x64\blender.exe --background --factory-startup ^
  --python tools/blender/people/build.py -- --out public/models/people.glb
```

- Add `--no-previews` to skip the Eevee stills.
- The script lowers its own priority to below-normal. A run takes about 6 s, plus about 10 s for the previews.
- It writes `people_summary.json`, the re-import summary.
- It writes `previews/*.png` (gitignored):
  - `lineup_front`, `lineup_threequarter` and `lineup_back` show the near LODs; `lineup_threequarter_far` shows the far LODs.
  - `closeup_<variant>_<clip>_<frame>_near_vs_far` are game-camera shots (about 1.5 m high, 2.7 m away), near on the left and far on the right. They cover man and woman in idle, woman mid-walk, sparkler, wave, call, fan and talk.
  - `clip_<clip>_<frame>` are frames of each clip on the near LODs from a street camera about 4 m away.
  - `face_<variant>` are face close-ups, near on the left and far on the right.
- Previews render on Eevee, and the GPU is asserted (`NVIDIA GeForce RTX 4060`). Face features are previewed emissive at their albedo, like the game's unlit face treatment.
- The build asserts each near mesh is at most 12 000 tris and the GLB is at most 4 MB.
- Code layout: `npc/geo.py` (mesh helpers), `npc/rig.py` (skeleton and weights), `npc/body.py` (body parts and garments), `npc/outfits.py` (the five far designs), `npc/near.py` (the five near designs), `npc/anim.py` (procedural clips), `npc/bl.py` (Blender objects and materials), `npc/glbtools.py` (GLB post-process), `npc/preview.py`.

## Nodes

Each variant is its own top-level skinned armature node. It has two skinned mesh children, bound to the same skin (22 joints):

- `npc_X_near` is the near LOD.
- `npc_X_body` is the far LOD, unchanged from version 1.

| node | far mesh | far tris | near mesh | near tris | look | height (m) | head top | hip | far bbox min → max (glTF, m) |
|---|---|---|---|---|---|---|---|---|---|
| `npc_woman` | `npc_woman_body` | 6298 | `npc_woman_near` | 11938 | yukata, obi with a bow, hair bun with kanzashi | 1.636 (bun) | 1.60 | 0.80 | (-0.338, 0, -0.151) → (0.338, 1.636, 0.180) |
| `npc_man` | `npc_man_body` | 5356 | `npc_man_near` | 10610 | dark yukata, narrow kaku obi with a flat knot | 1.75 | 1.74 | 0.875 | (-0.386, 0, -0.148) → (0.386, 1.75, 0.197) |
| `npc_kid` | `npc_kid_body` | 4696 | `npc_kid_near` | 10456 | jinbei (top and shorts), short hair; the near mesh adds a heko-obi | 1.206 (cowlick) | 1.15 | 0.50 | (-0.232, 0, -0.111) → (0.232, 1.206, 0.112) |
| `npc_keeper` | `npc_keeper_body` | 5204 | `npc_keeper_near` | 11360 | happi over dark clothes, twisted hachimaki, neck towel, apron, jika-tabi | 1.707 | 1.70 | 0.85 | (-0.372, 0, -0.122) → (0.372, 1.707, 0.186) |
| `npc_elder` | `npc_elder_body` | 5748 | `npc_elder_near` | 11598 | stooped, light yukata, taiko knot, grey bun, uchiwa fan in the right hand | 1.529 | 1.52 | 0.76 | (-0.341, 0, -0.151) → (0.319, 1.529, 0.313) |

- The origin is between the feet on the ground. Characters face +Z. There are no morph targets.
- The uchiwa is part of both `npc_elder_body` and `npc_elder_near`. It is 100% weighted to `hand_R`, so it follows every clip.
- The kid is intended to be scaled 0.9–1.05 in game. Scale the node uniformly; clips are scale-agnostic, apart from the root-translation note below.

## LODs (near / far)

| | `npc_X_near` | `npc_X_body` |
|---|---|---|
| use | within about 12 m of the camera | beyond 12 m |
| tris | 10.5k–11.9k (budget 12k) | 4.7k–6.3k |
| garments | lofted through smooth ring profiles; rounded shoulders, torso tapering into the obi, hem flare and fold ridges | straight tubes |
| sleeves | soft, thick, draped sode | stiff tubes with a hanging pouch |
| face | full anime eyes, brows, nose and mouth | small eyes |

**Alignment.** Both meshes are skinned to the same joints and built from the same joint positions, so they line up exactly. Height, head, feet, geta, hands, the hand_R palm/grip point and the head top are identical. Only the garment volume differs: near sleeves hang up to about 5 cm further back.

**Swapping.**
- Suggested swap distance: 12 m, with about 1 m of hysteresis. `scenes[0].extras.people.lod` holds `swapDistance: 12` and `hysteresis: 1`.
- Both meshes are children of the armature and the mixer drives the shared skeleton, so a swap is just visibility: `near.visible = d < 12; far.visible = !near.visible`.
- Do not hide the armature itself.
- `nodes[npc_X].extras.npc` has `mesh` (far), `nearMesh` and `nearTris`.

**What the near meshes add.**
- **Robe.** Lofted through monotone-cubic ring profiles: rounded, sloped shoulders with no box corners, a torso tapering into the obi, a slight hem flare, and soft fold ridges, with a little COLOR_0 shade in the grooves. The left-over-right front overlap edge runs down to the hem.
- **Sode (woman, man, elder).** A rounded tube round the arm runs into a thick bag (about 3.5 cm) behind and below the forearm. It is narrow at the shoulder and wider at the bottom, with rounded corners, and a dark cuff opening the forearm comes out of. The bag is weighted to `sleeve_X1`, so it hangs under gravity in every clip; with a raised forearm it drapes down from it. The kid's jinbei and keeper's happi sleeves are short, soft, flared tubes with a rolled cuff.
- **Collar.** Thick bands, the wearer's left band over the right.
- **Obi.** Rounded edges. The back fastening differs per variant:
  - woman: bow (wings, ends and knot), plus an obijime cord
  - man: flat kai-no-kuchi knot
  - kid: soft heko-obi sash with a floppy bow (the far kid has no sash)
  - elder: rounded taiko
  - keeper: sash with a small knot
- **Faces.** Projected decals in the `face` material, with colour in COLOR_0. Each eye has:
  - an eye white shaded under the lid
  - an iris that is dark on top, with a lighter lower half, a dark rim and a pupil
  - two catch-lights, on the same world side for both eyes
  - a thick upper lash line with an outer flick, and a lower lash
  - a brow, plus a lid crease on some variants
- **Face proportions.** The kid has the largest eyes. The man and keeper have flatter lids. The elder has soft, narrow, slightly drooping eyes with a smile crease. The nose hint is a small `skin` decal, so it follows the skin tint. The mouth is small; the kid and keeper have it open.
- **Hands.** Relaxed mittens with the fingers curled about 34° toward the palm and a resting thumb.

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
// 4) LOD: both skinned meshes follow the same bones; toggle visibility by camera distance
const near = npc.getObjectByName('npc_kid_near'), far = npc.getObjectByName('npc_kid_body');
```

`SkeletonUtils.clone` shares materials between clones, and the near and far meshes of a variant use the same glTF materials. If the game tints per instance by cloning or replacing `cloth_main` and `cloth_accent`, apply the tint to both meshes of the instance. Toonify both meshes too; they use the same material names.

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
- Rest pose: an A-pose with the arms 74° below horizontal. The clips never use the straight rest arm (see below).
- `sleeve_L1` and `sleeve_R1` drive the hanging yukata sleeve (tamoto). The clips animate them to hang under gravity with a little lag. They can be left alone or driven procedurally.

## Clips (30 fps, all loop seamlessly, in place)

Each clip has 22 rotation channels plus `root.position`. There are no scale keys and no other translations. Every channel's last key equals its first, so loops are exact.

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

### Arms (version 2): loose, never straight

Only the arm, hand and sleeve channels changed. Root, spine, head and legs are unchanged, and so are clip names, durations, 30 fps, in-place motion, walk/run speeds and foot-contact timings.

The relaxed arm, used by every clip:
- The upper arm hangs 13° out from vertical and 7° forward.
- The elbow is bent about 24°.
- The wrist flexes about 12° toward the palm, with 4° ulnar deviation.

Per clip:
- **idle**: each arm sways slowly on its own phase, with the elbow drifting 18–30° and small wrist shifts.
- **walk, sparkler (free arm)**: the arms swing ±17° with follow-through. The forearm's swing lags the upper arm's by 7% of the cycle, so the elbow opens on the back-swing and closes on the forward swing (15–33°). The wrist trails further.
- **run**: the arms pump ±38° with the elbow at 70–103°, plus forearm and wrist lag.
- **talk, lookup**: gestures and sway. Talk elbows are 54–90°; lookup elbows 19–25°.
- **wave, call, fan, sparkler**: the gesturing arm keeps its pose and the other arm uses the relaxed arm.
- The hanging-sleeve bones' lag is now computed cyclically, which closes a 1–2° seam in `run`.

The shared idle does not put the hands at the obi, because all five variants share it.

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
| `skin` | skin (and the near mesh's nose hint, a COLOR_0 shade) | `#f4d3bf` |
| `face` | eyes (whites, iris, pupil, catch-lights), lashes, brows, blush, mouth (geometry projected onto the head) | white; colours come from COLOR_0. Do not tint. |
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

- `nodes[npc_X].extras.npc` holds mesh (the far mesh), nearMesh, height, headTop, hipHeight, tris (far), nearTris, walkSpeed, runSpeed, rootScale, handR_palm, headTopOffset, bbox (far mesh) and tints. All values except the two new fields are unchanged from version 1.
- `scenes[0].extras.people` (version 2) holds clip metadata: frames, duration, loop, speed, stride, contacts, events, refSkeleton, refHip and the rootZ/rootX ranges. It also holds `lod` (near/far name patterns, swapDistance 12, hysteresis 1).

## Re-import check (Blender glTF importer)

| item | result |
|---|---|
| armatures | 5, with 22 bones each |
| skinned meshes | 10 (5 `_body` + 5 `_near`), with tris as above |
| actions | 9 |
| scale channels | 0 |
| texture | 1 PNG |
| vertex influences | max 4 (normalized) |
| file size | 3 167 868 bytes |

### Vertex attribute storage

`WEIGHTS_0` and `COLOR_0` are stored as normalized `UNSIGNED_BYTE` (core glTF 2.0, no extension). Weights sum to exactly 255 per vertex. `GLTFLoader` and Blender read this natively. Code that reads `geometry.attributes.skinWeight.array` or `color.array` directly gets a `Uint8Array` with `normalized: true`. The far meshes' positions, normals, UVs, joints and indices are bit-identical to version 1; weights and colours differ only by this rounding (≤ 0.003).

The importer also adds five 80-tri `Icosphere` objects. These are its own bone-display shapes and are not in the file.
