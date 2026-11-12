// @ts-nocheck -- TSL node graphs: @types/three node typings reject valid swizzles/overloads.
import * as THREE from "three/webgpu";
import {
  Fn, float, vec2, vec3, vec4, dot, mix, smoothstep, max, min, abs, normalize, clamp, exp, pow, length, cross,
  positionWorld, cameraPosition, mx_noise_float, fract, floor, sin, atan, step, Loop, attribute, hash, sqrt, If, select,
  fwidth,
} from "three/tsl";
import { U } from "./uniforms";

const LUM = vec3(0.2126, 0.7152, 0.0722);
const n2 = (p: any) => mx_noise_float(vec3(p.x, p.y, 0.0)).mul(0.5).add(0.5);
const h12 = Fn(([p]: [any]) => {
  const p3 = fract(vec3(p.x, p.y, p.x).mul(0.1031)).toVar();
  p3.addAssign(dot(p3, p3.yzx.add(33.33)));
  return fract(p3.x.add(p3.y).mul(p3.z));
});

/** Sky colour toward a direction (bay-ride `skyColor`). */
export const skyColor = Fn(([dir]: [any]) => {
  const h = clamp(dir.y, 0.0, 1.0);
  const col = mix(U.horizon, U.mid, smoothstep(0.0, 0.2, h)).toVar();
  col.assign(mix(col, U.zenith, smoothstep(0.14, 0.7, h)));
  const sd = max(dot(dir, U.skySun), 0.0);
  col.addAssign(U.sunGlow.mul(pow(sd, 5.0).mul(U.sunGlowAmt.x).add(pow(sd, 48.0).mul(U.sunGlowAmt.y))));
  const az = dot(normalize(dir.xz.add(1e-5)), normalize(U.skySun.xz.add(1e-5))).mul(0.5).add(0.5);
  col.assign(mix(col, U.horizGlow, clamp(exp(h.negate().mul(U.horizGlowK.y)).mul(az).mul(az).mul(U.horizGlowK.x), 0.0, 1.0)));
  col.assign(mix(col, U.haze, exp(h.mul(-26.0)).mul(0.7).add(exp(h.mul(-5.0)).mul(0.45)).mul(U.hazeAmt)));
  return col;
});

/** Coordinates around a sky direction, in units of its angular radius. */
const discQ = (dir: any, c: any, ang: number) => {
  const t1 = normalize(cross(c, vec3(0, 1, 0)));
  const t2 = cross(t1, c);
  return vec2(dot(dir, t1), dot(dir, t2)).div(ang);
};

const WISP = vec2(0.9004, 0.435);
const cirrus = Fn(([dir]: [any]) => {
  const h = max(dir.y, 0.02);
  const p = dir.xz.div(h).mul(0.6);
  const pw = p.add(vec2(n2(p.mul(0.16).add(3.7)), n2(p.mul(0.16).add(9.1))).sub(0.5).mul(2.6));
  const q = vec2(dot(pw, WISP), dot(pw, vec2(-0.435, 0.9004))).add(vec2(U.time.mul(0.004), 0.0));
  const qa = q.mul(vec2(0.75, 1.5));
  const w = n2(qa).mul(0.5).add(n2(qa.mul(2.03).add(17.1)).mul(0.3)).add(n2(qa.mul(4.1).add(3.3)).mul(0.2));
  const seg = smoothstep(0.45, 0.78, n2(q.mul(vec2(0.7, 1.2)).add(5.1)));
  const along = abs(dot(normalize(dir.xz.add(1e-5)), WISP));
  return smoothstep(0.5, 0.75, w).mul(seg).mul(float(1).sub(smoothstep(0.55, 0.9, along).mul(0.85)))
    .mul(smoothstep(0.12, 0.3, dir.y)).mul(float(1).sub(smoothstep(0.55, 0.95, dir.y)));
});

export function skyDome(): THREE.Mesh {
  const m = new THREE.MeshBasicNodeMaterial({ side: THREE.BackSide, depthWrite: false, fog: false });
  m.colorNode = Fn(() => {
    const dir = normalize(positionWorld.sub(cameraPosition)).toVar();
    const col = skyColor(dir).toVar();
    const skyLum = dot(col, LUM);
    const wisp = cirrus(dir).mul(U.wispAmt);
    const md = dot(dir, U.moonDir);
    col.assign(mix(col, U.wisp.add(U.moonCol.mul(pow(max(md, 0.0), 6.0)).mul(0.25).mul(U.night)), wisp as any));
    // Stars, late dusk to night only.
    If(U.stars.greaterThan(0.0).and(dir.y.greaterThan(0.02)), () => {
      const sp = dir.xz.div(dir.y.add(1.0)).mul(70.0);
      const ci = floor(sp);
      const hs = h12(ci);
      const off = vec2(h12(ci.add(3.1)), h12(ci.add(7.7))).mul(0.6).add(0.2);
      const d = length(fract(sp).sub(off));
      const tw = sin(U.time.mul(hs.mul(2.5).add(0.8)).add(hs.mul(40.0))).mul(0.35).add(0.65);
      // Small, of varied brightness (a few bright ones): bloom makes big ones read as snow.
      const star = step(0.93, hs).mul(float(1).sub(smoothstep(0.015, fract(hs.mul(17.0)).mul(0.04).add(0.05), d))).mul(tw).mul(fract(hs.mul(31.0)).pow(2.0).mul(0.8).add(0.35));
      const minY = mix(0.6, 0.06, U.stars);
      const dark = float(1).sub(smoothstep(0.05, 0.16, skyLum)).mul(smoothstep(0.6, 1.0, U.night));
      col.addAssign(vec3(0.95, 0.95, 1.0).mul(star).mul(smoothstep(minY, minY.add(0.15), dir.y)).mul(dark).mul(float(1).sub(wisp.mul(0.8))).mul(1.6));
    });
    // Sun disc, halo and rays.
    If(dot(U.sunDisk, vec3(1)).greaterThan(0.0).and(dot(dir, U.skySun).greaterThan(0.6)), () => {
      const q = discQ(dir, U.skySun, 0.012);
      const r = length(q);
      const fw = max(fwidth(r), 0.02);
      const disk = float(1).sub(smoothstep(float(1).sub(fw), fw.add(1.0), r));
      const ang = atan(q.y, q.x);
      const rays = pow(abs(sin(ang.mul(4.0).add(0.4))), 40.0).add(pow(abs(sin(ang.mul(7.0).add(1.3))), 60.0).mul(0.6))
        .mul(exp(max(r.sub(1.0), 0.0).mul(-0.16))).mul(smoothstep(1.0, 2.0, r));
      const halo = exp(max(r.sub(1.0), 0.0).mul(-0.55)).mul(0.35).add(exp(max(r.sub(1.0), 0.0).mul(-0.09)).mul(0.12))
        .mul(mix(1.0, 0.3, smoothstep(0.35, 0.85, skyLum)));
      const hot = U.sunDisk;
      col.assign(mix(col, hot, disk));
      col.addAssign(normalize(hot.add(1e-4)).mul(halo.mul(float(1).sub(disk)).add(rays.mul(0.22))).mul(min(length(hot), 1.4)));
    });
    // Painted moon with maria and a halo.
    If(dot(U.moonCol, vec3(1)).greaterThan(0.0).and(md.greaterThan(0.6)), () => {
      const q = discQ(dir, U.moonDir, 0.028);
      const r = length(q);
      const fw = max(fwidth(r), 0.02);
      const disk = float(1).sub(smoothstep(float(1).sub(fw), fw.add(1.0), r));
      const mq = q.mul(1.6);
      const maria = smoothstep(0.38, 0.78, n2(mq.mul(1.2).add(3.0)).mul(0.65).add(n2(mq.mul(2.6).add(9.0)).mul(0.35)));
      const mc = U.moonCol.mul(mix(vec3(1.0), vec3(0.8, 0.77, 0.72), maria.mul(0.8))).mul(1.0);
      col.assign(mix(col, mc, disk.mul(float(1).sub(wisp.mul(0.4)))));
      const halo = exp(max(r.sub(1.0), 0.0).mul(-2.2)).mul(0.32).add(exp(max(r.sub(1.0), 0.0).mul(-0.18)).mul(0.06));
      col.addAssign(U.moonCol.mul(halo).mul(float(1).sub(disk)));
    });
    return col;
  })();
  const dome = new THREE.Mesh(new THREE.SphereGeometry(3000, 48, 24), m);
  dome.frustumCulled = false;
  dome.renderOrder = -10;
  dome.name = "sky";
  return dome;
}

export { vec4 };
