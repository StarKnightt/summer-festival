import * as THREE from "three/webgpu";
import { MiniGame, type Ctx } from "./common";
import { ToonMaterial } from "../../render/toon";

export type SnackKind = "yakisoba" | "takoyaki" | "shavedice";

export const SYRUPS: [string, string][] = [["Strawberry", "#e8415a"], ["Melon", "#5fc46a"], ["Blue Hawaii", "#3d8fe0"], ["Lemon", "#f2cf3a"]];
const NAME: Record<SnackKind, string> = { yakisoba: "Yakisoba", takoyaki: "Takoyaki", shavedice: "Shaved ice" };

const mat = (color: string, paint = 0.2) => new ToonMaterial({ color, paint, rim: 0.3 });
const mesh = (g: THREE.BufferGeometry, m: THREE.Material, x = 0, y = 0, z = 0) => { const o = new THREE.Mesh(g, m); o.position.set(x, y, z); o.castShadow = true; return o; };

/** The dish she holds in her left hand, and the pieces that disappear as she eats. */
function dish(kind: SnackKind, syrup: string): { g: THREE.Group; bites: THREE.Object3D[] } {
  const g = new THREE.Group();
  const bites: THREE.Object3D[] = [];
  if (kind === "yakisoba") {
    g.add(mesh(new THREE.CylinderGeometry(0.085, 0.07, 0.014, 20), mat("#f4f0e6"), 0, 0.007, 0));
    // Three forkfuls of noodles with cabbage and pickled ginger.
    for (let i = 0; i < 3; i++) {
      const b = new THREE.Group();
      const a = (i / 3) * Math.PI * 2;
      const n = mesh(new THREE.SphereGeometry(0.038, 10, 8), mat("#b8743a", 0.6));
      n.scale.set(1.2, 0.55, 1.2);
      b.add(n);
      b.add(mesh(new THREE.BoxGeometry(0.02, 0.006, 0.014), mat("#7fb85a"), 0.012, 0.02, 0.006));
      b.add(mesh(new THREE.BoxGeometry(0.014, 0.006, 0.01), mat("#e0524a"), -0.012, 0.021, -0.004));
      b.position.set(Math.cos(a) * 0.028, 0.03, Math.sin(a) * 0.028);
      g.add(b);
      bites.push(b);
    }
  } else if (kind === "takoyaki") {
    // A paper boat with six balls, sauce and bonito on top.
    g.add(mesh(new THREE.BoxGeometry(0.15, 0.022, 0.1), mat("#d9b98a"), 0, 0.011, 0));
    for (let i = 0; i < 6; i++) {
      const b = new THREE.Group();
      b.add(mesh(new THREE.SphereGeometry(0.021, 12, 10), mat("#c98a48", 0.4)));
      const sauce = mesh(new THREE.SphereGeometry(0.0215, 12, 6, 0, Math.PI * 2, 0, Math.PI * 0.32), mat("#4a2618"));
      b.add(sauce);
      b.add(mesh(new THREE.BoxGeometry(0.012, 0.002, 0.008), mat("#7fb85a"), 0.003, 0.021, 0));
      b.position.set(((i % 3) - 1) * 0.046, 0.04, (Math.floor(i / 3) - 0.5) * 0.046);
      g.add(b);
      bites.push(b);
    }
  } else {
    // A paper cup with a mound of ice, the syrup soaked into its top.
    const cup = mesh(new THREE.CylinderGeometry(0.048, 0.034, 0.075, 16), mat("#f6f2ea"), 0, 0.0375, 0);
    g.add(cup, mesh(new THREE.CylinderGeometry(0.0485, 0.044, 0.016, 16), mat("#3c74b8"), 0, 0.05, 0));
    for (let i = 0; i < 3; i++) {
      const b = mesh(new THREE.SphereGeometry(0.05 - i * 0.008, 14, 10, 0, Math.PI * 2, 0, Math.PI * 0.5), mat(i === 0 ? "#f4f8fb" : syrup, 0.1), 0, 0.072 + i * 0.012, 0);
      b.scale.y = 0.9;
      g.add(b);
      bites.unshift(b);
    }
  }
  return { g, bites };
}

/** What's in her right hand: chopsticks, a toothpick, or a spoon-straw. */
function utensil(kind: SnackKind): THREE.Group {
  const g = new THREE.Group();
  if (kind === "yakisoba") {
    for (const x of [-0.005, 0.005]) g.add(mesh(new THREE.CylinderGeometry(0.0022, 0.0016, 0.2, 5), mat("#c9a878"), x, 0.06, 0));
  } else if (kind === "takoyaki") {
    g.add(mesh(new THREE.CylinderGeometry(0.001, 0.001, 0.07, 4), mat("#d8c8a0"), 0, 0.03, 0));
  } else {
    g.add(mesh(new THREE.CylinderGeometry(0.003, 0.003, 0.13, 6), mat("#e8546a"), 0, 0.05, 0));
    g.add(mesh(new THREE.BoxGeometry(0.012, 0.016, 0.003), mat("#e8546a"), 0, 0.118, 0));
  }
  return g;
}

/** Every prop a snack uses (for the loading-screen warm-up). */
export function snackProps(kind: SnackKind): THREE.Object3D[] {
  return [dish(kind, SYRUPS[0][1]).g, utensil(kind)];
}

/**
 * Buying something to eat at a food stall. She orders (at the shaved-ice stall she picks the
 * syrup first), the keeper hands it over, she turns to the street and eats it in a few bites:
 * steam off the takoyaki and a "hot!" on the first one, a brain-freeze shiver for the ice, and
 * a happy smile at the end. It can be bought again any time; the director keeps the count.
 */
export class Snack extends MiniGame {
  readonly task = null;
  private phase: "choose" | "serve" | "eat" | "done" = "serve";
  private t = 0;
  private pick = 0;
  private d: { g: THREE.Group; bites: THREE.Object3D[] } | null = null;
  private u: THREE.Group | null = null;
  private bite = 0;
  private biteT = 0;
  private faceH: number;
  /** The food on the end of the utensil, on its way to her mouth. */
  private morsel: THREE.Object3D | null = null;

  private hidden: { hide?: boolean }[] = [];
  private eye: THREE.Vector3 | null = null;

  constructor(c: Ctx, readonly kind: SnackKind, private eaten: () => number, private crowd: () => { mode: string; hide?: boolean; pos: THREE.Vector3 }[] = () => []) {
    super(c);
    this.faceH = Math.atan2(c.stall.front.x, c.stall.front.z);
    if (kind === "shavedice") {
      this.phase = "choose";
      this.pick = Math.floor(Math.random() * SYRUPS.length);
    } else this.order();
  }

  get syrup(): string { return SYRUPS[this.pick][0]; }

  private order() {
    const c = this.c;
    this.phase = "serve";
    this.t = 0;
    c.audio.blip("coin", c.stall.use);
    c.hud.setGuide(this.kind === "shavedice" ? `“${this.syrup}, coming up!”` : "“One portion, coming up!”");
  }

  update(dt: number): void {
    const c = this.c, g = c.game, input = g.input, her = g.her;
    this.t += dt;
    if (this.phase === "choose") {
      if (input.hit("KeyA") || input.hit("ArrowLeft")) { this.pick = (this.pick + SYRUPS.length - 1) % SYRUPS.length; c.audio.blip("pop"); }
      if (input.hit("KeyD") || input.hit("ArrowRight")) { this.pick = (this.pick + 1) % SYRUPS.length; c.audio.blip("pop"); }
      const [name, col] = SYRUPS[this.pick];
      c.hud.setGuide(`A / D choose a syrup · E to order: <b style="color:${col}">${name}</b>`, null, SYRUPS.map((_, i) => (i === this.pick ? "●" : "○")).join(" "));
      if (this.t > 0.3 && (input.hit("KeyE") || input.hit("Enter") || input.clicked)) this.order();
      return;
    }
    if (this.phase === "serve") {
      if (this.t > 1.3) {
        // In her hands; she turns to the street to eat.
        this.d = dish(this.kind, SYRUPS[this.pick][1]);
        this.u = utensil(this.kind);
        g.scene.add(this.d.g, this.u);
        this.phase = "eat";
        this.t = 0;
        this.biteT = 0.9;
        const eye = c.stall.use.clone().addScaledVector(c.stall.front, 2.1);
        eye.y = her.position.y + 1.42;
        eye.z += 0.55;
        g.rig.setShot(eye, her.position.clone().add(new THREE.Vector3(0, 1.22, 0)));
        this.eye = eye;
        c.hud.setGuide(`${NAME[this.kind]}${this.kind === "shavedice" ? ` · ${this.syrup}` : ""}`);
      }
    } else if (this.phase === "eat") {
      let dh = this.faceH - her.heading; dh = Math.atan2(Math.sin(dh), Math.cos(dh));
      her.heading += dh * Math.min(1, dt * 5);
      this.biteT -= dt;
      const total = this.kind === "takoyaki" ? 3 : 3;
      if (this.biteT <= 0 && this.bite < total) {
        this.bite++;
        const dur = her.play("eat");
        this.biteT = Math.max(1.5, Math.min(2.4, dur));
        // The piece leaves the dish now and reaches her mouth part-way through the motion.
        const per = Math.ceil(this.d!.bites.length / total);
        for (let i = 0; i < per; i++) { const b = this.d!.bites.pop(); if (b) { if (!this.morsel) { this.morsel = b; this.u!.add(b); b.position.set(0, this.kind === "yakisoba" ? 0.15 : this.kind === "takoyaki" ? 0.062 : 0.125, 0); b.scale.multiplyScalar(this.kind === "shavedice" ? 0.3 : 0.8); } else b.removeFromParent(); } }
        setTimeout(() => {
          if (this.phase === "done" && this.bite < total) return;
          this.morsel?.removeFromParent();
          this.morsel = null;
          const mouth = her.bone("head")?.getWorldPosition(new THREE.Vector3()).add(new THREE.Vector3(Math.sin(her.heading) * 0.1, -0.03, Math.cos(her.heading) * 0.1));
          c.audio.blip("pop", mouth ?? null);
          if (this.kind === "takoyaki" && mouth) {
            for (let i = 0; i < 5; i++) c.fx.puffs.spawn({ x: mouth.x, y: mouth.y, z: mouth.z, vx: (Math.random() - 0.5) * 0.1, vy: 0.25 + Math.random() * 0.15, vz: (Math.random() - 0.5) * 0.1, r: 1, g: 0.98, b: 0.95, a: 0.16, size: 0.05, grow: 0.12, life: 0.9, drag: 0.8, fade: 2 });
            if (this.bite === 1) c.hud.setGuide("あつっ！ · hot, hot!");
          }
          if (this.kind === "shavedice" && this.bite === 2) c.hud.setGuide("キーン… · brain freeze!");
          if (this.bite >= 2) her.smile = 1;
        }, this.biteT * 1000 * 0.45);
      }
      // Steam off the takoyaki while there's any left.
      if (this.kind === "takoyaki" && this.d && this.d.bites.length && Math.random() < dt * 6) {
        const p = this.d.g.position;
        c.fx.puffs.spawn({ x: p.x, y: p.y + 0.06, z: p.z, vx: 0, vy: 0.22, vz: 0, r: 1, g: 0.98, b: 0.95, a: 0.1, size: 0.04, grow: 0.1, life: 0.9, drag: 0.8, fade: 2 });
      }
      if (this.bite >= total && this.biteT <= 0) {
        this.phase = "done";
        this.t = 0;
        her.smile = 1;
        const n = this.eaten() + 1;
        const head = her.bone("head")?.getWorldPosition(new THREE.Vector3()) ?? her.position.clone().setY(her.position.y + 1.4);
        c.fx.sparkle(head.add(new THREE.Vector3(0, 0.25, 0)), new THREE.Color(1, 0.8, 0.6), 16, 0.6);
        c.hud.setGuide(`おいしい！ · delicious${n > 1 ? ` (${NAME[this.kind].toLowerCase()} ×${n} tonight)` : ""}`);
      }
    } else if (this.phase === "done") {
      her.smile = 1;
      if (this.t > 0.9) this.won = true;
    }
    this.follow();
  }

  /** The dish is held in front of her; the utensil rides her right hand, kept upright. */
  private follow() {
    const her = this.c.game.her;
    if (!this.d || !this.u) return;
    // Nobody wanders between her and the camera while she eats.
    if (this.eye) for (const n of this.crowd()) {
      if (n.mode === "keeper" || n.hide) continue;
      const ax = this.eye.x - her.position.x, az = this.eye.z - her.position.z;
      const u = THREE.MathUtils.clamp(((n.pos.x - her.position.x) * ax + (n.pos.z - her.position.z) * az) / (ax * ax + az * az), -0.3, 1.5);
      if (Math.hypot(n.pos.x - (her.position.x + ax * u), n.pos.z - (her.position.z + az * u)) < 1.5) { n.hide = true; this.hidden.push(n); }
    }
    // (The eating clip brings her left hand to her mouth, so that hand has the chopsticks.)
    const r = her.bone("hand_L");
    const fx = Math.sin(her.heading), fz = Math.cos(her.heading);
    // The dish sits level in front of her at chest height, (whatever the arm's
    // doing, it never tips or rides up to her face); on her right, clear of the eating hand.
    this.d.g.position.copy(her.position).add(new THREE.Vector3(fx * 0.27 - fz * 0.11, 0.98, fz * 0.27 + fx * 0.11));
    this.d.g.rotation.y = her.heading;
    if (r) { r.getWorldPosition(this.u.position); this.u.position.add(new THREE.Vector3(fx * 0.03, 0.0, fz * 0.03)); }
    else this.u.position.copy(her.position).add(new THREE.Vector3(fx * 0.2, 1.1, fz * 0.2));
    this.u.rotation.set(0.25, her.heading, 0);
  }

  end(): void {
    this.phase = "done";
    this.d?.g.removeFromParent();
    this.u?.removeFromParent();
    this.morsel?.removeFromParent();
    for (const n of this.hidden) n.hide = false;
    this.hidden = [];
  }
}
