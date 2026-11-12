import * as THREE from "three/webgpu";
import { MiniGame, pointerOnPlane, damp, type Ctx } from "./common";
import { ToonMaterial } from "../../render/toon";

interface Fish { g: THREE.Group; tail: THREE.Object3D; x: number; z: number; a: number; v: number; turn: number; t: number }

const W = 0.66, D = 0.28; // swimmable half-extents in the tub (local)
const UP = 0.07, DOWN = -0.022;

let fishGeo: { body: THREE.BufferGeometry; tail: THREE.BufferGeometry; fin: THREE.BufferGeometry } | null = null;
function geos() {
  if (fishGeo) return fishGeo;
  const body = new THREE.SphereGeometry(1, 14, 10);
  body.scale(0.014, 0.011, 0.028);
  const tail = new THREE.BufferGeometry();
  tail.setAttribute("position", new THREE.Float32BufferAttribute([0, 0, 0, -0.02, 0.002, -0.034, 0.02, 0.002, -0.034, 0, 0, 0, 0.02, 0.002, -0.034, 0, 0.004, -0.026, 0, 0, 0, 0, 0.004, -0.026, -0.02, 0.002, -0.034], 3));
  tail.computeVertexNormals();
  const fin = new THREE.SphereGeometry(1, 8, 6);
  fin.scale(0.004, 0.006, 0.012);
  fishGeo = { body, tail, fin };
  return fishGeo;
}

export function makeFish(color: string, patch?: string): { g: THREE.Group; tail: THREE.Object3D } {
  const { body, tail, fin } = geos();
  const g = new THREE.Group();
  const m = new ToonMaterial({ color, paint: 0, rim: 0.6, side: THREE.DoubleSide });
  const b = new THREE.Mesh(body, m);
  g.add(b);
  if (patch) {
    const p = new THREE.Mesh(body, new ToonMaterial({ color: patch, paint: 0, rim: 0.5 }));
    p.scale.set(0.8, 0.7, 0.5);
    p.position.set(0, 0.004, 0.008);
    g.add(p);
  }
  const tp = new THREE.Group();
  tp.position.z = -0.024;
  tp.add(new THREE.Mesh(tail, m));
  g.add(tp);
  const dorsal = new THREE.Mesh(fin, m);
  dorsal.position.set(0, 0.011, 0);
  g.add(dorsal);
  return { g, tail: tp };
}

/**
 * The goldfish tub: fish that swim all evening (seen from the street too), and react to a poi.
 */
export class Tub {
  readonly fish: Fish[] = [];
  readonly waterY: number;
  constructor(readonly mesh: THREE.Mesh) {
    this.waterY = mesh.getWorldPosition(new THREE.Vector3()).y;
    // See the fish through the water.
    if (!Array.isArray(mesh.material)) {
      const m = (mesh.material as THREE.Material).clone();
      m.transparent = true;
      (m as any).opacity = 0.45;
      m.depthWrite = false;
      mesh.material = m;
    }
    const kinds: [string, string?][] = [["#ff6a24"], ["#f2461f", "#fff4ea"], ["#ff7a2e"], ["#1d1a22"], ["#ff5520"], ["#f0441e", "#fff2e6"], ["#ff8a3a"], ["#e83b1c"]];
    for (const [col, patch] of kinds) this.add(col, patch);
  }

  add(col = "#ff6a24", patch?: string): void {
    const { g, tail } = makeFish(col, patch);
    const f: Fish = { g, tail, x: (Math.random() * 2 - 1) * W * 0.8, z: (Math.random() * 2 - 1) * D * 0.8, a: Math.random() * 6.28, v: 0.06, turn: 0, t: Math.random() * 10 };
    g.position.set(f.x, -0.03, f.z);
    this.mesh.add(g);
    this.fish.push(f);
  }

  remove(f: Fish): void {
    f.g.removeFromParent();
    this.fish.splice(this.fish.indexOf(f), 1);
  }

  /** poi: where the poi is (tub local), its speed and whether it's in the water. */
  swim(dt: number, poi: { x: number; z: number; v: number; y: number; dipped: boolean } | null, skip: Fish | null = null): void {
    for (const f of this.fish) {
      if (f === skip) continue;
      f.t += dt;
      f.turn += (Math.random() * 2 - 1) * dt * 3;
      f.turn *= Math.exp(-dt * 1.5);
      let want = 0.05 + 0.03 * Math.sin(f.t * 0.7);
      // Walls: steer back toward the middle.
      const edge = Math.max(Math.abs(f.x) / W, Math.abs(f.z) / D);
      if (edge > 0.82) {
        const toC = Math.atan2(-f.x, -f.z);
        let d = toC - f.a; d = Math.atan2(Math.sin(d), Math.cos(d));
        f.turn += d * dt * 6;
      }
      if (poi) {
        // Dart from a fast poi, drift toward one held still in the water.
        const dx = f.x - poi.x, dz = f.z - poi.z, dist = Math.hypot(dx, dz);
        if (dist < 0.16 && poi.v > 0.35 && (poi.dipped || poi.y < 0.03)) {
          const away = Math.atan2(dx, dz);
          let d = away - f.a; d = Math.atan2(Math.sin(d), Math.cos(d));
          f.turn += d * dt * 14;
          want = 0.28;
        } else if (poi.dipped && dist < 0.3 && poi.v < 0.12) {
          const to = Math.atan2(-dx, -dz);
          let d = to - f.a; d = Math.atan2(Math.sin(d), Math.cos(d));
          f.turn += d * dt * 2.2;
          want = dist > 0.03 ? 0.05 : 0.01;
        }
      }
      f.v = damp(f.v, want, 3, dt);
      f.a += f.turn * dt;
      f.x = THREE.MathUtils.clamp(f.x + Math.sin(f.a) * f.v * dt, -W, W);
      f.z = THREE.MathUtils.clamp(f.z + Math.cos(f.a) * f.v * dt, -D, D);
      // Just at the surface: under the tinted water they read pink, not gold.
      f.g.position.set(f.x, 0.001 + Math.sin(f.t * 1.7) * 0.002, f.z);
      f.g.rotation.set(0, f.a, 0);
      f.tail.rotation.y = Math.sin(f.t * (8 + f.v * 40)) * 0.45;
    }
  }
}

/**
 * Goldfish scooping (kingyo-sukui). Glide the poi over a fish, hold to dip it in, let go to lift.
 * The paper weakens while it's wet (and faster if you sweep it around); fish dart from a poi that
 * moves fast but drift curiously toward one held still. A torn poi is replaced with a smile.
 */
export class Goldfish extends MiniGame {
  readonly task = "goldfish" as const;
  private tub: Tub;
  private poi = new THREE.Group();
  private paper: THREE.Mesh;
  private y = UP;
  private px = 0;
  private pz = 0.1;
  private pv = 0;
  private wet = false;
  private dipT = 0;
  private strength = 1;
  private tries = 1;
  private torn = 0;
  private caught: Fish | null = null;
  private caughtT = 0;
  private shotT = 0;
  private get waterY() { return this.tub.waterY; }

  constructor(c: Ctx, tub: Tub) {
    super(c);
    this.tub = tub;
    // The poi: a plastic hoop with a thin paper skin and a handle toward her.
    const hoop = new THREE.Mesh(new THREE.TorusGeometry(0.046, 0.0045, 6, 28).rotateX(Math.PI / 2), new ToonMaterial({ color: "#e65a8a", paint: 0, rim: 0.6 }));
    this.paper = new THREE.Mesh(new THREE.CircleGeometry(0.045, 28).rotateX(-Math.PI / 2), new ToonMaterial({ color: "#fbf6ec", paint: 0, rim: 0.2, transparent: true, opacity: 0.8, side: THREE.DoubleSide }));
    const handle = new THREE.Mesh(new THREE.BoxGeometry(0.014, 0.005, 0.12), new ToonMaterial({ color: "#e65a8a", paint: 0 }));
    handle.position.set(0, 0.012, 0.105);
    handle.rotation.x = -0.2;
    this.poi.add(hoop, this.paper, handle);
    this.tub.mesh.add(this.poi);
    c.game.input.captureMouse = true;

  }

  update(dt: number): void {
    const g = this.c.game, input = g.input;
    // The camera looks down over her shoulder into the tub: once it's there she'd fill the frame.
    this.shotT += dt;
    g.her.root.visible = this.shotT < 0.6;
    // Poi follows the pointer on the water.
    const hit = pointerOnPlane(g, this.waterY);
    if (hit && !this.caught) {
      const l = this.tub.mesh.worldToLocal(hit);
      const nx = THREE.MathUtils.clamp(l.x, -W - 0.02, W + 0.02), nz = THREE.MathUtils.clamp(l.z, -D - 0.02, D + 0.02);
      const ox = this.px, oz = this.pz;
      this.px = damp(this.px, nx, 14, dt);
      this.pz = damp(this.pz, nz, 14, dt);
      this.pv = dt > 0 ? Math.hypot(this.px - ox, this.pz - oz) / dt : 0;
    }
    const dipping = input.down && !this.caught && this.torn <= 0;
    this.y = damp(this.y, this.caught ? 0.14 : dipping ? DOWN : UP, dipping ? 10 : 7, dt);
    this.poi.position.set(this.px, this.y, this.pz);
    this.poi.rotation.z = Math.sin(g.time * 1.3) * 0.04;
    const inWater = this.y < 0.002;
    if (inWater && !this.wet) this.c.audio.blip("splash", this.poi.getWorldPosition(new THREE.Vector3()));
    if (inWater) {
      this.dipT += dt;
      this.strength -= dt * (0.26 + Math.min(1.5, this.pv * 2.2));
    } else if (this.y > 0.02) this.dipT = 0;
    // Lifted out after a proper dip: is a fish over the paper?
    if (this.wet && !inWater && !this.caught && this.torn <= 0 && this.dipT >= 0.2) {
      let best: Fish | null = null, bd = 0.052;
      for (const f of this.tub.fish) {
        const d = Math.hypot(f.x - this.px, f.z - this.pz);
        if (d < bd) { bd = d; best = f; }
      }
      if (best) {
        this.caught = best;
        this.caughtT = 0;
        this.c.audio.blip("splash", this.poi.getWorldPosition(new THREE.Vector3()));
      } else this.c.audio.blip("fail");
      this.dipT = 0;
    }
    this.wet = inWater;
    // The paper gives way.
    if (this.strength <= 0 && this.torn <= 0) {
      this.torn = 1.4;
      this.paper.visible = false;
      this.c.audio.blip("fail");
      this.c.hud.setGuide("The paper tore. Here's a fresh poi…", 0, this.pips());
    }
    if (this.torn > 0) {
      this.torn -= dt;
      if (this.torn <= 0) { this.paper.visible = true; this.strength = 1; this.tries++; }
    }
    this.tub.swim(dt, { x: this.px, z: this.pz, v: this.pv, y: this.y, dipped: inWater }, this.caught);
    if (this.caught) {
      this.caughtT += dt;
      const f = this.caught;
      f.x = this.px; f.z = this.pz;
      f.g.position.set(this.px, this.y + 0.012, this.pz);
      f.g.rotation.z = Math.sin(this.caughtT * 30) * 0.4; // flapping on the paper
      if (this.caughtT > 0.9 && !this.won) {
        this.won = true;
        this.c.fx.sparkle(f.g.getWorldPosition(new THREE.Vector3()), new THREE.Color(1, 0.7, 0.4), 18, 0.6);
        this.giveBag(f);
      }
    }
    if (this.torn <= 0 && !this.won) this.c.hud.setGuide(this.caught ? "Got one!" : "Glide over a goldfish · hold to dip the poi · let go to scoop", Math.max(0, this.strength), this.pips());
  }

  private pips() { return this.tries > 1 ? `poi ${this.tries}` : ""; }

  private giveBag(f: Fish) {
    this.tub.remove(f);
    goldfishBag(this.c.game);
  }

  end(): void {
    this.poi.removeFromParent();
    this.c.game.her.root.visible = true;
    if (this.caught && this.tub.fish.includes(this.caught)) {
      // Stepped away with a fish on the paper: it slips back into the water.
      const f = this.caught;
      f.g.rotation.z = 0;
      f.g.position.y = this.waterY - (this.tub.mesh.getWorldPosition(new THREE.Vector3()).y) - 0.01;
      this.caught = null;
    }
    this.c.game.input.captureMouse = false;
  }
}

/** The keeper bags the fish: she carries it in a little water bag from here on. */
export function goldfishBag(game: { her: any; carry: THREE.Object3D[] }): void {
  // One bag is enough to carry, however many she scoops.
  if (game.carry.some((o) => o.name === "goldfish_bag")) return;
  const bag = new THREE.Group();
  bag.name = "goldfish_bag";
  const water = new THREE.Mesh(new THREE.SphereGeometry(0.055, 16, 12), new THREE.MeshBasicNodeMaterial({ color: "#bfe6f2", transparent: true, opacity: 0.35, depthWrite: false }));
  water.scale.set(1, 1.15, 1);
  const knot = new THREE.Mesh(new THREE.ConeGeometry(0.016, 0.05, 8), new ToonMaterial({ color: "#e65a8a", paint: 0 }));
  knot.position.y = 0.08;
  const string = new THREE.Mesh(new THREE.CylinderGeometry(0.002, 0.002, 0.08, 4), new ToonMaterial({ color: "#d63a5a", paint: 0 }));
  string.position.y = 0.13;
  const fish = makeFish("#ff6a24").g;
  fish.scale.setScalar(0.85);
  fish.rotation.y = 0.6;
  bag.add(water, fish, knot, string);
  game.her.hold("hand_L", bag, new THREE.Vector3(0.0, -0.16, 0.03));
  game.carry.push(bag);
}
