import * as THREE from "three/webgpu";
import { MiniGame, pick, damp, type Ctx } from "./common";
import { ToonMaterial } from "../../render/toon";

/**
 * Shared "choose one from the counter" game: hover lifts the item a little (and she glances at
 * it), A/D or the arrow keys step through them, click or E takes it.
 */
abstract class Picker extends MiniGame {
  protected items: THREE.Object3D[] = [];
  private home = new Map<THREE.Object3D, { p: THREE.Vector3; s: THREE.Vector3 }>();
  protected sel = -1;
  protected chosen: THREE.Object3D | null = null;
  private t = 0;
  protected abstract guide: string;

  protected setItems(items: THREE.Object3D[]) {
    this.items = items;
    for (const o of items) this.home.set(o, { p: o.position.clone(), s: o.scale.clone() });
    this.c.game.input.captureMouse = true;
  }

  update(dt: number): void {
    const g = this.c.game, input = g.input;
    this.t += dt;
    if (!this.chosen) {
      const avail = this.items.filter((o) => o.visible);
      if (input.hit("KeyA") || input.hit("ArrowLeft")) this.step(-1, avail);
      if (input.hit("KeyD") || input.hit("ArrowRight")) this.step(1, avail);
      const hovered = pick(g, avail);
      if (hovered && (input.dragX !== 0 || input.dragY !== 0 || input.clicked)) {
        const i = this.items.indexOf(hovered);
        if (i !== this.sel) this.c.audio.blip("pop");
        this.sel = i;
      }
      const choose = (input.clicked && hovered && this.items.indexOf(hovered) === this.sel) || input.hit("KeyE") || input.hit("Space") || input.hit("Enter");
      if (choose && this.sel >= 0 && this.items[this.sel].visible) {
        this.chosen = this.items[this.sel];
        this.onChoose(this.chosen);
      }
      this.c.hud.setGuide(this.guide);
    }
    // Hover lift.
    for (let i = 0; i < this.items.length; i++) {
      const o = this.items[i], h = this.home.get(o)!;
      const on = i === this.sel && !this.chosen;
      o.position.y = damp(o.position.y, h.p.y + (on ? 0.03 + Math.sin(this.t * 3) * 0.006 : 0), 10, dt);
      const s = on ? 1.1 : 1;
      o.scale.set(damp(o.scale.x, h.s.x * s, 10, dt), damp(o.scale.y, h.s.y * s, 10, dt), damp(o.scale.z, h.s.z * s, 10, dt));
    }
    const cur = this.items[this.sel];
    this.c.game.her.lookTarget = cur ? cur.getWorldPosition(new THREE.Vector3()) : null;
  }

  private step(d: number, avail: THREE.Object3D[]) {
    if (!avail.length) return;
    // Order left→right on screen.
    const cam = this.c.game.camera;
    const sorted = [...avail].sort((a, b) => a.getWorldPosition(new THREE.Vector3()).project(cam).x - b.getWorldPosition(new THREE.Vector3()).project(cam).x);
    const cur = sorted.indexOf(this.items[this.sel]);
    const next = sorted[(cur + d + sorted.length) % sorted.length];
    this.sel = this.items.indexOf(next);
    this.c.audio.blip("pop");
  }

  protected abstract onChoose(o: THREE.Object3D): void;

  /** The item's resting scale (not mid hover-grow). */
  protected homeScale(o: THREE.Object3D): THREE.Vector3 { return this.home.get(o)?.s.clone() ?? o.scale.clone(); }

  end(): void {
    for (const [o, h] of this.home) { o.position.copy(h.p); o.scale.copy(h.s); }
    this.c.game.input.captureMouse = false;
    this.c.game.her.lookTarget = null;
  }
}

/** Candy apples on the counter: pick one, pay, and she carries it from then on. */
export class CandyApple extends Picker {
  readonly task = "candyapple" as const;
  protected guide = "Choose a candy apple · click or E";
  private t2 = 0;
  constructor(c: Ctx) {
    super(c);
    let items = c.stall.findAll("apple_");
    if (!items.length) {
      // Placeholder apples on the counter.
      for (let i = 0; i < 6; i++) {
        const a = makeApple(i % 3 === 2 ? "#e8b04a" : "#c8182a");
        a.position.set(-0.5 + i * 0.2, 0.96, 0.7);
        c.stall.root.add(a);
        items.push(a);
      }
    }
    this.setItems(items);
    this.sel = 0;
  }
  protected onChoose(o: THREE.Object3D): void {
    this.c.audio.blip("coin");
    this.c.hud.say("“Thank you, enjoy!”", 2.5);
    // Buying another: the one she had is eaten by now.
    const carry = this.c.game.carry;
    for (const old of carry.filter((x) => x.name === "held_apple")) { old.removeFromParent(); carry.splice(carry.indexOf(old), 1); }
    const held = o.clone(true);
    held.name = "held_apple";
    held.scale.copy(this.homeScale(o));
    held.position.set(0, 0, 0);
    o.visible = false;
    // Held by the stick, apple up.
    this.c.game.her.hold("hand_R", held, new THREE.Vector3(0, 0.11, 0.03), new THREE.Euler(Math.PI - 0.2, 0, 0));
    this.c.game.carry.push(held);
    this.c.game.her.smile = 1;
  }
  update(dt: number): void {
    super.update(dt);
    if (this.chosen) {
      this.t2 += dt;
      if (this.t2 > 0.6) this.won = true;
    }
  }
}

function makeApple(col: string) {
  const g = new THREE.Group();
  const a = new THREE.Mesh(new THREE.SphereGeometry(0.045, 16, 12), new ToonMaterial({ color: col, paint: 0, rim: 0.8 }));
  const s = new THREE.Mesh(new THREE.CylinderGeometry(0.0035, 0.0035, 0.15, 6), new ToonMaterial({ color: "#d8c49a", paint: 0 }));
  s.position.y = 0.08;
  g.add(a, s);
  return g;
}

/** The mask wall: pick one and she wears it tilted on the side of her head. */
export class Masks extends Picker {
  readonly task = "masks" as const;
  protected guide = "Pick a mask · click or E · A / D to browse";
  private t2 = 0;
  constructor(c: Ctx, private onWear: (index: number) => void) {
    super(c);
    let items = c.stall.findAll("mask_").filter((o) => /^mask_\d+$/.test(o.name));
    if (!items.length) {
      const cols = ["#f4efe6", "#e04a3a", "#3a7ad8", "#f0c040", "#58b070", "#f4efe6"];
      cols.forEach((col, i) => {
        const m = new THREE.Mesh(new THREE.SphereGeometry(0.09, 16, 12, 0, Math.PI * 2, 0, Math.PI / 2).rotateX(Math.PI / 2), new ToonMaterial({ color: col, paint: 0, rim: 0.6, side: THREE.DoubleSide }));
        m.name = `mask_${i}`;
        m.position.set(-0.6 + i * 0.24, 1.4 + (i % 2) * 0.22, -0.66);
        c.stall.root.add(m);
        items.push(m);
      });
    }
    items.sort((a, b) => a.name.localeCompare(b.name));
    this.setItems(items);
    this.sel = Math.floor(items.length / 2);
  }
  protected onChoose(o: THREE.Object3D): void {
    this.c.audio.blip("coin");
    this.onWear(this.items.indexOf(o));
    this.c.game.her.smile = 1;
  }
  update(dt: number): void {
    super.update(dt);
    if (this.chosen) {
      this.t2 += dt;
      if (this.t2 > 0.7) this.won = true;
    }
  }
}

/**
 * Wears mask `index` from the stall kit on the side of her head (also used when a save is
 * loaded). Returns the worn object.
 */
export function wearMask(game: { her: any; carry: THREE.Object3D[]; stalls: { stalls: { spot: { kind: string }; findAll(p: string): THREE.Object3D[] }[] } }, index: number): THREE.Object3D | null {
  const st = game.stalls.stalls.find((s) => s.spot.kind === "masks");
  const masks = st ? st.findAll("mask_").filter((o) => /^mask_\d+$/.test(o.name)).sort((a, b) => a.name.localeCompare(b.name)) : [];
  const src = masks[index] ?? masks[0];
  if (!src) return null;
  for (const c of game.carry.filter((o) => o.name === "worn_mask")) { c.removeFromParent(); game.carry.splice(game.carry.indexOf(c), 1); }
  const m = src.clone(true);
  m.name = "worn_mask";
  m.scale.setScalar(0.85);
  // On her right temple, turned out and tipped back, as festival masks are worn (the rig's
  // maskCentre / mask-forward from tools/blender/heroine/README.md).
  game.her.hold("head", m, new THREE.Vector3(-0.097, 0.122, 0.016), new THREE.Euler(-0.23, -1.28, 0, "YXZ"));
  game.carry.push(m);
  return m;
}
