import * as THREE from "three/webgpu";
import { uniform } from "three/tsl";

/**
 * Shared TSL uniforms. Time-of-day values (ported from bay-ride's todUniforms) are written by
 * world/timeofday.ts; the wind by world/wind.ts. Every scene material reads these.
 */
const c = (hex: string) => new THREE.Color(hex);
const v3 = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z);
const v2 = (x: number, y: number) => new THREE.Vector2(x, y);

export const U = {
  /** Shading light direction (sun by day, moon at night), world space, toward the light. */
  sunDir: uniform(v3(0.3, 0.4, -0.86).normalize()),
  /** Where the sun really is (sky glow, disc). */
  skySun: uniform(v3(0.3, 0.1, -0.95).normalize()),
  sunColor: uniform(c("#ffa676")),
  shadowTint: uniform(c("#5f5596")),
  rimColor: uniform(c("#ff9448")),
  keyHue: uniform(0.45),
  zenith: uniform(c("#2c5078")),
  mid: uniform(c("#c08ca4")),
  horizon: uniform(c("#ffab68")),
  fogColor: uniform(c("#8a76a2")),
  sunGlow: uniform(c("#ff9a48")),
  sunGlowAmt: uniform(v2(0.4, 0.55)),
  haze: uniform(c("#ffa86b")),
  hazeAmt: uniform(0.38),
  horizGlow: uniform(c("#ff8a5c")),
  horizGlowK: uniform(v2(0.6, 5)),
  cloudTop: uniform(c("#ffffff")),
  cloudMid: uniform(c("#cccccc")),
  cloudLow: uniform(c("#888888")),
  cloudRim: uniform(c("#ffffff")),
  /** x = rim mix, y = backlit silver lining, z = warm underside amount. */
  cloudK: uniform(v3(0.5, 0, 0)),
  cloudUnder: uniform(c("#ff9a60")),
  cloudLight: uniform(v3(0.3, 0.4, -0.86).normalize()),
  wisp: uniform(c("#ffffff")),
  wispAmt: uniform(0.4),
  sunDisk: uniform(c("#000000")),
  stars: uniform(0),
  night: uniform(0),
  worldTint: uniform(c("#ffffff")),
  moonDir: uniform(v3(-0.2, 0.33, -0.92).normalize()),
  moonCol: uniform(c("#000000")),
  glint: uniform(1),
  glintDir: uniform(v3(0.3, 0.1, -0.95).normalize()),
  glintCol: uniform(c("#ffaa60")),
  glintShape: uniform(v2(0.12, 0.14)),
  waterShallow: uniform(c("#9a90a2")),
  waterDeep: uniform(c("#2a3868")),
  waterRefl: uniform(v3(1, 1, 1)),
  /** 0…1 paper-lantern glow (always > 0: they glow in every light) and the strength of their pools. */
  lantern: uniform(0.8),
  lanternPool: uniform(0.6),
  /** Fireworks flash over the sea: rgb × intensity, and its world position. */
  flashCol: uniform(c("#000000")),
  flashPos: uniform(v3(0, 60, -220)),

  // ---- wind (world/wind.ts)
  windDir: uniform(v2(0.6, 0.8).normalize()),
  /** 0…1 overall breeze strength with gusts. */
  wind: uniform(0.3),
  /** World-space time in seconds (paused with the game). */
  time: uniform(0),

  // ---- grade
  gradeMul: uniform(c("#ffffff")),
  sat: uniform(1.05),
};

export type Uniforms = typeof U;
