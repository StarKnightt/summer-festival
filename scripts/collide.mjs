// Beach collisions: she can't walk into the rocks, the boats (bow included) or the low walls by
// the steps, and open sand next to a boat (which the old axis-aligned box blocked) is walkable.
// Also checks T cycles the time of day.  Usage: node scripts/collide.mjs [--dist]
import { openGame, waitReady } from "./lib/harness.mjs";

const { page, url, errors, bye } = await openGame({ dist: process.argv.includes("--dist") });
let fail = 0;
const bad = (m) => { console.log("[collide] FAIL:", m); fail++; };
try {
  await page.goto(`${url}?play&fresh&tod=day`);
  await waitReady(page);
  // Walk straight at something for a while; report how close she got to its centre.
  const walkAt = async (from, heading, ms) => {
    await page.evaluate(([x, z, h]) => { __play.debugTeleport(x, z, h); __game.rig.yaw = h + Math.PI; }, [...from, heading]);
    await page.waitForTimeout(300);
    await page.keyboard.down("KeyW");
    await page.waitForTimeout(ms);
    await page.keyboard.up("KeyW");
    await page.waitForTimeout(200);
    return page.evaluate(() => ({ x: __game.her.position.x, z: __game.her.position.z }));
  };
  const cols = await page.evaluate(() => __game.player.colliders.filter((c) => c.circle || c.ob).map((c) => ({ circle: c.circle, ob: c.ob })));
  const rocks = cols.filter((c) => c.circle).map((c) => c.circle);
  const boats = cols.filter((c) => c.ob).map((c) => c.ob);
  console.log(`[collide] ${rocks.length} rocks, ${boats.length} boats`);
  // Rocks: approach the three nearest the steps from 4 m off.
  rocks.sort((a, b) => Math.hypot(a.x, a.z + 104) - Math.hypot(b.x, b.z + 104));
  for (const r of rocks.slice(0, 3)) {
    const h = Math.atan2(r.x - 0, 0) > 0 ? Math.PI / 2 : -Math.PI / 2;
    const p = await walkAt([r.x - Math.sin(h) * (r.r + 3), r.z], h, 4500);
    const d = Math.hypot(p.x - r.x, p.z - r.z);
    if (d < r.r + 0.2) bad(`walked into a rock (centre ${d.toFixed(2)} m, radius ${r.r.toFixed(2)})`);
    else console.log(`[collide] rock r=${r.r.toFixed(2)}: stopped ${(d - r.r).toFixed(2)} m from its surface`);
  }
  // Boats: along the hull axis into the bow, and across the middle.
  for (const b of boats) {
    const ax = Math.sin(b.ang), az = Math.cos(b.ang);
    const p = await walkAt([b.x + ax * (b.hz + 3), b.z + az * (b.hz + 3)], b.ang + Math.PI, 4500);
    const lz = (p.x - b.x) * ax + (p.z - b.z) * az;
    if (lz < b.hz + 0.15) bad(`walked into a boat's end (${lz.toFixed(2)} m from centre along the hull, half-length ${b.hz})`);
    const q = await walkAt([b.x + az * 3, b.z - ax * 3], b.ang - Math.PI / 2, 4500);
    const lx = (q.x - b.x) * az - (q.z - b.z) * ax;
    if (Math.abs(lx) < b.hx + 0.15) bad(`walked into a boat's side (${lx.toFixed(2)})`);
    // Open sand off the hull's corner: stand there; she must not be pushed away.
    const cx = b.x + Math.cos(b.ang) * 1.6 - Math.sin(b.ang) * 1.9, cz = b.z - Math.sin(b.ang) * 1.6 - Math.cos(b.ang) * 1.9;
    await page.evaluate(([x, z]) => __play.debugTeleport(x, z, 0), [cx, cz]);
    await page.waitForTimeout(400);
    const s = await page.evaluate(() => ({ x: __game.her.position.x, z: __game.her.position.z }));
    if (Math.hypot(s.x - cx, s.z - cz) > 0.05) bad(`open sand by a boat pushed her ${Math.hypot(s.x - cx, s.z - cz).toFixed(2)} m`);
    else console.log("[collide] boat: blocked at bow and side, open sand by its corner is free");
  }
  // The low walls beside the steps, from the beach.
  const w = await walkAt([5, -103], -Math.PI / 2, 4000);
  if (w.x < 2.68 + 0.2) bad(`walked through the low wall by the steps (x ${w.x.toFixed(2)})`);
  else console.log(`[collide] step wall: stopped at x ${w.x.toFixed(2)}`);
  // T cycles the time of day.
  const seen = [await page.evaluate(() => __game.tod.preset)];
  for (let i = 0; i < 4; i++) { await page.keyboard.press("KeyT"); await page.waitForTimeout(150); seen.push(await page.evaluate(() => __game.tod.preset)); }
  console.log("[collide] T:", seen.join(" → "));
  if (seen[0] !== seen[4] || new Set(seen).size !== 4) bad("T does not cycle through the four times of day");
} catch (e) { console.error(String(e?.stack ?? e)); fail++; }
for (const e of errors.filter((e) => !/powerPreference|404/.test(e)).slice(0, 10)) console.log(e);
console.log(fail ? `[collide] FAIL (${fail})` : "[collide] ok");
await bye(fail ? 1 : 0);
