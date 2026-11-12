import * as THREE from "three/webgpu";
import { MiniGame, pointerOnPlane, type Ctx } from "./common";
import { ToonMaterial } from "../../render/toon";

interface Ring { o: THREE.Object3D; s: THREE.Vector3; t: THREE.Vector3; u: number; peg: THREE.Vector3 | null; slide: number; done: boolean }

/**
 * Ring toss (wanage). A marker on the peg board follows the pointer, swaying with her hand;
 * click to toss. A ring that lands over a peg slides down it: that's a win. Five rings a round;
 * miss them all and the keeper hands over another round, with the pegs a touch more forgiving.
 */
export class RingToss extends MiniGame {
  readonly task = "ringtoss" as const;
  private pegs: { base: THREE.Vector3; top: THREE.Vector3 }[] = [];
  private boardY = 0.32;
  private reticle: THREE.Mesh;
  private aim = new THREE.Vector3();
  private rings: Ring[] = [];
  private left = 5;
  private assist = 0;
  private t = 0;
  private proto: THREE.Object3D;
  private winT = -1;
  private centre = new THREE.Vector3();

  constructor(c: Ctx) {
    super(c);
    const pegs = c.stall.findAll("peg_");
    for (const p of pegs) {
      const base = p.getWorldPosition(new THREE.Vector3());
      const s = p.getWorldScale(new THREE.Vector3()).y;
      this.pegs.push({ base, top: base.clone().add(new THREE.Vector3(0, 0.212 * s, 0)) });
    }
    if (!this.pegs.length) {
      const ct = c.stall.camTarget;
      for (let i = 0; i < 9; i++) {
        const base = ct.clone().add(new THREE.Vector3(((i % 3) - 1) * 0.25, 0, (Math.floor(i / 3) - 1) * 0.25));
        const peg = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.035, 0.21, 10), new ToonMaterial({ color: "#c89a64" }));
        peg.position.copy(base).add(new THREE.Vector3(0, 0.105, 0));
        c.game.scene.add(peg);
        this.pegs.push({ base, top: base.clone().add(new THREE.Vector3(0, 0.21, 0)) });
      }
    }
    this.boardY = this.pegs[0].base.y;
    for (const p of this.pegs) this.centre.add(p.base);
    this.centre.multiplyScalar(1 / this.pegs.length);
    this.aim.copy(this.centre);
    const rp = c.stall.find("ring_proto");
    this.proto = rp ?? new THREE.Mesh(new THREE.TorusGeometry(0.075, 0.011, 8, 28).rotateX(Math.PI / 2), new ToonMaterial({ color: "#e8503a", paint: 0, rim: 0.7 }));
    this.reticle = new THREE.Mesh(new THREE.RingGeometry(0.05, 0.062, 32).rotateX(-Math.PI / 2), new THREE.MeshBasicNodeMaterial({ color: "#fff2d8", transparent: true, opacity: 0.75, depthWrite: false }));
    this.reticle.renderOrder = 6;
    c.game.scene.add(this.reticle);
    c.game.input.captureMouse = true;
  }

  private pips() { return "●".repeat(this.left) + "○".repeat(5 - this.left); }

  update(dt: number): void {
    const g = this.c.game, input = g.input;
    this.t += dt;
    const hit = pointerOnPlane(g, this.boardY);
    if (hit) {
      // Keep the aim on (or just around) the board.
      hit.x = THREE.MathUtils.clamp(hit.x, this.centre.x - 0.45, this.centre.x + 0.45);
      hit.z = THREE.MathUtils.clamp(hit.z, this.centre.z - 0.45, this.centre.z + 0.45);
      this.aim.lerp(hit, 1 - Math.exp(-12 * dt));
    }
    // Her hand sways: a slow figure-eight the player times the toss against.
    const sway = new THREE.Vector3(Math.sin(this.t * 1.9) * 0.042 + Math.sin(this.t * 3.7) * 0.015, 0, Math.sin(this.t * 1.3 + 1) * 0.03);
    const target = this.aim.clone().add(sway);
    this.reticle.position.set(target.x, this.boardY + 0.004, target.z);
    this.reticle.visible = this.winT < 0;

    const flying = this.rings.some((r) => !r.done);
    if (input.clicked && !flying && this.left > 0 && this.winT < 0) this.toss(target);

    for (const r of this.rings) this.fly(r, dt);

    if (this.winT >= 0) {
      this.winT += dt;
      if (this.winT > 1.1) this.won = true;
    } else if (!flying && this.left === 0) {
      // Another round, on the house.
      this.left = 5;
      this.assist += 0.015;
      for (const r of this.rings) r.o.removeFromParent();
      this.rings = [];
      this.c.hud.say("“One more round, on the house!”", 3);
    }
    if (this.winT < 0) this.c.hud.setGuide("Aim at a peg · click to toss when your hand is steady", null, this.pips());
  }

  private toss(target: THREE.Vector3) {
    const her = this.c.game.her;
    const toward = this.centre.clone().sub(her.position).setY(0).normalize();
    const s = her.position.clone().add(new THREE.Vector3(0, 1.2, 0)).addScaledVector(toward, 0.35);
    const o = this.proto.clone(true);
    o.scale.copy(this.proto.getWorldScale(new THREE.Vector3()));
    o.position.copy(s);
    this.c.game.scene.add(o);
    // Does it ring a peg?
    let peg: THREE.Vector3 | null = null, best = 0.04 + this.assist;
    for (const p of this.pegs) {
      const d = Math.hypot(p.base.x - target.x, p.base.z - target.z);
      if (d < best) { best = d; peg = p.base; }
    }
    this.rings.push({ o, s, t: target.clone(), u: 0, peg, slide: 0, done: false });
    this.left--;
    this.c.audio.blip("whoosh", s);
    her.play("throw");
  }

  private fly(r: Ring, dt: number) {
    if (r.done) return;
    if (r.u < 1) {
      r.u = Math.min(1, r.u + dt / 0.7);
      const end = r.peg ? new THREE.Vector3(r.peg.x, this.boardY + 0.24, r.peg.z) : new THREE.Vector3(r.t.x, this.boardY + 0.012, r.t.z);
      const p = r.s.clone().lerp(end, r.u);
      p.y += Math.sin(r.u * Math.PI) * 0.35;
      r.o.position.copy(p);
      r.o.rotation.set(Math.sin(r.u * 7) * 0.25 * (1 - r.u), r.u * 9, 0);
      if (r.u >= 1) {
        this.c.audio.blip("clack", p);
        if (!r.peg) {
          r.done = true;
          r.o.rotation.set(0, r.o.rotation.y, 0.05);
        }
      }
      return;
    }
    // Slide down the peg.
    r.slide = Math.min(1, r.slide + dt / 0.3);
    r.o.position.y = this.boardY + 0.24 - (0.22 * r.slide * r.slide);
    r.o.rotation.set(0, r.o.rotation.y, 0);
    if (r.slide >= 1) {
      r.done = true;
      this.c.audio.blip("clack", r.o.position);
      this.c.fx.sparkle(r.o.position.clone().add(new THREE.Vector3(0, 0.1, 0)), new THREE.Color(1, 0.85, 0.5), 24, 0.7);
      this.winT = 0;
      this.c.hud.setGuide("Ringer!", null, this.pips());
      this.c.game.her.smile = 1;
    }
  }

  end(): void {
    this.reticle.removeFromParent();
    this.c.game.input.captureMouse = false;
    // The winning ring stays on its peg; the others are tidied away.
    for (const r of this.rings) if (!r.peg) r.o.removeFromParent();
  }
}
