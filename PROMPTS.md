# Prompts

The prompts given to Claude Code to build this game, in order and verbatim.

## 1. The build

build summer festival: an anime-style seaside town during its summer festival, a real little game you walk through at street level. you own this

reuse, don't rebuild: my old builds on F: have my best environments. find them (summer cycle / ghibli ride, bay ride, golden hour skatepark) and reuse their sky, lighting, time of day, water and toon shading. don't copy their characters or ui

keep everything close: you walk at street level the whole time, the camera stays near her. no wide distant views, those turn into blurry paint

the world:
- a seaside town street lined with festival stalls, paper lanterns strung overhead, wind chimes, banners moving in the wind
- stalls: goldfish scooping, candy apples, shaved ice, a ring toss, a mask stand
- the street leads down to the shore where fireworks launch over the sea
- time of day buttons: morning, day, sunset and night. it starts at sunset, the lanterns glow in every light, not just at night

the game:
- she wears a summer yukata and walks the street
- 5 festival tasks shown as a small checklist: scoop a goldfish, buy a candy apple, win the ring toss, pick a mask, light a lantern. each one is a short simple mini game
- a gentle chime and a small "task 2/5" that fades when one is done
- 3 checkpoints along the street (lantern gates). passing one lights it up and saves your progress
- achievements that pop up small and quiet: all 5 tasks done, found the 3 hidden cats, watched the fireworks, pet the sleeping cat. an achievements list opens from a small icon in the corner
- finishing all 5 tasks unlocks the finale: walk to the shore and the fireworks burst over the sea
- a short title card and a controls hint at the start that fades out. calm and cozy, no score popups, no clutter

taste, this matters as much as the look:
- the town feels alive: festival-goers in yukata walking in small groups, kids running with sparklers, stall owners waving and calling out, a cat sleeping on a step, steam rising from the food stalls
- she feels alive too: breathes, blinks, looks around at the stalls, her sleeves and hair move in the wind. never frozen when standing still
- small details everywhere: lanterns swaying, wind chimes ringing when the breeze picks up, petals drifting, footsteps on wood and stone, festival music getting louder near the stalls
- smooth transitions, nothing snaps

look: toon-shaded, soft painted textures, warm rim light, bloom on the lanterns and fireworks. an original world in that anime style, no characters or places from any existing film

use the skills in .claude/skills and my global skills (threejs-aaa-graphics-builder, threejs-gameplay-systems, threejs-game-ui-designer, threejs-lighting, threejs-postprocessing, webgpu-threejs-tsl, threejs-performance, character-artist, hair-groom, animation, rigging), and blender through the mcp for her and the stalls. use pnpm

done means proof: in-game screenshots at sunset, day and night, one of a task being done and one of the fireworks, plus the measured fps on my rtx 4060. then deploy to github pages as StarKnightt/summer-festival and give me the live link

## 2. Five fixes

great work. five fixes before i post, then i'm done:

1. the ground-floor shop fronts on the left are pitch black in every time of day, including noon. they should read as warm wooden shops with lit interiors, noren curtains and goods, not black walls.
2. in daytime she faces the camera while standing. she should always face the way she's walking, and when idle face down the street.
3. npcs up close look boxy and stiff (the man on the right in proof_night). give the near ones softer kimono shapes, faces with eyes, and loose arms. far ones can stay simple.
4. the fireworks finale is too thin. make it a real show: many bursts layered at different heights and colors, chrysanthemums, willows, crackle, a big final barrage, reflected on the sea. drop the flat green ring.
5. move the "fireworks are about to start" text so it never covers her, top-center or lower-third.

done means: new proof screenshots of the street at noon and at night, and three of the finale at its peak. don't touch anything else.
