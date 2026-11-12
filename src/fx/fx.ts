import * as THREE from "three/webgpu";
import { Particles, type P } from "./particles";
import { U } from "../render/uniforms";
import type { Audio } from "../audio/audio";

const rand = (a: number, b: number) => a + Math.random() * (b - a);
type RGB = [number, number, number];
type Kind = "peony" | "peony2" | "chrys" | "willow" | "kamuro" | "crackle";
type Layer = "low" | "mid" | "high";
const SEA_Y = -2.05;
/** Burst heights (m above the sea) for the three layers of the show. */
const LAYERS: Record<Layer, [number, number]> = { low: [17, 23], mid: [27, 34], high: [38, 48] };
/** The final barrage window (s into the show). */
const FINALE: [number, number] = [50, 60];
const pickLayer = (): Layer => (["low", "mid", "high", "high"] as Layer[])[Math.floor(Math.random() * 4)];
const pickKind = (): Kind => (["peony", "peony2", "chrys", "chrys", "willow", "crackle"] as Kind[])[Math.floor(Math.random() * 6)];
const pickCol = (not?: RGB): RGB => {
  let c: RGB;
  do c = PALETTE[Math.floor(Math.random() * PALETTE.length)]; while (c === not);
  return c;
};
const PALETTE: RGB[] = [
  [1.0, 0.24, 0.1], // vermilion
  [1.0, 0.66, 0.16], // gold
  [0.2, 0.5, 1.0], // blue
  [1.0, 0.28, 0.66], // pink
  [0.3, 1.0, 0.36], // green
  [0.15, 0.9, 0.95], // cyan
  [0.62, 0.28, 1.0], // violet
  [1.0, 0.92, 0.8], // silver-white
];

/**
 * Every effect in the world: fireworks over the sea (shells, trails, bursts, glitter, the flash
 * on the water), steam from the food stalls, petals drifting on the breeze and sparkler sparks.
 */
export class Fx {
  readonly group = new THREE.Group();
  readonly glow = new Particles(32000, "glow", true, 4);
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
    this.group.add(this.glow.mesh, this.glow.reflection(SEA_Y, 0.4, 4, -122), this.petals.mesh, this.puffs.mesh);
    this.glow.onTrail = (p, dt) => this.trail(p, dt);
  }

  // ------------------------------------------------------------------ fireworks
  startShow(): void {
    if (this.show) return;
    this.show = true;
    this.showT = 0;
    this.cue = 0;
    this.pending.length = 0;
    this.schedule();
  }
  stopShow(): void { this.show = false; this.pending.length = 0; }

  /** Seconds since the show began (for capture). */
  get showTime(): number { return this.showT; }

  private pending: { t: number; kind: Kind; x: number; layer: Layer; col?: RGB }[] = [];
  private cue = 0;
  private encoreT = 0;

  /**
   * The programme (~65 s), built up front as a list of timed shells, then an unhurried encore:
   * openers; layered pairs low and high; a willow curtain over crackle; mixed salvos at every
   * height; a fan of chrysanthemums from one barge; the final barrage ending in gold kamuro.
   */
  private schedule() {
    const P = this.pending;
    const add = (t: number, kind: Kind, x = rand(-30, 30), layer: Layer = pickLayer(), col?: RGB) => P.push({ t, kind, x, layer, col });
    // Openers: single big shells, alternating sides.
    [1.2, 3.8, 6.2, 8.4].forEach((t, i) => add(t, i % 2 ? "chrys" : "peony", i % 2 ? rand(8, 22) : rand(-22, -8), "high"));
    // Layered pairs: a low and a high shell together, contrasting colours.
    for (let t = 10.5; t < 21; t += rand(1.5, 2.0)) {
      const c1 = pickCol(), c2 = pickCol(c1);
      add(t, "peony", rand(-25, 0), "low", c1);
      add(t + 0.25, Math.random() < 0.5 ? "chrys" : "peony2", rand(0, 25), "high", c2);
      if (Math.random() < 0.5) add(t + 0.6, "peony2", rand(-15, 15), "mid", pickCol(c2));
    }
    // Willow curtain across the bay, with crackle underneath.
    for (let i = 0; i < 5; i++) add(22 + i * 0.45, "willow", -28 + i * 14, "high");
    for (let i = 0; i < 4; i++) add(24 + i * 0.9, "crackle", rand(-20, 20), "low");
    // Mixed salvos at every height.
    for (let t = 30; t < 41; t += rand(0.8, 1.2)) {
      const n = 2 + Math.floor(Math.random() * 2);
      for (let k = 0; k < n; k++) add(t + k * 0.15, pickKind(), rand(-32, 32), (["low", "mid", "high"] as Layer[])[k % 3]);
    }
    // A fan of chrysanthemums from one barge.
    for (let i = 0; i < 6; i++) add(42 + i * 0.35, "chrys", -6 + i * 2.4, i % 2 ? "mid" : "high", [1.0, 0.72, 0.3]);
    add(45, "crackle", 0, "mid");
    // The final barrage.
    for (let t = FINALE[0]; t < FINALE[1]; t += rand(0.2, 0.32)) add(t, pickKind(), rand(-34, 34), pickLayer());
    for (let i = 0; i < 7; i++) add(FINALE[1] + i * 0.12, "kamuro", -30 + i * 10, "high");
    for (let i = 0; i < 5; i++) add(FINALE[1] + 0.8 + i * 0.1, "crackle", -24 + i * 12, "low");
    P.sort((a, b) => a.t - b.t);
  }

  private launch(kind: Kind, x: number, layer: Layer, col?: RGB) {
    const z = rand(-172, -142);
    const [h0, h1] = LAYERS[layer];
    const h = rand(h0, h1);
    const t = 1.3 + h * 0.018 + rand(0, 0.2);
    const gr = 9.8 * 0.35;
    const vy = h / t + 0.5 * gr * t;
    const shell = this.glow.spawn({
      x, y: SEA_Y + 0.2, z, vx: rand(-0.6, 0.6), vy, vz: rand(-0.6, 0.6), r: 1, g: 0.75, b: 0.45, size: 1.6,
      life: t, grav: gr, fade: 1, trail: 1, tag: 1,
    });
    if (!shell) return;
    const q = shell as any;
    q.burst = true;
    q.kind = kind;
    q.col = col ?? pickCol();
    // Higher shells are bigger (larger calibre).
    q.scale = layer === "high" ? 1.25 : layer === "mid" ? 1.0 : 0.72;
    this.audio?.firework(new THREE.Vector3(x, 0, z), new THREE.Vector3(x, h, z), t, kind === "crackle" || kind === "kamuro" || Math.random() < 0.3);
    this.shellsLaunched++;
  }

  private trail(p: P, dt: number) {
    if ((p as any).burst) {
      if (Math.random() < dt * 40) this.glow.spawn({ x: p.x, y: p.y, z: p.z, vx: rand(-0.3, 0.3), vy: rand(-1, 0), vz: rand(-0.3, 0.3), r: 1, g: 0.6, b: 0.3, a: 0.6, size: 0.9, life: 0.45, grav: 2 });
      if (p.age + dt >= p.life) this.burst(p);
      return;
    }
    // Crackle stars pop into tiny white flashes as they die.
    const pop = (p as any).pop as number | undefined;
    if (pop && p.age + dt >= p.life) {
      for (let i = 0; i < 7; i++) this.glow.spawn({ x: p.x + rand(-0.9, 0.9) * pop, y: p.y + rand(-0.9, 0.9) * pop, z: p.z + rand(-0.9, 0.9) * pop, vx: 0, vy: -0.3, vz: 0, r: 1, g: 0.97, b: 0.9, size: rand(0.7, 1.1) * pop, life: rand(0.1, 0.28), fade: 0 });
    }
    // Comet tails on chrysanthemum, willow and kamuro stars.
    const tr = p.trail ?? 0;
    if (Math.random() < dt * (tr > 1 ? 16 : 9)) this.glow.spawn({ x: p.x, y: p.y, z: p.z, vx: 0, vy: -0.4, vz: 0, r: p.r, g: p.g * 0.82, b: p.b * 0.55, a: 0.55 * (1 - p.age / p.life), size: p.size * 0.65, life: 0.4 + tr * 0.5, grav: 1.4, drag: 1 });
  }

  private sphere(n: number, i: number): RGB {
    const k = i + 0.5, phi = Math.acos(1 - (2 * k) / n), th = Math.PI * (1 + Math.sqrt(5)) * k;
    return [Math.sin(phi) * Math.cos(th), Math.cos(phi), Math.sin(phi) * Math.sin(th)];
  }

  private burst(s: P) {
    const q = s as any, kind: Kind = q.kind, sc: number = q.scale;
    const col: RGB = q.col;
    const gold: RGB = [1.0, 0.7, 0.28];
    const second = pickCol(col);
    const star = (dx: number, dy: number, dz: number, v: number, o: Partial<P>) => this.glow.spawn({
      x: s.x + dx * 0.6 * sc, y: s.y + dy * 0.6 * sc, z: s.z + dz * 0.6 * sc, vx: dx * v, vy: dy * v, vz: dz * v, fade: 1, ...o,
    });
    const speed = rand(10.5, 13) * sc;
    if (kind === "peony" || kind === "peony2") {
      const n = Math.round(170 * Math.min(1.2, sc));
      for (let i = 0; i < n; i++) {
        const [dx, dy, dz] = this.sphere(n, i);
        const c = kind === "peony2" && i % 2 ? second : col;
        star(dx, dy, dz, speed * rand(0.94, 1.04), { r: c[0], g: c[1], b: c[2], size: 2.4 * sc, life: rand(1.6, 2.2), drag: 1.25, grav: 3.0, flicker: 0.06 });
      }
      // Pistil: a small bright core of another colour.
      for (let i = 0; i < 50; i++) {
        const [dx, dy, dz] = this.sphere(50, i);
        star(dx, dy, dz, speed * 0.42, { r: second[0], g: second[1], b: second[2], size: 2.0 * sc, life: 1.3, drag: 1.4, grav: 2.5 });
      }
    } else if (kind === "chrys") {
      const n = Math.round(150 * Math.min(1.2, sc));
      const c = Math.random() < 0.3 ? gold : col;
      for (let i = 0; i < n; i++) {
        const [dx, dy, dz] = this.sphere(n, i);
        star(dx, dy, dz, speed * rand(0.95, 1.03), { r: c[0], g: c[1], b: c[2], size: 2.2 * sc, life: rand(1.9, 2.5), drag: 1.2, grav: 3.0, trail: 0.5, flicker: 0.05 });
      }
      // An inner shell of a second colour.
      for (let i = 0; i < 60; i++) {
        const [dx, dy, dz] = this.sphere(60, i);
        star(dx, dy, dz, speed * 0.7, { r: second[0], g: second[1], b: second[2], size: 1.8 * sc, life: rand(1.6, 2.0), drag: 1.3, grav: 2.6 });
      }
    } else if (kind === "willow" || kind === "kamuro") {
      const n = kind === "kamuro" ? 140 : 110;
      for (let i = 0; i < n; i++) {
        const [dx, dy, dz] = this.sphere(n, i);
        star(dx, dy * 0.85 + 0.15, dz, speed * rand(0.8, 1.0) * (kind === "kamuro" ? 1.1 : 0.9), { r: gold[0], g: gold[1] * 0.95, b: gold[2], size: 1.9 * sc, life: rand(3.6, 4.6), drag: 1.7, grav: 2.0, trail: 1.6, flicker: kind === "kamuro" ? 0.25 : 0.05 });
      }
    } else {
      // Crackle: gold stars fly out, then each pops into a cluster of tiny white flashes.
      for (let i = 0; i < 70; i++) {
        const [dx, dy, dz] = this.sphere(70, i);
        const st = star(dx, dy, dz, speed * rand(0.7, 0.85), { r: gold[0], g: gold[1], b: gold[2], size: 1.3 * sc, life: rand(0.8, 1.1), drag: 1.3, grav: 2.5, trail: 0.2 });
        if (st) (st as any).pop = sc;
      }
    }
    // Some bursts end in a fizz of glitter on a shell around them.
    if (kind !== "crackle" && Math.random() < 0.3) {
      for (let i = 0; i < 60; i++) {
        const [dx, dy, dz] = this.sphere(60, i);
        star(dx, dy, dz, speed * rand(0.55, 0.75), { r: 1, g: 0.92, b: 0.75, a: 0.8, size: 0.9 * sc, life: rand(1.8, 2.6), drag: 1.4, grav: 2, flicker: 0.95 });
      }
    }
    // Light the sea and the sky haze.
    const fc = kind === "willow" || kind === "kamuro" || kind === "crackle" ? gold : col;
    this.flash.setRGB(fc[0], fc[1], fc[2]).multiplyScalar(0.6 + 0.4 * sc);
    this.flashK = 1;
    U.flashPos.value.set(s.x, s.y, s.z);
  }

  private updateShow(dt: number) {
    if (!this.show) return;
    this.showT += dt;
    const P = this.pending;
    while (this.cue < P.length && P[this.cue].t <= this.showT) {
      const c = P[this.cue++];
      this.launch(c.kind, c.x, c.layer, c.col);
    }
    // After the programme: an unhurried encore while she stays on the beach.
    if (this.cue >= P.length && this.showT > FINALE[1] + 12) {
      this.encoreT -= dt;
      if (this.encoreT <= 0) {
        this.encoreT = rand(3.5, 7);
        this.launch(pickKind(), rand(-28, 28), pickLayer());
        if (Math.random() < 0.4) this.launch(pickKind(), rand(-28, 28), pickLayer());
      }
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
