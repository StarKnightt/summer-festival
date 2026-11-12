// @ts-nocheck -- TSL node graphs: @types/three node typings reject valid swizzles/overloads.
import * as THREE from "three/webgpu";
import { materialColor, Fn, float, vec3, uv, smoothstep, abs, fract, mix, sin, vertexColor, diffuseColor, positionWorld, hash, floor, select } from "three/tsl";
import { ToonMaterial, paperGlow } from "./toon";
import { inkMask } from "./post";
import { U } from "./uniforms";

/** Shoji paper and lit shop backs: paper by day, a warm glow behind it from dusk (some stay dark). */
export function windowGlow(): ToonMaterial {
  const m = new ToonMaterial({ vertexColors: true, paint: 0.2, rim: 0.0 });
  m.emissiveNode = Fn(() => {
    const cell = floor(positionWorld.xz.div(3.1)).add(floor(positionWorld.y.div(2.6)).mul(7.0));
    const on = select(hash(cell.x.mul(13.0).add(cell.y)).greaterThan(0.28), float(1), float(0.15));
    const flick = sin(U.time.mul(1.3).add(cell.x)).mul(0.04).add(0.96);
    const k = U.night.mul(0.9).add(U.lantern.mul(0.12));
    return vec3(1.0, 0.66, 0.34).mul(vertexColor()).mul(on).mul(flick).mul(k).mul(1.3);
  })();
  return m;
}

/** Paper chochin: ribbed paper with black caps, glowing warm from inside in every light. */
export function lanternPaper(glow = U.lantern): ToonMaterial {
  const m = new ToonMaterial({ color: "#ffffff", paint: 0, rim: 0.3, soft: 0.1 });
  m.colorNode = Fn(() => {
    const v = uv().y;
    const cap = v.lessThan(-0.5);
    const rib = smoothstep(0.0, 0.18, abs(fract(v.mul(10.0)).sub(0.5)).mul(2.0)).mul(0.25).add(0.75);
    // A band near the middle in a darker shade of the lantern colour.
    const band = smoothstep(0.38, 0.42, v).mul(smoothstep(0.62, 0.58, v));
    const body = diffuseColor.rgb;
    void body;
    return select(cap, vec3(0.08, 0.06, 0.05), mix(vec3(1), vec3(0.72, 0.6, 0.55), band.mul(0.0)).mul(rib));
  })();
  paperGlow(m, glow, new THREE.Color("#ffb060"), 2.4);
  // The caps do not glow.
  const base = m.emissiveNode;
  m.emissiveNode = Fn(() => select(uv().y.lessThan(-0.5), vec3(0), base))();
  return m;
}

/** Shop noren: three panels with slits, a hem band and a pale crest on the middle panel. */
export function norenMaterial(color: string): ToonMaterial {
  const m = new ToonMaterial({ color, side: THREE.DoubleSide, paint: 0.25, rim: 0.3, alphaTest: 0.5 });
  m.colorNode = Fn(() => {
    const u = uv();
    const panel = fract(u.x.mul(3.0));
    const c = vec3(1.0).toVar();
    const hem = smoothstep(0.1, 0.12, u.y).mul(smoothstep(0.16, 0.14, u.y));
    c.assign(mix(c, vec3(1.6), hem.mul(0.5)));
    const mid = u.x.greaterThan(0.333).and(u.x.lessThan(0.667));
    const q = vec3(panel.sub(0.5).mul(1.0), u.y.sub(0.55).mul(0.9), 0.0);
    const ring = smoothstep(0.2, 0.18, q.length()).mul(smoothstep(0.12, 0.14, q.length()));
    c.assign(select(mid, mix(c, vec3(2.4), ring), c));
    return materialColor.mul(c).min(vec3(0.95));
  })();
  m.opacityNode = Fn(() => { const panel = fract(uv().x.mul(3.0)); return select(uv().y.lessThan(0.35).and(panel.lessThan(0.02).or(panel.greaterThan(0.98))), float(0), float(1)); })();
  return m;
}

export function noOutline(m: THREE.NodeMaterial): void {
  inkMask(m, 0);
}

export { mix };
