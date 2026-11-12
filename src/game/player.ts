import * as THREE from "three/webgpu";
import type { Input } from "../core/input";
import type { Heroine } from "../actors/heroine";
import type { Collider } from "../world/town";

const WALK = 1.15;
const RUN = 2.75;
const RADIUS = 0.28;

const dampAngle = (a: number, b: number, k: number, dt: number) => {
  let d = ((b - a + Math.PI) % (Math.PI * 2)) - Math.PI;
  if (d < -Math.PI) d += Math.PI * 2;
  return a + d * (1 - Math.exp(-k * dt));
};

/**
 * Walks her through the town: camera-relative WASD, a soft acceleration (no snapping), turns
 * that ease round, and circle-vs-box collisions against houses, stalls, gate posts and walls.
 * Other people push her gently aside instead of blocking.
 */
export class Player {
  enabled = true;
  private vel = new THREE.Vector2();
  /** Extra round obstacles this frame (people, cats). */
  circles: { x: number; z: number; r: number }[] = [];
  distance = 0;
  private idleT = 0;

  constructor(
    private her: Heroine,
    private colliders: Collider[],
    private groundY: (x: number, z: number) => number,
  ) {}

  update(dt: number, input: Input, camYaw: number): void {
    const her = this.her;
    let ix = 0, iy = 0, run = false;
    if (this.enabled) ({ x: ix, y: iy, run } = input.axis());
    const len = Math.hypot(ix, iy);
    // Camera forward is −(sin yaw, cos yaw) (the camera sits behind her).
    const fx = -Math.sin(camYaw), fz = -Math.cos(camYaw);
    const rx = -fz, rz = fx;
    let tx = 0, tz = 0;
    if (len > 0) {
      tx = (fx * iy + rx * ix) / len;
      tz = (fz * iy + rz * ix) / len;
    }
    const target = len > 0 ? (run ? RUN : WALK) : 0;
    const k = target > this.vel.length() ? 5.5 : 7;
    this.vel.x += (tx * target - this.vel.x) * (1 - Math.exp(-k * dt));
    this.vel.y += (tz * target - this.vel.y) * (1 - Math.exp(-k * dt));
    const sp = this.vel.length();
    if (len > 0) {
      her.heading = dampAngle(her.heading, Math.atan2(tx, tz), 9, dt);
      this.idleT = 0;
    } else if (this.enabled) {
      // Standing still: after a moment she turns to face down the street (toward the sea).
      this.idleT += dt;
      if (this.idleT > 1.2) her.heading = dampAngle(her.heading, Math.PI, 2.2, dt);
    }

    const p = her.position;
    const ox = p.x, oz = p.z;
    p.x += this.vel.x * dt;
    p.z += this.vel.y * dt;
    this.resolve(p);
    // The sea: no further than ankle-deep.
    p.z = Math.max(p.z, -125);
    const moved = Math.hypot(p.x - ox, p.z - oz);
    this.distance += moved;
    her.speed = dt > 0 ? Math.min(sp, moved / dt + 0.0001) : 0;
    const gy = this.groundY(p.x, p.z);
    p.y += (gy - p.y) * (1 - Math.exp(-18 * dt));
  }

  /** Push her out of every box and circle. */
  resolve(p: THREE.Vector3): void {
    for (let it = 0; it < 2; it++) {
      for (const c of this.colliders) {
        const cx = Math.max(c.x0, Math.min(p.x, c.x1));
        const cz = Math.max(c.z0, Math.min(p.z, c.z1));
        const dx = p.x - cx, dz = p.z - cz;
        const d2 = dx * dx + dz * dz;
        if (d2 >= RADIUS * RADIUS) continue;
        if (d2 > 1e-8) {
          const d = Math.sqrt(d2);
          p.x = cx + (dx / d) * RADIUS;
          p.z = cz + (dz / d) * RADIUS;
        } else {
          // Inside: leave by the nearest face.
          const l = p.x - c.x0, r = c.x1 - p.x, b = p.z - c.z0, f = c.z1 - p.z;
          const m = Math.min(l, r, b, f);
          if (m === l) p.x = c.x0 - RADIUS; else if (m === r) p.x = c.x1 + RADIUS; else if (m === b) p.z = c.z0 - RADIUS; else p.z = c.z1 + RADIUS;
        }
      }
      for (const c of this.circles) {
        const dx = p.x - c.x, dz = p.z - c.z;
        const d = Math.hypot(dx, dz), m = RADIUS + c.r;
        if (d < m && d > 1e-4) {
          const push = (m - d) * 0.5;
          p.x += (dx / d) * push;
          p.z += (dz / d) * push;
        }
      }
    }
  }
}
