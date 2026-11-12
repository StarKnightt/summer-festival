import * as THREE from "three/webgpu";
import { Particles, type P } from "./particles";
import { U } from "../render/uniforms";
import type { Audio } from "../audio/audio";

const rand = (a: number, b: number) => a + Math.random() * (b - a);
const PALETTE: [number, number, number][] = [
  [1.0, 0.42, 0.25], // vermilion
  [1.0, 0.78, 0.35], // gold
  [0.45, 0.75, 1.0], // sky blue
  [0.95, 0.45, 0.85], // peach-pink
  [0.55, 1.0, 0.55], // green
  [1.0, 0.95, 0.85], // white
  [0.75, 0.5, 1.0], // violet
];

/**
 * Every effect in the world: fireworks over the sea (shells, trails, bursts, glitter, the flash
 * on the water), steam from the food stalls, petals drifting on the breeze and sparkler sparks.
 */
export class Fx {
  readonly group = new THREE.Group();
  readonly glow = new Particles(9000, "glow", true, 4);
  readonly petals = new Particles(220, "petal", false);
  readonly puffs = new Particles(260, "puff", false);
  private flash = new THREE.Color(0, 0, 0);
  private flashK = 0;
  steamPoints: THREE.Vector3[] = [];
  private steamT = 0;
  private petalT = 0;
  /** Fireworks show state. */
  show = false;
  private showT = 0;
  private nextShell = 0;
  shellsLaunched = 0;
  audio: Audio | null = null;

  constructor() {
    this.group.add(this.glow.mesh, this.petals.mesh, this.puffs.mesh);
    this.glow.onTrail = (p, dt) => this.trail(p, dt);
  }

  // ------------------------------------------------------------------ fireworks
  startShow(): void {
    if (this.show) return;
    this.show = true;
    this.showT = 0;
    this.nextShell = 1.2;
  }
  stopShow(): void { this.show = false; }

  private launch(kind?: number, x = rand(-26, 26)) {
    const z = rand(-165, -145);
    const h = rand(24, 40);
    const t = rand(1.6, 2.1);
    const vy = h / t + 0.5 * 9.8 * 0.35 * t; // light gravity on the shell
    const [r, g, b] = PALETTE[Math.floor(Math.random() * PALETTE.length)];
    const shell = this.glow.spawn({
      x, y: -1.8, z, vx: rand(-1, 1), vy, vz: rand(-1, 1), r: 1, g: 0.75, b: 0.45, size: 2.0,
      life: t, grav: 9.8 * 0.35, fade: 1, trail: 1, tag: kind ?? Math.floor(Math.random() * 6),
    });
    if (!shell) return;
    (shell as any).col = [r, g, b];
    (shell as any).burst = true;
    this.audio?.firework(new THREE.Vector3(x, 0, z), new THREE.Vector3(x, h, z), t, Math.random() < 0.5);
    this.shellsLaunched++;
  }

  private trail(p: P, dt: number) {
    if ((p as any).burst) {
      if (Math.random() < dt * 40) this.glow.spawn({ x: p.x, y: p.y, z: p.z, vx: rand(-0.3, 0.3), vy: rand(-1, 0), vz: rand(-0.3, 0.3), r: 1, g: 0.6, b: 0.3, a: 0.6, size: 1.4, life: 0.5, grav: 2 });
      if (p.age + dt >= p.life) this.burst(p);
      return;
    }
    // Comet tails on chrysanthemum / willow stars.
    if (Math.random() < dt * 18) this.glow.spawn({ x: p.x, y: p.y, z: p.z, vx: 0, vy: -0.3, vz: 0, r: p.r, g: p.g * 0.85, b: p.b * 0.6, a: 0.5 * (1 - p.age / p.life), size: p.size * 0.7, life: 0.6 + (p.trail ?? 0), grav: 1.2, drag: 1 });
  }

  private burst(s: P) {
    const [r, g, b] = (s as any).col as [number, number, number];
    const kind = s.tag ?? 0;
    const n = kind === 2 ? 110 : kind === 4 ? 90 : 150;
    const speed = rand(10, 14);
    const gold: [number, number, number] = [1.0, 0.72, 0.3];
    const second = PALETTE[Math.floor(Math.random() * PALETTE.length)];
    // Ring bursts share one random tilt.
    const ax = new THREE.Vector3(rand(-0.5, 0.5), 1, rand(-0.3, 0.3)).normalize();
    const t1 = new THREE.Vector3(1, 0, 0).cross(ax).normalize();
    const t2 = ax.clone().cross(t1);
    for (let i = 0; i < n; i++) {
      let dx: number, dy: number, dz: number;
      if (kind === 2) {
        const a = (i / n) * Math.PI * 2;
        dx = t1.x * Math.cos(a) + t2.x * Math.sin(a); dy = t1.y * Math.cos(a) + t2.y * Math.sin(a); dz = t1.z * Math.cos(a) + t2.z * Math.sin(a);
      } else {
        // Even sphere (golden spiral) with a little jitter.
        const k = i + 0.5, phi = Math.acos(1 - (2 * k) / n), th = Math.PI * (1 + Math.sqrt(5)) * k;
        dx = Math.sin(phi) * Math.cos(th); dy = Math.cos(phi); dz = Math.sin(phi) * Math.sin(th);
      }
      const v = speed * rand(0.92, 1.05);
      const willow = kind === 3, chrys = kind === 1 || willow;
      const c = chrys ? gold : kind === 5 && i % 2 ? second : [r, g, b];
      this.glow.spawn({
        x: s.x + dx * 0.8, y: s.y + dy * 0.8, z: s.z + dz * 0.8, vx: dx * v, vy: dy * v, vz: dz * v, r: c[0], g: c[1], b: c[2],
        size: willow ? 2.4 : 3.0, life: willow ? rand(3.2, 4) : rand(1.6, 2.3), drag: willow ? 1.6 : 1.25, grav: willow ? 2.4 : 3.2,
        fade: 1, flicker: kind === 4 ? 0.9 : 0.08, trail: chrys ? (willow ? 1.2 : 0.4) : 0,
      });
    }
    // A pistil: small bright core of a second colour.
    if (kind === 0 || kind === 5) {
      for (let i = 0; i < 40; i++) {
        const d = new THREE.Vector3(rand(-1, 1), rand(-1, 1), rand(-1, 1)).normalize().multiplyScalar(rand(5, 7));
        this.glow.spawn({ x: s.x, y: s.y, z: s.z, vx: d.x, vy: d.y, vz: d.z, r: second[0], g: second[1], b: second[2], size: 2.6, life: 1.3, drag: 1.4, grav: 2.5, fade: 1 });
      }
    }
    // Glitter crackle after the burst.
    if (kind === 4 || Math.random() < 0.3) {
      for (let i = 0; i < 70; i++) {
        const d = new THREE.Vector3(rand(-1, 1), rand(-1, 1), rand(-1, 1)).normalize().multiplyScalar(rand(4, 12));
        this.glow.spawn({ x: s.x, y: s.y, z: s.z, vx: d.x, vy: d.y, vz: d.z, r: 1, g: 0.95, b: 0.8, size: 1.6, life: rand(1.5, 2.6), drag: 1.5, grav: 2, fade: 1, flicker: 0.95 });
      }
    }
    // Light the sea and the sky haze.
    this.flash.setRGB(chrysOr(kind, r, gold[0]), chrysOr(kind, g, gold[1]), chrysOr(kind, b, gold[2]));
    this.flashK = 1;
    U.flashPos.value.set(s.x, s.y, s.z);
  }

  private updateShow(dt: number) {
    if (!this.show) return;
    this.showT += dt;
    this.nextShell -= dt;
    if (this.nextShell <= 0) {
      const t = this.showT;
      // Opening single shells, then pairs, a willow interlude, and a finale volley; then calm.
      if (t < 14) { this.launch(); this.nextShell = rand(1.6, 2.6); }
      else if (t < 34) { this.launch(); if (Math.random() < 0.5) this.launch(); this.nextShell = rand(1.3, 2.2); }
      else if (t < 44) { this.launch(3, rand(-10, 10)); this.nextShell = rand(1.8, 2.4); }
      else if (t < 54) { for (let i = 0; i < 3; i++) this.launch(); this.nextShell = rand(0.5, 0.9); }
      else if (t < 60) { this.nextShell = 6; }
      else { this.launch(); this.nextShell = rand(4, 8); }
    }
  }

  // ------------------------------------------------------------------ ambience
  private updateSteam(dt: number) {
    this.steamT -= dt;
    if (this.steamT > 0) return;
    this.steamT = 0.12;
    for (const s of this.steamPoints) {
      this.puffs.spawn({ x: s.x + rand(-0.15, 0.15), y: s.y + 0.05, z: s.z + rand(-0.15, 0.15), vx: rand(-0.05, 0.05), vy: rand(0.35, 0.55), vz: rand(-0.05, 0.05), r: 1, g: 0.98, b: 0.95, a: 0.22, size: 0.18, grow: 0.35, life: rand(1.8, 2.6), drag: 0.6, fade: 2 });
    }
  }

  private updatePetals(dt: number, near: THREE.Vector3, wind: THREE.Vector2, windK: number) {
    this.petalT -= dt * (0.6 + windK * 2.2);
    if (this.petalT > 0 || near.z < -100) return;
    this.petalT = 0.09;
    // Born upwind and above her so they drift through the close view.
    const x = near.x + rand(-4, 4) - wind.x * 3;
    const z = near.z + rand(-8, 3) - wind.y * 3;
    const pink = Math.random();
    this.petals.spawn({ x: THREE.MathUtils.clamp(x, -4.3, 4.3), y: rand(3.2, 5.2), z, vx: wind.x * 0.6, vy: -0.35, vz: wind.y * 0.6, r: 1, g: 0.78 + pink * 0.12, b: 0.84 + pink * 0.08, size: 0.05, life: rand(7, 10), drag: 0.9, grav: 0.02, spin: rand(-3, 3), fade: 2 });
  }

  /** Sparkler sparks at a hand position. */
  sparkler(p: THREE.Vector3, dt: number): void {
    const n = Math.random() < dt * 60 ? 2 : 0;
    for (let i = 0; i < n; i++) {
      const d = new THREE.Vector3(rand(-1, 1), rand(-0.6, 1), rand(-1, 1)).normalize().multiplyScalar(rand(0.8, 2.2));
      this.glow.spawn({ x: p.x, y: p.y, z: p.z, vx: d.x, vy: d.y, vz: d.z, r: 1, g: 0.75, b: 0.4, size: 0.035, life: rand(0.18, 0.4), drag: 3, grav: 3, flicker: 0.5 });
    }
    if (Math.random() < dt * 30) this.glow.spawn({ x: p.x, y: p.y, z: p.z, r: 1, g: 0.85, b: 0.6, size: 0.12, life: 0.08 });
  }

  /** A little splash / sparkle burst (task done, fish scooped). */
  sparkle(p: THREE.Vector3, color = new THREE.Color(1, 0.85, 0.55), n = 20, speed = 0.8): void {
    for (let i = 0; i < n; i++) {
      const d = new THREE.Vector3(rand(-1, 1), rand(0, 1.2), rand(-1, 1)).normalize().multiplyScalar(rand(0.3, 1) * speed);
      this.glow.spawn({ x: p.x, y: p.y, z: p.z, vx: d.x, vy: d.y, vz: d.z, r: color.r, g: color.g, b: color.b, size: 0.03, life: rand(0.5, 1.0), drag: 2.5, grav: 0.6, flicker: 0.3 });
    }
  }

  update(dt: number, her: THREE.Vector3, wind: THREE.Vector2, windK: number): void {
    this.updateShow(dt);
    this.updateSteam(dt);
    this.updatePetals(dt, her, wind, windK);
    this.glow.update(dt);
    this.petals.update(dt, { x: wind.x, z: wind.y, k: windK });
    this.puffs.update(dt, { x: wind.x, z: wind.y, k: windK * 0.5 });
    this.flashK *= Math.exp(-dt * 2.6);
    U.flashCol.value.copy(this.flash).multiplyScalar(this.flashK * 1.4);
  }

  get flashLevel(): number { return this.flashK; }
}

function chrysOr(kind: number, c: number, gold: number) {
  return kind === 1 || kind === 3 ? gold : c;
}
