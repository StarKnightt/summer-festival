// Her walk and run in the game: measures how much a planted foot slides over the ground (the
// lower foot's horizontal speed in world space), checks her head never turns past its limit
// while something behind her calls for her attention, and writes 8-frame strips of both gaits
// seen from the side (shots/strip_walk.png, shots/strip_run.png) plus a short GIF of each.
// Usage: node scripts/gait.mjs [--dist]
import { openGame, waitReady } from "./lib/harness.mjs";
import { execFileSync } from "node:child_process";
import fs from "node:fs";

const { page, url, errors, bye } = await openGame({ dist: process.argv.includes("--dist") });
fs.mkdirSync("shots/_gait", { recursive: true });
let fail = 0;
const bad = (m) => { console.log("[gait] FAIL:", m); fail++; };
try {
  await page.goto(`${url}?play&fresh&tod=day`);
  await waitReady(page);
  // Nobody in the way.
  await page.evaluate(() => { for (const n of __play.crowd.npcs) { n.hide = true; n.root.visible = false; n.pos.x += 400; } __play.animals.group.visible = false; __play.guide.on = false; });
  for (const [gait, keys, limit] of [["walk", ["KeyW"], 3.0], ["run", ["KeyW", "ShiftLeft"], 5.0]]) {
    await page.evaluate(() => { __play.debugTeleport(0, -20, Math.PI); __game.rig.yaw = 0; });
    await page.waitForTimeout(600);
    // Side-on camera that keeps pace with her.
    await page.evaluate(() => {
      clearInterval(window.__f);
      window.__f = setInterval(() => { const h = __game.her, V = h.position.constructor; __game.rig.setShot(new V(h.position.x + 3.1, h.position.y + 0.95, h.position.z), new V(h.position.x, h.position.y + 0.85, h.position.z)); }, 8);
    });
    for (const k of keys) await page.keyboard.down(k);
    await page.waitForTimeout(1400);
    // Foot slip: sample every frame for a while.
    const m = await page.evaluate(() => new Promise((res) => {
      const her = __game.her, V = her.position.constructor;
      const L = her.bone("toe_L") ?? her.bone("foot_L"), R = her.bone("toe_R") ?? her.bone("foot_R");
      let pl = null, pr = null, t0 = performance.now(), last = t0;
      const slips = [], speeds = [];
      const tick = () => {
        const now = performance.now(), dt = (now - last) / 1000; last = now;
        const a = L.getWorldPosition(new V()), b = R.getWorldPosition(new V());
        if (pl && dt > 0.002) {
          const low = a.y < b.y ? [a, pl] : [b, pr];
          // Only while that foot is clearly the planted one.
          if (Math.abs(a.y - b.y) > 0.02) slips.push(Math.hypot(low[0].x - low[1].x, low[0].z - low[1].z) / dt);
          speeds.push(her.speed);
        }
        pl = a; pr = b;
        if (now - t0 < 2600) requestAnimationFrame(tick);
        else { slips.sort((x, y) => x - y); res({ med: slips[Math.floor(slips.length / 2)], p90: slips[Math.floor(slips.length * 0.9)], n: slips.length, speed: speeds.reduce((x, y) => x + y, 0) / speeds.length }); }
      };
      requestAnimationFrame(tick);
    }));
    console.log(`[gait] ${gait}: ${m.speed.toFixed(2)} m/s, planted-foot slide median ${(m.med * 100).toFixed(1)} cm/s, p90 ${(m.p90 * 100).toFixed(1)} cm/s (${m.n} samples)`);
    if (m.med * 100 > limit * 2) bad(`${gait}: feet slide ${(m.med * 100).toFixed(1)} cm/s`);
    // Eight frames across one stride.
    for (let i = 0; i < 8; i++) {
      await page.screenshot({ path: `shots/_gait/${gait}_${i}.png`, clip: { x: 760, y: 190, width: 400, height: 760 } });
      await page.waitForTimeout(gait === "walk" ? 105 : 58);
    }
    // And two seconds for the GIF.
    for (let i = 0; i < 30; i++) {
      await page.screenshot({ path: `shots/_gait/${gait}_g${String(i).padStart(2, "0")}.png`, clip: { x: 720, y: 170, width: 480, height: 800 } });
      await page.waitForTimeout(20);
    }
    for (const k of keys) await page.keyboard.up(k);
    await page.evaluate(() => { clearInterval(window.__f); __game.rig.setShot(null); });
    await page.waitForTimeout(700);
    // One-shot CPU work (stitching a handful of PNGs): ffmpeg on the CPU is the right tool here.
    const inputs = Array.from({ length: 8 }, (_, i) => ["-i", `shots/_gait/${gait}_${i}.png`]).flat();
    execFileSync("ffmpeg", ["-y", "-loglevel", "error", ...inputs, "-filter_complex", "hstack=inputs=8", `shots/strip_${gait}.png`]);
    execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-framerate", "15", "-i", `shots/_gait/${gait}_g%02d.png`, "-vf", "scale=300:-1:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse", `shots/${gait}.gif`]);
  }
  // Head look-at: targets all round her; the head must stay within its range.
  await page.evaluate(() => __play.debugTeleport(0, -20, Math.PI));
  await page.waitForTimeout(800);
  const yaws = [];
  for (const ang of [0.5, 1.2, 2.0, 2.8, -2.6, -1.4]) {
    await page.evaluate((ang) => { const h = __game.her, V = h.position.constructor; __play.lookAt = new V(h.position.x + Math.sin(h.heading + ang) * 3, h.position.y + 1.5, h.position.z + Math.cos(h.heading + ang) * 3); __play.lookT = 3; }, ang);
    let worst = 0;
    for (let i = 0; i < 12; i++) { await page.waitForTimeout(120); worst = Math.max(worst, Math.abs(await page.evaluate(() => __game.her.headYaw))); }
    await page.evaluate(() => { __play.lookT = 0; });
    await page.waitForTimeout(500);
    yaws.push(worst);
    console.log(`[gait]   target at ${(ang * 57.3).toFixed(0)}°: head reached ${(worst * 57.3).toFixed(0)}°`);
  }
  const max = Math.max(...yaws);
  console.log(`[gait] head look-at: worst turn ${(max * 57.3).toFixed(0)}° over targets all round her (limit 75°)`);
  if (max > 1.31) bad(`head turned ${(max * 57.3).toFixed(0)}°`);
} catch (e) { console.error(String(e?.stack ?? e)); fail++; }
for (const e of errors.filter((e) => !/powerPreference|404/.test(e)).slice(0, 10)) console.log(e);
fs.rmSync("shots/_gait", { recursive: true, force: true });
console.log(fail ? `[gait] FAIL (${fail})` : "[gait] ok");
await bye(fail ? 1 : 0);
