import * as THREE from "three/webgpu";
import type { Input } from "./input";

const damp = (a: number, b: number, k: number, dt: number) => b + (a - b) * Math.exp(-k * dt);
const dampAngle = (a: number, b: number, k: number, dt: number) => {
  let d = ((b - a + Math.PI) % (Math.PI * 2)) - Math.PI;
  if (d < -Math.PI) d += Math.PI * 2;
  return a + d * (1 - Math.exp(-k * dt));
};

/**
 * Close third-person camera. It sits ~3.2 m behind her at about head height, eases after her
 * heading when she walks and the player isn't steering, and never leaves the street corridor
 * (so there are no wide views). A "shot" (mini-game framing, fireworks) can take over; the
 * camera blends to it and back over ~1 s.
 */
export class CameraRig {
  yaw = Math.PI; // looking toward −Z (down the street)
  pitch = 0.12;
  dist = 3.3;
  private distGoal = 3.3;
  private readonly target = new THREE.Vector3();
  private readonly pos = new THREE.Vector3();
  private shot: { pos: THREE.Vector3; look: THREE.Vector3 } | null = null;
  private shotK = 0;
  private readonly shotPos = new THREE.Vector3();
  private readonly shotLook = new THREE.Vector3();
  private idleT = 0;
  /** Extra upward look (fireworks). */
  lookUp = 0;
  private lookUpCur = 0;
  /** Clamp so the camera stays in the walkable corridor (x half-width, z range). */
  bounds = (p: THREE.Vector3) => p;

  constructor(readonly camera: THREE.PerspectiveCamera) {}

  setShot(pos: THREE.Vector3 | null, look?: THREE.Vector3): void {
    if (pos && look) {
      this.shot = { pos: pos.clone(), look: look.clone() };
    } else this.shot = null;
  }
  get inShot(): boolean { return this.shotK > 0.01; }

  snap(herPos: THREE.Vector3, heading: number): void {
    this.yaw = heading + Math.PI;
    this.update(0, herPos, heading, 0, null, true);
  }

  update(dt: number, herPos: THREE.Vector3, heading: number, speed: number, input: Input | null, snap = false): void {
    if (input && !input.captureMouse) {
      this.yaw -= input.dragX * 0.0042;
      this.pitch = THREE.MathUtils.clamp(this.pitch + input.dragY * 0.003, -0.25, 0.75);
      this.distGoal = THREE.MathUtils.clamp(this.distGoal + input.wheel * 0.35, 2.2, 4.6);
      if (input.dragX !== 0 || input.dragY !== 0) this.idleT = 0;
    }
    this.idleT += dt;
    // Ease behind her while she walks and the player isn't orbiting.
    if (speed > 0.3 && this.idleT > 1.2) this.yaw = dampAngle(this.yaw, heading + Math.PI, 1.1 * Math.min(1, speed / 1.2), dt);
    this.dist = snap ? this.distGoal : damp(this.dist, this.distGoal, 4, dt);
    this.lookUpCur = snap ? this.lookUp : damp(this.lookUpCur, this.lookUp, 1.2, dt);

    const head = new THREE.Vector3(herPos.x, herPos.y + 1.45, herPos.z);
    const pitch = this.pitch - this.lookUpCur * 0.1;
    const back = new THREE.Vector3(Math.sin(this.yaw) * Math.cos(pitch), Math.sin(pitch), Math.cos(this.yaw) * Math.cos(pitch));
    const want = head.clone().addScaledVector(back, this.dist * (1 - this.lookUpCur * 0.15));
    want.y = Math.max(want.y, herPos.y + 0.5);
    this.bounds(want);
    if (snap) { this.pos.copy(want); this.target.copy(head); }
    else {
      this.pos.x = damp(this.pos.x, want.x, 10, dt);
      this.pos.y = damp(this.pos.y, want.y, 8, dt);
      this.pos.z = damp(this.pos.z, want.z, 10, dt);
      this.target.x = damp(this.target.x, head.x, 14, dt);
      this.target.y = damp(this.target.y, head.y, 8, dt);
      this.target.z = damp(this.target.z, head.z, 14, dt);
    }
    // Look a little ahead and up when the fireworks are on.
    const look = this.target.clone().add(new THREE.Vector3(0, 0.15 + this.lookUpCur * 0.75, 0));

    // Blend toward a framed shot.
    this.shotK = snap ? (this.shot ? 1 : 0) : damp(this.shotK, this.shot ? 1 : 0, 2.6, dt);
    if (this.shot) {
      this.shotPos.copy(this.shot.pos);
      this.shotLook.copy(this.shot.look);
    }
    const e = this.shotK * this.shotK * (3 - 2 * this.shotK);
    const p = this.pos.clone().lerp(this.shotPos, e);
    const l = look.lerp(this.shotLook, e);
    this.camera.position.copy(p);
    this.camera.lookAt(l);
    const fov = 55 - e * 8 + this.lookUpCur * 10;
    if (Math.abs(this.camera.fov - fov) > 0.01) {
      this.camera.fov = fov;
      this.camera.updateProjectionMatrix();
    }
  }
}
