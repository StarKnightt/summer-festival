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

  /** A blocker added after the world was built (benches and other props from the moments). */
  addCollider(c: Collider): void { this.colliders.push(c); }

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
      // Looking at something past her neck's range: turn the body toward it.
      if (her.bodyTurn !== 0) her.heading = dampAngle(her.heading, her.heading + her.bodyTurn, 2.5, dt);
      else if (this.idleT > 1.2 && !her.lookTarget) her.heading = dampAngle(her.heading, Math.PI, 2.2, dt);
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

  /** Push her out of every box, oriented box and circle. */
  resolve(p: THREE.Vector3): void {
    for (let it = 0; it < 2; it++) {
      for (const c of this.colliders) {
        if (p.x < c.x0 - RADIUS || p.x > c.x1 + RADIUS || p.z < c.z0 - RADIUS || p.z > c.z1 + RADIUS) continue;
        if (c.circle) {
          const dx = p.x - c.circle.x, dz = p.z - c.circle.z, d = Math.hypot(dx, dz), m = c.circle.r + RADIUS;
          if (d >= m) continue;
          if (d > 1e-4) { p.x = c.circle.x + (dx / d) * m; p.z = c.circle.z + (dz / d) * m; } else p.x = c.circle.x + m;
          continue;
        }
        if (c.ob) {
          // Into the box's own frame, resolve as an axis-aligned box, and back out.
          const o = c.ob, cs = Math.cos(o.ang), sn = Math.sin(o.ang);
          const wx = p.x - o.x, wz = p.z - o.z;
          const q = { x: wx * cs - wz * sn, z: wx * sn + wz * cs };
          if (boxOut(q, -o.hx, o.hx, -o.hz, o.hz)) {
            p.x = o.x + q.x * cs + q.z * sn;
            p.z = o.z - q.x * sn + q.z * cs;
          }
          continue;
        }
        boxOut(p, c.x0, c.x1, c.z0, c.z1);
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

/** Circle (her) out of an axis-aligned box; true if it moved her. */
function boxOut(p: { x: number; z: number }, x0: number, x1: number, z0: number, z1: number): boolean {
  const cx = Math.max(x0, Math.min(p.x, x1));
  const cz = Math.max(z0, Math.min(p.z, z1));
  const dx = p.x - cx, dz = p.z - cz;
  const d2 = dx * dx + dz * dz;
  if (d2 >= RADIUS * RADIUS) return false;
  if (d2 > 1e-8) {
    const d = Math.sqrt(d2);
    p.x = cx + (dx / d) * RADIUS;
    p.z = cz + (dz / d) * RADIUS;
  } else {
    // Inside: leave by the nearest face.
    const l = p.x - x0, r = x1 - p.x, b = p.z - z0, f = z1 - p.z;
    const m = Math.min(l, r, b, f);
    if (m === l) p.x = x0 - RADIUS; else if (m === r) p.x = x1 + RADIUS; else if (m === b) p.z = z0 - RADIUS; else p.z = z1 + RADIUS;
  }
  return true;
}
