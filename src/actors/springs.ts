import * as THREE from "three/webgpu";

/**
 * Secondary motion on bone chains (sleeves, hair locks, obi bow tails, kanzashi dangles): each
 * bone is a damped angular spring in world space. It lags behind the motion of its own pivot,
 * droops with gravity relative to the animated pose, and sways in the wind with gusts.
 * Applied after the animation mixer, on top of the clip pose.
 */
interface Link {
  bone: THREE.Bone;
  /** Angular offset state (axis-angle in world space, small angles: a vector). */
  ang: THREE.Vector3;
  vel: THREE.Vector3;
  prevPivot: THREE.Vector3;
  k: number;
  damp: number;
  gain: number;
  wind: number;
  phase: number;
  limit: number;
}

const _q = new THREE.Quaternion();
const _qp = new THREE.Quaternion();
const _qw = new THREE.Quaternion();
const _v = new THREE.Vector3();
const _a = new THREE.Vector3();
const _p = new THREE.Vector3();
const _dir = new THREE.Vector3();

export interface ChainSpec { prefix: string; stiff?: number; gain?: number; wind?: number; limit?: number }

export class Springs {
  private links: Link[] = [];
  private t = 0;

  constructor(root: THREE.Object3D, specs: ChainSpec[]) {
    const bones: THREE.Bone[] = [];
    root.traverse((o) => { if ((o as THREE.Bone).isBone) bones.push(o as THREE.Bone); });
    for (const s of specs) {
      const chain = bones.filter((b) => b.name.startsWith(s.prefix)).sort((a, b) => a.name.localeCompare(b.name));
      chain.forEach((bone, i) => {
        this.links.push({
          bone,
          ang: new THREE.Vector3(),
          vel: new THREE.Vector3(),
          prevPivot: bone.getWorldPosition(new THREE.Vector3()),
          k: (s.stiff ?? 60) * (1 - i * 0.18),
          damp: 7 - i * 0.8,
          gain: (s.gain ?? 1) * (1 + i * 0.35),
          wind: (s.wind ?? 1) * (1 + i * 0.5),
          phase: Math.random() * 6.28 + i * 0.7,
          limit: s.limit ?? 0.7,
        });
      });
    }
  }

  get count(): number { return this.links.length; }
  get bones(): THREE.Bone[] { return this.links.map((l) => l.bone); }

  /** wind: world xz direction × strength (0…1). */
  update(dt: number, wind: THREE.Vector2, windK: number): void {
    if (dt <= 0) return;
    dt = Math.min(dt, 1 / 30);
    this.t += dt;
    for (const L of this.links) {
      const b = L.bone;
      b.updateWorldMatrix(true, false);
      b.getWorldPosition(_p);
      // Pivot acceleration-ish: its velocity this frame, the chain swings the other way.
      _v.subVectors(_p, L.prevPivot).divideScalar(dt);
      L.prevPivot.copy(_p);
      if (_v.lengthSq() > 100) _v.set(0, 0, 0); // teleports
      // Drive: torque axis = up × (−velocity) so the bone trails behind; wind pushes downwind.
      const g = Math.sin(this.t * 2.3 + L.phase) * 0.5 + Math.sin(this.t * 3.7 + L.phase * 1.7) * 0.3;
      _dir.set(-_v.x * 0.11 + wind.x * windK * L.wind * (0.6 + 0.4 * g) * 0.35, 0, -_v.z * 0.11 + wind.y * windK * L.wind * (0.6 + 0.4 * g) * 0.35);
      _a.set(_dir.z, 0, -_dir.x).multiplyScalar(L.gain); // rotate about the horizontal axis ⟂ push
      // Vertical bounce adds a little twist forward/back.
      _a.x += -_v.y * 0.05 * L.gain;
      // Spring toward the drive.
      const ax = (_a.x - L.ang.x) * L.k - L.vel.x * L.damp;
      const ay = (_a.y - L.ang.y) * L.k - L.vel.y * L.damp;
      const az = (_a.z - L.ang.z) * L.k - L.vel.z * L.damp;
      L.vel.x += ax * dt; L.vel.y += ay * dt; L.vel.z += az * dt;
      L.ang.addScaledVector(L.vel, dt);
      const len = L.ang.length();
      if (len > L.limit) L.ang.multiplyScalar(L.limit / len);
      if (len < 1e-5) continue;
      // Apply: world rotation offset → local.
      _q.setFromAxisAngle(_dir.copy(L.ang).divideScalar(len), len);
      b.getWorldQuaternion(_qw);
      _qw.premultiply(_q);
      if (b.parent) {
        b.parent.getWorldQuaternion(_qp);
        _qp.invert();
        b.quaternion.copy(_qp.multiply(_qw));
      }
      b.updateMatrixWorld(true);
    }
  }

  reset(): void {
    for (const L of this.links) {
      L.ang.set(0, 0, 0);
      L.vel.set(0, 0, 0);
      L.bone.getWorldPosition(L.prevPivot);
    }
  }
}
