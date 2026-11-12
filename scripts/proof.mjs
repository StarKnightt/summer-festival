// Proof screenshots on the production build (1920×1080): the street at noon and at night,
// a task being played, and three frames of the fireworks finale. Output: shots/proof_*.png
import { openGame, waitReady } from "./lib/harness.mjs";
import fs from "node:fs";

const { page, url, errors, bye } = await openGame({ dist: true });
fs.mkdirSync("shots", { recursive: true });
let fail = 0;
const shot = (n) => page.screenshot({ path: `shots/proof_${n}.png` });
try {
  for (const tod of ["day", "night"]) {
    await page.goto(`${url}?play&fresh&tod=${tod}`);
    await waitReady(page);
    await page.evaluate(() => { __play.debugTeleport(0.6, -33); __game.rig.yaw = 0.25; /* behind her, looking down the street */ });
    // Hold the title card's controls hint out of frame; let the crowd settle in.
    await page.waitForTimeout(6000);
    await shot(tod);
    console.log("[proof]", tod);
  }
  // A task: the ring toss, ring in the air.
  await page.goto(`${url}?play&fresh&tod=sunset`);
  await waitReady(page);
  await page.evaluate(() => __play.debugStart("ringtoss"));
  await page.waitForTimeout(2200);
  const p = await page.evaluate(() => { const s = __game.stalls.stalls.find((s) => s.spot.kind === "ringtoss"); const v = s.findAll("peg_")[4].getWorldPosition(new s.root.position.constructor()).project(__game.camera); return { x: (v.x * 0.5 + 0.5) * innerWidth, y: (-v.y * 0.5 + 0.5) * innerHeight }; });
  await page.mouse.move(p.x, p.y, { steps: 3 });
  await page.waitForTimeout(300);
  await page.mouse.down(); await page.mouse.up();
  await page.waitForTimeout(380);
  await shot("task");
  console.log("[proof] task");
  // Fireworks finale: three frames across the final barrage (show seconds 50-61).
  await page.goto(`${url}?play&fresh&tod=sunset`);
  await waitReady(page);
  await page.evaluate(() => { __play.debugComplete(); __play.debugTeleport(0.5, -110); });
  for (const [i, at] of [[1, 54.5], [2, 58.5], [3, 61.6]]) {
    for (let k = 0; k < 900 && (await page.evaluate(() => __play.fx.showTime)) < at; k++) await page.waitForTimeout(100);
    await shot(`finale_${i}`);
    console.log("[proof] finale", i, await page.evaluate(() => ({ t: __play.fx.showTime.toFixed(1), stars: __play.fx.glow.list.length })));
  }
} catch (e) { console.error(String(e?.stack ?? e)); fail++; }
const fatal = await page.evaluate(() => window.__fatal).catch(() => null);
if (fatal) { console.error("[fatal]", fatal); fail++; }
for (const e of errors.filter((e) => !/powerPreference|404/.test(e)).slice(0, 20)) console.log(e);
await bye(fail ? 1 : 0);
