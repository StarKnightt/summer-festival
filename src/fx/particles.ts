// @ts-nocheck -- TSL node graphs: @types/three node typings reject valid swizzles/overloads.
import * as THREE from "three/webgpu";
import { instancedDynamicBufferAttribute, uv, vec4, float, smoothstep, length, vec2, Fn, mix } from "three/tsl";
import { U } from "../render/uniforms";

/**
 * A CPU-simulated pool of camera-facing sprites drawn in one instanced call: position, colour
 * (rgb + alpha), size and spin per particle are uploaded each frame. Shapes: soft glow dot
 * (fireworks, sparks, embers), petal (blossom drifting in the breeze) and puff (steam, smoke).
 */
export type Shape = "glow" | "petal" | "puff";

export interface P {
  x: number; y: number; z: number;
  vx: number; vy: number; vz: number;
  r: number; g: number; b: number; a: number;
  size: number; grow: number;
  life: number; age: number;
  drag: number; grav: number;
  spin: number; rot: number;
  /** Fade: 0 = linear, 1 = hold then fade, 2 = in and out. */
  fade: number;
  flicker: number;
  /** For fireworks trails: emits sparks while flying. */
  trail?: number;
  tag?: number;
}

export class Particles {
  readonly mesh: THREE.Sprite;
  private pos: THREE.InstancedBufferAttribute;
  private col: THREE.InstancedBufferAttribute;
  private siz: THREE.InstancedBufferAttribute;
  private rot: THREE.InstancedBufferAttribute;
  readonly list: P[] = [];
  /** Called for each live particle with a trail, every frame (spawn trail sparks). */
  onTrail: ((p: P, dt: number) => void) | null = null;

  constructor(readonly max: number, shape: Shape, additive: boolean, hdr = 1) {
    this.pos = new THREE.InstancedBufferAttribute(new Float32Array(max * 3), 3);
    this.col = new THREE.InstancedBufferAttribute(new Float32Array(max * 4), 4);
    this.siz = new THREE.InstancedBufferAttribute(new Float32Array(max), 1);
    this.rot = new THREE.InstancedBufferAttribute(new Float32Array(max), 1);
    for (const a of [this.pos, this.col, this.siz, this.rot]) a.setUsage(THREE.DynamicDrawUsage);
    const m = new THREE.SpriteNodeMaterial({ transparent: true, depthWrite: false, blending: additive ? THREE.AdditiveBlending : THREE.NormalBlending });
    m.positionNode = instancedDynamicBufferAttribute(this.pos);
    m.scaleNode = instancedDynamicBufferAttribute(this.siz);
    m.rotationNode = instancedDynamicBufferAttribute(this.rot);
    const c = instancedDynamicBufferAttribute(this.col);
    m.fog = !additive;
    m.colorNode = Fn(() => {
      const p = uv().sub(0.5).mul(2.0);
      if (shape === "glow") {
        const d = length(p);
        const core = smoothstep(0.3, 0.0, d);
        const halo = smoothstep(1.0, 0.0, d).pow(3.0).mul(0.22);
        const k = core.add(halo);
        // Hot white core, coloured halo.
        const rgb = mix(c.rgb, vec3w(c.rgb), core.mul(0.6));
        // HDR: sparks are far brighter than the lantern paper so they bloom.
        return vec4(rgb.mul(k).mul(c.a).mul(hdr), k.mul(c.a));
      }
      if (shape === "petal") {
        const q = vec2(p.x.mul(1.6), p.y.add(p.x.mul(p.x).mul(0.35)));
        const d = length(q);
        const a = smoothstep(1.0, 0.82, d);
        const shade = float(0.85).add(p.y.mul(0.15));
        return vec4(c.rgb.mul(shade).mul(U.worldTint.mul(0.6).add(0.4)), a.mul(c.a));
      }
      const d = length(p);
      const a = smoothstep(1.0, 0.1, d).pow(1.6);
      return vec4(c.rgb.mul(U.worldTint.mul(0.5).add(0.5)), a.mul(c.a));
    })();
    this.mesh = new THREE.Sprite(m);
    this.mesh.count = 0;
    this.mesh.frustumCulled = false;
    this.mesh.renderOrder = additive ? 5 : 4;
  }

  spawn(p: Partial<P>): P | null {
    if (this.list.length >= this.max) return null;
    const q: P = {
      x: 0, y: 0, z: 0, vx: 0, vy: 0, vz: 0, r: 1, g: 1, b: 1, a: 1, size: 0.05, grow: 0,
      life: 1, age: 0, drag: 0, grav: 0, spin: 0, rot: Math.random() * 6.28, fade: 0, flicker: 0, ...p,
    };
    this.list.push(q);
    return q;
  }

  update(dt: number, wind?: { x: number; z: number; k: number }): void {
    const L = this.list;
    let n = 0;
    const pa = this.pos.array as Float32Array, ca = this.col.array as Float32Array, sa = this.siz.array as Float32Array, ra = this.rot.array as Float32Array;
    for (let i = 0; i < L.length; i++) {
      const p = L[i];
      p.age += dt;
      if (p.age >= p.life) continue;
      const dr = Math.exp(-p.drag * dt);
      p.vx *= dr; p.vy *= dr; p.vz *= dr;
      p.vy -= p.grav * dt;
      if (wind && p.drag > 0) { p.vx += wind.x * wind.k * p.drag * dt * 0.6; p.vz += wind.z * wind.k * p.drag * dt * 0.6; }
      p.x += p.vx * dt; p.y += p.vy * dt; p.z += p.vz * dt;
      p.rot += p.spin * dt;
      p.size += p.grow * dt;
      if (p.trail && this.onTrail) this.onTrail(p, dt);
      const t = p.age / p.life;
      let a = p.fade === 0 ? 1 - t : p.fade === 1 ? (t < 0.6 ? 1 : 1 - (t - 0.6) / 0.4) : Math.sin(Math.PI * t);
      // Bursts start with every star in one point: ease them in so they don't stack into a white ball.
      if (p.fade === 1 && p.age < 0.3) a *= (p.age / 0.3) * (p.age / 0.3);
      if (p.flicker > 0) a *= 1 - p.flicker * (Math.random() < 0.3 ? 0.8 : 0);
      a *= p.a;
      pa[n * 3] = p.x; pa[n * 3 + 1] = p.y; pa[n * 3 + 2] = p.z;
      ca[n * 4] = p.r; ca[n * 4 + 1] = p.g; ca[n * 4 + 2] = p.b; ca[n * 4 + 3] = a;
      sa[n] = p.size;
      ra[n] = p.rot;
      L[n++] = p;
    }
    L.length = n;
    this.mesh.count = Math.max(1, n);
    this.mesh.visible = n > 0;
    for (const a of [this.pos, this.col, this.siz, this.rot]) {
      a.clearUpdateRanges();
      a.addUpdateRange(0, n * a.itemSize);
      a.needsUpdate = true;
    }
  }
}

/** Push a colour toward white (hot core of a spark). */
function vec3w(c) {
  return mix(c, c.max(0.0).add(1.0).mul(0.5).add(0.5), 0.7);
}
