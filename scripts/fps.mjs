// Measures frame rate on the production build at 1920×1080: a walk down the festival street at
// sunset, standing among the stalls at night, and the fireworks finale. Two modes:
//   vsync    — the frame rate a player sees (capped by the display refresh)
//   uncapped — vsync and the frame limiter off, to show the headroom on this GPU
// Usage: node scripts/fps.mjs [--uncapped]
import { openGame, waitReady } from "./lib/harness.mjs";

const uncapped = process.argv.includes("--uncapped");
const { page, url, errors, bye } = await openGame({ dist: true, extraArgs: uncapped ? ["--disable-gpu-vsync", "--disable-frame-rate-limit"] : [] });
const stats = (ms) => {
  const s = [...ms].sort((a, b) => a - b);
  const avg = s.reduce((a, b) => a + b, 0) / s.length;
  return { fps: +(1000 / avg).toFixed(1), avgMs: +avg.toFixed(2), p95Ms: +s[Math.floor(s.length * 0.95)].toFixed(2), p99Ms: +s[Math.floor(s.length * 0.99)].toFixed(2), frames: s.length };
};
const measure = async (secs) => {
  await page.evaluate(() => { __game.frameMs.length = 0; });
  await page.waitForTimeout(secs * 1000);
  return stats(await page.evaluate(() => __game.frameMs.slice(-1200)));
};
const out = {};
try {
  await page.goto(`${url}?play&fresh&tod=sunset`);
  await waitReady(page);
  await page.waitForTimeout(2500);
  // Walk down the street (held W, camera follows).
  await page.keyboard.down("KeyW");
  out.walkSunset = await measure(8);
  await page.keyboard.up("KeyW");
  await page.evaluate(() => { __game.setTod("night", true); __play.debugTeleport(0, -40); });
  await page.waitForTimeout(1500);
  out.stallsNight = await measure(6);
  await page.evaluate(() => { __play.debugComplete(); __play.debugTeleport(0.5, -110); });
  await page.waitForTimeout(9000);
  out.fireworks = await measure(10);
  out.gpu = await page.evaluate(() => window.__gpu);
  console.log(`[fps] ${uncapped ? "uncapped" : "vsync"}`, JSON.stringify(out, null, 1));
} catch (e) { console.error(String(e)); }
for (const e of errors.filter((e) => /pageerror/.test(e))) console.log(e);
await bye(0);
