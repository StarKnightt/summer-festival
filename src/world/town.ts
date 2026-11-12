import * as THREE from "three/webgpu";
import { mergeGeometries as mg, mergeVertices } from "three/addons/utils/BufferGeometryUtils.js";
import { RoundedBoxGeometry } from "three/addons/geometries/RoundedBoxGeometry.js";
import { Builder, rng, range, pick, vary, solid, sagCurve } from "./geo";
import { STREET, SHORE, GATES, STALLS, stallX, STALL_W } from "./layout";
import { ToonMaterial, lanternSwing, paperGlow, windCloth, type LightSpot } from "../render/toon";
import { seawallMaterial, pavingMaterial, stoneMaterial, roofMaterial, sandMaterial, plasterMaterial, woodMaterial, latticeMaterial } from "../render/surfaces";
import { windowGlow, lanternPaper, noOutline, norenMaterial, shopInterior } from "../render/townMats";

/**
 * The street, its houses, the shore, and everything strung overhead. Static geometry is merged
 * per material (a handful of draw calls); lanterns are instanced and swing in the wind.
 */

/**
 * A blocker on the ground plane. The AABB (x0..x1, z0..z1) is the shape for plain boxes and the
 * broad bound for the others: `circle` (rocks) or `ob`, an oriented box (beached boats).
 */
export interface Collider {
  x0: number; x1: number; z0: number; z1: number; y1?: number;
  circle?: { x: number; z: number; r: number };
  ob?: { x: number; z: number; hx: number; hz: number; ang: number };
}

export interface Town {
  group: THREE.Group;
  colliders: Collider[];
  lights: LightSpot[];
  /** Where the eaves are along both sides: wind chimes hang there. */
  chimes: THREE.Vector3[];
  /** Height of the walkable ground at (x, z). */
  groundY(x: number, z: number): number;
  /** Surface under foot for footsteps. */
  surface(x: number, z: number): "stone" | "wood" | "sand";
}

const WOOD = ["#5a3b2a", "#6a4430", "#4c3226", "#73503a"];
const DARKWOOD = ["#3a2820", "#33241d", "#2d201b"];
const PLASTER = ["#efe3cc", "#e9d6b9", "#f2e8d6", "#e2d2bd", "#d9cdb8"];
const TIN = ["#6d98a3", "#8eb3ae", "#b7c9c2", "#9a8f86"];
const ROOF = ["#4e5868", "#5a6374", "#6c5650", "#435062", "#5f6b6b"];
const NOREN = ["#2f4a7a", "#7a2f3a", "#3f6a5a", "#a8562a", "#2b2b3a", "#5a3a7a"];

/** What a shop sells: wall colours and the palette of its goods. */
const SHOPS = [
  { back: "#e8c896", side: "#c99a66", goods: ["#d84b3a", "#f0c040", "#f4efe6", "#e88aa0", "#7ab0d8"], shape: "box" }, // sweets & toys
  { back: "#e2c9a0", side: "#b88a5a", goods: ["#5f7fa8", "#c9b89a", "#8a5a3a", "#e9e2d2", "#3f5f5a"], shape: "pot" }, // pottery
  { back: "#ecd2a4", side: "#c8955c", goods: ["#a8322a", "#2f4a7a", "#e0a040", "#5a8a5a", "#f2e6cc"], shape: "cloth" }, // fabric & fans
  { back: "#e6cfa0", side: "#b98c5e", goods: ["#6a8a3a", "#c8562a", "#e8c050", "#8a3a4a", "#d8d0b0"], shape: "jar" }, // pickles & tea
] as const;
type Shop = (typeof SHOPS)[number];

/** One item of stock sitting on a surface at y (centre x, z; footprint ~sz). */
function goods(b: Builder, r: () => number, k: Shop, x: number, y: number, z: number, sz: number) {
  const c = vary(pick(r, k.goods as unknown as string[]), r, 0.08);
  const roll = r();
  if (k.shape === "pot" || (roll < 0.3 && k.shape !== "cloth")) {
    const h = sz * range(r, 0.7, 1.3);
    b.cyl(sz * 0.38, sz * 0.48, h, c, x, y + h / 2, z, 10);
    if (r() < 0.5) b.cyl(sz * 0.2, sz * 0.36, h * 0.25, c, x, y + h + h * 0.12, z, 10);
  } else if (k.shape === "jar" || roll < 0.5) {
    const h = sz * range(r, 1.0, 1.6);
    b.cyl(sz * 0.32, sz * 0.32, h, c, x, y + h / 2, z, 8);
    b.cyl(sz * 0.34, sz * 0.34, h * 0.12, "#3a2a20", x, y + h + h * 0.06, z, 8);
  } else if (k.shape === "cloth") {
    // Folded cloth stacks.
    let yy = y;
    for (let i = 0, n = 2 + Math.floor(r() * 3); i < n; i++) {
      const hh = sz * 0.18;
      b.box(sz, hh, sz * 0.8, vary(pick(r, k.goods as unknown as string[]), r, 0.08), x, yy + hh / 2, z);
      yy += hh;
    }
  } else {
    const h = sz * range(r, 0.6, 1.1);
    b.box(sz * 0.9, h, sz * 0.8, c, x, y + h / 2, z, range(r, -0.2, 0.2));
    if (r() < 0.4) b.box(sz * 0.92, h * 0.12, sz * 0.82, "#f4efe6", x, y + h * 0.7, z);
  }
}

/** Local frame of a house: facade plane at z = 0 facing +z, width along +x from 0 to w. */
interface HouseOut { wood: Builder; plaster: Builder; roof: Builder; paper: Builder; lattice: Builder; shop: Builder; noren: { x: number; w: number; color: string }[]; lanterns: THREE.Vector3[]; chimes: THREE.Vector3[] }

function house(w: number, r: () => number, o: HouseOut, depth = 7.5, tall = false): void {
  const { wood, plaster, roof, paper, shop } = o;
  const H1 = 3.0, H2 = tall ? 2.9 : 2.5, H = H1 + H2;
  const wd = pick(r, WOOD), dk = pick(r, DARKWOOD);
  const seaside = r() < 0.3;
  const wall = seaside ? pick(r, TIN) : pick(r, PLASTER);
  const roofC = pick(r, ROOF);
  // Body: the upper floor over the full depth; the ground floor set back behind the open shop.
  const D = 1.7;
  const wc = vary(wall, r);
  plaster.box(w, H - H1, depth, wc, w / 2, H1 + (H - H1) / 2, -depth / 2);
  plaster.box(w, H1, depth - D, wc, w / 2, H1 / 2, -D - (depth - D) / 2);
  // Plinth.
  wood.box(w + 0.02, 0.22, 0.12, "#5c5a58", w / 2, 0.11, 0.03);
  // Posts and beams.
  const posts = Math.max(2, Math.round(w / 1.8) + 1);
  for (let i = 0; i < posts; i++) {
    const x = 0.06 + (i / (posts - 1)) * (w - 0.12);
    wood.box(0.16, H, 0.16, wd, x, H / 2, 0.05);
  }
  wood.box(w, 0.2, 0.2, wd, w / 2, H1, 0.08);
  wood.box(w, 0.16, 0.18, wd, w / 2, H - 0.08, 0.06);

  // Ground floor: an open shop. A lamp-lit recess with shelves of goods, a display platform at
  // the front, a noren across the top of the opening and a signboard over the beam.
  const o0 = 0.3, o1 = w - 0.3, ow = o1 - o0, oh = H1 - 0.3, cx = w / 2;
  for (const x of [0.15, w - 0.15]) wood.box(0.3, H1, D, wd, x, H1 / 2, -D / 2);
  wood.box(w, 0.32, 0.12, wd, cx, H1 - 0.16, 0.03);
  const kind = pick(r, SHOPS);
  shop.box(ow, oh, 0.05, kind.back, cx, oh / 2, -D + 0.03);
  for (const x of [o0 + 0.03, o1 - 0.03]) shop.box(0.05, oh, D, kind.side, x, oh / 2, -D / 2);
  shop.box(ow, 0.05, D, "#9a6e48", cx, oh, -D / 2);
  shop.box(ow, 0.14, D, "#b08860", cx, 0.07, -D / 2);
  // Shelves along the back wall, stocked.
  const shelves = [0.7, 1.22, 1.74, 2.2].filter((y) => y < oh - 0.3);
  for (const y of shelves) {
    shop.box(ow - 0.2, 0.04, 0.34, "#8a5e3a", cx, y, -D + 0.22);
    let x = o0 + 0.18;
    while (x < o1 - 0.25) {
      const sz = range(r, 0.12, 0.24);
      goods(shop, r, kind, x + sz / 2, y + 0.02, -D + 0.22 + range(r, -0.05, 0.05), sz);
      x += sz + range(r, 0.03, 0.1);
    }
  }
  // Display platform out front with goods on it, leaving a way in.
  const pw = Math.min(ow * 0.42, 2.2);
  for (const px of [o0 + pw / 2 + 0.1, o1 - pw / 2 - 0.1]) {
    if (r() < 0.25) continue;
    wood.box(pw, 0.42, 0.6, "#8a6444", px, 0.21, -0.42);
    let x = px - pw / 2 + 0.12;
    while (x < px + pw / 2 - 0.18) {
      const sz = range(r, 0.16, 0.3);
      goods(shop, r, kind, x + sz / 2, 0.42, -0.42 + range(r, -0.12, 0.12), sz);
      x += sz + range(r, 0.04, 0.12);
    }
  }
  // A paper lamp inside lights it; sometimes one at the door too.
  o.lanterns.push(new THREE.Vector3(cx + range(r, -0.6, 0.6), oh - 0.32, -D / 2 - 0.1));
  if (r() < 0.5) o.lanterns.push(new THREE.Vector3(o0 + 0.15, H1 - 0.55, 0.45));
  o.noren.push({ x: cx, w: Math.min(ow - 0.2, range(r, 2.2, 3.4)), color: pick(r, NOREN) });
  wood.box(Math.min(ow, 1.6), 0.38, 0.06, pick(r, ["#2b2018", "#7a5a32", "#efe2c6"]), cx, H1 + 0.38, 0.17);
  // Upper floor windows with lattice over shoji paper.
  const nw = w > 5 ? 2 : 1;
  for (let k = 0; k < nw; k++) {
    const ww = Math.min(1.7, w / nw - 0.7);
    const cx = (w / nw) * (k + 0.5);
    const cy = H1 + H2 * 0.52;
    paper.box(ww, 1.0, 0.03, "#f4e8cf", cx, cy, 0.01);
    for (let x = -ww / 2; x <= ww / 2 + 0.01; x += ww / 6) wood.box(0.035, 1.04, 0.05, dk, cx + x, cy, 0.05);
    for (const y of [-0.5, 0, 0.5]) wood.box(ww + 0.06, 0.035, 0.05, dk, cx, cy + y, 0.05);
    if (r() < 0.4) {
      // Little balcony rail.
      wood.box(ww + 0.5, 0.06, 0.5, wd, cx, cy - 0.62, 0.28);
      for (let x = -ww / 2 - 0.2; x <= ww / 2 + 0.21; x += 0.12) wood.box(0.03, 0.42, 0.03, wd, cx + x, cy - 0.38, 0.5);
      wood.box(ww + 0.5, 0.05, 0.05, wd, cx, cy - 0.16, 0.5);
    }
  }
  // Ground-floor eave (hisashi), tiled.
  const ang = 0.38;
  roof.add(new THREE.BoxGeometry(w + 0.3, 0.08, 1.0), vary(roofC, r, 0.05), w / 2, H1 + 0.32, 0.45, ang);
  wood.box(w + 0.3, 0.06, 0.08, dk, w / 2, H1 + 0.13, 0.94);
  o.chimes.push(new THREE.Vector3(range(r, 0.6, w - 0.6), H1 + 0.05, 0.75));
  // Main gable roof, ridge parallel to the street.
  const over = 0.7;
  const rise = 1.7;
  const half = depth / 2 + over;
  const slope = Math.hypot(half, rise);
  const a = Math.atan2(rise, half);
  const rc = vary(roofC, r, 0.05);
  roof.add(new THREE.BoxGeometry(w + 0.5, 0.12, slope), rc, w / 2, H + rise / 2, over - half / 2 + 0.0, a);
  roof.add(new THREE.BoxGeometry(w + 0.5, 0.12, slope), rc, w / 2, H + rise / 2, -depth - over + half / 2, -a);
  roof.box(w + 0.6, 0.22, 0.3, new THREE.Color(rc).multiplyScalar(0.8), w / 2, H + rise + 0.06, -depth / 2);
  // Gable end walls.
  const tri = new THREE.Shape([new THREE.Vector2(-depth / 2, 0), new THREE.Vector2(depth / 2, 0), new THREE.Vector2(0, rise)]);
  for (const x of [0.02, w - 0.02]) {
    plaster.add(new THREE.ExtrudeGeometry(tri, { depth: 0.04, bevelEnabled: false }), vary(wall, r), x - 0.02, H, -depth / 2, 0, Math.PI / 2, 0);
  }
}

export function buildTown(): Town {
  const group = new THREE.Group();
  group.name = "town";
  const colliders: Collider[] = [];
  const lights: LightSpot[] = [];
  const chimes: THREE.Vector3[] = [];
  const r = rng(20260712);

  const wood = new Builder(), plaster = new Builder(), roof = new Builder(), paper = new Builder(), lattice = new Builder(), shop = new Builder();
  const houseLanterns: THREE.Vector3[] = [];
  const noren: { m: THREE.Matrix4; x: number; w: number; color: string }[] = [];

  /** Places a house built in its local frame. */
  const place = (m: THREE.Matrix4, w: number, tall = false, depth = 7.5) => {
    const o: HouseOut = { wood: new Builder(), plaster: new Builder(), roof: new Builder(), paper: new Builder(), lattice: new Builder(), shop: new Builder(), noren: [], lanterns: [], chimes: [] };
    house(w, r, o, depth, tall);
    for (const [src, dst] of [[o.wood, wood], [o.plaster, plaster], [o.roof, roof], [o.paper, paper], [o.lattice, lattice], [o.shop, shop]] as const) {
      if (src.empty) continue;
      const g = src.build();
      g.applyMatrix4(m);
      dst.addKeep(g);
    }
    for (const n of o.noren) noren.push({ m, ...n });
    for (const l of o.lanterns) houseLanterns.push(l.applyMatrix4(m));
    for (const c of o.chimes) chimes.push(c.applyMatrix4(m));
  };

  // ---- the two sides of the street
  for (const side of [-1, 1] as const) {
    let z = STREET.zStart + 2;
    let i = 0;
    while (z > STREET.zEnd + 2) {
      const w = Math.min(range(r, 5.5, 8.5), z - (STREET.zEnd + 2));
      if (w < 3) break;
      const z0 = z, z1 = z - w;
      // Facade faces the street: left side faces +X, right side faces −X.
      const m = new THREE.Matrix4();
      if (side < 0) m.makeRotationY(Math.PI / 2).setPosition(-STREET.half, 0, z0);
      else m.makeRotationY(-Math.PI / 2).setPosition(STREET.half, 0, z1);
      place(m, w, r() < 0.25);
      colliders.push({ x0: side < 0 ? -STREET.half - 8 : STREET.half, x1: side < 0 ? -STREET.half : STREET.half + 8, z0: z1, z1: z0 });
      z = z1;
      i++;
      // An alley every few houses, closed by a fence a few metres in.
      if (i % 3 === 0 && z > STREET.zEnd + 10) {
        const gap = range(r, 1.4, 2.0);
        const fx = side * (STREET.half + 3.2);
        for (let k = 0; k < 9; k++) wood.box(0.12, 1.9, gap / 9 - 0.02, "#5a4634", fx, 0.95, z - (k + 0.5) * (gap / 9));
        wood.box(0.08, 0.08, gap, "#4a3a2c", fx, 1.6, z - gap / 2);
        colliders.push({ x0: side < 0 ? fx - 0.2 : fx, x1: side < 0 ? fx : fx + 0.2, z0: z - gap, z1: z });
        // Barrels and crates in the alley.
        wood.cyl(0.32, 0.3, 0.8, "#6b4a30", side * (STREET.half + 1.2), 0.4, z - gap * 0.3, 12);
        wood.box(0.6, 0.45, 0.6, "#8a6a48", side * (STREET.half + 2.0), 0.22, z - gap * 0.6, 0.3);
        z -= gap;
      }
    }
  }
  // Row across the top of the street (behind the start), and the sea-facing rows at the shore.
  {
    const m = new THREE.Matrix4().makeRotationY(Math.PI).setPosition(STREET.half + 0.4, 0, STREET.zStart + 2.5);
    place(m, STREET.half * 2 + 0.8, true);
    colliders.push({ x0: -20, x1: 20, z0: STREET.zStart + 2.4, z1: STREET.zStart + 12 });
    for (const side of [-1, 1]) {
      let x = side * (STREET.half + 0.2);
      for (let k = 0; k < 5; k++) {
        const w = range(r, 6, 8.5);
        const xa = side < 0 ? x - w : x;
        const mm = new THREE.Matrix4().makeRotationY(Math.PI).setPosition(xa + w, 0, -94.6);
        // Facade at z = −94.6 faces −Z (the sea).
        mm.makeRotationY(Math.PI).setPosition(xa + w, 0, -94.6);
        place(mm, w, r() < 0.4);
        colliders.push({ x0: xa, x1: xa + w, z0: -94.6, z1: -86 });
        x = side < 0 ? xa : xa + w;
      }
    }
  }

  // ---- ground: street paving, gutters, promenade, sea wall, steps, beach
  // The paving stops exactly where the promenade strip starts (z = PROMO_Z0): both lie at y = 0,
  // so any overlap z-fights and the two tile patterns flicker over each other as the camera moves.
  const PROMO_Z0 = -94.6;
  const groundB = new THREE.PlaneGeometry(STREET.half * 2 + 6, STREET.zStart + 4 - PROMO_Z0, 1, 1).rotateX(-Math.PI / 2);
  groundB.translate(0, 0, (STREET.zStart + 4 + PROMO_Z0) / 2);
  const street = solid(groundB, pavingMaterial(), false);
  group.add(street);
  for (const side of [-1, 1]) {
    wood.box(0.28, 0.04, STREET.zStart - STREET.zEnd, "#4c4a4c", side * (STREET.half - 0.32), 0.012, (STREET.zStart + STREET.zEnd) / 2);
  }
  // Promenade (wide stone strip along the town front) and its sea wall.
  const promo = new THREE.PlaneGeometry(90, 5.4).rotateX(-Math.PI / 2).translate(0, 0.0, PROMO_Z0 - 2.7);
  group.add(solid(promo, stoneMaterial("#a39a8e", 1.2), false));
  // Sea wall, coping and steps: dressed stone with rounded, worn edges (seawallMaterial carves
  // the blocks and weathering; the vertex colour tells wall, coping and steps apart).
  const stone = new Builder();
  const rb = (w: number, h: number, d: number, rad: number) => new RoundedBoxGeometry(w, h, d, 2, Math.min(rad, w / 2.01, h / 2.01, d / 2.01));
  const wallC = "#a59c90", copeC = "#b8b0a3", stepC = "#b3aa9d";
  for (const side of [-1, 1]) {
    const x0 = side * 2.2, x1 = side * 45;
    const cx = (x0 + x1) / 2, w = Math.abs(x1 - x0);
    stone.add(rb(w, 2.2, 0.5, 0.05), wallC, cx, -0.55, -100.2);
    stone.add(rb(w, 0.5, 0.35, 0.04), wallC, cx, 0.25, -100.05);
    // Coping: separate dressed blocks, each sitting a hair differently.
    const xa = Math.min(x0, x1), xb = Math.max(x0, x1);
    for (let x = xa; x < xb - 0.3; ) {
      const len = Math.min(range(r, 1.05, 1.5), xb - x);
      stone.add(rb(len - 0.025, 0.24, 0.72, 0.06), vary(copeC, r, 0.12), x + len / 2, 0.62 + range(r, -0.008, 0.008), -100.1, range(r, -0.006, 0.006), range(r, -0.008, 0.008), 0);
      x += len;
    }
    colliders.push({ x0: xa, x1: xb, z0: -100.5, z1: -99.8 });
  }
  // Steps down to the beach, flanked by low walls with standing lanterns.
  const NS = 8;
  for (let k = 0; k < NS; k++) {
    const y = -((k + 1) / NS) * 1.6;
    stone.add(rb(4.4, 0.22, 0.54, 0.05), vary(stepC, r, 0.1), 0, y + 0.1, -100.25 - k * 0.5);
    // The riser under each tread stands on the sand and stops under the tread (so these are real
    // steps going down, not one block at promenade height).
    stone.add(rb(4.36, y + 1.95, 0.5, 0.03), wallC, 0, (y - 1.95) / 2, -100.25 - k * 0.5 - 0.02);
  }
  for (const side of [-1, 1]) {
    stone.add(rb(0.45, 0.9, 4.6, 0.05), wallC, side * 2.42, -0.6, -102.0);
    stone.add(rb(0.5, 0.12, 4.65, 0.04), copeC, side * 2.42, -0.1, -102.0);
    stone.add(rb(0.45, 0.4, 0.45, 0.05), copeC, side * 2.42, 0.55, -99.8);
    houseLanterns.push(new THREE.Vector3(side * 2.42, 1.15, -99.8));
    // The low walls beside the steps are solid.
    colliders.push({ x0: side < 0 ? -2.68 : 2.18, x1: side < 0 ? -2.18 : 2.68, z0: -104.35, z1: -100.4 });
  }
  group.add(solid(stone.build(), seawallMaterial()));
  // Beach: flat, then sloping gently into the sea.
  const beachG = new THREE.PlaneGeometry(140, 80, 70, 40).rotateX(-Math.PI / 2);
  const bp = beachG.attributes.position as THREE.BufferAttribute;
  for (let i = 0; i < bp.count; i++) {
    const z = bp.getZ(i) - 140;
    bp.setZ(i, z);
    bp.setY(i, beachHeight(bp.getX(i), z));
  }
  beachG.computeVertexNormals();
  group.add(solid(beachG, sandMaterial(SHORE.waterZ), false));
  colliders.push({ x0: -70, x1: -30, z0: -200, z1: -100 }, { x0: 30, x1: 70, z0: -200, z1: -100 });

  // Rocks and a couple of beached boats to frame the beach (close, so nothing reads as far).
  // Rounded, weathered boulders (smooth noise-displaced spheres settled into the sand), some in
  // small clusters; every one is solid.
  const rocks = new Builder();
  const rockSpots: [number, number, number][] = [];
  for (let k = 0; k < 9; k++) {
    const side = k % 2 ? 1 : -1;
    const x = side * range(r, 15, 29), z = range(r, -106, -128);
    rockSpots.push([x, z, range(r, 1.0, 2.1)]);
    // Smaller companions around some of them.
    const nb = Math.floor(range(r, 0, 3));
    for (let i = 0; i < nb; i++) {
      const a = range(r, 0, Math.PI * 2), d = range(r, 1.8, 3.0);
      rockSpots.push([x + Math.cos(a) * d, z + Math.sin(a) * d, range(r, 0.35, 0.8)]);
    }
  }
  for (const [x, z, sz] of rockSpots) {
    const sx = sz * range(r, 0.95, 1.35), sy = sz * range(r, 0.55, 0.8), szz = sz * range(r, 0.85, 1.15);
    const ry = range(r, 0, Math.PI * 2);
    const g = rockGeometry(r, sx, sy, szz);
    g.applyMatrix4(new THREE.Matrix4().makeRotationY(ry).setPosition(x, beachHeight(x, z) - sy * 0.22, z));
    rocks.addKeep(g);
    const rad = Math.max(sx, szz) * 0.92;
    colliders.push({ x0: x - rad, x1: x + rad, z0: z - rad, z1: z + rad, circle: { x, z, r: rad } });
  }
  for (const [x, z, ry] of [[-9, -109, 0.5], [11, -111, -0.3]]) {
    // A small wooden fishing boat hauled up on the sand, heeled over on its bilge.
    const b = new Builder();
    b.addKeep(boatHull(false)).addKeep(boatHull(true));
    for (const tz of [-0.75, 0.55]) b.box(1.16, 0.045, 0.24, "#8a6a48", 0, 0.4, tz);
    b.box(0.5, 0.04, 0.5, "#8a6a48", 0, 0.47, 1.62);
    // A pair of oars lying across the thwarts.
    b.cyl(0.022, 0.022, 2.6, "#b89a6c", 0.22, 0.44, -0.1, 8, Math.PI / 2, 0, 0.06);
    b.box(0.13, 0.02, 0.5, "#b89a6c", 0.3, 0.44, 1.28, 0.06);
    const g = b.build();
    g.applyMatrix4(new THREE.Matrix4().makeRotationZ(ry > 0 ? 0.14 : -0.14));
    g.applyMatrix4(new THREE.Matrix4().makeRotationY(ry).setPosition(x, beachHeight(x, z) - 0.04, z));
    rocks.addKeep(g);
    // The hull as an oriented box that turns with the boat (bow included), not an axis-aligned
    // box that both missed its ends and blocked open sand at its corners.
    const hx = 0.74, hz = 2.35;
    const ex = Math.abs(Math.cos(ry)) * hx + Math.abs(Math.sin(ry)) * hz, ez = Math.abs(Math.sin(ry)) * hx + Math.abs(Math.cos(ry)) * hz;
    colliders.push({ x0: x - ex, x1: x + ex, z0: z - ez, z1: z + ez, ob: { x, z, hx, hz, ang: ry } });
  }
  group.add(solid(rocks.build(), new ToonMaterial({ vertexColors: true, paint: 0.8 })));

  // ---- lantern strings: zig-zag across the street
  const strings: THREE.Vector3[][] = [];
  const stringLanterns: { p: THREE.Vector3; red: boolean }[] = [];
  const zz0 = STREET.zStart - 4, zz1 = STREET.zEnd + 3;
  let flip = 1;
  for (let z = zz0; z > zz1; z -= 5.2) {
    const a = new THREE.Vector3(-STREET.half + 0.2, STREET.lanternY + 0.3, z);
    const b = new THREE.Vector3(STREET.half - 0.2, STREET.lanternY + 0.3, z - 2.6 * flip);
    flip = -flip;
    const pts = sagCurve(a, b, 0.55, 20);
    strings.push(pts);
    const n = 8;
    for (let k = 1; k <= n; k++) {
      const t = k / (n + 1);
      const p = new THREE.Vector3().lerpVectors(a, b, t).add(new THREE.Vector3(0, -0.55 * 4 * t * (1 - t), 0));
      stringLanterns.push({ p, red: k % 2 === 0 });
    }
  }
  const wire = new Builder();
  for (const pts of strings) wire.add(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 24, 0.008, 4), "#2a2420");
  const wires = solid(wire.build(), new ToonMaterial({ vertexColors: true, paint: 0 }), false);
  noOutline(wires.material as THREE.NodeMaterial);
  group.add(wires);

  // String lanterns (instanced, swinging) + house lanterns.
  const lgeo = lanternGeometry();
  const lmat = lanternPaper();
  lanternSwing(lmat, 1);
  const all = [...stringLanterns.map((l) => ({ p: l.p, s: 1, c: l.red ? "#d84b33" : "#f3e7cf" })), ...houseLanterns.map((p) => ({ p, s: 1.25, c: "#f1e2c4" }))];
  const lim = new THREE.InstancedMesh(lgeo, lmat, all.length);
  const m4 = new THREE.Matrix4();
  all.forEach((l, i) => {
    m4.makeScale(l.s, l.s, l.s).setPosition(l.p);
    lim.setMatrixAt(i, m4);
    lim.setColorAt(i, new THREE.Color(l.c));
    lights.push({ x: l.p.x, y: l.p.y, z: l.p.z, r: 1.0, g: 0.62, b: 0.32, k: 0.55 * l.s, reach: 5.5 });
  });
  lim.castShadow = false;
  lim.frustumCulled = false;
  lim.name = "lanterns";
  group.add(lim);

  // ---- noren curtains (sway)
  for (const n of noren) {
    const g = new THREE.PlaneGeometry(n.w * 0.92, 0.9, 6, 4);
    // Split into three panels with slits.
    const pos = g.attributes.position as THREE.BufferAttribute;
    for (let i = 0; i < pos.count; i++) pos.setY(i, pos.getY(i) + 0);
    const mat = norenMaterial(n.color);
    windCloth(mat, 0.45, 0.9, 0.6);
    const mesh = new THREE.Mesh(g, mat);
    const local = new THREE.Matrix4().makeTranslation(n.x, 3.0 - 0.55, 0.14);
    mesh.applyMatrix4(local.premultiply(n.m));
    mesh.castShadow = true;
    group.add(mesh);
  }

  // ---- merge static builders
  group.add(solid(wood.build(), woodMaterial()));
  group.add(solid(plaster.build(), plasterMaterial()));
  group.add(solid(roof.build(), roofMaterial()));
  if (!lattice.empty) group.add(solid(lattice.build(), latticeMaterial()));
  group.add(solid(shop.build(), shopInterior()));
  const pm = windowGlow();
  group.add(solid(paper.build(), pm, false));

  // ---- the three lantern gates are built in gates.ts; stalls in stalls.ts.
  void GATES; void STALLS; void stallX; void STALL_W; void paperGlow;

  return {
    group,
    colliders,
    lights,
    chimes,
    groundY: (x, z) => groundHeight(x, z),
    surface: (x, z) => (z < SHORE.promenadeZ1 - 0.1 ? (Math.abs(x) < 2.2 && z > SHORE.stepsZ1 ? "stone" : "sand") : "stone"),
  };
}

/**
 * A clinker fishing boat hull, 4.6 m long, bow at +z, keel on y = 0: a lofted shell (outside or
 * inside) with a pointed stem, a flat transom, a rising sheer, and painted in vertex colour
 * (red-brown bottom, cream topsides, a blue sheer strake; bare wood inside).
 */
function boatHull(inside: boolean): THREE.BufferGeometry {
  const NS = 18, NJ = 7, L = 4.6;
  const pos: number[] = [], col: number[] = [], idx: number[] = [];
  const c = new THREE.Color();
  const paint = (u: number) => (inside ? "#8f6f4c" : u > 0.8 ? "#3f6d8a" : u < 0.3 ? "#7a3b30" : "#ece5d6");
  for (let i = 0; i <= NS; i++) {
    const s = i / NS, z = (s - 0.5) * L;
    const taper = s > 0.5 ? Math.pow(Math.max(0, 1 - Math.pow((s - 0.5) / 0.5, 2.2)), 0.7) : 0.86 + 0.14 * (s / 0.5);
    const B = 0.7 * taper * (inside ? 0.93 : 1), H = 0.5 + 0.24 * Math.pow(s, 2.4);
    const K = 0.3 * Math.pow(Math.max(0, (s - 0.72) / 0.28), 2) + (inside ? 0.05 : 0);
    for (let j = -NJ; j <= NJ; j++) {
      const u = Math.abs(j) / NJ;
      pos.push(Math.sign(j) * B * Math.pow(u, 0.62), K + (H - K) * Math.pow(u, 1.7), z + (inside ? (s < 0.5 ? 0.04 : -0.04 * taper) : 0));
      c.set(paint(u)).multiplyScalar(inside ? 0.92 + 0.1 * u : 1);
      col.push(c.r, c.g, c.b);
    }
  }
  const W = NJ * 2 + 1;
  for (let i = 0; i < NS; i++) for (let j = 0; j < W - 1; j++) {
    const a = i * W + j, b = a + 1, d = a + W, e = d + 1;
    if (inside) idx.push(a, d, b, b, d, e); else idx.push(a, b, d, b, e, d);
  }
  // Transom (flat stern): a fan from the keel point to the section's edge.
  const k0 = NJ;
  for (let j = 0; j < W - 1; j++) if (j !== k0 && j + 1 !== k0) { if (inside) idx.push(k0, j, j + 1); else idx.push(k0, j + 1, j); }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute("color", new THREE.Float32BufferAttribute(col, 3));
  g.setIndex(idx);
  g.computeVertexNormals();
  return g;
}

/**
 * A rounded, weathered boulder (radii sx, sy, sz): a smooth sphere pushed about by low-frequency
 * noise, its underside flattened where it has settled, with vertex colour for the weathering:
 * darker in hollows and toward the base, paler on the rain-washed top, patches of lichen.
 */
function rockGeometry(r: () => number, sx: number, sy: number, sz: number): THREE.BufferGeometry {
  let g: THREE.BufferGeometry = new THREE.IcosahedronGeometry(1, 3);
  g.deleteAttribute("normal");
  g.deleteAttribute("uv");
  g = mergeVertices(g);
  const seed = r() * 100;
  const pos = g.attributes.position as THREE.BufferAttribute;
  const n = pos.count;
  const col = new Float32Array(n * 3);
  const base = vary(pick(r, ["#8a8378", "#7d776f", "#948a7c", "#857c72"]), r, 0.15);
  const lichen = new THREE.Color(pick(r, ["#a59a6a", "#8e9672", "#b0a27c"]));
  const v = new THREE.Vector3(), c = new THREE.Color();
  for (let i = 0; i < n; i++) {
    v.fromBufferAttribute(pos, i).normalize();
    const big = fbm3(v.x * 1.3 + seed, v.y * 1.3, v.z * 1.3);
    const small = fbm3(v.x * 4.2, v.y * 4.2 + seed, v.z * 4.2);
    const rad = 1 + big * 0.32 + small * 0.07;
    let y = v.y * rad;
    if (y < -0.3) y = -0.3 + (y + 0.3) * 0.25;
    pos.setXYZ(i, v.x * rad * sx, y * sy, v.z * rad * sz);
    // Weathering.
    const hollow = THREE.MathUtils.clamp(0.5 - (big * 0.32 + small * 0.07) * 2.5, 0, 1);
    const up = THREE.MathUtils.clamp(v.y, 0, 1);
    const lich = THREE.MathUtils.smoothstep(fbm3(v.x * 3 - seed, v.y * 3, v.z * 3 + 7), 0.12, 0.3) * THREE.MathUtils.smoothstep(v.y, 0.0, 0.5);
    c.copy(base).multiplyScalar(0.8 + up * 0.28 - hollow * 0.22 - THREE.MathUtils.clamp(-v.y, 0, 1) * 0.18 + small * 0.25);
    c.lerp(lichen, lich * 0.6);
    col[i * 3] = c.r; col[i * 3 + 1] = c.g; col[i * 3 + 2] = c.b;
  }
  g.setAttribute("color", new THREE.BufferAttribute(col, 3));
  g.computeVertexNormals();
  return g;
}

/** Smooth 3D value noise, 3 octaves, about −0.5…0.5. */
function fbm3(x: number, y: number, z: number): number {
  let s = 0, a = 0.5, f = 1;
  for (let o = 0; o < 3; o++) { s += a * (vnoise(x * f, y * f, z * f) - 0.5); a *= 0.5; f *= 2.03; }
  return s * 1.6;
}
function vnoise(x: number, y: number, z: number): number {
  const xi = Math.floor(x), yi = Math.floor(y), zi = Math.floor(z);
  const xf = x - xi, yf = y - yi, zf = z - zi;
  const u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf), w = zf * zf * (3 - 2 * zf);
  const h = (a: number, b: number, c: number) => { const s = Math.sin(a * 127.1 + b * 311.7 + c * 74.7) * 43758.5453; return s - Math.floor(s); };
  const l = (a: number, b: number, t: number) => a + (b - a) * t;
  return l(
    l(l(h(xi, yi, zi), h(xi + 1, yi, zi), u), l(h(xi, yi + 1, zi), h(xi + 1, yi + 1, zi), u), v),
    l(l(h(xi, yi, zi + 1), h(xi + 1, yi, zi + 1), u), l(h(xi, yi + 1, zi + 1), h(xi + 1, yi + 1, zi + 1), u), v),
    w,
  );
}

/** Beach height: flat below the sea wall, then gently down into the sea. */
export function beachHeight(x: number, z: number): number {
  const t = Math.max(0, -z - 108);
  return SHORE.beachY - t * 0.04 - Math.max(0, -z - 125) * 0.08 + Math.sin(x * 0.08) * 0.05;
}

/** Walkable ground height: the street and promenade at 0, the steps, then the beach. */
export function groundHeight(x: number, z: number): number {
  // Tread k's top is at −0.2·k and its nose is at z = −100.02 − 0.5·k (matches the stone in buildTown).
  if (z > SHORE.promenadeZ1 - 0.02) return 0;
  if (Math.abs(x) < 2.2 && z > SHORE.stepsZ1) {
    const k = Math.min(8, Math.max(0, Math.floor(-(z - (SHORE.promenadeZ1 - 0.02)) / 0.5)));
    return -(k / 8) * 1.6;
  }
  return beachHeight(x, z);
}

/** A chochin paper lantern, local origin at its hanging point. ~0.42 m tall. */
export function lanternGeometry(): THREE.BufferGeometry {
  const pts: THREE.Vector2[] = [];
  for (let i = 0; i <= 12; i++) {
    const t = i / 12;
    pts.push(new THREE.Vector2(0.06 + Math.sin(t * Math.PI) * 0.12, -0.08 - t * 0.32));
  }
  const body = new THREE.LatheGeometry(pts, 14);
  const capT = new THREE.CylinderGeometry(0.065, 0.065, 0.045, 14).translate(0, -0.075, 0);
  const capB = new THREE.CylinderGeometry(0.065, 0.065, 0.045, 14).translate(0, -0.405, 0);
  const hook = new THREE.CylinderGeometry(0.006, 0.006, 0.08, 4).translate(0, -0.03, 0);
  // Body uv.y 0..1 down the lantern; caps get uv.y = −1 (painted black in the shader).
  const parts = [body, capT, capB, hook].map((g, i) => {
    const ng = g.index ? g.toNonIndexed() : g;
    const uv = ng.attributes.uv as THREE.BufferAttribute;
    if (i > 0) for (let k = 0; k < uv.count; k++) uv.setY(k, -1);
    return ng;
  });
  return mergeGeos(parts);
}

function mergeGeos(parts: THREE.BufferGeometry[]): THREE.BufferGeometry {
  for (const p of parts) for (const k of Object.keys(p.attributes)) if (!["position", "normal", "uv"].includes(k)) p.deleteAttribute(k);
  return mg(parts, false)!;
}
