# Asset contract (Blender → game)

Game: "Summer Festival", an anime-style seaside town at its summer festival. Third-person, the
camera stays ~3 m behind and a little above the heroine at street level, so every asset is seen
**close up**. Silhouette, clean shapes, and good colour matter more than micro detail.
Toon-shaded in game (cel ramp, rim light, ink outlines from normals/depth, bloom on lanterns).

## Tooling
- Blender: `E:\blender\blender-5.1.2-windows-x64\blender.exe` (5.1.2). There is no Blender MCP in
  this session: build everything with a Python script run headless:
  `blender.exe --background --factory-startup --python tools/blender/<x>/build.py -- --out public/models/<x>.glb`
- Scripts must be deterministic (fixed seeds) and must lower their own process priority to
  below-normal on start (`ctypes.windll.kernel32.SetPriorityClass(GetCurrentProcess(), 0x4000)`).
- Never leave a Blender process running when you finish.
- Nothing downloaded: no external models, textures, HDRIs. Procedural textures generated in the
  script (numpy → image → packed into the GLB as PNG) are fine.
- Verify your own work visually: render preview PNGs headless (Workbench or Eevee) from the game
  camera's angle (3 m back, 1.7 m up, looking slightly down) AND a front close-up, then Read the PNGs
  and fix what looks wrong. Save previews to `tools/blender/<x>/previews/`.
- An original design. No characters, costumes or places from any existing anime, film or game.
- Reference technique (NOT character design) if useful: `F:\bay-ride\tools\character\` is a prior
  headless-built anime heroine (rig via analytic weights, in-place clips, export). You may borrow
  generic tooling ideas/code (export settings, weight smoothing, clip authoring helpers). Do not
  reuse its head, face, hair, body shape or outfit.

## Export (glTF 2.0 binary)
- Units metres, Blender Z-up → exporter `export_yup=True`. Characters face **+Z in glTF** (Blender −Y).
- Apply all transforms/modifiers before export. No Draco/Meshopt compression (the game has no decoder).
- Animations: one action per clip, named exactly as listed in your brief, `export_animation_mode='ACTIONS'`,
  30 fps, locomotion **in place** (no root motion). Loops must be seamless. No bone scale keys.
- Max 4 bone influences per vertex, normalized.
- Morph targets (shape keys) are exported with their names.
- Name every node meaningfully; three.js strips `.` from names, so use `_` instead.

## Materials → toon roles
The game replaces every material with its own toon material, chosen by **material name prefix**.
The glTF base colour (factor and/or baseColorTexture) is used as albedo, multiplied by COLOR_0 if
present. Keep metallic=0, roughness=1. Use these prefixes:

| prefix | game treatment |
|---|---|
| `skin` | soft cel step, warm shade |
| `hair` | cel + anime hair sheen band |
| `cloth_` | standard cel (append any detail: `cloth_yukata`, `cloth_obi`) |
| `wood_`, `stone_`, `metal_`, `plastic_` | standard cel with painted brush variation |
| `paper_` | translucent paper: glows warm from inside when lit (lanterns, shoji) |
| `glow_` | emissive, blooms (bulbs, embers, flames) |
| `water_` | shallow water surface (the goldfish tub) |
| `eye`, `face` | unlit-ish painted face features (no shading bands) |
| `fabric_flag_` | thin cloth that the game ripples in the wind in a vertex shader |

Anything that should sway in wind in the vertex shader (banners, noren curtains, flag cloth) should
be a separate mesh object whose name starts with `wind_` and whose vertex colour **alpha / or a
`COLOR_1`** is not required: the game uses the object's local height (top fixed, bottom free).

## Budgets
- Heroine ≤ 40k triangles, GLB ≤ 3 MB, textures ≤ 1024².
- Each NPC body variant ≤ 7k triangles; people.glb ≤ 2.5 MB total.
- stalls.glb ≤ 80k triangles total, ≤ 3 MB.
- Each cat ≤ 3k triangles.

## Hand-off
Write `tools/blender/<x>/README.md`: how to rebuild, node/mesh names, bones, clips (duration, loop,
speed in m/s for locomotion), morph targets, attachment points (bone + local offset), heights,
bounding boxes, and anything the game must know. Print a summary of the GLB (meshes, tris, bones,
clips, file size) by re-importing it in Blender after export.
