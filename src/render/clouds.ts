// @ts-nocheck -- TSL node graphs: @types/three node typings reject valid swizzles/overloads.
import * as THREE from "three/webgpu";
import {
  Fn, float, vec2, vec3, vec4, dot, mix, smoothstep, max, normalize, length, cross, positionWorld, cameraPosition,
  mx_noise_float, attribute, sqrt, If, Loop, textureLoad, ivec2, int, positionLocal,
} from "three/tsl";
import { U } from "./uniforms";
import { skyColor } from "./sky";

/**
 * Painted cumulus, after bay-ride's cloud cards: each cloud is a camera-facing card whose
 * outline is the union of a few circular lobes (cumulus: a broad base under an off-centre heaped
 * body with cauliflower bumps; heaps; long thin strata). Lobe layouts are made on the CPU into a
 * lobe table (one row per cloud) and read with exact texel loads. Each pixel is shaded as the
 * front-most lobe sphere it hits: lavender bodies, warm undersides and a rim at a low sun.
 */
const LOBES = 24;
type Lobe = [number, number, number, number];
type Kind = "cumulus" | "heap" | "strata";

function rng(seed: number) {
  let s = seed >>> 0;
  return () => ((s = (Math.imul(s, 1664525) + 1013904223) >>> 0) / 4294967296);
}
const range = (r: () => number, a: number, b: number) => a + (b - a) * r();
const clampX = (x: number, rad: number) => Math.max(-0.97 + rad, Math.min(0.97 - rad, x));

/** bay-ride's cloudLobes (cumulus / heap / strata), unchanged in spirit. */
function cloudLobes(r: () => number, kind: Kind): { lobes: Lobe[]; top: number } {
  const lobes: Lobe[] = [];
  const max = LOBES - 1;
  const add = (x: number, y: number, rad: number, depth = -y * 0.15 + r() * 0.18 * rad / 0.3) => {
    if (lobes.length < max) lobes.push([clampX(x, rad), y, rad, depth]);
  };
  const bumps = (n: number, r0: number, r1: number) => {
    const body = lobes.slice();
    for (let k = 0; k < n && lobes.length < max; k++) {
      const b = body[Math.floor(r() * body.length)];
      const ang = range(r, 0.25, Math.PI - 0.25);
      const s = range(r, r0, r1);
      const d = b[2] - s * range(r, 0.15, 0.55);
      const onParent = b[3] + Math.sqrt(Math.max(0, b[2] * b[2] - d * d));
      add(b[0] + Math.cos(ang) * d, b[1] + Math.sin(ang) * d, s, onParent - s * range(r, 0.35, 0.6));
    }
  };
  if (kind === "strata") {
    const n = 6 + Math.floor(r() * 6);
    const phase = r() * 6.28;
    const step = 1.7 / n;
    for (let i = 0, x = -0.85; i < n && x < 0.9; i++, x += step * range(r, 0.8, 1.15)) {
      const swell = 0.6 + 0.7 * Math.max(0, Math.sin(x * 2.1 + phase));
      const rad = step * swell * range(r, 0.85, 1.2);
      add(x, rad * range(r, 0.7, 0.95), rad, r() * 0.03);
    }
  } else if (kind === "cumulus") {
    const nb = 3 + Math.floor(r() * 2);
    for (let i = 0; i < nb; i++) {
      const rad = range(r, 0.26, 0.36);
      add(((i / (nb - 1)) * 2 - 1) * (0.8 - rad) + range(r, -0.05, 0.05), rad * range(r, 0.45, 0.65), rad);
    }
    const cx = range(r, -0.25, 0.25);
    const tiers = 2 + Math.floor(r() * 2);
    let y = 0.3;
    for (let k = 0; k < tiers; k++) {
      y += range(r, 0.2, 0.26);
      const rad = range(r, 0.3, 0.38) * (1 - k * 0.1);
      add(cx + range(r, -0.18, 0.18), y, rad);
      if (r() < 0.6) add(cx + range(r, -0.35, 0.35), y - range(r, 0.05, 0.15), rad * range(r, 0.65, 0.85));
    }
    bumps(Math.min(max - lobes.length, 12 + Math.floor(r() * 7)), 0.08, 0.16);
  } else {
    const nb = 1 + Math.floor(r() * 3);
    for (let i = 0; i < nb; i++) {
      const rad = range(r, 0.26, 0.42) * (nb === 1 ? 1.25 : 1);
      add(nb === 1 ? range(r, -0.15, 0.15) : ((i / (nb - 1)) * 2 - 1) * (0.78 - rad) + range(r, -0.08, 0.08), rad * range(r, 0.35, 0.6), rad);
    }
    if (r() < 0.6) {
      const b = lobes[Math.floor(r() * lobes.length)];
      add(b[0] + range(r, -0.2, 0.2), b[1] + b[2] * range(r, 0.5, 0.8), b[2] * range(r, 0.6, 0.8));
    }
    bumps(8 + Math.floor(r() * 9), 0.07, 0.15);
  }
  const top = Math.max(...lobes.map((l) => l[1] + l[2]));
  return { lobes, top };
}

const CENTRE = new THREE.Vector3(0, 0, -60);

export function cloudCards(seed = 77): THREE.Mesh {
  const r = rng(seed);
  interface C { x: number; y: number; z: number; hw: number; sy: number; lobes: Lobe[]; top: number; d: number }
  const clouds: C[] = [];
  const place = (kind: Kind, az: number, d: number, y: number, hw: number, sy: number) => {
    const { lobes, top } = cloudLobes(r, kind);
    clouds.push({ x: CENTRE.x + Math.sin(az) * d, y, z: CENTRE.z + Math.cos(az) * d, hw, sy, lobes, top, d });
  };
  // Towering cumulus over the sea and to either side; heaps over the roofs; strata low on the sea.
  for (const az0 of [150, 205, 120, 240, 60, 300]) place("cumulus", (az0 + range(r, -8, 8)) * Math.PI / 180, range(r, 900, 1200), range(r, 60, 100), range(r, 180, 260), range(r, 0.9, 1.05));
  for (let i = 0; i < 12; i++) place("heap", r() * Math.PI * 2, range(r, 600, 1500), range(r, 90, 190), range(r, 80, 200), range(r, 0.75, 1.0));
  for (let i = 0; i < 6; i++) place("strata", (180 + range(r, -50, 50)) * Math.PI / 180, range(r, 1600, 2400), range(r, 70, 120), range(r, 200, 380), range(r, 0.45, 0.7));
  clouds.sort((a, b) => b.d - a.d);

  const n = clouds.length;
  const table = new Float32Array(LOBES * n * 4);
  const pos: number[] = [], corner: number[] = [], size: number[] = [], idx: number[] = [];
  clouds.forEach((c, row) => {
    c.lobes.forEach((l, i) => table.set(l, (row * LOBES + i) * 4));
    // Unused lobe slots: radius 0.
    table.set([c.top, c.lobes.length, 0, 0], (row * LOBES + LOBES - 1) * 4);
    const v0 = pos.length / 3;
    for (const [cx, cy] of [[-1.45, -0.1], [1.45, -0.1], [1.45, c.top + 0.4], [-1.45, c.top + 0.4]]) {
      pos.push(c.x, c.y, c.z);
      corner.push(cx, cy);
      size.push(c.hw, c.sy, row);
    }
    idx.push(v0, v0 + 1, v0 + 2, v0, v0 + 2, v0 + 3);
  });
  const tex = new THREE.DataTexture(table, LOBES, n, THREE.RGBAFormat, THREE.FloatType);
  tex.magFilter = tex.minFilter = THREE.NearestFilter;
  tex.needsUpdate = true;
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute("aCorner", new THREE.Float32BufferAttribute(corner, 2));
  g.setAttribute("aSize", new THREE.Float32BufferAttribute(size, 3));
  g.setIndex(idx);

  const m = new THREE.MeshBasicNodeMaterial({ transparent: true, depthWrite: false, fog: false });
  const aCorner = attribute("aCorner", "vec2");
  const aSize = attribute("aSize", "vec3");
  const cardBasis = (c: any) => {
    const toC = normalize(vec3(float(CENTRE.x).sub(c.x), 0.0, float(CENTRE.z).sub(c.z)));
    return { toC, right: normalize(cross(vec3(0, 1, 0), toC)) };
  };
  m.positionNode = Fn(() => {
    const c = positionLocal;
    const { right } = cardBasis(c);
    return c.add(right.mul(aCorner.x.mul(aSize.x))).add(vec3(0, 1, 0).mul(aCorner.y.mul(aSize.x).mul(aSize.y)));
  })();
  const vCorner = aCorner.toVarying();
  const vRow = aSize.z.toVarying();
  const n2 = (p: any) => mx_noise_float(vec3(p.x, p.y, 0.0)).mul(0.5).add(0.5);
  m.colorNode = Fn(() => {
    const p = vCorner;
    const row = int(vRow.add(0.5));
    const info = textureLoad(tex, ivec2(int(LOBES - 1), row));
    const count = int(info.y.add(0.5));
    // Wobbly outline: the lobes' edge is broken by noise, more on the lower half.
    const wob = n2(p.mul(7.0).add(float(row).mul(3.7))).sub(0.5).mul(0.07).add(n2(p.mul(19.0).add(float(row))).sub(0.5).mul(0.03));
    const field = float(-9).toVar();
    const acc = vec3(0, 0, 0.0001).toVar();
    Loop(LOBES - 1, ({ i }) => {
      If(i.lessThan(count), () => {
        const l = textureLoad(tex, ivec2(i, row));
        const q = p.sub(l.xy).div(l.z);
        const d2 = dot(q, q);
        const f = float(1).sub(sqrt(d2)).mul(l.z);
        field.assign(max(field, f));
        // Blend the lobes' sphere normals smoothly (no seams between lobes: one soft mass
        // instead of a cluster of balls). Nearer and bigger lobes weigh more.
        const h = max(float(1).sub(d2), 0.0);
        const w = h.mul(h).mul(l.z).mul(l.w.mul(0.5).add(1.0).max(0.2));
        acc.addAssign(vec3(q.x, q.y, sqrt(h)).mul(w));
      });
    });
    const a = smoothstep(0.0, 0.025, field.add(wob)).mul(smoothstep(-0.02, 0.05, p.y));
    const { toC, right } = cardBasis(positionWorld);
    const L = normalize(vec3(dot(U.cloudLight, right), U.cloudLight.y, dot(U.cloudLight, toC).negate()));
    const nn = normalize(acc);
    // Lit from the light, but also brighter toward the top of the mass (painted, less ball-like).
    const lam = mix(dot(nn, L).mul(0.5).add(0.5), smoothstep(0.0, info.x, p.y), 0.35);
    const col = mix(U.cloudLow, U.cloudMid, smoothstep(0.2, 0.55, lam)).toVar();
    col.assign(mix(col, U.cloudTop, smoothstep(0.55, 0.85, lam)));
    // Warm underside toward the base; rim on the lit edge; silver lining when backlit.
    col.assign(mix(col, U.cloudUnder, U.cloudK.z.mul(float(1).sub(smoothstep(0.02, 0.35, p.y))).mul(0.75)));
    const edge = float(1).sub(smoothstep(0.0, 0.05, field));
    col.assign(mix(col, U.cloudRim, edge.mul(smoothstep(0.35, 0.8, lam)).mul(U.cloudK.x)));
    col.addAssign(U.cloudRim.mul(edge).mul(U.cloudK.y).mul(0.35));
    col.assign(mix(col, skyColor(normalize(positionWorld.sub(cameraPosition))), 0.15));
    return vec4(col, a.mul(0.97));
  })();
  const mesh = new THREE.Mesh(g, m);
  mesh.frustumCulled = false;
  mesh.renderOrder = -5;
  mesh.name = "clouds";
  return mesh;
}

void vec2; void length;
