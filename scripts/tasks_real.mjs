// Plays each stall the way a player does: stand at the counter, press E, play a bit, step away
// with Esc at an awkward moment (ring in the air, fish on the paper, match burning), check that
// nothing was left behind, go back in with E. Fails on anything left floating or stuck.
// Usage: node scripts/tasks_real.mjs [--dist]
import { openGame, waitReady } from "./lib/harness.mjs";

const { page, url, errors, bye } = await openGame({ dist: process.argv.includes("--dist") });
let fail = 0;
const bad = (m) => { console.log("[tasks] FAIL:", m); fail++; };
try {
  await page.goto(`${url}?play&fresh&tod=sunset`);
  await waitReady(page);
  await page.waitForTimeout(1200);
  const screen = (expr) => page.evaluate(`(() => { const p = (${expr}); if (!p) return null; const v = p.clone().project(__game.camera); return { x: (v.x * 0.5 + 0.5) * innerWidth, y: (-v.y * 0.5 + 0.5) * innerHeight }; })()`);
  const enter = async (kind) => {
    await page.evaluate((kind) => {
      const s = __game.stalls.stalls.find((s) => s.spot.kind === kind);
      const dx = s.camTarget.x - s.use.x, dz = s.camTarget.z - s.use.z;
      __play.debugTeleport(s.use.x - dx * 0.15, s.use.z - dz * 0.15, Math.atan2(dx, dz));
    }, kind);
    await page.waitForTimeout(700);
    const prompt = await page.evaluate(() => document.querySelector("#prompt, .prompt")?.textContent ?? [...document.querySelectorAll(".hud")].map((e) => e.textContent).find((t) => /^E/.test(t ?? "")));
    await page.keyboard.press("KeyE");
    await page.waitForTimeout(1600);
    const on = await page.evaluate(() => !!__play.mini);
    if (!on) bad(`${kind}: E at the counter did not start it (prompt: ${prompt})`);
    return on;
  };
  const leave = async (kind) => {
    await page.keyboard.press("Escape");
    await page.waitForTimeout(900);
    const st = await page.evaluate(() => {
      const g = __game, her = g.her;
      let floating = 0;
      g.scene.traverse((o) => { if (o.visible && o.isMesh && o.geometry?.type === "TorusGeometry" && !o.parent?.isBone) { const p = o.getWorldPosition(new o.position.constructor()); if (p.y > 1.3) floating++; } });
      return { mini: !!__play.mini, visible: her.root.visible, pose: her.pose, capture: g.input.captureMouse, look: !!her.lookTarget, guide: document.querySelector(".hud .line")?.closest(".hud")?.classList.contains("on") ?? false, floating };
    });
    if (st.mini) bad(`${kind}: Esc did not leave`);
    if (!st.visible) bad(`${kind}: she stayed hidden after leaving`);
    if (st.pose !== "none") bad(`${kind}: pose stuck on ${st.pose}`);
    if (st.capture) bad(`${kind}: the mini-game kept the mouse`);
    if (st.guide) bad(`${kind}: the guide line stayed up`);
    if (st.floating) bad(`${kind}: ${st.floating} ring(s) left in the air`);
    console.log(`[tasks] ${kind}: left cleanly`, JSON.stringify(st));
  };

  // Ring toss: toss, and step away while the ring is in the air.
  if (await enter("ringtoss")) {
    const p = await screen(`(() => { const s = __game.stalls.stalls.find(s => s.spot.kind === 'ringtoss'); const pg = s.findAll('peg_')[4]; return pg.getWorldPosition(new pg.position.constructor()); })()`);
    await page.mouse.move(p.x, p.y, { steps: 3 });
    await page.waitForTimeout(250);
    await page.mouse.down(); await page.mouse.up();
    await page.waitForTimeout(200);
    await leave("ringtoss");
  }
  // Goldfish: get a fish on the paper and step away before it's bagged.
  if (await enter("goldfish")) {
    let caught = false;
    for (let i = 0; i < 14 && !caught; i++) {
      const fishPos = `(() => { const f = __play.tub.fish[0]; return f ? f.g.getWorldPosition(new f.g.position.constructor()) : null; })()`;
      const p = await screen(fishPos);
      if (!p) break;
      await page.mouse.move(p.x, p.y, { steps: 4 });
      await page.mouse.down();
      for (let k = 0; k < 5; k++) { await page.waitForTimeout(90); const q = await screen(fishPos); if (q) await page.mouse.move(q.x, q.y, { steps: 2 }); }
      await page.mouse.up();
      await page.waitForTimeout(250);
      caught = await page.evaluate(() => !!__play.mini?.caught);
      if (!caught) await page.waitForTimeout(900);
    }
    if (!caught) console.log("[tasks] goldfish: (never got a fish on the paper to test stepping away with it)");
    await leave("goldfish");
    const hovering = await page.evaluate(() => __play.tub.fish.filter((f) => f.g.position.y > 0.05).length);
    if (hovering) bad(`goldfish: ${hovering} fish left hovering above the water`);
  }
  // Lantern: strike a match and step away while it burns; go back in and check the gust hooks.
  if (await enter("lantern")) {
    await page.mouse.click(960, 540);
    await page.waitForTimeout(400);
    const before = await page.evaluate(() => __game.wind.listeners?.length ?? -1);
    await leave("lantern");
    await enter("lantern");
    await leave("lantern");
    const after = await page.evaluate(() => __game.wind.listeners?.length ?? -1);
    if (after >= 0 && after > before - 1 + 0) console.log(`[tasks] lantern: gust listeners ${before} while playing → ${after} after two visits`);
    if (after >= before) bad(`lantern: gust listeners pile up (${before} → ${after})`);
  }
  // Pickers: browse, step away, come back and take one.
  for (const kind of ["candyapple", "masks"]) {
    if (await enter(kind)) {
      await page.keyboard.press("KeyD"); await page.waitForTimeout(300);
      await leave(kind);
      if (await enter(kind)) {
        await page.keyboard.press("KeyE");
        await page.waitForTimeout(3000);
        const done = await page.evaluate((k) => __play.prog.has(k), kind);
        if (!done) bad(`${kind}: not won after choosing`);
        const st = await page.evaluate(() => ({ mini: !!__play.mini, pose: __game.her.pose, visible: __game.her.root.visible }));
        if (st.mini) bad(`${kind}: did not end after winning`);
        console.log(`[tasks] ${kind}: won`, JSON.stringify(st));
      }
    }
  }
  // The held apple's size vs. the ones on the counter.
  const sz = await page.evaluate(() => {
    const held = __game.carry.find((o) => o.name === "held_apple");
    const s = __game.stalls.stalls.find((s) => s.spot.kind === "candyapple").findAll("apple_").find((a) => a.visible);
    if (!held || !s) return null;
    const V = held.position.constructor;
    return [held.getWorldScale(new V()).x, s.getWorldScale(new V()).x];
  });
  console.log("[tasks] apple scale held/counter", JSON.stringify(sz));
  if (sz && Math.abs(sz[0] / sz[1] - 1) > 0.03) bad(`candyapple: held apple is ${(sz[0] / sz[1]).toFixed(2)}× the size of the ones on the counter`);
  // The mask sits on the side of her head, not over her face.
  const mask = await page.evaluate(() => {
    const her = __game.her, m = __game.carry.find((o) => o.name === "worn_mask");
    if (!m) return null;
    const V = her.position.constructor;
    const h = her.bone("head").getWorldPosition(new V()), p = m.getWorldPosition(new V());
    const f = new V(Math.sin(her.heading), 0, Math.cos(her.heading));
    return { forward: +p.clone().sub(h).dot(f).toFixed(3), up: +(p.y - h.y).toFixed(3) };
  });
  console.log("[tasks] mask vs head", JSON.stringify(mask));
  if (mask && mask.forward > 0.07) bad("masks: the mask sits in front of her face");
} catch (e) { console.error(String(e?.stack ?? e)); fail++; }
const fatal = await page.evaluate(() => window.__fatal).catch(() => null);
if (fatal) { console.error("[fatal]", fatal); fail++; }
for (const e of errors.filter((e) => !/powerPreference|404/.test(e)).slice(0, 20)) console.log(e);
console.log(fail ? `[tasks] FAIL (${fail})` : "[tasks] ok");
await bye(fail ? 1 : 0);
