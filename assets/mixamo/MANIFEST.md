# Mixamo assets for Summer Festival

All files: FBX Binary (fbx7_2019), Without Skin (skeleton + animation only), 30 fps, no keyframe reduction.
Downloaded on the stock character **Y Bot** (4f5d21e1-4ccc-41f1-b35b-fb2547bd8493); only the motion is used.
The motion is retargeted in Blender onto the game's own characters (heroine and townspeople); no Mixamo mesh ships.
`In place` = yes for locomotion (walk, run); all other clips are stationary and were exported with In Place off.

The raw `.fbx` files are **not committed** (`.gitignore`: Adobe's terms don't allow redistributing the raw
files). Only the converted GLBs in `public/models/` ship with the game. This manifest lists what to download
again to rebuild them.

| File | Mixamo product | Variant | Product id | In place | Use |
|---|---|---|---|---|---|
| idle.fbx | Breathing Idle | Breathing Idle | c9c6d0d5-b96c-11e4-a802-0aaa78deedf9 | no | Townspeople standing idle |
| idle_f.fbx | Idle | Female Idle | c9ccf750-b96c-11e4-a802-0aaa78deedf9 | no | Heroine idle |
| walk.fbx | Standard Walk | Standard Walk | c9ccc2e9-b96c-11e4-a802-0aaa78deedf9 | yes | Townspeople walk |
| walk_f.fbx | Female Walk | Female Normal Walk | c9c68b91-b96c-11e4-a802-0aaa78deedf9 | yes | Heroine walk (also women in the crowd) |
| run.fbx | Jogging | Jogging | c9c8707d-b96c-11e4-a802-0aaa78deedf9 | yes | Townspeople run (kids, the bag chase) |
| run_f.fbx | Run Forward | Female Run Forward | c9ccfb22-b96c-11e4-a802-0aaa78deedf9 | yes | Heroine run |
| wave.fbx | Waving | Waving | c9c5ed32-b96c-11e4-a802-0aaa78deedf9 | no | Wave emote, NPC greetings |
| bow.fbx | Quick Informal Bow | Quick Informal Bow | c9c9f57a-b96c-11e4-a802-0aaa78deedf9 | no | Bow emote, NPC bows |
| eat.fbx | Drinking | Male Drinking | c9c63255-b96c-11e4-a802-0aaa78deedf9 | no | Eating (hand to mouth). Mixamo has no eating clip; this is the stand-in |
| talk.fbx | Talking | General Conversation | c9c88301-b96c-11e4-a802-0aaa78deedf9 | no | Chatting groups, keepers |
| cheer.fbx | Cheering | Male Cheering With Two Fists Pump | c9c66dfd-b96c-11e4-a802-0aaa78deedf9 | no | Cheer emote, fireworks |
| point.fbx | Pointing | Pointing With Arm Bent | c9c6947c-b96c-11e4-a802-0aaa78deedf9 | no | Pointing (at the sky, at a stall) |
| look.fbx | Looking Around | Idle Stand Looking Around | c9c6cdf7-b96c-11e4-a802-0aaa78deedf9 | no | Look-around layer / idle variation |
