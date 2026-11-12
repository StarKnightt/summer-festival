import * as THREE from "three/webgpu";
import { ToonMaterial } from "../render/toon";
import { STALLS, stallX } from "../world/layout";

/**
 * Two street animals with their own little lives:
 *  - a shiba that sits by the middle gate; when she comes close it trots over and follows her for
 *    a while (tail going), then loses interest and trots home again;
 *  - a cat sitting in front of the houses; if she runs near it (or walks right up to it), it bolts
 *    and ducks under the nearest stall, and comes back much later when she's gone.
 *
 * Both are small procedural quadrupeds. Each leg is a two-bone chain solved by IK onto a foot
 * target that, during stance, stays fixed on the ground while the body moves over it (stride
 * length × cadence = speed), so the paws never slide. Trot for the dog, gallop for the cat.
 */

const rand = (a: number, b: number) => a + Math.random() * (b - a);
const dampAngle = (a: number, b: number, k: number, dt: number) => {
  let d = b - a;
  while (d > Math.PI) d -= Math.PI * 2;
  while (d < -Math.PI) d += Math.PI * 2;
  return a + d * (1 - Math.exp(-k * dt));
};
const damp = (a: number, b: number, k: number, dt: number) => a + (b - a) * (1 - Math.exp(-k * dt));

interface Spec {
  hipY: number; upper: number; lower: number; halfLen: number; halfW: number;
  bodyR: number; coat: string; belly: string; dark: string; cat: boolean;
}

interface Leg { hip: THREE.Group; knee: THREE.Group; front: boolean; side: number; off: number; fx: number; fy: number }

class Quadruped {
  readonly root = new THREE.Group();
  readonly body = new THREE.Group();
  readonly head = new THREE.Group();
  readonly tail = new THREE.Group();
  private tailSegs: THREE.Group[] = [];
  private legs: Leg[] = [];
  pos = new THREE.Vector3();
  heading = 0;
  speed = 0;
  /** 0 = standing, 1 = sitting. */
  sit = 0;
  /** Tail wag amount 0..1; head yaw/pitch offsets (radians). */
  wag = 0;
  lookYaw = 0;
  lookPitch = 0;
  private phase = 0;
  private t = rand(0, 10);
  gallop = false;

  constructor(readonly s: Spec) {
    const coat = new ToonMaterial({ color: s.coat, paint: 0.25, rim: 0.45 });
    const belly = new ToonMaterial({ color: s.belly, paint: 0.2, rim: 0.4 });
    const dark = new ToonMaterial({ color: s.dark, paint: 0, rim: 0.2 });
    const mesh = (g: THREE.BufferGeometry, m: THREE.Material) => { const o = new THREE.Mesh(g, m); o.castShadow = true; return o; };
    this.root.add(this.body);
    this.body.position.y = s.hipY;
    // Body: a capsule along z, a lighter chest/belly under it.
    const torso = mesh(new THREE.CapsuleGeometry(s.bodyR, s.halfLen * 2 - s.bodyR * 0.6, 6, 14), coat);
    torso.rotation.x = Math.PI / 2;
    torso.scale.set(1, 1, s.cat ? 0.92 : 1.05);
    torso.position.y = s.bodyR * 0.35;
    const chest = mesh(new THREE.SphereGeometry(s.bodyR * 0.92, 14, 10), belly);
    chest.scale.set(0.9, 0.85, 1.25);
    chest.position.set(0, s.bodyR * 0.15, s.halfLen * 0.55);
    this.body.add(torso, chest);
    // Head.
    this.head.position.set(0, s.bodyR * (s.cat ? 1.5 : 1.3), s.halfLen + s.bodyR * (s.cat ? 0.75 : 0.55));
    this.body.add(this.head);
    const hr = s.bodyR * (s.cat ? 0.95 : 0.88);
    const skull = mesh(new THREE.SphereGeometry(hr, 16, 12), coat);
    skull.scale.set(s.cat ? 1.08 : 1, 0.95, 1);
    const snout = mesh(new THREE.SphereGeometry(hr * (s.cat ? 0.34 : 0.55), 12, 8), belly);
    snout.scale.set(1, 0.75, s.cat ? 0.8 : 1.35);
    snout.position.set(0, -hr * (s.cat ? 0.3 : 0.28), hr * (s.cat ? 0.82 : 0.95));
    const nose = mesh(new THREE.SphereGeometry(hr * (s.cat ? 0.1 : 0.14), 8, 6), dark);
    nose.position.set(0, -hr * (s.cat ? 0.12 : 0.1), hr * (s.cat ? 1.12 : 1.62));
    this.head.add(skull, snout, nose);
    for (const sd of [-1, 1]) {
      const ear = mesh(new THREE.ConeGeometry(hr * (s.cat ? 0.5 : 0.5), hr * (s.cat ? 0.95 : 0.95), 4), coat);
      ear.position.set(sd * hr * (s.cat ? 0.6 : 0.55), hr * 0.85, -hr * 0.05);
      ear.rotation.set(-0.12, Math.PI / 4, sd * -0.32);
      ear.scale.set(1, 1, 0.45);
      const eye = mesh(new THREE.SphereGeometry(hr * 0.11, 8, 6), dark);
      eye.position.set(sd * hr * 0.42, hr * 0.12, hr * 0.84);
      eye.scale.set(1, s.cat ? 1.25 : 1, 0.6);
      this.head.add(ear, eye);
      if (s.cat) {
        // Whisker pads.
        const pad = mesh(new THREE.SphereGeometry(hr * 0.2, 8, 6), belly);
        pad.position.set(sd * hr * 0.17, -hr * 0.32, hr * 0.95);
        this.head.add(pad);
      }
    }
    if (!s.cat) {
      // A red collar.
      const collar = mesh(new THREE.TorusGeometry(hr * 0.78, hr * 0.1, 6, 18), new ToonMaterial({ color: "#b8282c", paint: 0, rim: 0.3 }));
      collar.position.set(0, -hr * 0.55, -hr * 0.45);
      collar.rotation.x = Math.PI / 2 + 0.5;
      this.head.add(collar);
    }
    // Tail: a chain of segments off the rump.
    this.tail.position.set(0, s.bodyR * 0.75, -s.halfLen - s.bodyR * 0.2);
    this.body.add(this.tail);
    let parent: THREE.Object3D = this.tail;
    const n = s.cat ? 7 : 4, segLen = s.cat ? 0.05 : 0.05;
    for (let i = 0; i < n; i++) {
      const seg = new THREE.Group();
      if (i) seg.position.z = -segLen;
      const r = s.cat ? 0.017 : 0.028 - i * 0.002;
      const piece = mesh(new THREE.CapsuleGeometry(r, segLen, 3, 8), i === n - 1 && !s.cat ? belly : coat);
      piece.rotation.x = Math.PI / 2;
      piece.position.z = -segLen / 2;
      seg.add(piece);
      parent.add(seg);
      this.tailSegs.push(seg);
      parent = seg;
    }
    // Legs: two-bone chains from the hips/shoulders.
    const legMat = coat, pawMat = belly;
    for (const front of [true, false]) for (const side of [-1, 1]) {
      const hip = new THREE.Group();
      hip.position.set(side * s.halfW, 0, front ? s.halfLen * 0.82 : -s.halfLen * 0.82);
      const up = mesh(new THREE.CapsuleGeometry(s.bodyR * (front ? 0.33 : 0.42) * (s.cat ? 0.8 : 1), s.upper, 3, 8), legMat);
      up.position.y = -s.upper / 2;
      const knee = new THREE.Group();
      knee.position.y = -s.upper;
      const lo = mesh(new THREE.CapsuleGeometry(s.bodyR * (s.cat ? 0.2 : 0.25), s.lower, 3, 8), front && !s.cat ? pawMat : legMat);
      lo.position.y = -s.lower / 2;
      const paw = mesh(new THREE.SphereGeometry(s.bodyR * 0.3, 8, 6), pawMat);
      paw.scale.set(1, 0.6, 1.35);
      paw.position.set(0, -s.lower, s.bodyR * 0.1);
      knee.add(lo, paw);
      hip.add(up, knee);
      this.body.add(hip);
      // Trot: diagonal pairs together. (Gallop offsets are set per frame.)
      const off = (front ? 0 : 0.5) + (side > 0 ? 0.5 : 0);
      this.legs.push({ hip, knee, front, side, off: off % 1, fx: 0, fy: -s.hipY });
    }
  }

  /** Advances the gait and pose; place the root first (pos / heading / speed). */
  update(dt: number, groundY: number): void {
    const s = this.s;
    this.t += dt;
    this.root.position.set(this.pos.x, groundY, this.pos.z);
    this.root.rotation.y = this.heading;
    const v = this.speed;
    const moving = Math.min(1, v / 0.15);
    const reach = s.upper + s.lower;
    // Stride grows with speed; cadence = speed / stride, so a planted paw keeps still.
    const stride = Math.min(reach * (this.gallop ? 1.5 : 1.05), reach * 0.45 + v * (this.gallop ? 0.2 : 0.16));
    this.phase = (this.phase + (v / stride) * dt) % 1;
    const duty = this.gallop ? 0.38 : 0.58;
    const sitK = this.sit * (1 - moving);
    // Body first: bob at the step rate, haunches down and chest up when sitting.
    const cyc = this.phase * Math.PI * 2;
    const bob = Math.abs(Math.sin(cyc * (this.gallop ? 1 : 2))) * reach * (this.gallop ? 0.12 : 0.045) * moving;
    this.body.position.y = s.hipY - reach * 0.02 + bob - sitK * s.hipY * 0.2;
    this.body.position.z = -sitK * s.halfLen * 0.3;
    this.body.rotation.x = -sitK * (s.cat ? 0.7 : 0.5) + (this.gallop ? Math.sin(cyc) * 0.12 * moving : 0);
    const pitch = this.body.rotation.x, cp = Math.cos(pitch), sp = Math.sin(pitch);
    for (const L of this.legs) {
      // Gallop: fronts nearly together, then the backs.
      const off = this.gallop ? (L.front ? 0 : 0.5) + (L.side > 0 ? 0.08 : 0) : L.off;
      const p = (this.phase + off) % 1;
      let fz: number, lift: number;
      if (p < duty) { fz = stride * (0.5 - p / duty); lift = 0; }
      else { const q = (p - duty) / (1 - duty); fz = stride * (-0.5 + q); lift = Math.sin(q * Math.PI) * reach * (this.gallop ? 0.32 : 0.22); }
      // Foot target in the root frame (ground at y = 0).
      const hz = L.hip.position.z;
      let tz = hz + fz * moving, ty = lift * moving + 0.02;
      if (!L.front) tz += sitK * (s.halfLen * 0.75);
      // Into the hip's frame: hip position in root space, then undo the body pitch.
      const hipY = this.body.position.y + (0 * cp - hz * sp);
      const hipZ = this.body.position.z + (0 * sp + hz * cp);
      const dy = ty - hipY, dz = tz - hipZ;
      L.fy = dy * cp + dz * sp;
      L.fx = -dy * sp + dz * cp;
      this.solve(L, L.fy, L.fx);
    }
    // Head: steadier than the body; looks where it's told.
    this.head.rotation.set(-pitch * 0.7 + this.lookPitch + (this.gallop ? -Math.sin(cyc) * 0.1 : 0), this.lookYaw, 0);
    // Tail: the dog's curls up over the back and wags; the cat's sways low walking, up when sitting.
    const w = Math.sin(this.t * (s.cat ? 2.2 : 13)) * (s.cat ? 0.25 + this.wag * 0.2 : 0.15 + this.wag * 0.55);
    this.tailSegs.forEach((g, i) => {
      if (s.cat) {
        const up = this.gallop ? -0.22 : sitK > 0.5 ? 0.05 : -0.32 + i * 0.02;
        g.rotation.set(i === 0 ? (this.gallop ? -0.5 : 0.75 - sitK * 1.4) : up + Math.sin(this.t * 1.7 - i * 0.6) * 0.06, w * (0.3 + i * 0.12) * (sitK > 0.5 ? 1 : 0.5), 0);
      } else {
        g.rotation.set(i === 0 ? -1.3 : -0.75, i === 0 ? w : w * 0.3, 0);
      }
    });
  }

  /** Two-bone IK in the leg's sagittal plane: foot to (z forward, y up) relative to the hip. */
  private solve(L: Leg, y: number, z: number) {
    const a = this.s.upper, b = this.s.lower;
    const d = Math.min(a + b - 1e-4, Math.max(0.02, Math.hypot(z, y)));
    const alpha = Math.atan2(z, -y);
    const A = Math.acos(Math.max(-1, Math.min(1, (a * a + d * d - b * b) / (2 * a * d))));
    // Front joint (wrist) points forward, back joint (hock) points back.
    const th1 = alpha + (L.front ? A : -A);
    const kz = a * Math.sin(th1), ky = -a * Math.cos(th1);
    const th2 = Math.atan2(z - kz, -(y - ky));
    L.hip.rotation.x = -th1;
    L.knee.rotation.x = -(th2 - th1);
  }
}

export class Animals {
  readonly group = new THREE.Group();
  readonly dog: Quadruped;
  readonly cat: Quadruped;
  private dogState: "home" | "follow" | "return" = "home";
  private dogT = 0;
  private dogCool = 0;
  private dogSide = 1;
  private sniffT = rand(4, 10);
  private dogHome = new THREE.Vector3(-2.15, 0, -49.6);
  private catHome = new THREE.Vector3(2.3, 0, -71.4);
  private catState: "sit" | "flee" | "gone" = "sit";
  private catPath: THREE.Vector3[] = [];
  private catT = 0;
  private heroPrev = new THREE.Vector3();

  constructor(private groundY: (x: number, z: number) => number) {
    this.group.name = "animals";
    this.dog = new Quadruped({ hipY: 0.355, upper: 0.17, lower: 0.18, halfLen: 0.165, halfW: 0.075, bodyR: 0.125, coat: "#c9753a", belly: "#f3e3c8", dark: "#1d1715", cat: false });
    this.cat = new Quadruped({ hipY: 0.225, upper: 0.105, lower: 0.11, halfLen: 0.13, halfW: 0.045, bodyR: 0.066, coat: "#3a3436", belly: "#f2ece4", dark: "#1a1614", cat: true });
    this.group.add(this.dog.root, this.cat.root);
    this.dog.pos.copy(this.dogHome);
    this.dog.heading = Math.PI / 2;
    this.dog.sit = 1;
    this.cat.pos.copy(this.catHome);
    this.cat.heading = -Math.PI / 2 + 0.4;
    this.cat.sit = 1;
  }

  /** Keeps animals on open street (stall fronts are at |x| ≈ 2.35). */
  private clampStreet(p: THREE.Vector3) {
    if (p.z > -95.5 && p.z < -1) p.x = Math.max(-2.25, Math.min(2.25, p.x));
  }

  update(dt: number, her: THREE.Vector3, heroHeading: number, heroSpeed: number): void {
    this.updateDog(dt, her, heroHeading, heroSpeed);
    this.updateCat(dt, her, heroSpeed);
    this.heroPrev.copy(her);
  }

  private moveTo(a: Quadruped, x: number, z: number, speed: number, dt: number, stopAt = 0.06): boolean {
    const dx = x - a.pos.x, dz = z - a.pos.z, d = Math.hypot(dx, dz);
    if (d < stopAt) { a.speed = damp(a.speed, 0, 10, dt); return true; }
    a.heading = dampAngle(a.heading, Math.atan2(dx, dz), 8, dt);
    // Turn before going fast; slow down on arrival.
    const facing = Math.max(0, Math.cos(Math.atan2(dx, dz) - a.heading));
    const want = Math.min(speed, d * 2.2) * (0.35 + 0.65 * facing);
    a.speed = damp(a.speed, want, 6, dt);
    const step = Math.min(d, a.speed * dt);
    a.pos.x += Math.sin(a.heading) * step;
    a.pos.z += Math.cos(a.heading) * step;
    return false;
  }

  private look(a: Quadruped, x: number, z: number, dt: number, k = 1) {
    const yaw = Math.atan2(x - a.pos.x, z - a.pos.z) - a.heading;
    let y = Math.atan2(Math.sin(yaw), Math.cos(yaw));
    y = Math.max(-0.9, Math.min(0.9, y)) * k;
    a.lookYaw = damp(a.lookYaw, y, 5, dt);
  }

  private updateDog(dt: number, her: THREE.Vector3, hh: number, hs: number) {
    const d = this.dog;
    const dHer = Math.hypot(her.x - d.pos.x, her.z - d.pos.z);
    this.dogCool = Math.max(0, this.dogCool - dt);
    d.lookPitch = damp(d.lookPitch, 0, 4, dt);
    if (this.dogState === "home") {
      // Sits; now and then gets up, sniffs about the spot, sits again.
      this.sniffT -= dt;
      const atHome = Math.hypot(d.pos.x - this.dogHome.x, d.pos.z - this.dogHome.z) < 0.1;
      if (this.sniffT < 0) {
        if (this.sniffT < -3.5 || (this.sniffT < -1 && atHome)) this.sniffT = rand(7, 16);
        else {
          const a = this.t2 ??= rand(0, Math.PI * 2);
          this.moveTo(d, this.dogHome.x + Math.cos(a) * 0.7, this.dogHome.z + Math.sin(a) * 0.7, 0.6, dt);
          d.lookPitch = damp(d.lookPitch, 0.45, 4, dt);
        }
      } else {
        this.t2 = undefined;
        if (!atHome) this.moveTo(d, this.dogHome.x, this.dogHome.z, 0.6, dt);
        else { d.speed = damp(d.speed, 0, 8, dt); d.heading = dampAngle(d.heading, Math.PI / 2, 3, dt); }
      }
      d.sit = damp(d.sit, d.speed < 0.05 && this.sniffT > 0 ? 1 : 0, 3, dt);
      d.wag = damp(d.wag, dHer < 6 ? 0.8 : 0.1, 3, dt);
      if (dHer < 7) this.look(d, her.x, her.z, dt); else d.lookYaw = damp(d.lookYaw, 0, 3, dt);
      if (dHer < 4.5 && this.dogCool <= 0) {
        this.dogState = "follow";
        this.dogT = rand(18, 36);
        this.dogSide = Math.random() < 0.5 ? -1 : 1;
      }
    } else if (this.dogState === "follow") {
      d.sit = damp(d.sit, 0, 6, dt);
      this.dogT -= dt;
      // Trots at her heel, a bit behind and to one side.
      const fx = Math.sin(hh), fz = Math.cos(hh);
      const tx = her.x - fx * 1.2 + fz * 0.65 * this.dogSide, tz = her.z - fz * 1.2 - fx * 0.65 * this.dogSide;
      const tgt = new THREE.Vector3(tx, 0, tz);
      this.clampStreet(tgt);
      const gap = Math.hypot(tgt.x - d.pos.x, tgt.z - d.pos.z);
      if (gap > 0.35) this.moveTo(d, tgt.x, tgt.z, Math.min(6.2, hs * 1.05 + gap * 1.6), dt, 0.3);
      else { d.speed = damp(d.speed, 0, 8, dt); d.heading = dampAngle(d.heading, Math.atan2(her.x - d.pos.x, her.z - d.pos.z), 4, dt); }
      d.gallop = d.speed > 3.2;
      d.wag = damp(d.wag, 1, 3, dt);
      this.look(d, her.x, her.z, dt, d.speed > 1.5 ? 0.4 : 1);
      // Up at her now and then.
      d.lookPitch = damp(d.lookPitch, d.speed < 0.2 ? 0.35 : 0, 3, dt);
      const fromHome = Math.hypot(her.x - this.dogHome.x, her.z - this.dogHome.z);
      if (this.dogT <= 0 || fromHome > 30 || her.z < -95 || her.z > -1 || dHer > 14) {
        this.dogState = "return";
        this.dogCool = rand(35, 70);
      }
    } else {
      d.gallop = false;
      d.wag = damp(d.wag, 0.2, 2, dt);
      d.lookYaw = damp(d.lookYaw, 0, 3, dt);
      if (this.moveTo(d, this.dogHome.x, this.dogHome.z, 1.3, dt)) { this.dogState = "home"; this.sniffT = rand(6, 14); }
    }
    this.clampStreet(d.pos);
    d.update(dt, this.groundY(d.pos.x, d.pos.z));
  }
  private t2: number | undefined;

  private updateCat(dt: number, her: THREE.Vector3, hs: number) {
    const c = this.cat;
    const dHer = Math.hypot(her.x - c.pos.x, her.z - c.pos.z);
    if (this.catState === "sit") {
      c.speed = damp(c.speed, 0, 8, dt);
      c.sit = 1;
      c.wag = dHer < 6 ? 0.6 : 0.1;
      if (dHer < 8) this.look(c, her.x, her.z, dt); else c.lookYaw = damp(c.lookYaw, 0.3 * Math.sin(performance.now() / 2300), 1.5, dt);
      if ((dHer < 7.5 && hs > 2.2) || dHer < 1.25) {
        // Bolt: away from her along the street, then under the nearest stall that way.
        const away = Math.sign(c.pos.z - her.z) || -1;
        const cands = STALLS.filter((s) => (s.z - c.pos.z) * away > 5).sort((a, b) => Math.abs(a.z - c.pos.z) - Math.abs(b.z - c.pos.z));
        const s = cands[0];
        if (s) {
          const sx = Math.sign(stallX(s.side));
          this.catPath = [new THREE.Vector3(sx * 1.6, 0, s.z + away * -1.2), new THREE.Vector3(sx * 3.5, 0, s.z)];
        } else this.catPath = [new THREE.Vector3(c.pos.x, 0, c.pos.z + away * 12)];
        this.catState = "flee";
        c.sit = 0;
      }
    } else if (this.catState === "flee") {
      c.gallop = true;
      c.wag = 0;
      c.lookYaw = damp(c.lookYaw, 0, 6, dt);
      const p = this.catPath[0];
      if (this.moveTo(c, p.x, p.z, 5.2, dt, 0.25)) {
        this.catPath.shift();
        if (!this.catPath.length) { this.catState = "gone"; this.catT = rand(35, 60); c.root.visible = false; }
      }
      if (this.catPath.length && this.catPath[0].x === c.pos.x) this.clampStreet(c.pos);
    } else {
      this.catT -= dt;
      if (this.catT <= 0 && Math.hypot(her.x - this.catHome.x, her.z - this.catHome.z) > 16) {
        this.catState = "sit";
        c.gallop = false;
        c.speed = 0;
        c.pos.copy(this.catHome);
        c.heading = -Math.PI / 2 + rand(-0.5, 0.5);
        c.root.visible = true;
      }
    }
    if (c.root.visible) c.update(dt, this.groundY(c.pos.x, c.pos.z));
  }
}
