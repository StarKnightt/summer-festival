// Proof screenshots for the "make it feel real" round (1920x1080, production build):
//   her face from the front, side and three-quarter at noon and at night; a close NPC talking
//   with a speech bubble; her eating takoyaki; the guide path; a shopkeeper's face at a food stall.
// (Walk and run strips come from scripts/gait.mjs.)   Usage: node scripts/proof3.mjs [--dev]
import { openGame, waitReady } from "./lib/harness.mjs";
import fs from "node:fs";

const { page, url, errors, bye } = await openGame({ dist: !process.argv.includes("--dev") });
fs.mkdirSync("shots", { recursive: true });
let fail = 0;
const shot = (n) => page.screenshot({ path: `shots/proof3_${n}.png` });
try {
  // ---- her face, noon and night
  for (const [tod, label] of [["day", "noon"], ["night", "night"]]) {
    await page.goto(`${url}?play&fresh&tod=${tod}`);
    await waitReady(page);
    await page.evaluate(() => { __play.guide.on = false; __play.debugTeleport(0.3, -36, Math.PI); for (const n of __play.crowd.npcs) if (Math.hypot(n.pos.x - 0.3, n.pos.z + 36) < 6 && n.mode !== "keeper") { n.hide = true; n.root.visible = false; } });
    await page.waitForTimeout(2500);
    for (const [view, ang, dist] of [["front", 0, 0.95], ["threequarter", 0.75, 0.98], ["side", Math.PI / 2, 1.0]]) {
      await page.evaluate(([ang, dist]) => {
        clearInterval(window.__f);
        window.__f = setInterval(() => {
          const her = __game.her, V = her.position.constructor;
          const hp = her.bone("head").getWorldPosition(new V());
          hp.y += 0.05;
          const fd = her.faceDir();
          const a = Math.atan2(fd.x, fd.z) + ang; // off where her face actually points
          __game.rig.setShot(new V(hp.x + Math.sin(a) * dist, hp.y + 0.03, hp.z + Math.cos(a) * dist), hp.clone().add(new V(0, -0.06, 0)));
        }, 8);
      }, [ang, dist]);
      await page.waitForTimeout(1600);
      await shot(`face_${label}_${view}`);
    }
    await page.evaluate(() => { clearInterval(window.__f); __game.rig.setShot(null); });
  }

  // ---- sunset street: guide, a talking NPC, a keeper's face, eating
  await page.goto(`${url}?play&fresh&tod=sunset`);
  await waitReady(page);
  await page.evaluate(() => { __play.debugTeleport(1.2, -8, Math.PI); __game.rig.yaw += 0.45; });
  await page.waitForTimeout(3000);
  await shot("guide_path");
  console.log("[proof3] guide dots", await page.evaluate(() => __play.guide.shown));

  // A close NPC talking, with a bubble.
  const ok = await page.evaluate(() => {
    const V = __game.her.position.constructor;
    const n = __play.crowd.npcs.find((n) => n.mode === "stand" && n.v === "woman") ?? __play.crowd.npcs.find((n) => n.mode === "stand");
    __play.crowd.play(n, "idle", 0.2);
    n.look = null;
    if (!n) return false;
    __play.guide.on = false;
    __play.debugTeleport(n.pos.x - Math.sign(n.pos.x) * 2.4, n.pos.z + 1.2, 0);
    clearInterval(window.__f);
    window.__f = setInterval(() => {
      const h = n.head.getWorldPosition(new V());
      const f = new V(Math.sin(n.heading), 0, Math.cos(n.heading));
      __game.rig.setShot(h.clone().addScaledVector(f, 1.3).add(new V(f.z * 0.12, 0.02, -f.x * 0.12)), h.clone().add(new V(0, 0.04, 0)));
      __play.social.say(n, "Did you try the takoyaki yet?", 1, 3);
      n.smile = 0.35;
    }, 30);
    return true;
  });
  await page.waitForTimeout(2200);
  await shot("npc_talking");
  if (!ok) { console.log("[proof3] no standing NPC found"); fail++; }
  const bubbles = await page.evaluate(() => [...document.querySelectorAll(".bubble.on")].map((e) => e.textContent));
  console.log("[proof3] bubbles", JSON.stringify(bubbles));
  await page.evaluate(() => { clearInterval(window.__f); __game.rig.setShot(null); });

  // A shopkeeper's face at the yakisoba stall (no glow over it).
  await page.evaluate(() => {
    const V = __game.her.position.constructor;
    const k = __play.crowd.npcs.find((n) => n.mode === "keeper" && n.stall?.spot.kind === "food_a");
    __play.debugTeleport(0, k.pos.z + 7, 0);
    clearInterval(window.__f);
    window.__f = setInterval(() => { const h = k.head.getWorldPosition(new V()); __game.rig.setShot(new V(h.x + Math.sin(k.heading) * 1.5, h.y + 0.05, h.z + Math.cos(k.heading) * 1.5), h); }, 30);
  });
  await page.waitForTimeout(2500);
  await shot("keeper_face");
  await page.evaluate(() => { clearInterval(window.__f); __game.rig.setShot(null); });

  // Eating takoyaki.
  await page.evaluate(() => { const s = __game.stalls.stalls.find((s) => s.spot.kind === "food_b"); const dx = s.camTarget.x - s.use.x, dz = s.camTarget.z - s.use.z; __play.debugTeleport(s.use.x - dx * 0.1, s.use.z - dz * 0.1, Math.atan2(dx, dz)); });
  await page.waitForTimeout(900);
  await page.keyboard.press("KeyE");
  for (let i = 0; i < 20 && !(await page.evaluate(() => !!__play.mini)); i++) await page.waitForTimeout(150);
  // Catch her with the food at her mouth: part-way into the first bite.
  for (let i = 0; i < 60; i++) { await page.waitForTimeout(100); if (await page.evaluate(() => __play.mini?.bite >= 1)) break; }
  await page.waitForTimeout(900);
  await shot("eating_takoyaki");
  await page.waitForTimeout(1500);
  await shot("eating_takoyaki_2");
  for (let i = 0; i < 100 && (await page.evaluate(() => !!__play.mini)); i++) await page.waitForTimeout(200);
  console.log("[proof3] takoyaki eaten:", await page.evaluate(() => __play.prog.count("takoyaki")));
} catch (e) { console.error(String(e?.stack ?? e)); fail++; }
const fatal = await page.evaluate(() => window.__fatal).catch(() => null);
if (fatal) { console.error("[fatal]", fatal); fail++; }
for (const e of errors.filter((e) => !/powerPreference|404/.test(e)).slice(0, 20)) console.log(e);
console.log(fail ? "[proof3] FAIL" : "[proof3] ok");
await bye(fail ? 1 : 0);
