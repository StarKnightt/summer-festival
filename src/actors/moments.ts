import * as THREE from "three/webgpu";
import { ToonMaterial } from "../render/toon";
import { WALK, type Crowd, type Npc, type Variant } from "./crowd";
import type { Fx } from "../fx/fx";
import type { Audio } from "../audio/audio";
import { makeFish } from "../game/mg/goldfish";

/**
 * Small moments the player stumbles on. Each is a little scene at its own spot on the street or
 * the beach, played by a few townspeople on its own loose schedule (with rests in between, and
 * random choices), so no two walks down the street are quite the same:
 *
 *  - two kids chasing each other; one drops a sparkler and cries, a parent comes over and leads
 *    them off; later the kids are back at it
 *  - a couple sharing a candy apple, passing it back and forth
 *  - friends taking a photo with a phone, then crowding round to look at it
 *  - an old man fanning himself on a bench; a man asleep on a house step
 *  - someone drops a goldfish bag, it bounces off, they hurry after it
 *  - someone's geta slips off; they hop back for it
 *  - at night: couples sit on the sea wall, people light sparklers on the beach
 *  - when the fireworks start, people point up and drift down to the shore to watch
 *  - passers-by react to her: some wave, some bow; kids stop and stare at her mask
 *  - keepers yawn when nobody's about (and wave when she comes near: the director's job)
 *
 * The moments use clips from people.glb when they're there and fall back to the basic set.
 */

/** Wanted clip → what to use if people.glb doesn't have it. */
const FALLBACK: Record<string, string[]> = {
  cry: ["cry", "idle"], comfort: ["comfort", "talk", "idle"], eat: ["eat", "talk"], photo: ["photo", "point", "idle"],
  peace: ["peace", "wave"], laugh: ["laugh", "cheer", "talk"], sit_fan: ["sit_fan", "fan"], sit_sleep: ["sit_sleep", "idle"],
  sit: ["sit", "idle"], cheer: ["cheer", "wave"], yawn: ["yawn", "idle"], bow: ["bow", "wave"], point_up: ["point_up", "point", "lookup"],
  pick_up: ["pick_up", "idle"], hop: ["hop", "walk"], sparkler_stand: ["sparkler_stand", "idle"],
  run: ["run", "walk"], walk: ["walk"], idle: ["idle"], talk: ["talk", "idle"], wave: ["wave"], lookup: ["lookup", "idle"],
};

const rand = (a: number, b: number) => a + Math.random() * (b - a);
const dampAngle = (a: number, b: number, k: number, dt: number) => {
  let d = b - a; d = Math.atan2(Math.sin(d), Math.cos(d));
  return a + d * (1 - Math.exp(-k * dt));
};

interface Ctx { her: THREE.Vector3; heroHeading: number; heroSpeed: number; night: boolean; show: boolean; masked: boolean; dt: number; t: number }

abstract class Moment {
  protected t = 0;
  constructor(protected m: Moments) {}
  abstract update(c: Ctx): void;
}

export class Moments {
  private list: Moment[] = [];
  private t = 0;
  /** People on the street who react to her as she passes (cooldowns per person). */
  private reactCool = new Map<Npc, number>();
  private reacting = new Map<Npc, { t: number; resume: string; rate: number }>();
  private yawnT = new Map<Npc, number>();
  private gathered = false;
  private stareT = new Map<Npc, number>();

  constructor(
    readonly crowd: Crowd, readonly fx: Fx, readonly audio: Audio, readonly scene: THREE.Object3D,
    readonly groundY: (x: number, z: number) => number, private appleProto: THREE.Object3D | null,
    readonly block: (x0: number, x1: number, z0: number, z1: number) => void,
  ) {}

  build(): void {
    if (!this.crowd.ok) return;
    this.list.push(
      new KidsChase(this, new THREE.Vector3(0.9, 0, -11.5), new THREE.Vector3(-2.9, 0, -10.2)),
      new SharedApple(this, new THREE.Vector3(2.6, 0, -33.6)),
      new PhotoGroup(this, new THREE.Vector3(2.5, 0, -57.2)),
      new Bench(this, new THREE.Vector3(3.95, 0, -47.2)),
      new StepSleeper(this, new THREE.Vector3(-4.2, 0, -70.2)),
      new BagDrop(this, -1.7, -21, -47),
      new LostGeta(this, 1.7, -81, -58),
      new WallCouples(this),
      new BeachSparklers(this),
    );
  }

  // ---------------------------------------------------------------- helpers for the moments
  clip(name: string): string {
    for (const c of FALLBACK[name] ?? [name]) if (this.crowd.has(c)) return c;
    return "idle";
  }
  play(n: Npc, name: string, fade = 0.35, rate = 1, once = false): void { this.crowd.play(n, this.clip(name), fade, rate, once); }
  /** Length of a clip in seconds (for one-shots). */
  dur(name: string): number {
    const n = this.crowd.npcs[0];
    const a = n?.acts.get(this.clip(name));
    return a ? a.getClip().duration : 1.5;
  }
  spawn(v: Variant, x: number, z: number, heading: number, clip = "idle"): Npc {
    const n = this.crowd.spawn(v, "scripted", x, z, heading);
    this.play(n, clip, 0);
    n.mixer.update(rand(0, 3));
    return n;
  }
  /** Walks n toward (x, z) at `speed`; true once there. */
  walkTo(n: Npc, x: number, z: number, speed: number, dt: number, run = false): boolean {
    const dx = x - n.pos.x, dz = z - n.pos.z, d = Math.hypot(dx, dz);
    if (d < 0.08) return true;
    // No faster than the legs can carry them (the cadence is capped at 1.7x the clip).
    speed = Math.min(speed, this.crowd.clipSpeed(n, run ? "run" : "walk") * 1.7);
    const step = Math.min(d, speed * dt);
    n.pos.x += (dx / d) * step;
    n.pos.z += (dz / d) * step;
    n.pos.y = this.groundY(n.pos.x, n.pos.z);
    n.heading = dampAngle(n.heading, Math.atan2(dx, dz), 7, dt);
    this.play(n, run ? "run" : "walk", 0.3, 1);
    if (n.cur) n.cur.timeScale = THREE.MathUtils.clamp(speed / this.crowd.clipSpeed(n, n.cur.getClip().name), 0.4, 1.7);
    return false;
  }
  face(n: Npc, x: number, z: number, dt: number, k = 4): void {
    n.heading = dampAngle(n.heading, Math.atan2(x - n.pos.x, z - n.pos.z), k, dt);
  }
  /**
   * Puts `obj` in n's hand (bone "hand_R" / "hand_L"): offset given in n's own frame (+Z
   * forward, +Y up) from the hand's current position, then parented to the bone.
   */
  hold(n: Npc, hand: "hand_R" | "hand_L", obj: THREE.Object3D, off = new THREE.Vector3(), rot = new THREE.Euler()): void {
    const b = n.root.getObjectByName(hand) ?? n.root;
    n.root.rotation.y = n.heading;
    n.root.updateMatrixWorld(true);
    const base = n.root.worldToLocal(b.getWorldPosition(new THREE.Vector3()));
    obj.position.copy(base).add(off);
    obj.rotation.copy(rot);
    n.root.add(obj);
    obj.updateMatrixWorld(true);
    b.attach(obj);
  }
  /** Drops a held prop into the world where it is now. */
  drop(obj: THREE.Object3D): void { this.scene.attach(obj); }
  apple(): THREE.Object3D {
    if (this.appleProto) { const a = this.appleProto.clone(true); a.visible = true; a.scale.setScalar(1); return a; }
    const g = new THREE.Group();
    const s = new THREE.Mesh(new THREE.SphereGeometry(0.045, 14, 10), new ToonMaterial({ color: "#c8182a", paint: 0, rim: 0.8 }));
    const st = new THREE.Mesh(new THREE.CylinderGeometry(0.0035, 0.0035, 0.15, 6), new ToonMaterial({ color: "#d8c49a", paint: 0 }));
    st.position.y = -0.08;
    g.add(s, st);
    return g;
  }
  sparkler(): THREE.Object3D {
    const w = new THREE.Mesh(new THREE.CylinderGeometry(0.003, 0.003, 0.3, 4).translate(0, 0.15, 0), new ToonMaterial({ color: "#3a3430", paint: 0 }));
    w.name = "sparkler";
    return w;
  }
  sparkTip(o: THREE.Object3D, dt: number): void {
    if (!o.parent || !o.visible) return;
    this.fx.sparkler(o.localToWorld(new THREE.Vector3(0, 0.3, 0)), dt);
  }
  phone(): THREE.Object3D {
    const g = new THREE.Group();
    const body = new THREE.Mesh(new THREE.BoxGeometry(0.072, 0.15, 0.009), new ToonMaterial({ color: "#2a2c34", paint: 0, rim: 0.5 }));
    const scr = new THREE.Mesh(new THREE.PlaneGeometry(0.064, 0.138), new THREE.MeshBasicNodeMaterial({ color: new THREE.Color(0.75, 0.85, 1.0).multiplyScalar(1.4) }));
    scr.position.z = -0.0047;
    scr.rotation.y = Math.PI;
    g.add(body, scr);
    return g;
  }
  bag(): THREE.Object3D {
    const bag = new THREE.Group();
    const water = new THREE.Mesh(new THREE.SphereGeometry(0.055, 14, 10), new THREE.MeshBasicNodeMaterial({ color: "#bfe6f2", transparent: true, opacity: 0.35, depthWrite: false }));
    water.scale.set(1, 1.15, 1);
    const knot = new THREE.Mesh(new THREE.ConeGeometry(0.016, 0.05, 8), new ToonMaterial({ color: "#e65a8a", paint: 0 }));
    knot.position.y = 0.08;
    const fish = makeFish("#ff6a24").g;
    fish.scale.setScalar(0.85);
    bag.add(water, fish, knot);
    return bag;
  }
  geta(): THREE.Object3D {
    const g = new THREE.Group();
    const wood = new ToonMaterial({ color: "#c8a070", paint: 0.3 });
    const base = new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.018, 0.23), wood);
    base.position.y = 0.045;
    for (const z of [-0.06, 0.06]) { const t = new THREE.Mesh(new THREE.BoxGeometry(0.09, 0.035, 0.02), wood); t.position.set(0, 0.018, z); g.add(t); }
    const strap = new THREE.Mesh(new THREE.TorusGeometry(0.035, 0.006, 5, 12, Math.PI), new ToonMaterial({ color: "#c0303a", paint: 0 }));
    strap.position.set(0, 0.055, 0.03);
    g.add(base, strap);
    return g;
  }
  dist(n: Npc, p: THREE.Vector3): number { return Math.hypot(n.pos.x - p.x, n.pos.z - p.z); }

  // ---------------------------------------------------------------- per frame
  update(dt: number, her: THREE.Vector3, heroHeading: number, heroSpeed: number, night: boolean, show: boolean, masked: boolean): void {
    if (!this.crowd.ok) return;
    this.t += dt;
    const c: Ctx = { her, heroHeading, heroSpeed, night, show, masked, dt, t: this.t };
    for (const m of this.list) m.update(c);
    this.reactions(c);
    this.keepers(c);
    this.fireworks(c);
  }

  /** Passers-by: a wave or a small bow as she goes by; kids stop and stare at her mask. */
  private reactions(c: Ctx) {
    for (const [n, cd] of this.reactCool) { if (cd - c.dt <= 0) this.reactCool.delete(n); else this.reactCool.set(n, cd - c.dt); }
    for (const [n, r] of this.reacting) {
      r.t -= c.dt;
      if (r.t <= 0) {
        this.reacting.delete(n);
        n.mode = n.v === "kid" && (n as any).tip ? "kid" : "stroll";
        this.crowd.play(n, r.resume, 0.4, r.rate);
      } else this.face(n, c.her.x, c.her.z, c.dt, 3);
    }
    for (const n of this.crowd.npcs) {
      if ((n.mode !== "stroll" && n.mode !== "kid") || this.reactCool.has(n)) continue;
      const d = this.dist(n, c.her);
      if (n.v === "kid" && c.masked && d < 6 && d > 1.4) {
        // Mask! They stop and stare a moment.
        this.reactCool.set(n, rand(25, 45));
        this.startReact(n, "idle", rand(2.2, 3.4));
        this.stareT.set(n, 3);
        continue;
      }
      if (d > 2.6 || d < 0.9) continue;
      // Only when they're coming toward her (they've seen her).
      const toward = Math.cos(Math.atan2(c.her.x - n.pos.x, c.her.z - n.pos.z) - n.heading);
      if (toward < 0.4) continue;
      this.reactCool.set(n, rand(30, 60));
      const r = Math.random();
      if (r < 0.28) this.startReact(n, "wave", Math.min(2.2, this.dur("wave")), true);
      else if (r < 0.5 && n.v !== "kid") this.startReact(n, "bow", Math.min(2.0, this.dur("bow")), true);
    }
  }
  /** Someone answers her (a wave, a bow, a cheer): strollers stop for it, then walk on. */
  react(n: Npc, clip: string, secs: number): void {
    if (n.mode !== "stroll" && n.mode !== "kid") {
      this.play(n, clip, 0.3, 1, true);
      n.oneShot = secs;
      setTimeout(() => { if (n.mode === "stand") this.crowd.play(n, "idle", 0.5); }, secs * 1000);
      return;
    }
    if (this.reacting.has(n)) return;
    this.reactCool.set(n, rand(20, 40));
    this.startReact(n, clip, secs, true);
  }
  private startReact(n: Npc, clip: string, secs: number, once = false) {
    const resume = n.cur?.getClip().name ?? "walk";
    const rate = n.cur?.timeScale ?? 1;
    n.mode = "scripted";
    this.play(n, clip, 0.3, 1, once);
    this.reacting.set(n, { t: secs, resume, rate });
  }

  /** Keepers with nobody about now and then stretch and yawn. */
  private keepers(c: Ctx) {
    for (const n of this.crowd.npcs) {
      if (n.mode !== "keeper" || n.oneShot > 0) continue;
      let t = this.yawnT.get(n) ?? rand(8, 40);
      t -= c.dt;
      if (t <= 0) {
        t = rand(25, 60);
        if (this.dist(n, c.her) > 12 && this.crowd.has("yawn")) {
          this.play(n, "yawn", 0.4, 1, true);
          n.oneShot = this.dur("yawn") + 0.2;
        }
      }
      this.yawnT.set(n, t);
    }
  }

  /** Fireworks: the beach watchers point up; people on the lower street drift down to the shore. */
  private fireworks(c: Ctx) {
    if (!c.show || this.gathered) return;
    this.gathered = true;
    let k = 0;
    for (const n of this.crowd.npcs) {
      if (n.mode === "watch") {
        this.play(n, "point_up", 0.4, 1, true);
        setTimeout(() => this.play(n, "lookup", 1.0), this.dur("point_up") * 1000);
      } else if (n.mode === "stroll" && n.pos.z < -55 && k < 8) {
        // Down to the promenade rail to watch.
        const slot = k++;
        const x = (slot % 2 ? 1 : -1) * (4 + Math.floor(slot / 2) * 1.6 + rand(-0.3, 0.3));
        this.list.push(new GoWatch(this, n, x, -98.4 + rand(-0.3, 0.3)));
      }
    }
  }
}

// ======================================================================== the moments

/** Kids chasing each other round a lantern pole; one drops her sparkler and cries; a parent comes. */
class KidsChase extends Moment {
  private a: Npc; private b: Npc; private parent: Npc;
  private ang = 0;
  private state: "chase" | "cry" | "comfort" | "leave" | "rest" | "back" = "chase";
  private dropped: THREE.Object3D | null = null;
  private wireA: THREE.Object3D; private wireB: THREE.Object3D;
  private home: THREE.Vector3;
  constructor(m: Moments, private c: THREE.Vector3, parentAt: THREE.Vector3) {
    super(m);
    this.home = parentAt.clone();
    this.a = m.spawn("kid", c.x + 1.4, c.z, 0, "run");
    this.b = m.spawn("kid", c.x - 1.4, c.z, Math.PI, "run");
    this.parent = m.spawn("woman", parentAt.x, parentAt.z, Math.PI / 2, "talk");
    this.wireA = m.sparkler(); this.wireB = m.sparkler();
    m.hold(this.a, "hand_R", this.wireA, new THREE.Vector3(0, 0.05, 0.03));
    m.hold(this.b, "hand_R", this.wireB, new THREE.Vector3(0, 0.05, 0.03));
    this.t = rand(12, 30);
  }
  update(c: Ctx): void {
    const m = this.m, dt = c.dt;
    this.t -= dt;
    m.sparkTip(this.wireA, dt);
    if (this.wireB.parent && this.wireB.visible && !this.dropped) m.sparkTip(this.wireB, dt);
    // The chasers run a loose figure round the centre.
    const run = (n: Npc, off: number) => {
      const r = 1.5 + Math.sin(this.ang * 0.7 + off) * 0.35;
      const x = this.c.x + Math.sin(this.ang + off) * r, z = this.c.z + Math.cos(this.ang + off) * r * 0.8;
      m.walkTo(n, x, z, 2.0, dt, true);
    };
    if (this.state === "chase" || this.state === "back") {
      this.ang += dt * 1.15;
      run(this.a, 0);
      if (this.state === "chase") run(this.b, Math.PI * 0.75);
      else if (m.walkTo(this.b, this.c.x, this.c.z + 1.6, 1.0, dt)) this.state = "chase";
      if (this.state === "chase" && this.t <= 0) {
        // She trips over her own feet: the sparkler falls, and she cries.
        this.state = "cry";
        this.t = rand(2.5, 4);
        m.drop(this.wireB);
        this.dropped = this.wireB;
        this.dropped.position.y = m.groundY(this.dropped.position.x, this.dropped.position.z) + 0.01;
        this.dropped.rotation.set(Math.PI / 2, rand(0, 6), 0);
        m.play(this.b, "cry", 0.25);
      }
    } else if (this.state === "cry") {
      this.ang += dt * 0.6;
      run(this.a, 0);
      if (this.t <= 0) this.state = "comfort";
    } else if (this.state === "comfort") {
      // The parent comes over, kneels and comforts her, then they walk off together.
      const to = this.b.pos.clone().add(new THREE.Vector3(Math.sin(this.b.heading) * 0.55, 0, Math.cos(this.b.heading) * 0.55));
      if (m.walkTo(this.parent, to.x, to.z, 1.2, dt)) {
        m.face(this.parent, this.b.pos.x, this.b.pos.z, dt);
        m.face(this.b, this.parent.pos.x, this.parent.pos.z, dt);
        if (!(this.parent as any).kneel) { (this.parent as any).kneel = true; m.play(this.parent, "comfort", 0.4); this.t = Math.max(3.2, m.dur("comfort")); }
        if (this.t <= 0) { (this.parent as any).kneel = false; this.state = "leave"; this.dropped?.removeFromParent(); m.play(this.b, "walk", 0.5); }
      } else this.t = 3;
      run(this.a, 0);
      this.ang += dt * 0.5;
    } else if (this.state === "leave") {
      // Off toward the parent's spot, the kid at her side.
      const done = m.walkTo(this.parent, this.home.x, this.home.z, 0.75, dt);
      m.walkTo(this.b, this.home.x + 0.5, this.home.z + 0.5, 0.75, dt);
      run(this.a, 0);
      this.ang += dt * 0.5;
      if (done) { this.state = "rest"; this.t = rand(25, 50); m.play(this.parent, "talk", 0.5); m.play(this.b, "idle", 0.5); m.face(this.parent, this.c.x, this.c.z, 1); }
    } else if (this.state === "rest") {
      // The other kid waits; then the two are back at it with a fresh sparkler.
      m.walkTo(this.a, this.c.x + 0.6, this.c.z, 0.8, dt) && m.play(this.a, "idle", 0.5);
      if (this.t <= 0) {
        this.state = "back";
        this.wireB = m.sparkler();
        m.hold(this.b, "hand_R", this.wireB, new THREE.Vector3(0, 0.05, 0.03));
        this.dropped = null;
        this.t = rand(25, 45);
      }
    }
  }
}

/** A couple sharing a candy apple: one nibbles, passes it over, the other does. */
class SharedApple extends Moment {
  private p: Npc[];
  private apple: THREE.Object3D;
  private who = 0;
  constructor(m: Moments, at: THREE.Vector3) {
    super(m);
    this.p = [m.spawn("woman", at.x, at.z - 0.35, 0, "eat"), m.spawn("man", at.x, at.z + 0.35, Math.PI, "talk")];
    this.apple = m.apple();
    m.hold(this.p[0], "hand_R", this.apple, new THREE.Vector3(0, 0.1, 0.03), new THREE.Euler(0, 0, 0));
    this.t = rand(4, 8);
  }
  update(c: Ctx): void {
    const m = this.m;
    this.t -= c.dt;
    m.face(this.p[0], this.p[1].pos.x, this.p[1].pos.z, c.dt);
    m.face(this.p[1], this.p[0].pos.x, this.p[0].pos.z, c.dt);
    if (this.t <= 0) {
      // Pass it over.
      this.t = rand(5, 10);
      const from = this.p[this.who], to = this.p[1 - this.who];
      this.who = 1 - this.who;
      m.hold(to, "hand_R", this.apple, new THREE.Vector3(0, 0.1, 0.03));
      m.play(to, "eat", 0.4);
      m.play(from, Math.random() < 0.5 ? "laugh" : "talk", 0.4);
    }
  }
}

/** Friends taking a photo with a phone, then crowding round to look at it. */
class PhotoGroup extends Moment {
  private cam: Npc; private posers: Npc[];
  private phone: THREE.Object3D;
  private state: "pose" | "look" | "back" = "pose";
  private at: THREE.Vector3;
  constructor(m: Moments, at: THREE.Vector3) {
    super(m);
    this.at = at.clone();
    this.posers = [m.spawn("woman", at.x + 0.1, at.z - 0.35, -Math.PI / 2, "peace"), m.spawn("woman", at.x + 0.15, at.z + 0.35, -Math.PI / 2, "peace")];
    this.cam = m.spawn(Math.random() < 0.5 ? "man" : "woman", at.x - 1.8, at.z, Math.PI / 2, "photo");
    this.phone = m.phone();
    m.hold(this.cam, "hand_R", this.phone, new THREE.Vector3(-0.03, 0.06, 0.05), new THREE.Euler(0, 0, 0));
    this.t = rand(3, 6);
  }
  update(c: Ctx): void {
    const m = this.m;
    this.t -= c.dt;
    if (this.state === "pose") {
      m.face(this.cam, this.at.x + 0.1, this.at.z, c.dt);
      for (const p of this.posers) m.face(p, this.cam.pos.x, this.cam.pos.z, c.dt);
      if (this.t <= 0) {
        // Click: a little flash, then everyone gathers to see.
        const p = this.phone.getWorldPosition(new THREE.Vector3());
        m.fx.sparkle(p, new THREE.Color(1, 1, 1), 10, 0.25);
        m.audio.blip("clack", p);
        this.state = "look";
        this.t = rand(4, 6);
        for (const q of this.posers) m.play(q, "walk", 0.3);
      }
    } else if (this.state === "look") {
      const done = this.posers.map((q, i) => m.walkTo(q, this.cam.pos.x + 0.45, this.cam.pos.z + (i ? 0.45 : -0.45), 0.8, c.dt));
      this.posers.forEach((q, i) => { if (done[i]) { m.face(q, this.cam.pos.x, this.cam.pos.z, c.dt); if (q.cur?.getClip().name !== m.clip("laugh")) m.play(q, "laugh", 0.4); } });
      if (this.t <= 0) this.state = "back";
    }
    if (this.state === "back") {
      // Back to their places for another one, a while later.
      const done = this.posers.map((q, i) => m.walkTo(q, this.at.x + 0.1 + i * 0.05, this.at.z + (i ? 0.35 : -0.35), 0.8, c.dt));
      if (done.every(Boolean)) {
        this.state = "pose";
        this.t = rand(25, 50);
        for (const q of this.posers) m.play(q, "peace", 0.5);
      }
    }
  }
}

/** An old man on a bench, fanning himself. */
class Bench extends Moment {
  private n: Npc;
  constructor(m: Moments, at: THREE.Vector3) {
    super(m);
    // The old man first (heights vary), then a bench built to the height he sits at: a plank on
    // two legs against the house front. His feet are on the ground, hips back on the plank.
    const side = at.x > 0 ? -1 : 1;
    const sits = m.crowd.has("sit_fan");
    this.n = m.spawn("elder", at.x, at.z + 0.2, side * Math.PI / 2, "sit_fan");
    const seat = m.crowd.seat(this.n);
    const top = sits ? seat.h : 0.43;
    if (sits) this.n.pos.x = at.x + side * (seat.back - 0.02);
    else { this.n.pos.x = at.x + side * 0.1; this.n.pos.z = at.z + 1.25; }
    const wood = new ToonMaterial({ color: "#8a6a48", paint: 0.5 });
    const g = new THREE.Group();
    const plank = new THREE.Mesh(new THREE.BoxGeometry(0.4, 0.05, 1.5), wood);
    plank.position.y = top - 0.025;
    g.add(plank);
    for (const z of [-0.6, 0.6]) { const l = new THREE.Mesh(new THREE.BoxGeometry(0.34, top - 0.05, 0.06), wood); l.position.set(0, (top - 0.05) / 2, z); g.add(l); }
    g.traverse((o) => { if ((o as THREE.Mesh).isMesh) { o.castShadow = true; o.receiveShadow = true; } });
    g.position.copy(at);
    m.scene.add(g);
    // Solid: the bench and his knees and feet in front of it.
    m.block(Math.min(at.x - 0.22, this.n.pos.x - 0.15), Math.max(at.x + 0.22, this.n.pos.x + 0.15), at.z - 0.78, at.z + 0.78);
  }
  update(): void {}
}

/** A man asleep sitting on a house step, head nodding. */
class StepSleeper extends Moment {
  constructor(m: Moments, at: THREE.Vector3) {
    super(m);
    // A man dozing on a low stone step in front of a house door; the step is as high as he sits.
    const side = at.x > 0 ? -1 : 1;
    const n = m.crowd.has("sit_sleep") ? m.spawn("man", at.x, at.z, side * Math.PI / 2, "sit_sleep") : null;
    const seat = n ? m.crowd.seat(n) : { h: 0.42, back: 0.3 };
    if (n) n.pos.x = at.x + side * (seat.back - 0.04);
    const step = new THREE.Mesh(new THREE.BoxGeometry(0.55, seat.h, 1.3), new ToonMaterial({ color: "#9d968c", paint: 0.6 }));
    step.position.set(at.x, seat.h / 2, at.z);
    step.castShadow = step.receiveShadow = true;
    m.scene.add(step);
    m.block(Math.min(at.x - 0.28, (n?.pos.x ?? at.x) - 0.15), Math.max(at.x + 0.28, (n?.pos.x ?? at.x) + 0.15), at.z - 0.65, at.z + 0.65);
  }
  update(): void {}
}

/** Someone carrying a goldfish bag drops it; it bounces off and they hurry after it. */
class BagDrop extends Moment {
  private n: Npc;
  private bag: THREE.Object3D;
  private dir = -1;
  private state: "walk" | "drop" | "chase" | "pick" = "walk";
  private vel = new THREE.Vector3();
  constructor(m: Moments, private x: number, private z0: number, private z1: number) {
    super(m);
    this.n = m.spawn("woman", x, rand(z1, z0), Math.PI, "walk");
    this.bag = m.bag();
    m.hold(this.n, "hand_L", this.bag, new THREE.Vector3(0, -0.14, 0.02));
    this.t = rand(15, 40);
  }
  update(c: Ctx): void {
    const m = this.m, n = this.n, dt = c.dt;
    this.t -= dt;
    if (this.state === "walk") {
      const tz = this.dir < 0 ? this.z1 : this.z0;
      if (m.walkTo(n, this.x, tz, WALK.woman * n.scale * 0.9, dt)) this.dir *= -1;
      if (this.t <= 0 && m.dist(n, c.her) < 25) {
        this.state = "drop";
        m.drop(this.bag);
        this.vel.set(Math.sin(n.heading) * 1.1 + rand(-0.3, 0.3), 0.6, Math.cos(n.heading) * 1.1);
        m.play(n, "idle", 0.2);
        this.t = 0.5;
      } else if (this.t <= 0) this.t = rand(5, 10);
    } else {
      // The bag bounces and skids along the paving.
      const b = this.bag;
      if (this.vel.lengthSq() > 1e-4) {
        this.vel.y -= 9.8 * dt;
        b.position.addScaledVector(this.vel, dt);
        const gy = m.groundY(b.position.x, b.position.z) + 0.065;
        if (b.position.y < gy) { b.position.y = gy; this.vel.y = Math.abs(this.vel.y) * 0.45; this.vel.x *= 0.7; this.vel.z *= 0.7; if (Math.abs(this.vel.y) < 0.25) this.vel.y = 0; if (Math.hypot(this.vel.x, this.vel.z) < 0.08) this.vel.set(0, 0, 0); }
        b.rotation.z = Math.sin(c.t * 9) * 0.3 * Math.min(1, this.vel.length());
      }
      if (this.state === "drop" && this.t <= 0) this.state = "chase";
      if (this.state === "chase" && m.walkTo(n, b.position.x - Math.sin(n.heading) * 0.35, b.position.z - Math.cos(n.heading) * 0.35, 1.6, dt, false) && this.vel.lengthSq() < 1e-4) {
        this.state = "pick";
        m.play(n, "pick_up", 0.3, 1, true);
        this.t = Math.max(1.2, m.dur("pick_up") * 0.55);
      }
      if (this.state === "pick" && this.t <= 0) {
        m.hold(n, "hand_L", this.bag, new THREE.Vector3(0, -0.14, 0.02));
        this.bag.rotation.set(0, 0, 0);
        this.state = "walk";
        this.t = rand(60, 120);
      }
    }
  }
}

/** A geta slips off mid-stride; they hop back on one foot to slip it on again. */
class LostGeta extends Moment {
  private n: Npc;
  private dir = 1;
  private state: "walk" | "hop" | "put" = "walk";
  private sandal: THREE.Object3D | null = null;
  private foot: THREE.Object3D | null;
  constructor(m: Moments, private x: number, private z0: number, private z1: number) {
    super(m);
    this.n = m.spawn("man", x, rand(z0, z1), 0, "walk");
    this.foot = this.n.root.getObjectByName("geta_R") ?? null;
    this.t = rand(20, 50);
  }
  update(c: Ctx): void {
    const m = this.m, n = this.n, dt = c.dt;
    this.t -= dt;
    if (this.state === "walk") {
      const tz = this.dir > 0 ? this.z1 : this.z0;
      if (m.walkTo(n, this.x, tz, WALK.man * n.scale * 0.95, dt)) this.dir *= -1;
      if (this.t <= 0 && m.dist(n, c.her) < 22) {
        // Off it comes, left behind on the paving.
        this.state = "hop";
        this.sandal = m.geta();
        const back = new THREE.Vector3(-Math.sin(n.heading) * 0.9, 0, -Math.cos(n.heading) * 0.9);
        this.sandal.position.copy(n.pos).add(back).add(new THREE.Vector3(0.12, 0, 0));
        this.sandal.position.y = m.groundY(this.sandal.position.x, this.sandal.position.z);
        this.sandal.rotation.y = n.heading + rand(-0.8, 0.8);
        m.scene.add(this.sandal);
        if (this.foot) this.foot.visible = false;
        this.t = 0;
      } else if (this.t <= 0) this.t = rand(5, 10);
    } else if (this.state === "hop") {
      const s = this.sandal!;
      // Hop back to it (facing it).
      const there = m.walkTo(n, s.position.x - 0.12, s.position.z + 0.0001, 0.8, dt);
      m.play(n, "hop", 0.25, 1.2);
      if (there) { this.state = "put"; m.play(n, "pick_up", 0.3, 1, true); this.t = Math.max(1.0, m.dur("pick_up") * 0.6); }
    } else if (this.state === "put" && this.t <= 0) {
      this.sandal?.removeFromParent();
      this.sandal = null;
      if (this.foot) this.foot.visible = true;
      this.state = "walk";
      this.t = rand(70, 140);
    }
  }
}

/** After dark: two couples sitting on the sea wall, looking out over the water. */
class WallCouples extends Moment {
  private p: Npc[] = [];
  private sit = this.m.crowd.has("sit");
  private y = new Map<Npc, number>();
  constructor(m: Moments) {
    super(m);
    // Coping top y = 0.74; a sitter's seat is 0.45 above their feet.
    for (const [x, v] of [[-8.2, "woman"], [-7.6, "man"], [11.4, "man"], [12.0, "woman"]] as [number, Variant][]) {
      // On the coping (top y = 0.74) facing the sea, feet hanging over the beach side; without
      // the sitting clip they stand at the wall instead.
      const n = this.sit ? m.spawn(v, x, -100.1, Math.PI, "sit") : m.spawn(v, x, -99.35, Math.PI, "idle");
      if (this.sit) { const st = m.crowd.seat(n); n.pos.z = -100.1 - st.back; this.y.set(n, 0.74 - st.h); n.pos.y = 0.74 - st.h; }
      n.root.visible = false;
      this.p.push(n);
    }
  }
  update(c: Ctx): void {
    for (const n of this.p) {
      if (this.sit) n.pos.y = this.y.get(n) ?? 0.3;
      if (!c.night) n.root.visible = false;
      n.hide = !c.night;
    }
  }
}

/** At night, people on the beach with sparklers. */
class BeachSparklers extends Moment {
  private s: { n: Npc; w: THREE.Object3D }[] = [];
  constructor(m: Moments) {
    super(m);
    for (const [x, z, v] of [[-3.2, -110.5, "kid"], [-2.6, -110.9, "woman"], [7.8, -109.6, "woman"], [8.4, -110.2, "kid"], [14, -112, "man"]] as [number, number, Variant][]) {
      const n = m.spawn(v, x, z, Math.PI + rand(-0.6, 0.6), "sparkler_stand");
      const w = m.sparkler();
      m.hold(n, "hand_R", w, new THREE.Vector3(0, 0.05, 0.03));
      this.s.push({ n, w });
    }
  }
  update(c: Ctx): void {
    for (const { n, w } of this.s) {
      n.hide = !c.night;
      w.visible = c.night;
      if (c.night && n.root.visible) this.m.sparkTip(w, c.dt);
    }
  }
}

/** One person walking down to the shore when the fireworks start, then watching. */
class GoWatch extends Moment {
  private there = false;
  constructor(m: Moments, private n: Npc, private x: number, private z: number) {
    super(m);
    n.mode = "scripted";
    m.play(n, "point_up", 0.3, 1, true);
    this.t = m.dur("point_up");
  }
  update(c: Ctx): void {
    const m = this.m, n = this.n;
    this.t -= c.dt;
    if (this.t > 0 || this.there) return;
    if (m.walkTo(n, this.x, this.z, WALK[n.v] * n.scale, c.dt)) {
      this.there = true;
      n.heading = Math.PI;
      m.play(n, "lookup", 1.0);
    }
  }
}
