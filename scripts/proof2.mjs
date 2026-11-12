// Proof screenshots for the polish round (1920×1080, production build):
//   loader mid-load, a task marker near a stall, the beach rocks and sea wall, her face from the
//   front and the side while she walks, and a close NPC with glasses.
// Usage: node scripts/proof2.mjs [--only loader,marker,beach,face,npc]
import { openGame, waitReady } from "./lib/harness.mjs";
import fs from "node:fs";

const only = (() => { const i = process.argv.indexOf("--only"); return i > 0 ? process.argv[i + 1].split(",") : null; })();
const want = (k) => !only || only.includes(k);
const { page, url, errors, bye } = await openGame({ dist: true });
fs.mkdirSync("shots", { recursive: true });
let fail = 0;
const shot = (n) => page.screenshot({ path: `shots/proof2_${n}.png` });
try {
  if (want("loader")) {
    // Slow the network so the loader is caught part-way.
    const cdp = await page.context().newCDPSession(page);
    await cdp.send("Network.enable");
    await cdp.send("Network.setCacheDisabled", { cacheDisabled: true });
    await cdp.send("Network.emulateNetworkConditions", { offline: false, latency: 40, downloadThroughput: 1_400_000, uploadThroughput: 1_000_000 });
    await page.goto(`${url}?fresh&tod=sunset`);
    let k = 0;
    for (let i = 0; i < 400 && k < 0.5; i++) {
      await page.waitForTimeout(100);
      k = await page.evaluate(() => { const t = document.querySelector("#title .bar i")?.style.transform ?? ""; const m = /scaleX\(([\d.]+)\)/.exec(t); return m ? +m[1] : 0; });
    }
    await page.waitForTimeout(250);
    await shot("loader");
    console.log("[proof2] loader at", k.toFixed(2));
    await cdp.send("Network.emulateNetworkConditions", { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1 });
    await cdp.send("Network.setCacheDisabled", { cacheDisabled: false });
  }
  if (want("marker")) {
    await page.goto(`${url}?play&fresh&tod=sunset`);
    await waitReady(page);
    // A few metres short of the goldfish stall, looking toward it.
    const p = await page.evaluate(() => { const s = __game.stalls.stalls.find((s) => s.spot.kind === "goldfish"); return { x: s.camTarget.x, z: s.camTarget.z, side: s.spot.side }; });
    await page.evaluate(({ x, z, side }) => { __play.debugTeleport(-side * 0.8, z + 7.5); __game.rig.yaw = Math.PI * 0.0 + (side > 0 ? -0.35 : 0.35); }, p);
    await page.waitForTimeout(4000);
    await shot("marker");
    console.log("[proof2] marker", await page.evaluate(() => [...document.querySelectorAll(".marker")].map((m) => m.style.opacity).join(",")));
  }
  if (want("beach")) {
    await page.goto(`${url}?play&fresh&tod=day`);
    await waitReady(page);
    await page.evaluate(() => { __play.debugTeleport(12, -112, Math.PI * 0.75); __game.rig.yaw = Math.PI * 0.75 + Math.PI; });
    await page.waitForTimeout(4000);
    await shot("beach");
    await page.evaluate(() => { __play.debugTeleport(5.5, -104.5, 0); __game.rig.yaw = Math.PI + 0.5; __game.rig.pitch = 0.05; });
    await page.waitForTimeout(3000);
    await shot("seawall");
    console.log("[proof2] beach");
  }
  if (want("face")) {
    await page.goto(`${url}?play&fresh&tod=day`);
    await waitReady(page);
    await page.evaluate(() => __play.debugTeleport(0.4, -20, Math.PI));
    await page.waitForTimeout(1500);
    // Walk down the street; the camera keeps pace in front of her (or beside her).
    for (const view of ["front", "side"]) {
      await page.evaluate((view) => {
        clearInterval(window.__follow);
        window.__follow = setInterval(() => {
          const her = __game.her, V = her.position.constructor;
          const hp = her.bone("head").getWorldPosition(new V());
          const f = new V(Math.sin(her.heading), 0, Math.cos(her.heading));
          const sd = new V(f.z, 0, -f.x);
          const off = view === "front" ? f.clone().multiplyScalar(1.15) : sd.clone().multiplyScalar(1.15).addScaledVector(f, 0.1);
          __game.rig.setShot(hp.clone().add(off).add(new V(0, 0.02, 0)), hp.clone().add(new V(0, -0.1, 0)));
        }, 16);
      }, view);
      await page.keyboard.down("KeyW");
      await page.waitForTimeout(view === "front" ? 3200 : 2600);
      await shot(`face_${view}`);
      await page.keyboard.up("KeyW");
      await page.waitForTimeout(500);
    }
    await page.evaluate(() => { clearInterval(window.__follow); __game.rig.setShot(null); });
    console.log("[proof2] face");
  }
  if (want("npc")) {
    await page.goto(`${url}?play&fresh&tod=sunset`);
    await waitReady(page);
    await page.waitForTimeout(2500);
    // The nearest NPC wearing glasses, framed close.
    const ok = await page.evaluate(() => {
      const her = __game.her, V = her.position.constructor;
      const list = __play.crowd.npcs.filter((n) => n.glasses && n.root.visible && n.mode !== "watch");
      if (!list.length) return false;
      list.sort((a, b) => a.pos.distanceTo(her.position) - b.pos.distanceTo(her.position));
      const n = list[0];
      __play.debugTeleport(n.pos.x + 1.6 * Math.sin(n.heading), n.pos.z + 1.6 * Math.cos(n.heading), n.heading + Math.PI);
      window.__npc = n;
      clearInterval(window.__follow);
      window.__follow = setInterval(() => {
        const h = n.head.getWorldPosition(new V());
        const f = new V(Math.sin(n.heading), 0, Math.cos(n.heading));
        __game.rig.setShot(h.clone().addScaledVector(f, 1.3).add(new V(0, 0.0, 0)), h.clone().add(new V(0, -0.2, 0)));
      }, 16);
      return true;
    });
    await page.waitForTimeout(2500);
    await shot("npc_glasses");
    console.log("[proof2] npc", ok ? "" : "(no NPC with glasses found)");
    if (!ok) fail++;
  }
} catch (e) { console.error(String(e?.stack ?? e)); fail++; }
const fatal = await page.evaluate(() => window.__fatal).catch(() => null);
if (fatal) { console.error("[fatal]", fatal); fail++; }
for (const e of errors.filter((e) => !/powerPreference|404/.test(e)).slice(0, 20)) console.log(e);
await bye(fail ? 1 : 0);
