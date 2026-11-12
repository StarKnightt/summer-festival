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
  // Her head, sampled all run long: height above her feet and how far it has turned from the
  // body (vs. the idle rest), so a head that sinks or spins fails the run.
  await page.evaluate(() => {
    const her = __game.her, head = her.bone("head");
    const V = head.position.constructor, Q = head.quaternion.constructor;
    const rel = () => her.root.getWorldQuaternion(new Q()).invert().multiply(head.getWorldQuaternion(new Q()));
    const rest = rel();
    window.__head = { minH: 9, maxH: 0, maxTurn: 0, n: 0 };
    setInterval(() => {
      if (her.pose !== "none" || !her.root.visible) return;
      const h = head.getWorldPosition(new V()).y - her.position.y;
      const turn = rest.angleTo(rel());
      const L = window.__head;
      L.n++; L.minH = Math.min(L.minH, h); L.maxH = Math.max(L.maxH, h); L.maxTurn = Math.max(L.maxTurn, turn);
    }, 100);
  });
  // A close shot of her face from the front after each task.
  const faceShot = async (name) => {
    await page.waitForTimeout(1500);
    await page.evaluate(() => {
      const her = __game.her, hp = her.bone("head").getWorldPosition(new her.position.constructor());
      hp.y += 0.06;
      const f = new her.position.constructor(Math.sin(her.heading), 0, Math.cos(her.heading));
      __game.rig.setShot(hp.clone().addScaledVector(f, 1.1).add(new her.position.constructor(0, 0.05, 0)), hp.clone().add(new her.position.constructor(0, -0.12, 0)));
    });
    await page.waitForTimeout(1800);
    await page.screenshot({ path: `shots/after_${name}.png` });
    await page.evaluate(() => __game.rig.setShot(null));
    await page.waitForTimeout(600);
  };
  const finish = async (t, ms = 2200) => { await page.waitForTimeout(ms); const ok = await done(t); console.log(`[task] ${t}: ${ok ? "won" : "NOT WON"}`); if (!ok) fail++; await faceShot(t); };

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

  // ---- Every task a second time: they stay playable, and keep a count or a best.
  const over = async () => !(await page.evaluate(() => !!__play.mini));
  const count = (k) => page.evaluate((k) => __play.prog.count(k), k);
  const again = async (t, key, want) => {
    for (let i = 0; i < 40 && !(await over()); i++) await page.waitForTimeout(200);
    if (!(await over())) { console.log(`[task] ${t} again: did not finish`); fail++; await page.keyboard.press("Escape"); await page.waitForTimeout(600); return; }
    const n = key ? await count(key) : null;
    const ok = key ? (want ? n === want : n > 0) : true;
    console.log(`[task] ${t} again: ${ok ? "won" : "NOT COUNTED"}${key ? ` (${key} = ${n})` : ""}`);
    if (!ok) fail++;
    const st = await page.evaluate(() => ({ pose: __game.her.pose, en: __game.player.enabled, vis: __game.her.root.visible }));
    if (st.pose !== "none" || !st.en || !st.vis) { console.log(`[task] ${t} again: left in a bad state ${JSON.stringify(st)}`); fail++; }
    await page.waitForTimeout(500);
  };
  await start("goldfish");
  for (let i = 0; i < 14 && !(await page.evaluate(() => __play.mini?.won ?? true)); i++) {
    const fp = `(() => { const t = __play.tub; const f = t.fish[0]; return f ? f.g.getWorldPosition(new f.g.position.constructor()) : null; })()`;
    const p = await screen(fp);
    if (!p) break;
    await page.mouse.move(p.x, p.y, { steps: 4 });
    await page.mouse.down();
    for (let k = 0; k < 5; k++) { await page.waitForTimeout(90); const q = await screen(fp); if (q) await page.mouse.move(q.x, q.y, { steps: 2 }); }
    await page.mouse.up();
    await page.waitForTimeout(1200);
  }
  await again("goldfish", "goldfish", 2);
  await start("candyapple");
  await page.keyboard.press("KeyD"); await page.waitForTimeout(400);
  await page.keyboard.press("KeyE");
  await again("candyapple", "candyapple", 2);
  const apples = await page.evaluate(() => __game.carry.filter((o) => o.name === "held_apple").length);
  if (apples !== 1) { console.log(`[task] candyapple again: she holds ${apples} apples`); fail++; }
  await start("ringtoss");
  for (let i = 0; i < 16 && !(await page.evaluate(() => __play.mini?.won ?? true)); i++) {
    const p = await screen(`(() => { const s = __game.stalls.stalls.find(s => s.spot.kind === 'ringtoss'); const pg = s.findAll('peg_')[4]; return pg.getWorldPosition(new pg.position.constructor()); })()`);
    await page.mouse.move(p.x, p.y, { steps: 3 });
    await page.waitForTimeout(250);
    await page.mouse.down(); await page.mouse.up();
    await page.waitForTimeout(1300);
  }
  await again("ringtoss", "ringtoss.best", 0);
  await start("masks");
  await page.keyboard.press("KeyD"); await page.waitForTimeout(400);
  await page.keyboard.press("KeyE");
  await again("masks", null, 0);
  const masks = await page.evaluate(() => __game.carry.filter((o) => o.name === "worn_mask").length);
  if (masks !== 1) { console.log(`[task] masks again: she wears ${masks} masks`); fail++; }
  await start("lantern");
  {
    const w2 = await screen(`__play.lantern.wickTop`);
    await page.mouse.move(w2.x + 120, w2.y - 60);
    await page.mouse.down(); await page.mouse.up();
    await page.waitForTimeout(300);
    for (let k = 0; k < 40 && !(await page.evaluate(() => __play.mini?.won ?? true)); k++) {
      const m = await screen(`__play.lantern.wickTop`);
      await page.mouse.move(m.x, m.y + 4, { steps: 2 });
      await page.waitForTimeout(100);
    }
  }
  await again("lantern", "lantern", 2);

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
  const H = await page.evaluate(() => window.__head);
  console.log("[head]", JSON.stringify(H));
  if (H.minH < 1.3 || H.maxTurn > 1.45) { console.log("[head] FAIL: sank or over-turned"); fail++; }
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
