// Plays everything that isn't one of the five tasks: the three food stalls (shaved ice with a
// syrup choice), the cork-gun gallery, the lucky draw, the four emotes (and that people answer),
// crowd speech bubbles (never more than two), and the guide (path, pin/arrow, G to toggle).
// Usage: node scripts/extras.mjs [--dist]
import { openGame, waitReady } from "./lib/harness.mjs";
import fs from "node:fs";

const { page, url, errors, bye } = await openGame({ dist: process.argv.includes("--dist") });
fs.mkdirSync("shots", { recursive: true });
let fail = 0;
const bad = (m) => { console.log("[extras] FAIL:", m); fail++; };
const count = (k) => page.evaluate((k) => __play.prog.count(k), k);
const mini = () => page.evaluate(() => !!__play.mini);
const until = async (fn, ms) => { for (let t = 0; t < ms; t += 150) { if (await fn()) return true; await page.waitForTimeout(150); } return false; };
try {
  await page.goto(`${url}?play&fresh&tod=sunset`);
  await waitReady(page);
  await page.waitForTimeout(1800);

  // ---- guide
  let shown = await page.evaluate(() => __play.guide.shown);
  const tgt = await page.evaluate(() => [...document.querySelectorAll(".gpin, .garrow")].filter((e) => +e.style.opacity > 0.3).map((e) => e.className + ":" + e.textContent));
  console.log(`[extras] guide: ${shown} path dots, ${JSON.stringify(tgt)}`);
  if (shown < 5) bad("no guide path on the ground");
  if (!tgt.length) bad("no guide pin or arrow");
  await page.screenshot({ path: "shots/guide_path.png" });
  await page.keyboard.press("KeyG");
  await page.waitForTimeout(1800);
  shown = await page.evaluate(() => __play.guide.shown);
  if (shown > 0) bad(`guide still showing after G (${shown} dots)`);
  await page.keyboard.press("KeyG");
  await page.waitForTimeout(600);

  const enter = async (expr) => {
    await page.evaluate(`(() => { const s = ${expr}; const dx = s.camTarget.x - s.use.x, dz = s.camTarget.z - s.use.z; __play.debugTeleport(s.use.x - dx * 0.1, s.use.z - dz * 0.1, Math.atan2(dx, dz)); })()`);
    await page.waitForTimeout(700);
    const prompt = await page.evaluate(() => document.querySelector("#prompt")?.textContent);
    await page.keyboard.press("KeyE");
    // (The very first stall can take a moment: its shaders compile on first sight.)
    if (!(await until(mini, 3000))) { bad(`E did nothing at ${expr} (prompt: ${prompt})`); return false; }
    return true;
  };

  // ---- food stalls, each twice
  const food = [["yakisoba", "__game.stalls.stalls.find((s) => s.spot.kind === 'food_a')"], ["takoyaki", "__game.stalls.stalls.find((s) => s.spot.kind === 'food_b')"], ["shavedice", "__game.stalls.stalls.find((s) => s.spot.kind === 'shavedice')"]];
  for (const [kind, expr] of food) for (let round = 0; round < 2; round++) {
    if (!(await enter(expr))) continue;
    if (kind === "shavedice") { await page.waitForTimeout(600); await page.keyboard.press("KeyD"); await page.waitForTimeout(300); await page.keyboard.press("KeyE"); }
    if (round === 0) { await page.waitForTimeout(4200); await page.screenshot({ path: `shots/eat_${kind}.png` }); }
    if (!(await until(async () => !(await mini()), 20000))) { bad(`${kind}: never finished`); await page.keyboard.press("Escape"); }
    const n = await count(kind);
    if (n !== round + 1) bad(`${kind}: count ${n} after round ${round + 1}`);
    else console.log(`[extras] ${kind}: eaten x${n}`);
    if (!(await page.evaluate(() => __game.player.enabled))) bad(`${kind}: player left locked`);
    await page.waitForTimeout(400);
  }

  // ---- cork-gun gallery, twice
  for (let round = 0; round < 2; round++) {
    if (!(await enter("__play.gallery"))) break;
    await page.waitForTimeout(600);
    for (let i = 0; i < 6; i++) {
      const p = await page.evaluate(() => {
        const t = __play.gallery.targets.find((t) => !t.userData.down);
        if (!t) return null;
        const v = t.getWorldPosition(new t.position.constructor()); v.y += t.userData.h;
        v.project(__game.camera);
        return { x: (v.x * 0.5 + 0.5) * innerWidth, y: (-v.y * 0.5 + 0.5) * innerHeight };
      });
      if (!p) break;
      await page.mouse.move(p.x, p.y, { steps: 4 });
      await page.waitForTimeout(450);
      await page.mouse.down(); await page.mouse.up();
      await page.waitForTimeout(500);
      if (round === 0 && i === 2) await page.screenshot({ path: "shots/gallery.png" });
    }
    if (!(await until(async () => !(await mini()), 8000))) { bad("gallery: never finished"); await page.keyboard.press("Escape"); }
    console.log(`[extras] gallery: round ${round + 1}, best ${await count("gallery.best")} of 6`);
  }
  if ((await count("gallery")) !== 2) bad("gallery: rounds not counted");
  if ((await count("gallery.best")) < 1) bad("gallery: no prize hit in 12 aimed shots");

  // ---- lucky draw, twice
  for (let round = 0; round < 2; round++) {
    if (!(await enter("__play.shrine"))) break;
    for (let i = 0; i < 3; i++) { await page.waitForTimeout(750); await page.keyboard.press("KeyE"); }
    await page.waitForTimeout(1500);
    if (round === 0) await page.screenshot({ path: "shots/omikuji.png" });
    const text = await page.evaluate(() => document.querySelector("#mg .line")?.textContent);
    console.log(`[extras] omikuji: ${text}`);
    if (!(await until(async () => !(await mini()), 8000))) { bad("omikuji: never finished"); await page.keyboard.press("Escape"); }
  }
  if ((await count("omikuji")) !== 2) bad("omikuji: draws not counted");

  // ---- emotes, among people
  await page.evaluate(() => {
    const n = __play.crowd.npcs.filter((n) => n.mode === "stand")[0];
    __play.debugTeleport(n.pos.x - Math.sign(n.pos.x) * 1.6, n.pos.z + 0.4, Math.atan2(Math.sign(n.pos.x), -0.2));
  });
  await page.waitForTimeout(1200);
  let maxBubbles = 0, reacted = 0;
  const watch = setInterval(async () => { try { const n = await page.evaluate(() => [...document.querySelectorAll(".bubble.on")].length); maxBubbles = Math.max(maxBubbles, n); } catch {} }, 200);
  for (const [key, id] of [["Digit1", "wave"], ["Digit2", "bow"], ["Digit3", "cheer"], ["Digit4", "photo"]]) {
    await page.keyboard.press(key);
    await page.waitForTimeout(1500);
    const b = await page.evaluate(() => [...document.querySelectorAll(".bubble.on")].map((e) => e.textContent));
    if (b.length) reacted++;
    console.log(`[extras] emote ${id}: bubbles ${JSON.stringify(b)}`);
    if (id === "wave") await page.screenshot({ path: "shots/npc_bubble.png" });
    await page.waitForTimeout(1900);
  }
  const done = await page.evaluate(() => __play.social.done);
  if (done.length !== 4) bad(`emotes played: ${done.join(",")}`);
  if (reacted < 3) bad(`people answered only ${reacted} of 4 emotes`);
  // Ambient chatter: stand about for a while and count bubbles.
  await page.waitForTimeout(12000);
  clearInterval(watch);
  console.log(`[extras] most bubbles on screen at once: ${maxBubbles}`);
  if (maxBubbles > 2) bad(`${maxBubbles} speech bubbles at once`);
  if (maxBubbles < 1) bad("no speech bubbles at all");
  if (!(await page.evaluate(() => __game.player.enabled))) bad("player locked after emotes");
} catch (e) { console.error(String(e?.stack ?? e)); fail++; }
const fatal = await page.evaluate(() => window.__fatal).catch(() => null);
if (fatal) { console.error("[fatal]", fatal); fail++; }
const errs = errors.filter((e) => !/powerPreference|404/.test(e));
for (const e of errs.slice(0, 20)) console.log(e);
if (errs.length) fail++;
console.log(fail ? `[extras] FAIL (${fail})` : "[extras] ok");
await bye(fail ? 1 : 0);
