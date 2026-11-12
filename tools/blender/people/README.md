# people.glb: festival townsfolk NPCs

Five original background characters for the street, built procedurally. Output: `public/models/people.glb` (4,495,076 bytes; the budget is 5.5 MB). Each character has two LODs on one skeleton. The meshes are generated; the motion of most clips is retargeted from Mixamo clips (only the motion: see Version 4).

## Rebuild

```
E:\blender\blender-5.1.2-windows-x64\blender.exe --background --factory-startup ^
  --python tools/blender/people/build.py -- --out public/models/people.glb
```

- The clips need the raw Mixamo FBX files in `assets/mixamo/` (gitignored; `MANIFEST.md` there lists what to download). If one is missing the build stops at once and names it.
- `--no-previews` skips the Eevee stills; `--clip-previews` renders only the walk strips and the clip stills.
- The script lowers its own priority to below-normal. A run takes about 100 s (most of it the clips and their checks), plus about 30 s for all previews.
- It writes `people_summary.json` (the re-import summary) and `clips_report.json` (feet, slip, seams, arm clearance per clip and variant).
- It writes `previews/*.png` (gitignored): `lineup_crowd_mix`, `face_<v>`, `hands_<v>`, `far_10m_*` as before; `walk_<v>`, `walk_f_<v>`, `run_<v>`, `sparkler_kid` are side strips of one cycle with the character moving at its clipSpeed over 10 cm ground ticks; `clip_<name>` shows every other clip on all five variants (3/4 front and side; the seated ones with a 0.45 m bench).
- Previews render on Eevee, and the GPU is asserted (`NVIDIA GeForce RTX 4060`).
- The build fails (after writing the GLB) if a check fails: walk slip over 3 cm/s, run slip over 5 cm/s, a sole more than 4 mm off the floor, a loop or one-shot seam, a missing head / neck track, a rest pose that moved.
- Code layout: `npc/geo.py`, `npc/rig.py`, `npc/body.py`, `npc/outfits.py`, `npc/near.py` (meshes); `npc/mocap.py` (the Mixamo clips, driven through `tools/blender/mixamo/retarget.py`), `npc/handmade.py` (the new hand-made clips), `npc/anim.py` (the older hand-made clips: call, fan, lookup, the sparkler arm); `npc/glbtools.py` (GLB post-process), `npc/glbcheck.py` (checks on the exported file), `npc/bl.py`, `npc/preview.py`.

## Version 4 (motion)

Meshes, materials, morphs, bone names and the rest pose in world space are unchanged. What changed is the clips and two rest scales.

### Clips

All clips are in place, 30 keys per second (the run 60), on the same 41 rotation tracks (every bone except `root`, fingers included) plus `hips.position`. There is no `root` track and no scale track. Slow clips have had the keys removed that linear interpolation reproduces within 0.1 degree / 0.2 mm; walk, walk_f, run and sparkler keep every key.

| clip | s | kind | source | notes |
|---|---|---|---|---|
| `idle` | 9.9333 | loop | idle.fbx | breathing idle |
| `walk` | 0.9333 | loop | walk.fbx | standard walk |
| `walk_f` | 0.8667 | loop | walk_f.fbx | female walk (women) |
| `run` | 0.4 | loop | run.fbx | jog; keyed at 60 Hz |
| `sparkler` | 0.9333 | loop | walk.fbx | the walk with the right arm up drawing small circles (attach the sparkler to hand_R) |
| `talk` | 6.8333 | loop | talk.fbx | conversation, gestures inside the shoulders |
| `look` | 6.3333 | loop | look.fbx | looking around, head turn limited to about 68 deg |
| `wave` | 1.8667 | one-shot | wave.fbx | right hand |
| `bow` | 2.2667 | one-shot | bow.fbx | quick informal bow |
| `eat` | 3.9333 | one-shot | eat.fbx | hand to mouth |
| `cheer` | 2.9 | one-shot | cheer.fbx | two fists pumping |
| `point` | 2.2667 | one-shot | point.fbx | pointing with a bent arm |
| `call` | 3.0 | loop | hand-made (npc/anim.py) | cupped hand at the mouth, then a gesture to the side |
| `fan` | 4.0 | loop | hand-made (npc/anim.py) | idle while fanning with the right hand |
| `lookup` | 4.0 | loop | hand-made (npc/anim.py) | looking up at the sky |
| `sit` | 4.0 | loop | hand-made (npc/handmade.py) | seated, hands on knees |
| `sit_fan` | 4.0 | loop | hand-made (npc/handmade.py) | seated, right hand fanning slowly |
| `sit_sleep` | 6.0 | loop | hand-made (npc/handmade.py) | seated asleep, nodding |
| `yawn` | 3.2 | one-shot | hand-made (npc/handmade.py) | stretch, hand to mouth |
| `cry` | 2.0 | loop | hand-made (npc/handmade.py) | fists at the eyes, shoulders bobbing |
| `pick_up` | 2.4 | one-shot | hand-made (npc/handmade.py) | crouch, right hand to the ground |
| `peace` | 2.4 | one-shot | hand-made (npc/handmade.py) | V sign beside the face, held about a second |

- Loops close exactly (last key = first key). One-shots start and end exactly on the idle's first pose.
- Every standing clip uses the same foot placement, so a crossfade between them never slides a foot.
- `look`: the source turns the whole mannequin right round. Here the heading is limited: head 69.0 degrees, chest 28.0 degrees at most (`retarget.limit_turn`).
- `talk`: wrists are held inside the shoulder joints' width. `eat`: while the hand is up, the arm is steered to each variant's own mouth.
- Fingers follow the Mixamo fingers in the Mixamo clips; they keep the relaxed rest curl in call / fan / lookup, grip in sparkler, and are posed in the hand-made clips (`peace` is a V: index and middle straight, ring and little finger folded under the thumb).
- The game also asks for `comfort`, `photo`, `laugh`, `point_up`, `hop`, `sparkler_stand` (it falls back to other clips); these are not in the file.

### One clip set, five bodies: what the game must do

**Hips height: nothing.** Legs and pelvis height of every variant are the woman's times one number, `legScale` (man 1.09375, kid 0.625, keeper 1.0625, elder 0.95). A bent knee needs the hips lower by an amount in proportion, so the clips carry a `hips.position` track in the woman's metres, and the file makes it fit everyone: each variant's `root` bone has rest scale `legScale` and its `hips` bone rest scale `1 / legScale` (uniform, so they cancel exactly below the hips; the world rest pose and skinning are as before). The same track therefore lowers a kid's hips 0.625 times as far as a woman's, and every variant's soles are on the floor in every clip (table below) with the mixer doing nothing special.

- Keep the `hips.position` track. The current loader only drops `root.position`, which no longer exists: no change needed.
- Do not write to the scale of the `root` or `hips` bones, and do not set `hips.position` in metres by hand (it is in the woman's units; multiply by nothing, the rest scale does it).
- Scaling the whole NPC (`npc_<v>.scale`) is fine, as before.

**Walking speed: use `clipSpeed`.** `scenes[0].extras.people.clipSpeed[clip][variant]` is the ground speed in m/s the clip implies at rate 1 and scale 1, measured on the exported file. Play at `rate = actual speed / (clipSpeed[clip][variant] * model scale)`.

| clip | woman | man | kid | keeper | elder |
|---|---|---|---|---|---|
| `walk` | 0.901 | 0.986 | 0.565 | 0.958 | 0.856 |
| `walk_f` | 0.9 | 0.985 | 0.564 | 0.957 | 0.856 |
| `run` | 1.851 | 2.023 | 1.154 | 1.965 | 1.758 |
| `sparkler` | 0.901 | 0.986 | 0.565 | 0.958 | 0.856 |

The walk values equal the old `WALK` table in `crowd.ts` (0.9 times legScale), so walking already matches without a code change. `walk_f` has the same speed as `walk`, so women can use either with the same rate. The run is a short-stepped jog (a longer stride comes through the yukata hem); a kid sprinting at 2.2 m/s plays it at about rate 1.9.

**Sitting.** In `sit`, `sit_fan`, `sit_sleep` the root stays at the feet (soles on the floor at the root's height) and the hips are behind and above it. With the root on the ground the pose is right for a seat of about `seatHeight` (the underside of the thighs, m at scale 1); on a higher seat the thighs sink into it by the difference. To sit exactly on a seat top at height h, put the root at `h - seatHeight[variant] * scale` above the ground; the feet then hang by that much. `hipsBack` is how far the hip joints are behind the root.

| | woman | man | kid | keeper | elder |
|---|---|---|---|---|---|
| seatHeight | 0.366 | 0.407 | 0.195 | 0.43 | 0.344 |
| hipsBack | 0.347 | 0.379 | 0.217 | 0.368 | 0.329 |

### Measured on the exported GLB (`clips_report.json`)

`npc/glbcheck.py` plays every clip on every variant the way three.js does (tracks bound by bone name, linear / slerp keys, the file's own skinning) and looks at the shoes: `npc_<v>_geta_R` (the keeper's boot) and the left shoe in `npc_<v>_body`.

Slip of a planted shoe against the ground moving at clipSpeed, 240 samples per second, cm/s (max / 95th percentile):

| clip | woman | man | kid | keeper | elder |
|---|---|---|---|---|---|
| `walk` | 2.33 / 1.33 | 2.61 / 1.47 | 1.76 / 0.89 | 2.61 / 1.48 | 2.25 / 1.29 |
| `walk_f` | 1.77 / 1.35 | 1.93 / 1.43 | 1.19 / 0.88 | 1.88 / 1.41 | 1.7 / 1.21 |
| `run` | 2.52 / 2.19 | 2.82 / 2.4 | 2.17 / 2.0 | 2.87 / 2.37 | 3.03 / 2.14 |
| `sparkler` | 2.33 / 1.33 | 2.61 / 1.47 | 1.76 / 0.89 | 2.61 / 1.48 | 2.25 / 1.29 |

- Soles: in every standing clip the lowest point of each shoe stays between -0.9 and 0.8 mm of the floor on every variant; in the walks the lower shoe is within 1 mm of it at all times; the run has a flight phase (up to 27 mm).
- Hips travel horizontally at most 3.34 cm (weight shift); the bow moves them back 5 cm and `pick_up` 14 cm as counterbalance.
- `armClearance` in the report: the smallest distance of elbows, wrists and fingers from each variant's own trunk / skirt and head, per clip. Arms are pushed out of every variant's body in turn (`mocap.Ctx.clear_arms`). `reachMissCm`: how far the shared arm rotations miss each variant's own target (a mouth, an eye, a knee) in the hand-made clips: 2 to 4 cm at the face, up to 7 cm for the kid's hands on its knees and for the hand on the ground in `pick_up`.

### Extras

- `scenes[0].extras.people` (version 4): `clips` (duration, loop, kind, source, keys, keyRate, note; for locomotion `speed` per variant, `events` foot down / up times, `duty`), `clipSpeed`, `legScale`, `hips` (the note above), `seat` (`seatHeight`, `hipsBack` per variant), and the older `lod`, `bones`, `materials`, `hair`, `specs`, `faceMorph`, `clothMainPattern`.
- `nodes[npc_<v>].extras.npc`: `walkSpeed` and `runSpeed` are now clipSpeed.walk / clipSpeed.run for that variant, `legScale` and `seatHeight` are new, `rootScale` is gone.

Sections below this line describe versions 1 to 3. Where they speak of `root.position`, `rootScale`, 22 animated bones, unkeyed fingers or the old clip table, this section replaces them.

## Version 3 (faces, hair, glasses, fingers, right geta)

New meshes per variant `<v>` (all children of `npc_<v>`, all on the same 42-joint skin):

| mesh | what | weights | material(s) |
|---|---|---|---|
| `npc_<v>_hair_<style>` | one hairstyle; show exactly one. woman: `bun`, `bob`, `ponytail`; man: `short`, `crop`, `slick`; kid: `short`, `bowl`, `pigtails`; keeper: `short`, `crop`, `tied` (all fit under the hachimaki); elder: `bun`, `low`, `short` | 100% `head` | `hair` (white base, colour in COLOR_0: browns, black, grey elder hair) + small `cloth_accent` / `cloth_dark` / `wood_geta` trims |
| `npc_<v>_glasses` | thin frames (woman gold round, man / keeper dark rectangular, elder silver round), clear lenses with a glint; not for the kid | 100% `head` | `glasses_frame`, `glasses_lens` |
| `npc_<v>_sunglasses` | dark lenses; the kid's are red plastic | 100% `head` | `glasses_frame`, `glasses_lens` |
| `npc_<v>_geta_R` | the right geta (keeper: right jika-tabi boot over a sock foot left in the body); used with BOTH LODs | 100% `foot_R` (keeper cuff blends into the shin) | as before |

- The hair is no longer in `_near` / `_body`; without a hair mesh the head is bald.
- Glasses sit on the nose bridge in front of the eyes (sized over both face looks), stay under the brows, and the arms run back to the ear tops with a few mm of clearance. Bangs always end above the brows.
- `glasses_lens` has `alphaMode: BLEND`; the tint AND the opacity are in COLOR_0 (rgb, a): about 0.20 for clear lenses, 0.88 for sunglasses. The game's toon pass keeps `transparent` but not `opacity`, which is why the alpha lives in the vertex colour.
- `nodes[npc_<v>].extras.npc` adds `hairStyles` (per style: mesh, top height, headTopOffset), `glasses`, `getaR`, `faceLooks`, `nearTrisWorst`, `hairTris`, `glassesTris`.

**Faces.** One analytic head per variant (`npc/headshape.py`, the heroine's SDF construction, rescaled), with normals from the SDF gradient. The painted face is in `npc/face.py`: eye whites, a polar iris with highlights, an upper lash line with a flick, a lower lash, a crease, soft brows, a nose tick, a small mouth and blush. Eyes are about 1/6 of the face height, at mid-head, one eye width apart. Men have narrower eyes, heavier brows and a squarer jaw; elders have crow's feet, smile folds and grey brows; the kid has a rounder face and bigger eyes. The keeper has the full face like everyone else. The far LOD has the same face with fewer vertices, so nobody reads blank at 10 m. Face vertex colours are clamped to at most 0.96 and no material is emissive.

Morph targets on `npc_<v>_near` and `npc_<v>_body` (same names on both; drive both):

| index | name | effect |
|---|---|---|
| 0 | `face_b` | second face look: different eye shape, brows and mouth (0 = look A, 1 = look B). Pick per NPC. |
| 1 | `blink` | eyes closed (upper lid onto the lower one; the lash line becomes a closed arc) |
| 2 | `smile` | mouth corners up, slightly wider mouth, lower lids raised |

The morphs are POSITION only (stored sparse); `blink` and `smile` are authored on look A and add on top of `face_b`.

**Fingers.** Five separate fingers per hand on both LODs: the near LOD has round 7-sided fingers with a thenar pad and a nail tint, the far LOD 4-sided ones. All sit in a relaxed curl with the thumb opposed. New bones `finger_<thumb|index|middle|ring|pinky>_<1|2>_<L|R>`: `_1` is a child of `hand_<side>`, `_2` a child of `_1`. The rest pose IS the relaxed curl and the clips do not key these bones. The original 22 bones keep their names, parents and rest pose.

**Walk (job dropped).** The walk was partly reworked before the scope change: the root no longer sways sideways (`rootX` 0 in walk / run / sparkler), the swing foot lifts and lands while staying on the ground spot, the geta rocks on its real tooth edges and the arms swing 22 deg with forearm follow-through. Measured slip on the skinned `geta_R` (`slip/slip_<v>.json`, informational): walk is at most 1.6 cm/s for the geta variants and 18.5 cm/s peak for the keeper's flat tabi sole (p95 2 cm/s); run is 10–41 cm/s. Locomotion is to be replaced by retargeted Mixamo motion.

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

- The origin is between the feet on the ground. Characters face +Z. `_near` and `_body` carry three morph targets (see Version 3). The tables below are from version 2; the current per-mesh triangle counts are in `people_summary.json`.
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

## Skeleton (22 original bones + 20 finger bones, identical layout on all variants; full list in `bones.json`)

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
