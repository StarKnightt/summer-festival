// Solid-prop audit: on a grid over the street, promenade and beach, finds every spot where a mesh
// stands in her body volume (0.35–1.5 m above the ground) but no collider keeps her out.
// Usage: node scripts/audit_solid.mjs [--dist]   (exit 1 if anything is found)
import { openGame, waitReady } from "./lib/harness.mjs";
const { page, url, errors, bye } = await openGame({ dist: process.argv.includes("--dist") });
let fail = 0;
try {
  await page.goto(`${url}?play&fresh&tod=day`);
  await waitReady(page);
  await page.waitForTimeout(1500);
  const found = await page.evaluate(async () => {
    const g = __game, THREE_V = g.her.position.constructor;
    const skip = new Set();
    for (const o of [__play.crowd.group, __play.animals?.group, g.her.root, __play.fx.group, __play.cats?.group]) o?.traverse((c) => skip.add(c));
    const meshes = [];
    g.scene.traverse((o) => { if (o.isMesh && o.visible && !skip.has(o) && !o.isInstancedMesh && !o.isSkinnedMesh && !o.isSprite) meshes.push(o); });
    const rc = new __THREE.Raycaster();
    const down = new THREE_V(0, -1, 0);
    const free = (x, z) => {
      const p = { x, z };
      const q = { x, z };
      g.player.resolve(q);
      return Math.hypot(q.x - p.x, q.z - p.z) < 0.02;
    };
    const hits = [];
    const scan = (x0, x1, z0, z1, step) => {
      for (let x = x0; x <= x1; x += step) for (let z = z0; z >= z1; z -= step) {
        if (!free(x, z)) continue;
        const gy = g.town.groundY(x, z);
        rc.set(new THREE_V(x, gy + 1.5, z), down);
        rc.far = 1.32;
        const h = rc.intersectObjects(meshes, false)[0];
        if (h) { let n = h.object; let name = n.name; while (!name && n.parent) { n = n.parent; name = n.name; } hits.push({ x: +x.toFixed(2), z: +z.toFixed(2), y: +(h.point.y - gy).toFixed(2), name }); }
      }
    };
    scan(-4.4, 4.4, 10, -100, 0.3);
    scan(-29.6, 29.6, -100.6, -125, 0.35);
    // People standing still must not be inside anything either.
    for (const n of __play.crowd.npcs) {
      if (n.mode === "stroll" || n.mode === "kid" || n.mode === "keeper") continue;
      if (/^sit/.test(n.cur?.getClip().name ?? "")) continue; // seated on a bench, step or wall: meant to be there
      const gy = g.town.groundY(n.pos.x, n.pos.z);
      for (const [dx, dz] of [[0, 0], [0.18, 0], [-0.18, 0], [0, 0.18], [0, -0.18]]) {
        rc.set(new THREE_V(n.pos.x + dx, gy + 1.5, n.pos.z + dz), down);
        rc.far = 1.32;
        const h = rc.intersectObjects(meshes, false)[0];
        if (h) { let o = h.object, name = o.name; while (!name && o.parent) { o = o.parent; name = o.name; } hits.push({ x: +n.pos.x.toFixed(2), z: +n.pos.z.toFixed(2), y: +(h.point.y - gy).toFixed(2), name: `NPC(${n.v},${n.mode}) in ${name}` }); break; }
      }
    }
    return hits;
  });
  // Cluster neighbouring hits.
  const clusters = [];
  for (const h of found) {
    const c = clusters.find((c) => c.name === h.name && Math.abs(c.x - h.x) < 1.6 && Math.abs(c.z - h.z) < 1.6);
    if (c) { c.n++; c.x0 = Math.min(c.x0, h.x); c.x1 = Math.max(c.x1, h.x); c.z0 = Math.min(c.z0, h.z); c.z1 = Math.max(c.z1, h.z); c.y = Math.max(c.y, h.y); }
    else clusters.push({ name: h.name, x: h.x, z: h.z, x0: h.x, x1: h.x, z0: h.z, z1: h.z, y: h.y, n: 1 });
  }
  for (const c of clusters) console.log(`[solid] walk-through: ${c.name || "(unnamed)"} x ${c.x0}..${c.x1} z ${c.z1}..${c.z0} top ${c.y} m (${c.n} pts)`);
  fail = clusters.length;
} catch (e) { console.error(String(e?.stack ?? e)); fail++; }
for (const e of errors.filter((e) => !/powerPreference|404/.test(e)).slice(0, 10)) console.log(e);
console.log(fail ? `[solid] FAIL (${fail})` : "[solid] ok");
await bye(fail ? 1 : 0);
