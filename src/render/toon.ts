// @ts-nocheck -- TSL node graphs: @types/three node typings reject valid swizzles/overloads.
import * as THREE from "three/webgpu";
import {
  Fn, float, vec2, vec3, vec4, dot, mix, smoothstep, max, min, abs, normalize, clamp, select, length,
  positionWorld, normalWorld, cameraPosition, diffuseColor, mx_noise_float, texture, pow, sin, positionLocal,
  instanceIndex, hash, uniform,
} from "three/tsl";
import { U } from "./uniforms";

/**
 * Toon shading for every surface, ported from bay-ride's GLSL `toonT` to a TSL lighting model:
 * three cel steps (lit / shadow / dark shadow) with a painterly brush-noise terminator, the
 * light's own hue on lit faces at a low sun (key hue), a cool shadow tint, warm bounce from the
 * ground, and a warm rim on the sun side of silhouettes. Shadows come from the scene's single
 * directional light (`lightNode.shadowNode`). Paper lanterns add warm pools of light from a
 * baked top-down light field (see lanternField) that lifts shadows inside them.
 */

const LUM = vec3(0.2126, 0.7152, 0.0722);
export const lum = (c: any) => dot(c, LUM);

// ------------------------------------------------------------------ lantern light field
/** Area covered by the lantern light field (world XZ) and its resolution (texels per metre). */
export const FIELD = { x0: -14, x1: 14, z0: -150, z1: 18, res: 4 };
const fw = Math.round((FIELD.x1 - FIELD.x0) * FIELD.res);
const fh = Math.round((FIELD.z1 - FIELD.z0) * FIELD.res);
export const lanternFieldTex = new THREE.DataTexture(new Float32Array(fw * fh * 4), fw, fh, THREE.RGBAFormat, THREE.FloatType);
lanternFieldTex.magFilter = lanternFieldTex.minFilter = THREE.LinearFilter;
lanternFieldTex.wrapS = lanternFieldTex.wrapT = THREE.ClampToEdgeWrapping;

export interface LightSpot { x: number; y: number; z: number; r: number; g: number; b: number; k: number; reach: number }
/**
 * Bakes every lantern / bulb into the field once: inverse-square-ish falloff on the ground with a
 * soft reach. Light height is folded in as a wider, dimmer pool for high lanterns. CPU on purpose:
 * a one-shot ~110k-texel pass at load (tens of ms), cheaper than spinning up a compute pass.
 */
export function bakeLanternField(spots: LightSpot[]): void {
  const data = lanternFieldTex.image.data as Float32Array;
  data.fill(0);
  for (const s of spots) {
    const reach = s.reach;
    const ix0 = Math.max(0, Math.floor((s.x - reach - FIELD.x0) * FIELD.res));
    const ix1 = Math.min(fw - 1, Math.ceil((s.x + reach - FIELD.x0) * FIELD.res));
    const iz0 = Math.max(0, Math.floor((s.z - reach - FIELD.z0) * FIELD.res));
    const iz1 = Math.min(fh - 1, Math.ceil((s.z + reach - FIELD.z0) * FIELD.res));
    const h2 = Math.max(0.5, s.y) ** 2;
    for (let j = iz0; j <= iz1; j++) {
      const z = FIELD.z0 + (j + 0.5) / FIELD.res;
      for (let i = ix0; i <= ix1; i++) {
        const x = FIELD.x0 + (i + 0.5) / FIELD.res;
        const d2 = (x - s.x) ** 2 + (z - s.z) ** 2;
        if (d2 > reach * reach) continue;
        const edge = 1 - Math.sqrt(d2) / reach;
        const f = (s.k * h2) / (d2 + h2) * edge * edge;
        const o = (j * fw + i) * 4;
        data[o] += s.r * f;
        data[o + 1] += s.g * f;
        data[o + 2] += s.b * f;
      }
    }
  }
  lanternFieldTex.needsUpdate = true;
}

/** Lantern light arriving at a world point (pre-multiplied by the time-of-day pool strength). */
export const lanternLight = Fn(([wp, n]: [any, any]) => {
  const uv = vec2(wp.x.sub(FIELD.x0).div(FIELD.x1 - FIELD.x0), wp.z.sub(FIELD.z0).div(FIELD.z1 - FIELD.z0));
  const l = texture(lanternFieldTex, uv).rgb;
  const hk = float(1).sub(smoothstep(3.6, 6.0, wp.y));
  const facing = n.y.max(0).mul(0.55).add(0.45);
  return l.mul(hk).mul(facing).mul(U.lanternPool);
});

// ------------------------------------------------------------------ painterly helpers
const n2 = (p: any) => mx_noise_float(vec3(p.x, p.y, 0.0)).mul(0.5).add(0.5);

/** World-space brush strokes, band-limited by distance (bay-ride `brush`). */
export const brush = Fn(([wp, n]: [any, any]) => {
  const an = abs(n);
  const horiz = an.y.greaterThan(max(an.x, an.z));
  const p = select(horiz, wp.xz, select(an.x.greaterThan(an.z), wp.zy, wp.xy)).toVar();
  const w = vec2(n2(p.mul(0.12)), n2(p.mul(0.12).add(7.3))).sub(0.5);
  const rot = select(horiz,
    vec2(p.x.mul(0.8).sub(p.y.mul(0.6)), p.x.mul(0.6).add(p.y.mul(0.8))),
    vec2(p.x.mul(0.94).add(p.y.mul(0.34)), p.x.mul(-0.34).add(p.y.mul(0.94))));
  const q = rot.add(w.mul(4.0));
  const fp = length(wp.sub(cameraPosition)).mul(0.0011 * 1.3);
  const k1 = float(1).sub(smoothstep(0.25, 0.6, fp.mul(6.0)));
  const k2 = float(1).sub(smoothstep(0.25, 0.6, fp.mul(13.0)));
  return float(0.5)
    .add(n2(q.mul(vec2(1.1, 6.0))).sub(0.5).mul(0.6).mul(k1))
    .add(n2(q.mul(vec2(2.3, 13.0))).sub(0.5).mul(0.4).mul(k2));
});

// ------------------------------------------------------------------ toon lighting
export interface ToonOpts {
  /** Brush-stroke strength on the terminator and albedo (0 = clean, 1 = painted). */
  paint?: number;
  rim?: number;
  /** Softness of the cel step (skin ~0.08). */
  soft?: number;
  jitter?: number;
  /** Her skin / hair: soft cast shadows, form shading, moonlit fill at night. */
  her?: boolean;
  skin?: boolean;
  hair?: boolean;
  /** Painted face / eyes: no bands, just the light level. */
  flat?: boolean;
}

function toonColor(o: ToonOpts, shadowNode: any) {
  const paint = o.paint ?? 0.6, rimAmt = o.rim ?? 0.5, soft = o.soft ?? 0.0, jitter = o.jitter ?? 0.0;
  const base = diffuseColor.rgb;
  const N = normalize(normalWorld);
  const wpos = positionWorld;
  const V = normalize(cameraPosition.sub(wpos));
  const sunL = lum(U.sunColor);
  const lp = lanternLight(wpos, N);

  if (o.flat) {
    // Face features: the light level and a touch of its hue, lifted by lantern light.
    const lvl = mix(vec3(sunL.mul(0.9).add(0.18)), U.sunColor.mul(0.8).add(0.15), 0.35);
    return base.mul(lvl.mul(mix(1.0, 1.25, U.night))).mul(U.worldTint).add(base.mul(lp).mul(0.8));
  }

  const br = paint > 0 ? brush(wpos, N) : float(0.5);
  const flatK = float(1).sub(smoothstep(0.7, 0.95, N.y).mul(0.75));
  let Ld: any = U.sunDir;
  if (o.her) {
    // At night her key comes partly from the camera side (a painted moonlight fill).
    const Vh = normalize(vec3(V.x, 0.0, V.z).add(1e-4));
    const sd0 = vec3(Vh.z.negate(), 0.0, Vh.x);
    const sd = select(dot(sd0, U.sunDir).lessThan(0), sd0.negate(), sd0);
    const kd = normalize(Vh.mul(0.3).add(sd.mul(0.95)).add(vec3(0, 0.45, 0)));
    Ld = normalize(mix(U.sunDir, kd, U.night.mul(0.65)));
  }
  const t = dot(N, Ld).add(br.sub(0.5).mul(0.32 * paint).mul(flatK)).add(jitter);
  let sv: any = shadowNode ?? float(1);
  if (o.her) sv = mix(sv, 1.0, U.night.mul(0.3));
  sv = mix(sv, 1.0, clamp(lum(lp).mul(4.0), 0.0, 0.9));
  if (soft > 0.12 || o.skin || o.hair) sv = mix(sv, 1.0, 0.45);
  const lit = smoothstep(0.02 - soft, 0.06 + soft, t).mul(sv);
  const midS = smoothstep(-0.5 - soft, -0.44 + soft, t);
  const al = lum(base);
  let cLit: any = base.mul(U.sunColor).mul(o.her ? U.night.mul(0.2).add(1.0) : 1.0);
  if (o.skin) {
    const ml = sunL.mul(1.5);
    cLit = mix(cLit, base.mul(ml).mul(vec3(1.12, 0.97, 0.92)), U.night.mul(0.45));
  }
  // Bright ground takes a warm sun only partly (bay-ride's "calm").
  const chroma = max(base.r, max(base.g, base.b)).sub(min(base.r, min(base.g, base.b)));
  const bright = smoothstep(0.3, 0.6, al).mul(smoothstep(0.08, 0.2, chroma));
  const calm = base.mul(mix(vec3(sunL), U.sunColor, 0.35).mul(0.74).add(U.mid.mul(0.16)));
  cLit = mix(cLit, calm, bright);
  // Whites shade to a light blue-grey, never holes.
  const whiteK = smoothstep(0.35, 0.75, al).mul(float(1).sub(smoothstep(0.12, 0.3, chroma)));
  let cSh: any = base.mul(mix(U.shadowTint, mix(vec3(0.37, 0.4, 0.52), U.shadowTint.mul(1.3), U.night), whiteK));
  // Painted key: lit faces take the light's hue, shade goes cool.
  const kh = U.keyHue.mul(o.skin ? 0.0 : 1.0).mul(float(1).sub(bright.mul(0.8)));
  const keyCol = mix(U.shadowTint.mul(al.mul(1.8).add(0.07)), U.sunColor.mul(al.mul(1.9).add(0.05)), smoothstep(0.04, 0.42, t));
  cLit = mix(cLit, keyCol, kh);
  cSh = mix(cSh, U.shadowTint.mul(al.mul(1.6).add(0.07)), kh.mul(0.5));
  const cDk = cSh.mul(vec3(0.7, 0.72, 0.84));
  let col: any = mix(cDk, cSh, max(midS, float(1).sub(sv)));
  col = mix(col, cLit, lit);
  col = col.add(base.mul(U.mid).mul(0.1).mul(N.y.mul(0.5).add(0.5)));
  col = col.add(base.mul(vec3(0.07, 0.045, 0.02)).mul(float(0.5).sub(N.y.mul(0.5))).mul(float(1).sub(lit)));
  const fr = float(1).sub(max(dot(N, V), 0.0));
  const rim = smoothstep(0.58, 0.72, fr).mul(rimAmt).mul(float(1).sub(smoothstep(0.75, 0.97, N.y).mul(0.85)));
  const sunSide = smoothstep(-0.3, 0.3, dot(N, Ld).add(0.2)).mul(sv.mul(0.7).add(0.3));
  col = col.add(U.rimColor.mul(base).mul(rim).mul(sunSide.mul(0.8).add(0.2)).mul(0.8));
  if (o.skin) col = mix(col, cSh, smoothstep(0.46, 0.6, fr).mul(0.75));
  if (o.her) {
    const moonRim = smoothstep(0.66, 0.86, fr).mul(smoothstep(-0.25, 0.35, dot(N, Ld))).mul(U.night);
    col = col.add(U.rimColor.mul(base.mul(0.5).add(0.06)).mul(moonRim).mul(o.hair ? 0.25 : 0.75));
    col = col.mul(U.night.mul(0.15).add(1.0));
    const herRim = smoothstep(0.4, 0.8, fr);
    col = col.add(vec3(0.62, 0.76, 1.0).mul(base.mul(0.3).add(0.02)).mul(herRim.mul(herRim)).mul(U.night).mul(o.hair ? 0.4 : 1.0));
  }
  if (o.hair) {
    // Anime hair sheen: a soft band where the view grazes the hair under the light.
    const hv = dot(N, normalize(V.add(Ld).mul(0.5)));
    const band = smoothstep(0.72, 0.8, hv).mul(float(1).sub(smoothstep(0.86, 0.93, hv)));
    col = col.add(U.sunColor.mul(base.mul(0.6).add(0.05)).mul(band).mul(lit).mul(0.5));
  }
  if (paint > 0) col = col.mul(br.sub(0.5).mul(0.14 * paint).add(1.0));
  col = col.mul(float(1).sub(whiteK.mul(0.4).mul(U.night)));
  col = min(col, vec3(0.97));
  // World tint (night dims the land), then lantern light on top, untinted.
  return col.mul(U.worldTint).add(base.mul(lp).mul(o.her ? 0.9 : 1.0));
}

class ToonLightingModel extends THREE.LightingModel {
  constructor(private o: ToonOpts) { super(); }
  direct({ lightNode, reflectedLight }: any): void {
    const s = lightNode?.shadowNode ?? null;
    reflectedLight.directDiffuse.addAssign(toonColor(this.o, s));
  }
}

export interface ToonMatOpts extends ToonOpts {
  color?: THREE.ColorRepresentation;
  map?: THREE.Texture | null;
  vertexColors?: boolean;
  side?: THREE.Side;
  transparent?: boolean;
  opacity?: number;
  alphaTest?: number;
  name?: string;
}

/** A lit toon material (needs the scene's one directional light). */
export class ToonMaterial extends THREE.MeshLambertNodeMaterial {
  readonly toon: ToonOpts;
  constructor(o: ToonMatOpts = {}) {
    super();
    this.toon = o;
    this.color.set(o.color ?? 0xffffff);
    if (o.map) this.map = o.map;
    this.vertexColors = !!o.vertexColors;
    this.side = o.side ?? THREE.FrontSide;
    this.transparent = !!o.transparent;
    this.opacity = o.opacity ?? 1;
    if (o.alphaTest) this.alphaTest = o.alphaTest;
    this.name = o.name ?? "toon";
  }
  setupLightingModel(): any {
    return new ToonLightingModel(this.toon);
  }
}

// ------------------------------------------------------------------ deformers

/** Cloth hanging from its top edge: banners, noren, flags (local y from top to bottom). */
export function windCloth(m: THREE.NodeMaterial, top: number, height: number, amp = 1): void {
  m.positionNode = Fn(() => {
    const p = positionLocal.toVar();
    const w = clamp(float(top).sub(p.y).div(height), 0.0, 1.0);
    const w2 = w.mul(w);
    const ph = p.x.mul(2.3).add(p.z.mul(1.7));
    const g = U.wind.mul(0.75).add(0.25);
    const rip = sin(U.time.mul(3.2).sub(ph).add(w.mul(2.5))).mul(0.6).add(sin(U.time.mul(5.1).sub(ph.mul(1.7)).add(1.3)).mul(0.4));
    const sway = sin(U.time.mul(1.1).add(ph.mul(0.2))).mul(0.5).add(0.5);
    const off = w2.mul(g).mul(rip.mul(0.05).add(sway.mul(0.08))).mul(amp);
    p.z.addAssign(off);
    p.x.addAssign(w2.mul(g).mul(rip).mul(0.02 * amp));
    return p;
  })();
}

/** An instanced lantern swinging about its hanging point (local origin at the top). */
export function lanternSwing(m: THREE.NodeMaterial, amp = 1): void {
  m.positionNode = Fn(() => {
    const p = positionLocal.toVar();
    const ph = hash(instanceIndex).mul(6.283);
    const g = U.wind.mul(0.8).add(0.2);
    const ax = sin(U.time.mul(1.7).add(ph)).mul(0.07).add(sin(U.time.mul(2.9).add(ph.mul(2.0))).mul(0.025)).mul(g).mul(amp);
    const az = sin(U.time.mul(1.3).add(ph.mul(1.3))).mul(0.06).mul(g).mul(amp);
    // Rotate about X then Z (small angles).
    const y1 = p.y.mul(ax.cos()).sub(p.z.mul(ax.sin()));
    const z1 = p.y.mul(ax.sin()).add(p.z.mul(ax.cos()));
    const x2 = p.x.mul(az.cos()).sub(y1.mul(az.sin()));
    const y2 = p.x.mul(az.sin()).add(y1.mul(az.cos()));
    return vec3(x2, y2, z1);
  })();
}

/** Paper glowing from a flame inside: warm, brighter at the middle of the lantern. */
export function paperGlow(m: THREE.NodeMaterial, glow: any = U.lantern, tint = new THREE.Color("#ffb060"), gain = 2.2): void {
  const k = uniform(gain);
  m.emissiveNode = Fn(() => {
    const flick = sin(U.time.mul(13.0).add(positionWorld.x.mul(3.1)).add(positionWorld.z.mul(2.3))).mul(0.04).add(0.96);
    return vec3(tint.r, tint.g, tint.b).mul(diffuseColor.rgb.mul(0.6).add(0.4)).mul(glow).mul(k).mul(flick);
  })();
}

export { vec4, pow };
