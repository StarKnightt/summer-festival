import * as THREE from "three/webgpu";

/**
 * The pieces of her animation system, after the three.js examples:
 *
 *  - Locomotion: idle, walk and run all play at once and are mixed by weight
 *    (webgl_animation_skinning_blending); walk and run share one stride phase so a foot never
 *    changes its mind mid-step while the weights cross (webgl_animation_walk), and the cadence
 *    follows the ground speed (rate = speed / the clip's own speed), so the feet don't slide.
 *    Weights ease, which is what makes the starts and stops soft.
 *  - Layers: small additive clips (a nod, a head shake, a look to either side) played on top of
 *    whatever the base is doing (webgl_animation_skinning_additive_blending).
 *  - IK: a CCD chain for a hand reaching to a point, and a clamped look-at down the upper
 *    spine, neck and head (webgl_animation_skinning_ik).
 */

const damp = (a: number, b: number, k: number, dt: number) => b + (a - b) * Math.exp(-k * dt);
const clamp = THREE.MathUtils.clamp;

export interface ClipInfo { duration: number; speed?: number; events?: Record<string, number> }

export class Locomotion {
  private idle: THREE.AnimationAction | null;
  private walk: THREE.AnimationAction | null;
  private run: THREE.AnimationAction | null;
  private w = { idle: 1, walk: 0, run: 0 };
  /** Shared stride phase 0..1 (walk's own clock; run is offset so the same foot lands). */
  phase = 0;
  private runOffset = 0;
  readonly vWalk: number;
  readonly vRun: number;

  constructor(actions: Map<string, THREE.AnimationAction>, info: Record<string, ClipInfo>) {
    this.idle = actions.get("idle") ?? null;
    this.walk = actions.get("walk") ?? null;
    this.run = actions.get("run") ?? null;
    this.vWalk = info.walk?.speed ?? 1.1;
    this.vRun = info.run?.speed ?? 2.8;
    for (const a of [this.idle, this.walk, this.run]) {
      if (!a) continue;
      a.setLoop(THREE.LoopRepeat, Infinity);
      a.clampWhenFinished = false;
      a.enabled = true;
      a.play();
      a.setEffectiveWeight(a === this.idle ? 1 : 0);
    }
    // Line the run up with the walk: left foot down at the same phase.
    const wl = info.walk?.events?.footDownL, rl = info.run?.events?.footDownL;
    if (wl !== undefined && rl !== undefined && this.walk && this.run) {
      this.runOffset = rl / this.run.getClip().duration - wl / this.walk.getClip().duration;
    }
  }

  /** `speed` in m/s over the ground; `layer` 0..1 scales the whole layer (poses and one-shots take from it). */
  update(dt: number, speed: number, layer: number): void {
    const { vWalk, vRun } = this;
    // Targets: idle below a shuffle, walk up to its natural speed, then run takes over.
    const moving = clamp(speed / 0.35, 0, 1);
    const r = clamp((speed - vWalk * 1.12) / (vRun * 0.9 - vWalk * 1.12), 0, 1);
    const tRun = moving * r * r * (3 - 2 * r);
    const tWalk = moving * (1 - tRun);
    const tIdle = 1 - moving;
    // Ease in quicker than out: a start reads at once, a stop settles.
    this.w.idle = damp(this.w.idle, tIdle, tIdle > this.w.idle ? 6 : 9, dt);
    this.w.walk = damp(this.w.walk, tWalk, 8, dt);
    this.w.run = damp(this.w.run, tRun, 7, dt);
    const sum = Math.max(1e-4, this.w.idle + this.w.walk + this.w.run);
    this.idle?.setEffectiveWeight((this.w.idle / sum) * layer);
    this.walk?.setEffectiveWeight((this.w.walk / sum) * layer);
    this.run?.setEffectiveWeight((this.w.run / sum) * layer);
    if (!this.walk || !this.run) return;
    // One cadence for both clips: strides per second from the ground speed, mixed by weight.
    const dw = this.walk.getClip().duration, dr = this.run.getClip().duration;
    const fWalk = clamp(speed / vWalk, 0.55, 1.5) / dw;
    const fRun = clamp(speed / vRun, 0.7, 1.35) / dr;
    const k = this.w.run / Math.max(1e-4, this.w.walk + this.w.run);
    const f = speed < 0.05 ? 1 / dw : fWalk + (fRun - fWalk) * k;
    this.phase = (this.phase + f * dt) % 1;
    // Drive the clip clocks directly from the shared phase (their own timeScale is parked).
    this.walk.timeScale = 0;
    this.run.timeScale = 0;
    this.walk.time = this.phase * dw;
    this.run.time = (((this.phase + this.runOffset) % 1) + 1) % 1 * dr;
  }
}

/** Additive clips layered over the base: one-shots (nod, shake) and held looks to the side. */
export class Layers {
  private acts = new Map<string, THREE.AnimationAction>();
  private side = 0;

  constructor(mixer: THREE.AnimationMixer, clips: THREE.AnimationClip[], refName = "add_ref") {
    const ref = clips.find((c) => c.name === refName);
    for (const c of clips) {
      if (!c.name.startsWith("add_") || c.name === refName) continue;
      const add = THREE.AnimationUtils.makeClipAdditive(c.clone(), 0, ref ?? c, 30);
      add.name = c.name;
      const a = mixer.clipAction(add);
      a.blendMode = THREE.AdditiveAnimationBlendMode;
      a.setLoop(THREE.LoopOnce, 1);
      a.clampWhenFinished = true;
      a.enabled = true;
      a.setEffectiveWeight(0);
      this.acts.set(c.name.slice(4), a);
    }
    // The side looks are poses: parked on their last frame and mixed in by weight.
    for (const n of ["look_l", "look_r"]) {
      const a = this.acts.get(n);
      if (!a) continue;
      a.play();
      a.paused = true;
      a.time = a.getClip().duration;
    }
  }

  has(name: string): boolean { return this.acts.has(name); }

  /** Plays a nod or a shake once on top of everything. */
  once(name: "nod" | "shake", weight = 1): void {
    const a = this.acts.get(name);
    if (!a) return;
    a.reset();
    a.setEffectiveWeight(weight);
    a.fadeIn(0.12);
    a.play();
    const d = a.getClip().duration;
    setTimeout(() => a.fadeOut(0.25), Math.max(0, d * 1000 - 120));
  }

  /** Eases the held look: −1 full left … +1 full right. */
  look(dt: number, side: number): void {
    this.side = damp(this.side, side, 3.5, dt);
    this.acts.get("look_l")?.setEffectiveWeight(Math.max(0, -this.side));
    this.acts.get("look_r")?.setEffectiveWeight(Math.max(0, this.side));
  }
}

const _a = new THREE.Vector3(), _b = new THREE.Vector3(), _p = new THREE.Vector3();
const _q = new THREE.Quaternion(), _qp = new THREE.Quaternion(), _qw = new THREE.Quaternion(), _id = new THREE.Quaternion();

/** Turns `bone` in world space by `q` (keeping its place in the hierarchy). */
function rotateWorld(bone: THREE.Object3D, q: THREE.Quaternion): void {
  bone.getWorldQuaternion(_qw).premultiply(q);
  bone.parent!.getWorldQuaternion(_qp).invert();
  bone.quaternion.copy(_qp.multiply(_qw));
  bone.updateMatrixWorld(true);
}

/**
 * CCD: turns each bone of `chain` (tip-most first) so the effector moves onto `target`, a few
 * passes, never more than `limits[i]` from where the animation had the bone; then blends the
 * result in by `weight`.
 */
export function ccd(chain: THREE.Object3D[], effector: THREE.Object3D, target: THREE.Vector3, limits: number[], weight: number, iterations = 6): void {
  if (weight <= 0.001) return;
  const anim = chain.map((b) => b.quaternion.clone());
  for (let it = 0; it < iterations; it++) {
    for (let i = 0; i < chain.length; i++) {
      const b = chain[i];
      b.getWorldPosition(_p);
      effector.getWorldPosition(_a).sub(_p);
      _b.copy(target).sub(_p);
      if (_a.lengthSq() < 1e-8 || _b.lengthSq() < 1e-8) continue;
      _q.setFromUnitVectors(_a.normalize(), _b.normalize());
      rotateWorld(b, _q);
      const from = anim[i];
      const ang = b.quaternion.angleTo(from);
      if (ang > limits[i]) { _q.copy(b.quaternion); b.quaternion.copy(from).rotateTowards(_q, limits[i]); b.updateMatrixWorld(true); }
    }
    if (effector.getWorldPosition(_a).distanceToSquared(target) < 1e-5) break;
  }
  if (weight < 0.999) chain.forEach((b, i) => { _q.copy(b.quaternion); b.quaternion.copy(anim[i]).slerp(_q, weight); b.updateMatrixWorld(true); });
}

/**
 * Look-at down the upper spine, neck and head. The head's own forward axis is aimed at a
 * direction given as yaw/pitch relative to her body (already clamped to a natural range by the
 * caller); each bone takes a share and is held to its own limit from the animated pose, so the
 * chain can never wind past what a neck does, whatever the clip underneath is doing.
 */
export class LookIK {
  /** Per-bone limits (radians) from the animated pose: together about 70°. */
  static readonly LIMITS = { spine2: 0.2, neck: 0.4, head: 0.64 };
  private chain: { bone: THREE.Object3D; limit: number; share: number }[] = [];
  private head: THREE.Object3D | null;
  /** Head-local forward and up, from the bind pose. */
  private fwd = new THREE.Vector3(0, 0, 1);

  constructor(bones: Map<string, THREE.Bone>, headRest: THREE.Matrix4 | null) {
    this.head = bones.get("head") ?? null;
    const add = (n: keyof typeof LookIK.LIMITS, share: number) => { const b = bones.get(n); if (b) this.chain.push({ bone: b, limit: LookIK.LIMITS[n], share }); };
    add("head", 0.55);
    add("neck", 0.5);
    add("spine2", 0.35);
    if (headRest) {
      const q = new THREE.Quaternion().setFromRotationMatrix(headRest).invert();
      this.fwd.set(0, 0, 1).applyQuaternion(q).normalize();
    }
  }

  /** `yaw`/`pitch`: where to look, relative to `heading`; `weight` blends it over the animation. */
  solve(heading: number, yaw: number, pitch: number, weight: number): void {
    if (!this.head || weight <= 0.001) return;
    const anim = this.chain.map((c) => c.bone.quaternion.clone());
    const cy = Math.cos(pitch);
    const want = new THREE.Vector3(Math.sin(heading + yaw) * cy, Math.sin(pitch), Math.cos(heading + yaw) * cy);
    for (let it = 0; it < 3; it++) {
      for (let i = 0; i < this.chain.length; i++) {
        const c = this.chain[i];
        this.head.getWorldQuaternion(_qw);
        _a.copy(this.fwd).applyQuaternion(_qw).normalize();
        _q.setFromUnitVectors(_a, want);
        // Each bone takes its share of what's left; the last pass takes all of it.
        _q.copy(_id.identity()).slerp(new THREE.Quaternion().setFromUnitVectors(_a, want), it === 2 ? 1 : c.share);
        rotateWorld(c.bone, _q);
        const ang = c.bone.quaternion.angleTo(anim[i]);
        if (ang > c.limit) { _q.copy(c.bone.quaternion); c.bone.quaternion.copy(anim[i]).rotateTowards(_q, c.limit); c.bone.updateMatrixWorld(true); }
      }
    }
    if (weight < 0.999) this.chain.forEach((c, i) => { _q.copy(c.bone.quaternion); c.bone.quaternion.copy(anim[i]).slerp(_q, weight); c.bone.updateMatrixWorld(true); });
  }

  /** Where the face points right now, in world space. */
  forward(out = new THREE.Vector3()): THREE.Vector3 {
    if (!this.head) return out.set(0, 0, 1);
    this.head.getWorldQuaternion(_qw);
    return out.copy(this.fwd).applyQuaternion(_qw).normalize();
  }

  /** The head's current facing as yaw relative to `heading` (for tests). */
  yawNow(heading: number): number {
    if (!this.head) return 0;
    this.head.getWorldQuaternion(_qw);
    _a.copy(this.fwd).applyQuaternion(_qw);
    const y = Math.atan2(_a.x, _a.z) - heading;
    return Math.atan2(Math.sin(y), Math.cos(y));
  }
}
