// Bot playtest: plays all five mini-games through real mouse/keyboard input, walks to the shore
// and watches the fireworks. Screenshots go to shots/play_*.png. Usage:
//   node scripts/playtest.mjs [--dist] [--tod sunset]
import { openGame, waitReady } from "./lib/harness.mjs";
import fs from "node:fs";

const arg = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
const tod = arg("--tod", "sunset");
const { page, url, errors, bye } = await openGame({ dist: process.argv.includes("--dist") });
fs.mkdirSync("shots", { recursive: true });
let fail = 0;
try {
  await page.goto(`${url}?play&fresh&tod=${tod}`);
  await waitReady(page);
  await page.waitForTimeout(1500);
  const done = (t) => page.evaluate((t) => __play.prog.has(t), t);
  const screen = (expr) => page.evaluate(`(() => { const p = (${expr}); if (!p) return null; const v = p.clone().project(__game.camera); return { x: (v.x * 0.5 + 0.5) * innerWidth, y: (-v.y * 0.5 + 0.5) * innerHeight }; })()`);
  const start = async (t) => { await page.evaluate((t) => __play.debugStart(t), t); await page.waitForTimeout(1800); };
  const finish = async (t, ms = 2200) => { await page.waitForTimeout(ms); const ok = await done(t); console.log(`[task] ${t}: ${ok ? "won" : "NOT WON"}`); if (!ok) fail++; };

  // Goldfish: hover a fish, dip, hold still a moment, lift.
  await start("goldfish");
  for (let i = 0; i < 14 && !(await page.evaluate(() => __play.mini?.won)); i++) {
    const p = await screen(`(() => { const t = __play.tub; const f = t.fish[0]; return f ? f.g.getWorldPosition(new f.g.position.constructor()) : null; })()`);
    if (!p) break;
    await page.mouse.move(p.x, p.y, { steps: 4 });
    await page.mouse.down();
    for (let k = 0; k < 5; k++) {
      await page.waitForTimeout(90);
      const q = await screen(`(() => { const t = __play.tub; const f = t.fish[0]; return f ? f.g.getWorldPosition(new f.g.position.constructor()) : null; })()`);
      if (q) await page.mouse.move(q.x, q.y, { steps: 2 });
    }
    if (i === 0) await page.screenshot({ path: "shots/play_goldfish.png" });
    await page.mouse.up();
    await page.waitForTimeout(1200);
  }
  await finish("goldfish");

  // Candy apple: the first one is selected; take it.
  await start("candyapple");
  await page.keyboard.press("KeyD");
  await page.waitForTimeout(400);
  await page.keyboard.press("KeyE");
  await page.waitForTimeout(500);
  await page.screenshot({ path: "shots/play_candyapple.png" });
  await finish("candyapple");

  // Ring toss: aim at the middle peg, toss.
  await start("ringtoss");
  for (let i = 0; i < 16 && !(await done("ringtoss")); i++) {
    const p = await screen(`(() => { const s = __game.stalls.stalls.find(s => s.spot.kind === 'ringtoss'); const pg = s.findAll('peg_')[4]; return pg.getWorldPosition(new pg.position.constructor()); })()`);
    await page.mouse.move(p.x, p.y, { steps: 3 });
    await page.waitForTimeout(250);
    await page.mouse.down(); await page.mouse.up();
    if (i === 1) { await page.waitForTimeout(350); await page.screenshot({ path: "shots/play_ringtoss.png" }); }
    await page.waitForTimeout(1300);
  }
  await finish("ringtoss");

  // Masks: browse twice, take one.
  await start("masks");
  await page.keyboard.press("KeyA"); await page.waitForTimeout(300);
  await page.keyboard.press("KeyA"); await page.waitForTimeout(500);
  await page.screenshot({ path: "shots/play_masks.png" });
  await page.keyboard.press("KeyE");
  await finish("masks");

  // Lantern: strike a match, bring it to the wick and hold.
  await start("lantern");
  const w = await screen(`__play.lantern.wickTop`);
  await page.mouse.move(w.x + 120, w.y - 60);
  await page.mouse.down(); await page.mouse.up();
  await page.waitForTimeout(300);
  for (let k = 0; k < 30 && !(await done("lantern")); k++) {
    const m = await screen(`__play.lantern.wickTop`);
    // Aim the match's flame tip (≈1 cm above the head) at the wick.
    await page.mouse.move(m.x, m.y + 4, { steps: 2 });
    await page.waitForTimeout(100);
    if (k === 6) await page.screenshot({ path: "shots/play_lantern.png" });
  }
  await finish("lantern", 2600);

  // Pet the sleeping cat.
  await page.evaluate(() => __play.debugTeleport(-2.7, -76.2, -Math.PI / 2));
  await page.waitForTimeout(800);
  await page.keyboard.press("KeyE");
  await page.waitForTimeout(1600);
  await page.screenshot({ path: "shots/play_pet.png" });
  await page.waitForTimeout(3500);
  // Find the hidden cats.
  for (const [x, z] of [[2.2, -40.6], [-4.4, -48.6], [5.2, -98.4]]) {
    await page.evaluate(([x, z]) => __play.debugTeleport(x, z), [x, z]);
    await page.waitForTimeout(700);
  }
  console.log("[cats]", JSON.stringify(await page.evaluate(() => ({ cats: __play.prog.data.cats, petted: __play.prog.data.petted }))));

  // Walk out of the shot and down to the shore.
  await page.evaluate(() => __play.debugTeleport(0, -108));
  await page.waitForTimeout(12000);
  await page.screenshot({ path: "shots/play_fireworks.png" });
  await page.waitForTimeout(16000);
  const s = await page.evaluate(() => ({ tasks: __play.prog.data.tasks, ach: __play.prog.data.ach, shells: __play.fx.shellsLaunched }));
  console.log("[state]", JSON.stringify(s));
  for (const a of ["tasks", "fireworks", "pet", "cats"]) if (!s.ach.includes(a)) { console.log("[missing achievement]", a); fail++; }
} catch (e) {
  console.error(String(e?.stack ?? e));
  fail++;
}
const fatal = await page.evaluate(() => window.__fatal).catch(() => null);
if (fatal) { console.error("[fatal]", fatal); fail++; }
for (const e of errors.filter((e) => !/powerPreference|404/.test(e)).slice(0, 20)) console.log(e);
console.log(fail ? `[playtest] FAIL (${fail})` : "[playtest] ok");
await bye(fail ? 1 : 0);
