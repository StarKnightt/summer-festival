import * as THREE from "three/webgpu";
import { mergeGeometries as mg } from "three/addons/utils/BufferGeometryUtils.js";
import { Builder, rng, range, pick, vary, solid, sagCurve } from "./geo";
import { STREET, SHORE, GATES, STALLS, stallX, STALL_W } from "./layout";
import { ToonMaterial, lanternSwing, paperGlow, windCloth, type LightSpot } from "../render/toon";
import { pavingMaterial, stoneMaterial, roofMaterial, sandMaterial, plasterMaterial, woodMaterial, latticeMaterial } from "../render/surfaces";
import { windowGlow, lanternPaper, noOutline, norenMaterial, shopInterior } from "../render/townMats";

/**
 * The street, its houses, the shore, and everything strung overhead. Static geometry is merged
 * per material (a handful of draw calls); lanterns are instanced and swing in the wind.
 */

export interface Collider { x0: number; x1: number; z0: number; z1: number; y1?: number }

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
  const groundB = new THREE.PlaneGeometry(STREET.half * 2 + 6, STREET.zStart - SHORE.promenadeZ1 + 4, 1, 1).rotateX(-Math.PI / 2);
  groundB.translate(0, 0, (STREET.zStart + SHORE.promenadeZ1) / 2 + 2);
  const street = solid(groundB, pavingMaterial(), false);
  group.add(street);
  for (const side of [-1, 1]) {
    wood.box(0.28, 0.04, STREET.zStart - STREET.zEnd, "#4c4a4c", side * (STREET.half - 0.32), 0.012, (STREET.zStart + STREET.zEnd) / 2);
  }
  // Promenade (wide stone strip along the town front) and its sea wall.
  const promo = new THREE.PlaneGeometry(90, 5.4).rotateX(-Math.PI / 2).translate(0, 0.0, -97.3);
  group.add(solid(promo, stoneMaterial("#a39a8e", 1.2), false));
  const stone = new Builder();
  const wallC = "#8d867c";
  for (const side of [-1, 1]) {
    const x0 = side * 2.2, x1 = side * 45;
    const cx = (x0 + x1) / 2, w = Math.abs(x1 - x0);
    stone.box(w, 2.2, 0.5, wallC, cx, -0.55, -100.2);
    stone.box(w, 0.25, 0.7, "#9c968c", cx, 0.62, -100.1);
    stone.box(w, 0.5, 0.35, wallC, cx, 0.25, -100.05);
    colliders.push({ x0: Math.min(x0, x1), x1: Math.max(x0, x1), z0: -100.5, z1: -99.8 });
  }
  // Steps down to the beach, flanked by low walls with standing lanterns.
  const NS = 8;
  for (let k = 0; k < NS; k++) {
    const y = -((k + 1) / NS) * 1.6;
    stone.box(4.4, 0.22, 0.52, k % 2 ? "#a49d92" : "#9b958b", 0, y + 0.1, -100.25 - k * 0.5);
    stone.box(4.4, Math.abs(y) - 0.0, 0.5, "#8f897f", 0, y / 2, -100.25 - k * 0.5 - 0.02);
  }
  for (const side of [-1, 1]) {
    stone.box(0.45, 0.9, 4.6, wallC, side * 2.42, -0.6, -102.0);
    stone.box(0.45, 0.4, 0.45, "#9c968c", side * 2.42, 0.55, -99.8);
    houseLanterns.push(new THREE.Vector3(side * 2.42, 1.15, -99.8));
  }
  group.add(solid(stone.build(), stoneMaterial("#ffffff", 1.0)));
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
  const rocks = new Builder();
  for (let k = 0; k < 14; k++) {
    const side = k % 2 ? 1 : -1;
    const x = side * range(r, 16, 30), z = range(r, -104, -130);
    const s = range(r, 0.6, 2.2);
    rocks.add(new THREE.DodecahedronGeometry(s, 0), vary("#7c766e", r, 0.2), x, beachHeight(x, z) + s * 0.3, z, r(), r(), r(), 1, range(r, 0.5, 0.8), 1);
  }
  for (const [x, z, ry] of [[-9, -109, 0.5], [11, -111, -0.3]]) {
    const b = new Builder();
    b.box(1.3, 0.45, 4.2, "#e9e2d2", 0, 0.32, 0);
    b.box(1.34, 0.12, 4.24, "#3f6d8a", 0, 0.12, 0);
    b.box(1.1, 0.06, 3.9, "#7a5a3a", 0, 0.52, 0);
    b.box(1.0, 0.25, 0.9, "#e9e2d2", 0, 0.42, 2.3, 0, 0.3);
    const g = b.build();
    g.applyMatrix4(new THREE.Matrix4().makeRotationY(ry).setPosition(x, beachHeight(x, z), z));
    rocks.addKeep(g);
    colliders.push({ x0: x - 1.4, x1: x + 1.4, z0: z - 2.4, z1: z + 2.4 });
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

/** Beach height: flat below the sea wall, then gently down into the sea. */
export function beachHeight(x: number, z: number): number {
  const t = Math.max(0, -z - 108);
  return SHORE.beachY - t * 0.04 - Math.max(0, -z - 125) * 0.08 + Math.sin(x * 0.08) * 0.05;
}

/** Walkable ground height: the street and promenade at 0, the steps, then the beach. */
export function groundHeight(x: number, z: number): number {
  if (z > SHORE.promenadeZ1 + 0.25) return 0;
  if (Math.abs(x) < 2.2 && z > SHORE.stepsZ1) {
    const k = Math.min(8, Math.max(0, Math.floor((-(z - (SHORE.promenadeZ1 + 0.25))) / 0.5) + 1));
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
