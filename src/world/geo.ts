import * as THREE from "three/webgpu";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";

/** Small seeded RNG (mulberry32). All world layout randomness goes through this. */
export function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
export const range = (r: () => number, a: number, b: number) => a + (b - a) * r();
export const pick = <T,>(r: () => number, a: readonly T[]): T => a[Math.floor(r() * a.length)];

const _m = new THREE.Matrix4();
const _q = new THREE.Quaternion();
const _e = new THREE.Euler();
const _s = new THREE.Vector3();
const _p = new THREE.Vector3();
const _c = new THREE.Color();

/** Collects coloured parts and merges them into one vertex-coloured geometry. */
export class Builder {
  private parts: THREE.BufferGeometry[] = [];

  /** Adds `g` (consumed) painted `color`, moved by position / euler / scale. */
  add(g: THREE.BufferGeometry, color: THREE.ColorRepresentation, x = 0, y = 0, z = 0, rx = 0, ry = 0, rz = 0, sx = 1, sy = 1, sz = 1): this {
    const geo = g.index ? g.toNonIndexed() : g;
    if (g.index) g.dispose();
    for (const k of Object.keys(geo.attributes)) if (k !== "position" && k !== "normal") geo.deleteAttribute(k);
    if (!geo.attributes.normal) geo.computeVertexNormals();
    _m.compose(_p.set(x, y, z), _q.setFromEuler(_e.set(rx, ry, rz)), _s.set(sx, sy, sz));
    geo.applyMatrix4(_m);
    _c.set(color);
    const n = geo.attributes.position.count;
    const col = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) { col[i * 3] = _c.r; col[i * 3 + 1] = _c.g; col[i * 3 + 2] = _c.b; }
    geo.setAttribute("color", new THREE.BufferAttribute(col, 3));
    this.parts.push(geo);
    return this;
  }

  /** Adds an already-coloured geometry as is (keeps its colour attribute). */
  addKeep(g: THREE.BufferGeometry): this {
    const geo = g.index ? g.toNonIndexed() : g;
    for (const k of Object.keys(geo.attributes)) if (k !== "position" && k !== "normal" && k !== "color") geo.deleteAttribute(k);
    this.parts.push(geo);
    return this;
  }

  box(w: number, h: number, d: number, color: THREE.ColorRepresentation, x: number, y: number, z: number, ry = 0, rx = 0, rz = 0): this {
    return this.add(new THREE.BoxGeometry(w, h, d), color, x, y, z, rx, ry, rz);
  }

  cyl(rt: number, rb: number, h: number, color: THREE.ColorRepresentation, x: number, y: number, z: number, seg = 10, rx = 0, rz = 0, ry = 0): this {
    return this.add(new THREE.CylinderGeometry(rt, rb, h, seg), color, x, y, z, rx, ry, rz);
  }

  get empty(): boolean { return this.parts.length === 0; }

  build(): THREE.BufferGeometry {
    const g = mergeGeometries(this.parts, false)!;
    for (const p of this.parts) p.dispose();
    this.parts = [];
    g.computeBoundingSphere();
    g.computeBoundingBox();
    return g;
  }
}

/** Jitter a colour's value / hue a little. */
export function vary(hex: THREE.ColorRepresentation, r: () => number, amt = 0.08): THREE.Color {
  const c = new THREE.Color(hex);
  const hsl = { h: 0, s: 0, l: 0 };
  c.getHSL(hsl);
  return c.setHSL((hsl.h + (r() - 0.5) * amt * 0.15 + 1) % 1, Math.min(1, hsl.s * (1 + (r() - 0.5) * amt)), Math.min(1, hsl.l * (1 + (r() - 0.5) * amt * 1.5)));
}

/** A static, shadow-casting mesh. */
export function solid(g: THREE.BufferGeometry, m: THREE.Material, cast = true): THREE.Mesh {
  const mesh = new THREE.Mesh(g, m);
  mesh.castShadow = cast;
  mesh.receiveShadow = true;
  mesh.matrixAutoUpdate = false;
  mesh.updateMatrix();
  return mesh;
}

/** A sagging catenary-ish curve between two points. */
export function sagCurve(a: THREE.Vector3, b: THREE.Vector3, sag: number, n = 16): THREE.Vector3[] {
  const out: THREE.Vector3[] = [];
  for (let i = 0; i <= n; i++) {
    const t = i / n;
    out.push(new THREE.Vector3().lerpVectors(a, b, t).add(new THREE.Vector3(0, -sag * 4 * t * (1 - t), 0)));
  }
  return out;
}
