# Festival stall kit + street props (`public/models/stalls.glb`)

Built headless from `tools/blender/stalls/build.py` (shared helpers in `tools/blender/lib/kit.py`).

```
E:\blender\blender-5.1.2-windows-x64\blender.exe --background --factory-startup --python-exit-code 1 ^
    --python tools/blender/stalls/build.py -- --out public/models/stalls.glb
```

Previews + the inventory table below come from re-importing the exported GLB:

```
E:\blender\blender-5.1.2-windows-x64\blender.exe --background --factory-startup --python-exit-code 1 ^
    --python tools/blender/lib/inspect_glb.py -- --glb public/models/stalls.glb ^
    --out tools/blender/stalls/previews --readme tools/blender/stalls/README.md --lineup
```

Previews (Eevee, RTX 4060 asserted) land in `previews/`: `<node>_game.png` (street-level 3/4,
≥3 m away, eye 1.6 m), `<node>_front.png` (front close-up), `<stall>_cam.png` (seen from the stall's
own `cam` → `cam_target` anchors, 50° vertical FOV), `_lineup.png`. Procedural textures are
written to `textures/` and packed into the GLB.

## Conventions

- Every top-level node sits at the world origin = **ground centre of its footprint**. Front of every
  stall / prop faces **+Z in glTF** (Blender −Y). Units metres, Y up. No Draco/Meshopt.
- Static geometry of a stall is one mesh `stall_<x>_body` (several primitives, one per material).
  Everything the game touches is its own node (names below).
- Colour lives in `COLOR_0` (8-bit normalized, linear) × material base colour (white, except
  `water_tub` and `glow_flame`). Textures only on `plastic_mask` (1024×768 atlas), `fabric_flag_ice`
  (256×320), `fabric_flag_nobori` (256×768). All materials metallic 0 / roughness 1.
- Material prefixes used: `wood_`, `cloth_`, `metal_`, `plastic_`, `stone_`, `paper_` (lanterns,
  poi paper, matchbox, shoji, gate plaque), `glow_flame`, `water_tub`, `fabric_flag_ice`,
  `fabric_flag_nobori`.
- `wind_*` meshes have their origin at the **top edge** (pin line); local height goes down from 0.
  Extras: `role: "wind"`, `pin: "top"`.
- Lantern nodes (`lantern_*`, `gatelantern_*`, `lantern_light`) have their origin at the **hook at the
  top of the cord** (swing pivot); the paper body hangs below. Extras `role: "lantern"`.

### Duplicate anchor names (important for three.js)

Each stall has empties literally named `keeper`, `use`, `cam`, `cam_target` (and both food stalls
have `fx_steam`). Blender needs unique names, so they are built as `keeper__goldfish` etc. and renamed
in the GLB by a post-pass. **three.js GLTFLoader de-duplicates node names per file** (`keeper`,
`keeper_1`, `keeper_2` …, in file order), so do not rely on `getObjectByName('keeper')` beyond the
first stall. Every anchor also carries extras → `userData`:
`{ anchor: "keeper" | "use" | "cam" | "cam_target" | "fx_steam" | "fx_mist", stall: "stall_goldfish" }`.
Find them per stall with e.g. `stall.getObjectsByProperty('userData', …)` or a traverse on
`o.userData.anchor === 'keeper'`.

### Anchors (glTF coords, relative to the stall origin)

| anchor | meaning |
|---|---|
| `keeper` | where the stall keeper stands (behind the counter), facing +Z |
| `use` | where the player stands to use the stall, rotated 180° so its +Z faces the stall; 1.1 m in front of the counter edge (goldfish: 0.55 m from the tub rim so she can reach the water) |
| `cam` | mini-game close-up camera position; its local −Z already points at `cam_target` (`camera.position.copy(cam.getWorldPosition(v)); camera.lookAt(target)` also works). extras `fov: 50` |
| `cam_target` | look-at point for `cam` |
| `fx_steam` | steam spawn point above the griddle (food_a, food_b) |
| `fx_mist` | cold mist point at the shaved-ice machine's cup |

| stall | keeper | use | cam → cam_target |
|---|---|---|---|
| goldfish | (0, 0, −0.05) | (0, 0, 1.50) | (0, 1.78, 1.53) → (0, 0.38, 0.55): 1.4 m above the water, 55° down into the tub |
| candyapple | (0, 0, −0.25) | (0, 0, 1.94) | (0.25, 1.42, 1.55) → (0, 0.98, 0.58): onto the apple rack |
| shavedice | (−0.2, 0, −0.2) | (0, 0, 1.94) | (−0.05, 1.45, 1.55) → (−0.15, 1.06, 0.6): machine + syrups |
| ringtoss | (0.85, 0, −0.2) | (0, 0, 1.94) | (0, 1.45, 1.75) → (0, 0.32, −0.05): from behind the throw line onto the 9 pegs |
| masks | (−0.95, 0, −0.2) | (0, 0, 1.94) | (0, 1.40, 0.75) → (0, 1.36, −0.65): square onto the mask wall |
| lantern | (0, 0, −0.2) | (0, 0, 1.94) | (0.05, 1.32, 1.2) → (0.3, 1.16, 0.56): close on `lantern_light` |
| food_a | (−0.1, 0, −0.1) | (0, 0, 1.94) | – (fx_steam (−0.1, 1.15, 0.56)) |
| food_b | (−0.2, 0, −0.1) | (0, 0, 1.94) | – (fx_steam (−0.2, 1.16, 0.56)) |

## Nodes

Common to every stall (`<x>` = goldfish, candyapple, shavedice, ringtoss, masks, lantern, food_a,
food_b): frame 2.6 × 1.6 m (posts), front posts 2.15 m, back 2.4 m, striped curved awning
(overall 2.88 × 2.04 × 2.49 m), counter top 0.86 m (ring toss 0.5 m), front cloth skirt, back
canopy, short side curtains.

- `stall_<x>_body` – all static geometry.
- `wind_<x>_valance` – 5-panel noren valance under the awning front edge (0.30 m tall), `cloth_noren`.
- `lantern_<x>_0`, `lantern_<x>_1` – unlit chochin at the front corners (`paper_lantern` + `wood_lacquer` caps).

Stall specifics:

- **stall_goldfish** – red/white. Blue tub 1.6 × 0.8 m, rim 0.45 m, centred at glTF z = 0.55 (in front).
  `water_tub` (material `water_tub`, 16×8 grid at y = 0.38, origin at the water centre). Back table
  with poi tray (9 poi), bowl stacks, bucket; 3 goldfish water bags on a string; spare poi box by the
  tub; keeper stool; cooler. No counter (the tub is the counter).
- **stall_candyapple** – pink/white. Stepped 3-tier rack with 16 red apples + tray with 2 green and
  2 pink small ones: `apple_00`..`apple_15` red (r 4.6 cm), `apple_16`/`apple_18` green,
  `apple_17`/`apple_19` pink (r 3.3 cm). Each apple = apple + stick, origin at the apple centre,
  extras `role: "pickup"`, `kind`. Syrup pot on a burner, spare apple crate.
- **stall_shavedice** – blue/white. Hand-crank machine (red frame, ice block, crank wheel) with a cup of
  shaved ice, 4 syrup bottles (red, green, blue, yellow), two stacks of cups. `wind_flag_ice`
  (`fabric_flag_ice`: white cloth, blue waves, red ice-crystal symbol, no text) hangs from a bracket
  on the right front post. `fx_mist`.
- **stall_ringtoss** – green/white. Low throw counter (0.5 m) with a rope-ring stack and `ring_proto`
  (torus Ø ≈ 0.16 m, tube r 1.2 cm, red/straw striped; origin at its centre, lying flat). Platform
  (0.32 m, red felt) with `peg_0`..`peg_8` in a 3×3 grid (0.3 m spacing; origins at the peg bases on
  the platform top; row bands red/yellow/blue; extras `row`). Back shelf, 3 tiers of prizes: plush
  bear / chick / whale / bunny / frog / bear, balls, spinning tops, glass bottle with marble, toy
  robot, toy car, den-den style drums, and an original lucky-cat figurine (round white cat with a
  blue scarf and bell, one paw up, holding a little fish, on a red cushion).
- **stall_masks** – orange/white. Pegboard wall with `mask_00`..`mask_11` (≈0.2–0.25 m tall, curved
  shells, painted atlas): 00 fox (white/red), 01 cat white (calico patch, blue eyes), 02 cat black
  (yellow eyes), 03 goofy smiling face, 04 friendly red demon (horns), 05 long-nosed red mask (nose),
  06 blue bird (beak), 07 rabbit, 08 green dragon (gold horns, red mane), 09 turtle, 10 frog,
  11 sun face. Origins at mask centres; extras `role: "mask"`, `kind`. Pinwheels and a cash tin on
  the counter.
- **stall_lantern** – indigo. Four lanterns waiting on the counter (one folded), `lantern_light`
  (white/red chochin hanging from a little T-stand, origin at its hook), `candle_wick` (candle on a
  dish, origin at its base) with child `flame` (`glow_flame`, origin at the wick tip, 3 cm tall —
  toggle its visibility), matchbox + matches, crate of folded lanterns.
- **stall_food_a** – yellow/white, red skirt. Yakisoba griddle with a noodle pile (strands, cabbage,
  carrot, ginger, pork bits), two spatulas, food packs, sauce bottles. `fx_steam`.
- **stall_food_b** – teal/white. Takoyaki ball-mould plate (6×4 moulds, 19 balls), picks, two boat
  trays of 6 with sauce + nori, batter bowl and ladle, little octopus figure. `fx_steam`.

Props:

- **gate** – lantern gate for a 7.5 m street: dark-red lacquered posts (Ø 0.26 m) at x = ±3.95 on
  stone bases, lower beam at 3.72 m, top beam + black cap with up-turned ends (top ≈ 4.5 m), blank
  plaque with a gold flower. `gatelantern_0`..`gatelantern_6` (0.46 m tall, alternating red/white,
  hooks at y = 3.63 m, x = −3..3). `gate_andon_0/1`: standing paper lanterns (1.8 m) just outside the
  posts at x = ±4.45. Static mesh `gate_frame`.
- **lantern_string_unit** – children `lantern_red` and `lantern_white`, both at the node origin (pick
  one per instance); 0.32 m paper body + 5 cm cord, origin at the hook.
- **furin** – `furin_bell` (glass bell `plastic_furin`, clapper) and `wind_furin_strip`
  (`cloth_furin_strip`, origin at its top, 0.13 m below the hook). Origin at the hook (top).
- **nobori** – 3.2 m pole on a weighted base (`nobori_pole`) and `wind_nobori_cloth`
  (`fabric_flag_nobori`: white, red top band and pole-side stripe, blue circle with a red five-petal
  flower, wave scallops; no text). Cloth 0.6 × 1.9 m, origin at its top centre (pinned along the top
  and the pole side, x = 0.03).
- **bench** 1.6 × 0.38 × 0.43 m; **steps** 3 stone steps 1.6 m wide up to a stoop landing (0.45 m)
  with a shoji doorway behind; **crate**; **barrel**; **potted_plant** (terracotta pot, bamboo
  trellis, morning-glory vines in blue / violet / pink); **bicycle** (step-through town bike with
  basket and rear rack, parked side-on along X, front wheel at +X).

## Inventory

<!-- inventory:start (generated by tools/blender/lib/inspect_glb.py from the exported GLB) -->

File: `stalls.glb`, **2702 KiB**, **73184 triangles**, 18 top-level nodes.

| node | tris | size w×d×h (m) | named meshes | empties |
|---|---:|---|---|---|
| `barrel` | 504 | 0.51 × 0.5 × 0.64 | - | - |
| `bench` | 528 | 1.6 × 0.38 × 0.43 | - | - |
| `bicycle` | 2264 | 1.76 × 0.59 × 1.07 | - | - |
| `crate` | 540 | 0.5 × 0.36 × 0.3 | - | - |
| `furin` | 444 | 0.09 × 0.09 × 0.31 | `wind_furin_strip` | - |
| `gate` | 4008 | 9.51 × 0.46 × 4.51 | `gatelantern_0`, `gatelantern_1`, `gatelantern_2`, `gatelantern_3`, `gatelantern_4`, `gatelantern_5`, `gatelantern_6` | - |
| `lantern_string_unit` | 664 | 0.24 × 0.23 × 0.39 | `lantern_red`, `lantern_white` | - |
| `nobori` | 504 | 0.92 × 0.52 × 3.23 | `wind_nobori_cloth` | - |
| `potted_plant` | 2526 | 0.43 × 0.38 × 1.25 | - | - |
| `stall_candyapple` | 9736 | 2.88 × 2.04 × 2.49 | `apple_00`, `apple_01`, `apple_02`, `apple_03`, `apple_04`, `apple_05`, `apple_06`, `apple_07`, `apple_08`, `apple_09`, `apple_10`, `apple_11`, `apple_12`, `apple_13`, `apple_14`, `apple_15`, `apple_16`, `apple_17`, `apple_18`, `apple_19`, `lantern_candyapple_0`, `lantern_candyapple_1`, `wind_candyapple_valance` | `cam`, `cam_target`, `keeper`, `use` |
| `stall_food_a` | 5032 | 2.88 × 2.04 × 2.49 | `lantern_food_a_0`, `lantern_food_a_1`, `wind_food_a_valance` | `fx_steam`, `keeper`, `use` |
| `stall_food_b` | 7264 | 2.88 × 2.04 × 2.49 | `lantern_food_b_0`, `lantern_food_b_1`, `wind_food_b_valance` | `fx_steam`, `keeper`, `use` |
| `stall_goldfish` | 7136 | 2.88 × 2.04 × 2.49 | `lantern_goldfish_0`, `lantern_goldfish_1`, `water_tub`, `wind_goldfish_valance` | `cam`, `cam_target`, `keeper`, `use` |
| `stall_lantern` | 5720 | 2.88 × 2.04 × 2.49 | `candle_wick`, `flame`, `lantern_lantern_0`, `lantern_lantern_1`, `lantern_light`, `wind_lantern_valance` | `cam`, `cam_target`, `keeper`, `use` |
| `stall_masks` | 7898 | 2.88 × 2.04 × 2.49 | `lantern_masks_0`, `lantern_masks_1`, `mask_00`, `mask_01`, `mask_02`, `mask_03`, `mask_04`, `mask_05`, `mask_06`, `mask_07`, `mask_08`, `mask_09`, `mask_10`, `mask_11`, `wind_masks_valance` | `cam`, `cam_target`, `keeper`, `use` |
| `stall_ringtoss` | 11160 | 2.88 × 2.04 × 2.49 | `lantern_ringtoss_0`, `lantern_ringtoss_1`, `peg_0`, `peg_1`, `peg_2`, `peg_3`, `peg_4`, `peg_5`, `peg_6`, `peg_7`, `peg_8`, `ring_proto`, `wind_ringtoss_valance` | `cam`, `cam_target`, `keeper`, `use` |
| `stall_shavedice` | 6708 | 2.88 × 2.04 × 2.49 | `lantern_shavedice_0`, `lantern_shavedice_1`, `wind_flag_ice`, `wind_shavedice_valance` | `cam`, `cam_target`, `fx_mist`, `keeper`, `use` |
| `steps` | 548 | 1.94 × 1.51 × 2.72 | - | - |

Textures: `flag_ice` 256×320, `masks` 1024×768, `nobori` 256×768

<!-- inventory:end -->
