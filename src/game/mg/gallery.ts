import * as THREE from "three/webgpu";
import { MiniGame, pointerRay, type Ctx } from "./common";
import { ToonMaterial } from "../../render/toon";
import { Builder, solid } from "../../world/geo";
import { woodMaterial } from "../../render/surfaces";

export interface Site { use: THREE.Vector3; cam: THREE.Vector3; camTarget: THREE.Vector3; front: THREE.Vector3; keeper: THREE.Vector3 }
export interface GalleryStall extends Site { root: THREE.Group; targets: THREE.Object3D[]; gun: THREE.Vector3; planeX: number; collider: { x0: number; x1: number; z0: number; z1: number } }

const W = 2.7, D = 1.7;

/** The cork-gun stall (shateki): three shelves of little prizes at the back, guns on the counter. */
export function buildGallery(side: -1 | 1, z: number): GalleryStall {
  const b = new Builder();
  const wood = "#7a5536";
  for (const sx of [-1, 1]) for (const sz of [-1, 1]) b.box(0.09, 2.5, 0.09, wood, sx * (W / 2 - 0.07), 1.25, sz * (D / 2 - 0.07));
  // Counter at the front, shelves along the back wall, a striped awning and a valance.
  b.box(W, 0.9, 0.45, "#8a6444", 0, 0.45, D / 2 - 0.22);
  b.box(W + 0.1, 0.05, 0.56, "#b08860", 0, 0.925, D / 2 - 0.22);
  b.box(W, 2.2, 0.04, "#6a2f2a", 0, 1.25, -D / 2 + 0.06);
  for (const y of [1.0, 1.36, 1.72]) b.box(W - 0.3, 0.035, 0.24, "#c9a878", 0, y, -D / 2 + 0.2);
  for (let i = 0; i < 8; i++) b.box(W / 8 + 0.01, 0.05, D + 0.6, i % 2 ? "#f2ead8" : "#c8372f", -W / 2 + (i + 0.5) * (W / 8), 2.56, 0.18, 0, -0.16);
  b.box(W + 0.05, 0.3, 0.03, "#c8372f", 0, 2.3, D / 2 + 0.42);
  b.box(1.2, 0.2, 0.035, "#f2ead8", 0, 2.3, D / 2 + 0.44);
  // Two cork guns lying on the counter.
  for (const x of [-0.75, 0.8]) { b.box(0.05, 0.04, 0.42, "#3a2a20", x, 0.975, D / 2 - 0.2, 0.3); b.box(0.045, 0.1, 0.07, "#5a3b2a", x + 0.05, 0.96, D / 2 - 0.02, 0.3); }
  const root = new THREE.Group();
  root.name = "stall_gallery";
  root.add(solid(b.build(), woodMaterial()));
  // Prizes: small boxes, daruma, cans, each its own mesh so it can be knocked over.
  const targets: THREE.Object3D[] = [];
  const cols = ["#e8503a", "#f2c84a", "#4a8fd0", "#5fb86a", "#e88ab0", "#f0e6d8"];
  let k = 0;
  for (const y of [1.0, 1.36, 1.72]) for (let i = 0; i < 5; i++) {
    const kind = (k + i) % 3;
    const m = new ToonMaterial({ color: cols[(k * 2 + i) % cols.length], paint: 0.15, rim: 0.4 });
    const g = kind === 0 ? new THREE.BoxGeometry(0.11, 0.15, 0.07) : kind === 1 ? new THREE.SphereGeometry(0.07, 14, 10) : new THREE.CylinderGeometry(0.045, 0.045, 0.15, 12);
    const h = kind === 1 ? 0.07 : 0.075;
    g.translate(0, h, 0);
    const t = new THREE.Mesh(g, m);
    t.position.set(-0.9 + i * 0.45 + ((k % 2) ? 0.1 : -0.05), y + 0.02, -D / 2 + 0.2);
    t.castShadow = true;
    t.userData.home = t.position.clone();
    t.userData.h = h;
    root.add(t);
    targets.push(t);
    k++;
  }
  const x = side * (4.6 - D / 2 - 0.05);
  root.position.set(x, 0, z);
  root.rotation.y = side < 0 ? Math.PI / 2 : -Math.PI / 2;
  root.updateMatrixWorld(true);
  const local = (lx: number, ly: number, lz: number) => root.localToWorld(new THREE.Vector3(lx, ly, lz));
  const use = local(0, 0, D / 2 + 0.75); use.y = 0;
  const keeper = local(1.0, 0, -0.15); keeper.y = 0;
  return {
    root, targets, use, keeper,
    cam: local(0.45, 1.5, D / 2 + 1.55), camTarget: local(0, 1.36, -D / 2 + 0.2), front: new THREE.Vector3(-side, 0, 0),
    gun: local(0.12, 1.22, D / 2 + 0.35), planeX: local(0, 0, -D / 2 + 0.2).x,
    collider: { x0: x - D / 2 - 0.05, x1: x + D / 2 + 0.05, z0: z - W / 2, z1: z + W / 2 },
  };
}

interface Cork { o: THREE.Mesh; s: THREE.Vector3; e: THREE.Vector3; u: number; hit: THREE.Object3D | null }

/**
 * Cork shooting. Six corks; the sight drifts with her breathing, so squeeze when it crosses a
 * prize. A hit knocks the prize off its shelf. The round's score and the best so far are kept.
 */
export class Shooting extends MiniGame {
  readonly task = null;
  private left = 6;
  hits = 0;
  private t = 0;
  private aim = new THREE.Vector3();
  private reticle: THREE.Mesh;
  private corks: Cork[] = [];
  private falling: { o: THREE.Object3D; t: number }[] = [];
  private overT = -1;

  constructor(c: Ctx, private s: GalleryStall, private best: () => number) {
    super(c);
    for (const t of s.targets) { t.position.copy(t.userData.home); t.rotation.set(0, 0, 0); t.visible = true; t.userData.down = false; }
    this.aim.copy(s.camTarget);
    this.reticle = new THREE.Mesh(new THREE.RingGeometry(0.035, 0.045, 28), new THREE.MeshBasicNodeMaterial({ color: "#fff2d8", transparent: true, opacity: 0.85, depthWrite: false, depthTest: false }));
    this.reticle.rotation.y = s.front.x > 0 ? Math.PI / 2 : -Math.PI / 2;
    this.reticle.renderOrder = 6;
    c.game.scene.add(this.reticle);
    c.game.input.captureMouse = true;
    c.game.her.setPose("reach");
  }

  private pips() { return "●".repeat(this.left) + "○".repeat(6 - this.left); }

  update(dt: number): void {
    const c = this.c, g = c.game, s = this.s;
    this.t += dt;
    // Pointer onto the shelves' plane (a wall across the stall at the prizes).
    const r = pointerRay(g);
    const k = (s.planeX - r.origin.x) / (r.direction.x || 1e-6);
    if (k > 0) {
      const p = r.origin.clone().addScaledVector(r.direction, k);
      p.y = THREE.MathUtils.clamp(p.y, 0.95, 2.0);
      p.z = THREE.MathUtils.clamp(p.z, s.camTarget.z - 1.2, s.camTarget.z + 1.2);
      this.aim.lerp(p, 1 - Math.exp(-14 * dt));
    }
    const sway = new THREE.Vector3(0, Math.sin(this.t * 1.7) * 0.035 + Math.sin(this.t * 4.1) * 0.01, Math.sin(this.t * 1.15 + 1) * 0.045);
    const target = this.aim.clone().add(sway);
    this.reticle.position.copy(target).addScaledVector(s.front, 0.03);
    this.reticle.visible = this.overT < 0;
    c.game.her.lookTarget = target;

    if (g.input.clicked && this.left > 0 && this.overT < 0 && !this.corks.some((k) => k.u < 1)) {
      this.left--;
      const o = new THREE.Mesh(new THREE.CylinderGeometry(0.012, 0.014, 0.03, 8).rotateZ(Math.PI / 2), new ToonMaterial({ color: "#c9a060", paint: 0 }));
      g.scene.add(o);
      let hit: THREE.Object3D | null = null, bd = 0.085;
      for (const t of s.targets) {
        if (t.userData.down) continue;
        const wp = t.getWorldPosition(new THREE.Vector3());
        const d = Math.hypot(wp.y + t.userData.h - target.y, wp.z - target.z);
        if (d < bd) { bd = d; hit = t; }
      }
      this.corks.push({ o, s: s.gun.clone(), e: target.clone(), u: 0, hit });
      c.audio.blip("pop", s.gun);
    }
    for (const k of this.corks) {
      if (k.u >= 1) continue;
      k.u = Math.min(1, k.u + dt / 0.16);
      k.o.position.lerpVectors(k.s, k.e, k.u);
      if (k.u >= 1) {
        if (k.hit) {
          k.hit.userData.down = true;
          this.falling.push({ o: k.hit, t: 0 });
          this.hits++;
          c.audio.blip("clack", k.e);
          c.fx.sparkle(k.e.clone(), new THREE.Color(1, 0.85, 0.5), 14, 0.6);
          g.her.smile = 1;
        } else c.audio.blip("fail", k.e);
        k.o.removeFromParent();
      }
    }
    // Prizes tip backward off the shelf and drop.
    for (const f of this.falling) {
      f.t += dt;
      f.o.rotation.x = -Math.min(1.5, f.t * 6);
      if (f.t > 0.25) f.o.position.y -= dt * (f.t - 0.25) * 9;
      if (f.t > 0.8) f.o.visible = false;
    }
    if (this.overT < 0) {
      c.hud.setGuide("Line up the sight · click to fire", null, this.pips());
      if (this.left === 0 && !this.corks.some((k) => k.u < 1)) this.overT = 0;
    } else {
      this.overT += dt;
      const b = Math.max(this.best(), this.hits);
      c.hud.setGuide(this.hits === 0 ? "No luck this time!" : `${this.hits} prize${this.hits > 1 ? "s" : ""} down · best ${b}`, null, "");
      if (this.overT > 1.4) this.won = true;
    }
  }

  end(): void {
    this.reticle.removeFromParent();
    for (const k of this.corks) k.o.removeFromParent();
    this.c.game.input.captureMouse = false;
    this.c.game.her.lookTarget = null;
    // The shelf is restocked for the next customer.
    for (const t of this.s.targets) { t.position.copy(t.userData.home); t.rotation.set(0, 0, 0); t.visible = true; t.userData.down = false; }
  }
}
