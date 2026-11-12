import * as THREE from "three/webgpu";
import { U } from "../render/uniforms";

/**
 * Time of day: morning, day, sunset, night. The look tables are bay-ride's presets (its
 * morning / noon / sunset / night), rotated so the sea lies down the street toward −Z
 * (bay-ride's sea was at azimuth −90°, here 180°: every azimuth +270°). Lantern glow is never
 * zero: the paper lanterns glow in every light, their pools of light only show once the sun is low.
 *
 * Bearings: azimuth = atan2(x, z) in degrees. The street runs from the town (+Z) down to the
 * shore (−Z). The sun rises behind the town and sets over the sea, a little to the right.
 */
export const PRESETS = ["morning", "day", "sunset", "night"] as const;
export type Preset = (typeof PRESETS)[number];

type RGB = [number, number, number];
interface Look {
  az: number; el: number; shadeMin: number; keyHue: number;
  sun: RGB; shadow: RGB; rim: RGB;
  zenith: RGB; mid: RGB; horizon: RGB; fog: RGB; fogNear: number; fogFar: number;
  glow: RGB; glowA: number; glowB: number;
  haze: RGB; hazeA: number;
  hgl: RGB; hglA: number; hglF: number;
  cTop: RGB; cMid: RGB; cLow: RGB; cRim: RGB; cRimK: number; cBack: number; cUnder: RGB; cUnderA: number;
  wisp: RGB; wispA: number;
  disk: RGB; stars: number; night: number;
  world: RGB;
  grade: RGB; sat: number;
  bloomS: number; bloomR: number; bloomT: number;
  moonAz: number; moonEl: number; moon: RGB;
  wShallow: RGB; wDeep: RGB; wRefl: RGB; glint: number; glintCol: RGB; glintMoon: number;
  gSpread: number; gSheen: number;
  lantern: number; pool: number;
  /** Ambient (hemisphere) fill so shaded faces keep colour. */
  amb: number;
}

const hx = (hex: string, k = 1): RGB => {
  const c = new THREE.Color(hex);
  return [c.r * k, c.g * k, c.b * k];
};
const R = 270; // bay-ride → this town azimuth rotation

const LOOKS: Record<Preset, Look> = {
  // Low sun behind the town: pale peach key, long cool shadows, paler teal over a cream horizon.
  morning: {
    az: 140 + R, el: 13, shadeMin: 15, keyHue: 0.15,
    sun: hx("#ffd9b4", 0.98), shadow: hx("#7b8ac4"), rim: hx("#ffd2a8", 1.35),
    zenith: hx("#208ca3"), mid: hx("#55b5ca"), horizon: hx("#f2dccc"), fog: hx("#dedfe2"), fogNear: 40, fogFar: 340,
    glow: [1.0, 0.82, 0.62], glowA: 0.24, glowB: 0.36,
    haze: [0.97, 0.9, 0.86], hazeA: 0.5,
    hgl: hx("#ffd2b0"), hglA: 0.38, hglF: 8,
    cTop: [1.0, 0.9, 0.8], cMid: [0.8, 0.83, 0.88], cLow: [0.48, 0.55, 0.66], cRim: [1.0, 0.86, 0.72], cRimK: 0.6, cBack: 0.35,
    cUnder: [1.0, 0.8, 0.68], cUnderA: 0.25,
    wisp: [1.0, 0.93, 0.88], wispA: 0.5, disk: [1.7, 1.5, 1.2], stars: 0, night: 0,
    world: [1.02, 0.98, 0.94],
    grade: [1.02, 1.0, 0.98], sat: 0.98,
    bloomS: 0.28, bloomR: 0.5, bloomT: 0.95,
    moonAz: -78 + R, moonEl: 24, moon: [0.86, 0.88, 0.92],
    wShallow: hx("#86cfc6"), wDeep: hx("#326c9c"), wRefl: [1.0, 0.97, 0.95], glint: 0.55, glintCol: [1.0, 0.9, 0.78], glintMoon: 0,
    gSpread: 0.15, gSheen: 0.12,
    lantern: 0.55, pool: 0.08, amb: 0.22,
  },
  day: {
    az: -150 + R, el: 62, shadeMin: 62, keyHue: 0,
    sun: hx("#fff5e6"), shadow: hx("#8290bc"), rim: hx("#fff1d6"),
    zenith: hx("#167586"), mid: hx("#04a8c0"), horizon: hx("#afe8f6"), fog: hx("#c8e6ea"), fogNear: 50, fogFar: 420,
    glow: [1.0, 0.92, 0.75], glowA: 0.12, glowB: 0.25,
    haze: [0.82, 0.93, 0.94], hazeA: 0.4,
    hgl: hx("#ffffff"), hglA: 0, hglF: 6,
    cTop: [1.0, 0.98, 0.94], cMid: [0.8, 0.85, 0.9], cLow: [0.42, 0.5, 0.63], cRim: [1.0, 0.98, 0.92], cRimK: 0.45, cBack: 0.1,
    cUnder: [1.0, 0.9, 0.8], cUnderA: 0,
    wisp: [0.96, 0.97, 1.0], wispA: 0.55, disk: [3.0, 2.9, 2.6], stars: 0, night: 0,
    world: [1.0, 1.0, 1.0],
    grade: [1.0, 1.0, 1.01], sat: 1.06,
    bloomS: 0.24, bloomR: 0.5, bloomT: 1.0,
    moonAz: 0, moonEl: -30, moon: [0, 0, 0],
    wShallow: hx("#58d6c8"), wDeep: hx("#1a5aa0"), wRefl: [1.12, 0.95, 1.05], glint: 0.5, glintCol: [1.0, 0.97, 0.9], glintMoon: 0,
    gSpread: 0.17, gSheen: 0.1,
    lantern: 0.5, pool: 0.0, amb: 0.2,
  },
  // Sun on the horizon over the sea: violet cloud bodies with orange undersides, warm rim light.
  sunset: {
    az: -112 + R, el: 6.5, shadeMin: 8, keyHue: 0.45,
    sun: hx("#ffa676", 0.95), shadow: hx("#5f5596"), rim: hx("#ff9448", 2.1),
    zenith: hx("#2c5078"), mid: hx("#c08ca4"), horizon: hx("#ffab68"), fog: hx("#b08aa2"), fogNear: 35, fogFar: 300,
    glow: [1.0, 0.6, 0.28], glowA: 0.4, glowB: 0.55,
    haze: [1.0, 0.66, 0.42], hazeA: 0.38,
    hgl: hx("#ff8a5c"), hglA: 0.6, hglF: 5,
    cTop: [0.46, 0.33, 0.38], cMid: [0.3, 0.22, 0.3], cLow: [0.18, 0.14, 0.23], cRim: [1.0, 0.62, 0.28], cRimK: 0.9, cBack: 0.7,
    cUnder: [1.0, 0.5, 0.2], cUnderA: 0.95,
    wisp: [1.0, 0.62, 0.48], wispA: 0.45, disk: [2.0, 1.55, 1.05], stars: 0, night: 0.3,
    world: [0.96, 0.86, 0.82],
    grade: [1.02, 0.98, 0.96], sat: 1.05,
    bloomS: 0.34, bloomR: 0.45, bloomT: 0.95,
    moonAz: 0, moonEl: -30, moon: [0, 0, 0],
    wShallow: hx("#9a90a2"), wDeep: hx("#2a3868"), wRefl: [1.05, 0.9, 0.85], glint: 1.0, glintCol: [1.0, 0.66, 0.38], glintMoon: 0,
    gSpread: 0.12, gSheen: 0.14,
    lantern: 0.85, pool: 0.45, amb: 0.24,
  },
  // Moonlight: cool weak clouds, indigo sea with a moon path; the lanterns carry the street.
  night: {
    az: -84 + R, el: 26, shadeMin: 20, keyHue: 0.55,
    sun: hx("#7d90c8", 0.6), shadow: hx("#26305e"), rim: hx("#a8bce8", 0.8),
    zenith: hx("#071131"), mid: hx("#172a5a"), horizon: hx("#33497e"), fog: hx("#1a2446"), fogNear: 30, fogFar: 260,
    glow: [0.62, 0.72, 0.98], glowA: 0.1, glowB: 0.22,
    haze: [0.2, 0.25, 0.44], hazeA: 0.3,
    hgl: hx("#3a4e86"), hglA: 0.22, hglF: 10,
    cTop: [0.13, 0.155, 0.27], cMid: [0.07, 0.09, 0.18], cLow: [0.04, 0.05, 0.11], cRim: [0.34, 0.38, 0.54], cRimK: 0.45, cBack: 0.35,
    cUnder: [0.2, 0.22, 0.38], cUnderA: 0.05,
    wisp: [0.035, 0.05, 0.11], wispA: 0.3, disk: [0, 0, 0], stars: 1, night: 1,
    world: [0.42, 0.46, 0.68],
    grade: [0.98, 0.98, 1.04], sat: 1.06,
    bloomS: 0.6, bloomR: 0.55, bloomT: 0.8,
    moonAz: -84 + R, moonEl: 19, moon: [0.95, 0.88, 0.7],
    wShallow: hx("#264874"), wDeep: hx("#0e2048"), wRefl: [0.9, 0.92, 1.0], glint: 0.75, glintCol: [1.0, 0.92, 0.74], glintMoon: 1,
    gSpread: 0.13, gSheen: 0.14,
    lantern: 1.0, pool: 1.0, amb: 0.3,
  },
};

function mix(a: Look, b: Look, k: number, out: Look): Look {
  const o = out as unknown as Record<string, number | RGB>;
  for (const key of Object.keys(a) as (keyof Look)[]) {
    const x = a[key], y = b[key];
    if (Array.isArray(x)) {
      const r = o[key] as RGB, yy = y as RGB;
      for (let i = 0; i < 3; i++) r[i] = x[i] + (yy[i] - x[i]) * k;
    } else o[key] = (x as number) + ((y as number) - (x as number)) * k;
  }
  return out;
}
const cloneLook = (l: Look): Look => {
  const o = { ...l } as unknown as Record<string, number | RGB>;
  for (const k in o) if (Array.isArray(o[k])) o[k] = [...(o[k] as RGB)] as RGB;
  return o as unknown as Look;
};
const DEG = Math.PI / 180;
const dirFrom = (v: THREE.Vector3, azDeg: number, elDeg: number) => {
  const a = azDeg * DEG, e = elDeg * DEG;
  return v.set(Math.sin(a) * Math.cos(e), Math.sin(e), Math.cos(a) * Math.cos(e));
};

export function parsePreset(s: string | null | undefined): Preset | null {
  if (!s) return null;
  const k = s.toLowerCase().replace(/[^a-z]/g, "");
  if (k === "noon") return "day";
  return (PRESETS as readonly string[]).includes(k) ? (k as Preset) : null;
}

/** Hooks the time of day drives outside the uniforms (bloom, fog, lights). */
export interface TodSinks {
  bloom(strength: number, radius: number, threshold: number): void;
  fog(color: THREE.Color, near: number, far: number): void;
  key(dir: THREE.Vector3, color: THREE.Color, shadowDir: THREE.Vector3): void;
  ambient(sky: THREE.Color, ground: THREE.Color, k: number): void;
}

const TRANSITION = 4.0;

export class TimeOfDay {
  private from: Look;
  private to: Look;
  private k = 1;
  private cur: Look;
  private readonly blend: Look;
  private dirty = true;
  preset: Preset;
  private readonly listeners: ((p: Preset) => void)[] = [];
  private readonly tmpV = new THREE.Vector3();
  private readonly tmpS = new THREE.Vector3();
  private readonly tmpC = new THREE.Color();
  private readonly tmpC2 = new THREE.Color();
  private readonly tmpC3 = new THREE.Color();

  constructor(private sinks: TodSinks, start: Preset) {
    this.preset = start;
    this.cur = this.from = this.to = LOOKS[start];
    this.blend = cloneLook(LOOKS.day);
    this.apply(this.cur);
  }

  get night(): number { return this.cur.night; }
  get lantern(): number { return this.cur.lantern; }
  get pool(): number { return this.cur.pool; }
  /** 0…1 how far the transition has got (1 when settled). */
  get settled(): boolean { return this.k >= 1; }

  onChange(fn: (p: Preset) => void): void { this.listeners.push(fn); }

  set(p: Preset, instant = false): void {
    if (p === this.preset && this.k >= 1 && !instant) return;
    this.preset = p;
    this.from = cloneLook(this.cur);
    this.to = LOOKS[p];
    this.k = instant ? 1 : 0;
    if (instant) this.cur = this.to;
    this.dirty = true;
    for (const fn of this.listeners) fn(p);
  }

  update(dt: number): void {
    if (this.k < 1) {
      this.k = Math.min(1, this.k + dt / TRANSITION);
      const e = this.k * this.k * (3 - 2 * this.k);
      this.cur = this.k >= 1 ? this.to : mix(this.from, this.to, e, this.blend);
      this.dirty = true;
    }
    if (this.dirty) {
      this.apply(this.cur);
      this.dirty = false;
    }
  }

  private apply(l: Look): void {
    dirFrom(U.skySun.value, l.az, l.el);
    dirFrom(U.sunDir.value, l.az, Math.max(l.el, l.shadeMin));
    U.sunColor.value.setRGB(...l.sun);
    U.shadowTint.value.setRGB(...l.shadow);
    U.rimColor.value.setRGB(...l.rim);
    U.keyHue.value = l.keyHue;
    U.zenith.value.setRGB(...l.zenith);
    U.mid.value.setRGB(...l.mid);
    U.horizon.value.setRGB(...l.horizon);
    U.fogColor.value.setRGB(...l.fog);
    U.sunGlow.value.setRGB(...l.glow);
    U.sunGlowAmt.value.set(l.glowA, l.glowB);
    U.haze.value.setRGB(...l.haze);
    U.hazeAmt.value = l.hazeA;
    U.horizGlow.value.setRGB(...l.hgl);
    U.horizGlowK.value.set(l.hglA, l.hglF);
    U.cloudTop.value.setRGB(...l.cTop);
    U.cloudMid.value.setRGB(...l.cMid);
    U.cloudLow.value.setRGB(...l.cLow);
    U.cloudRim.value.setRGB(...l.cRim);
    U.cloudK.value.set(l.cRimK, l.cBack, l.cUnderA);
    U.cloudUnder.value.setRGB(...l.cUnder);
    U.wisp.value.setRGB(...l.wisp);
    U.wispAmt.value = l.wispA;
    U.sunDisk.value.setRGB(...l.disk);
    U.stars.value = l.stars;
    U.night.value = l.night;
    U.worldTint.value.setRGB(...l.world);
    dirFrom(U.moonDir.value, l.moonAz, l.moonEl);
    U.moonCol.value.setRGB(...l.moon);
    U.glint.value = l.glint;
    U.glintDir.value.copy(U.skySun.value).lerp(U.moonDir.value, l.glintMoon).normalize();
    U.glintCol.value.setRGB(...l.glintCol);
    U.glintShape.value.set(l.gSpread, l.gSheen);
    U.cloudLight.value.copy(U.glintDir.value);
    U.waterShallow.value.setRGB(...l.wShallow);
    U.waterDeep.value.setRGB(...l.wDeep);
    U.waterRefl.value.set(...l.wRefl);
    U.lantern.value = l.lantern;
    U.lanternPool.value = l.pool;
    U.gradeMul.value.setRGB(...l.grade);
    U.sat.value = l.sat;

    this.sinks.bloom(l.bloomS, l.bloomR, l.bloomT);
    this.sinks.fog(this.tmpC.setRGB(...l.fog), l.fogNear, l.fogFar);
    dirFrom(this.tmpS, l.az, Math.max(l.el, 12));
    this.sinks.key(U.sunDir.value, U.sunColor.value, this.tmpS);
    this.tmpC2.setRGB(...l.mid).lerp(this.tmpC3.setRGB(...l.zenith), 0.4);
    this.tmpC3.setRGB(...l.horizon).multiplyScalar(0.5);
    this.sinks.ambient(this.tmpC2, this.tmpC3, l.amb);
    void this.tmpV;
  }
}
