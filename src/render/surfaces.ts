// @ts-nocheck -- TSL node graphs: @types/three node typings reject valid swizzles/overloads.
import * as THREE from "three/webgpu";
import {
  Fn, float, vec2, vec3, floor, fract, smoothstep, mix, positionWorld, abs, min, max, mx_noise_float, vertexColor, hash,
  sin, length, dot, normalWorld, fwidth,
} from "three/tsl";
import { ToonMaterial } from "./toon";
import { U } from "./uniforms";

const h2 = (p: any) => hash(p.x.mul(127.1).add(p.y.mul(311.7)).floor());
const nz = (p: any) => mx_noise_float(vec3(p.x, p.y, 0.0)).mul(0.5).add(0.5);

/** Street paving: running-bond granite slabs with grout, worn smoother down the middle. */
export function pavingMaterial(): ToonMaterial {
  const m = new ToonMaterial({ color: "#ffffff", paint: 0.5, rim: 0.2 });
  m.colorNode = Fn(() => {
    const p = positionWorld.xz;
    const row = floor(p.y.div(0.42));
    const cell = vec2(p.x.div(0.66).add(fract(row.mul(0.37))), p.y.div(0.42));
    const id = floor(cell);
    const f = fract(cell);
    const g = smoothstep(0.0, 0.03, f.x).mul(smoothstep(1.0, 0.97, f.x)).mul(smoothstep(0.0, 0.045, f.y)).mul(smoothstep(1.0, 0.955, f.y));
    const tone = h2(id).mul(0.22).add(0.82);
    const warm = mix(vec3(0.46, 0.45, 0.46), vec3(0.58, 0.52, 0.45), h2(id.add(9.0)));
    const wear = float(1).sub(smoothstep(1.2, 3.6, abs(p.x))).mul(0.06);
    const speck = nz(p.mul(6.0)).mul(0.08).add(0.96);
    const c = warm.mul(tone).mul(speck).add(wear);
    return mix(c.mul(0.55), c, g);
  })();
  return m;
}

/**
 * Sea wall, steps and coping: dressed ashlar blocks in courses with recessed mortar, each block
 * its own tone, the faces mottled and pitted, grime and damp darkening toward the sand, a little
 * green weed at the foot, and paler, worn treads and tops. Tinted by the vertex colour (wall /
 * coping / step), so the parts read apart.
 */
export function seawallMaterial(): ToonMaterial {
  const m = new ToonMaterial({ vertexColors: true, paint: 0.65, rim: 0.35 });
  m.colorNode = Fn(() => {
    const vc = vertexColor();
    const n = abs(normalWorld);
    const top = smoothstep(0.6, 0.85, n.y);
    // Triplanar 2D coordinates: along the face, up the face.
    const p = mix(mix(positionWorld.xy, positionWorld.zy, smoothstep(0.4, 0.6, n.x)), positionWorld.xz, top);
    const row = floor(p.y.div(0.46));
    const cell = vec2(p.x.div(mix(float(0.95), float(1.25), h2(vec2(row, 3.0)))).add(h2(vec2(row, 7.0))), p.y.div(0.46));
    const id = floor(cell);
    const f = fract(cell);
    // Mortar: soft recessed joints, with a lighter lip just above each joint.
    const jx = smoothstep(0.0, 0.035, f.x).mul(smoothstep(1.0, 0.965, f.x));
    const jy = smoothstep(0.0, 0.07, f.y).mul(smoothstep(1.0, 0.93, f.y));
    const joint = jx.mul(jy);
    const lip = smoothstep(0.07, 0.16, f.y).mul(smoothstep(0.3, 0.16, f.y)).mul(0.06);
    // Each block: its own tone and warmth; the face mottled, pitted and edge-worn.
    const tone = h2(id).mul(0.2).add(0.86);
    const warm = mix(vec3(0.95, 0.97, 1.0), vec3(1.05, 1.0, 0.92), h2(id.add(5.0)));
    const mott = nz(p.mul(2.2)).mul(0.16).add(nz(p.mul(9.0)).mul(0.08)).add(0.86);
    const pit = smoothstep(0.78, 0.86, nz(p.mul(14.0))).mul(0.12);
    const edge = smoothstep(0.82, 1.0, max(abs(f.x.sub(0.5)), abs(f.y.sub(0.5))).mul(2.0)).mul(0.08);
    const face = vc.mul(tone).mul(warm).mul(mott).sub(pit).add(edge).add(lip);
    // Treads and tops: paler and smoother, worn by feet; no vertical courses.
    const tread = vc.mul(nz(positionWorld.xz.mul(3.0)).mul(0.1).add(1.02)).mul(h2(floor(positionWorld.xz.mul(vec2(0.8, 2.0)))).mul(0.08).add(0.95));
    const c0 = mix(face, tread, top);
    // Grime and damp toward the sand, weed at the very foot (vertical faces only).
    const low = smoothstep(-0.2, -1.5, positionWorld.y).mul(float(1).sub(top));
    const streak = nz(vec2(positionWorld.x.mul(3.0).add(positionWorld.z.mul(3.0)), 0.5));
    const c1 = c0.mul(float(1).sub(low.mul(streak.mul(0.25).add(0.12))));
    const weed = smoothstep(-1.25, -1.55, positionWorld.y).mul(smoothstep(0.45, 0.7, nz(positionWorld.xz.mul(1.7).add(positionWorld.y)))).mul(float(1).sub(top));
    const c2 = mix(c1, vec3(0.3, 0.38, 0.24), weed.mul(0.55));
    return mix(c2.mul(0.42), c2, mix(joint, float(1), top.mul(0.7)));
  })();
  return m;
}

/** Plain stone (promenade, steps, sea wall): big blocks with soft joints. */
export function stoneMaterial(base = "#9a948c", scale = 1): ToonMaterial {
  const m = new ToonMaterial({ color: base, paint: 0.7, rim: 0.3 });
  const b = new THREE.Color(base);
  m.colorNode = Fn(() => {
    const n = abs(normalWorld);
    const p = mix(mix(positionWorld.xy, positionWorld.zy, smoothstep(0.4, 0.6, n.x)), positionWorld.xz, smoothstep(0.6, 0.8, n.y)).div(scale);
    const row = floor(p.y.div(0.5));
    const cell = vec2(p.x.div(1.1).add(fract(row.mul(0.5))), p.y.div(0.5));
    const f = fract(cell);
    const g = smoothstep(0.0, 0.03, f.x).mul(smoothstep(1.0, 0.97, f.x)).mul(smoothstep(0.0, 0.06, f.y)).mul(smoothstep(1.0, 0.94, f.y));
    const tone = h2(floor(cell)).mul(0.16).add(0.88).mul(nz(p.mul(3.0)).mul(0.1).add(0.95));
    return mix(vec3(b.r, b.g, b.b).mul(0.55), vec3(b.r, b.g, b.b).mul(tone), g);
  })();
  return m;
}

/** Roof tiles: rows of rounded clay tiles (grooves down the slope, overlapping courses). */
export function roofMaterial(): ToonMaterial {
  const m = new ToonMaterial({ vertexColors: true, paint: 0.4, rim: 0.6 });
  m.colorNode = Fn(() => {
    const vc = vertexColor();
    const along = positionWorld.z.add(positionWorld.x.mul(0.001));
    const groove = abs(fract(along.mul(3.6)).sub(0.5)).mul(2.0);
    const course = fract(positionWorld.y.mul(4.2).add(positionWorld.x.mul(0.6)));
    const shade = smoothstep(0.0, 0.5, groove).mul(0.22).add(0.78).mul(smoothstep(0.0, 0.12, course).mul(0.18).add(0.82));
    return vc.mul(shade);
  })();
  return m;
}

/** Beach sand: warm, darker and smoother toward the waterline, faint ripples. */
export function sandMaterial(waterZ: number): ToonMaterial {
  const m = new ToonMaterial({ color: "#e2cfa6", paint: 0.8, rim: 0.1 });
  m.colorNode = Fn(() => {
    const p = positionWorld.xz;
    const wet = smoothstep(float(waterZ + 6), float(waterZ), p.y);
    const rip = sin(p.y.mul(5.0).add(nz(p.mul(0.4)).mul(6.0))).mul(0.5).add(0.5).mul(0.05);
    const dry = vec3(0.86, 0.74, 0.55).mul(nz(p.mul(1.5)).mul(0.1).add(0.95)).add(rip);
    return mix(dry, vec3(0.6, 0.5, 0.42), wet.mul(0.8));
  })();
  return m;
}

/** Plaster wall: soft blotches, a little grime toward the ground. */
export function plasterMaterial(): ToonMaterial {
  const m = new ToonMaterial({ vertexColors: true, paint: 0.8, rim: 0.4 });
  m.colorNode = Fn(() => {
    const vc = vertexColor();
    const p = positionWorld;
    const blot = nz(vec2(p.x.add(p.z), p.y).mul(1.3)).mul(0.08).add(0.96);
    const grime = smoothstep(0.0, 0.9, p.y).mul(0.15).add(0.85);
    return vc.mul(blot).mul(grime);
  })();
  return m;
}

/** Wood: grain streaks along the board. */
export function woodMaterial(): ToonMaterial {
  const m = new ToonMaterial({ vertexColors: true, paint: 0.5, rim: 0.4 });
  m.colorNode = Fn(() => {
    const vc = vertexColor();
    const p = positionWorld;
    const grain = nz(vec2(p.x.add(p.z).mul(7.0), p.y.mul(0.6))).mul(0.16).add(0.9);
    return vc.mul(grain);
  })();
  return m;
}

/** Wooden lattice (koshi): vertical slats over a dark interior, anti-aliased, no per-slat ink. */
export function latticeMaterial(): ToonMaterial {
  const m = new ToonMaterial({ vertexColors: true, paint: 0.2, rim: 0.2 });
  m.colorNode = Fn(() => {
    const vc = vertexColor();
    const s = positionWorld.x.add(positionWorld.z).div(0.105);
    const f = abs(fract(s).sub(0.5)).mul(2.0);
    const w = fwidth(s).mul(1.5).add(0.02);
    const slat = smoothstep(float(0.62).sub(w), float(0.62).add(w), f);
    // Between the slats: shoji paper in the shade behind (pale by day), lamp-lit at night.
    const interior = mix(vec3(0.42, 0.37, 0.31), vec3(0.62, 0.4, 0.2), U.night);
    return mix(vc.mul(2.3).add(vec3(0.04, 0.025, 0.01)), interior, slat);
  })();
  return m;
}

export { U, min, max, length, dot };
