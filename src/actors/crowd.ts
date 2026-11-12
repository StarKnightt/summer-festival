import { uniform } from "three/tsl";
import * as THREE from "three/webgpu";
import { clone as skClone } from "three/addons/utils/SkeletonUtils.js";
import { loadGLB, type Stall } from "../world/stalls";
import { toonify } from "../render/toonify";
import { ToonMaterial } from "../render/toon";
import type { Fx } from "../fx/fx";
import type { Audio } from "../audio/audio";

export type Variant = "woman" | "man" | "kid" | "keeper" | "elder";
/** scripted: driven by a Moment (position, heading and clips set from outside). */
export type Mode = "stroll" | "stand" | "kid" | "keeper" | "watch" | "scripted";

export interface Npc {
  root: THREE.Object3D;
  v: Variant;
  mode: Mode;
  mixer: THREE.AnimationMixer;
  acts: Map<string, THREE.AnimationAction>;
  cur: THREE.AnimationAction | null;
  pos: THREE.Vector3;
  heading: number;
  speed: number;
  /** stroll: lane x and direction (−1 toward the sea). */
  lane: number;
  dir: number;
  side: number;
  hand: THREE.Object3D | null;
  stall?: Stall;
  oneShot: number;
  acc: number;
  next: number;
  look: THREE.Vector3 | null;
  head: THREE.Bone | null;
  /** The head's pure animated rotation (glances are added on top of this, never stacked). */
  headQ: THREE.Quaternion | null;
  /** Body scale (heights vary); clip rates are divided by it so strides still match the ground. */
  scale: number;
  /** Wearing glasses or sunglasses (when people.glb has them). */
  glasses: string | null;
  /** Face meshes with blink / smile morphs (both LODs). */
  faces: THREE.Mesh[];
  blinkT: number;
  /** 0..1: how much they're smiling (set by whoever directs them; eases back to 0). */
  smile: number;
  /** Kept out of sight by a moment (e.g. night-only scenes during the day). */
  hide?: boolean;
  /** Detailed mesh for close range (npc_X_near) and the simple one (npc_X_body). */
  near: THREE.Object3D | null;
  far: THREE.Object3D | null;
}

/** Per-variant palettes for cloth_main / cloth_accent (yukata colours). */
const PALETTES: Record<Variant, [string, string][]> = {
  woman: [["#f19aa6", "#f3c74f"], ["#7fb4e0", "#f6efe0"], ["#f6e6b8", "#d8423a"], ["#b89ee0", "#f3c74f"], ["#3c4f86", "#f19aa6"]],
  man: [["#40507a", "#e8dcc4"], ["#5a6a52", "#2a2a2a"], ["#8a6a4a", "#e8dcc4"], ["#2e3346", "#c8a060"]],
  kid: [["#7cc3ea", "#f3c74f"], ["#f39a6a", "#ffffff"], ["#f7b7d0", "#7cc3ea"], ["#9ad08a", "#f3c74f"]],
  keeper: [["#d8423a", "#f6efe0"], ["#3a6ab0", "#f6efe0"], ["#e0a040", "#2a2a2a"]],
  elder: [["#cfc6e6", "#6a5a8a"], ["#c8d8c0", "#5a6a52"]],
};
export const WALK: Record<Variant, number> = { woman: 0.9, man: 0.984, kid: 0.562, keeper: 0.956, elder: 0.855 };

const rand = (a: number, b: number) => a + Math.random() * (b - a);
const damp = (a: number, b: number, k: number, dt: number) => b + (a - b) * Math.exp(-k * dt);
const dampAngle = (a: number, b: number, k: number, dt: number) => {
  let d = b - a; d = Math.atan2(Math.sin(d), Math.cos(d));
  return a + d * (1 - Math.exp(-k * dt));
};

/**
 * The festival crowd (people.glb): couples and friends strolling in small groups, people chatting
 * by the stalls, kids skipping with sparklers, a keeper behind every stall who calls out and waves
 * when she comes near, and people gathered on the beach for the fireworks. Animation is updated at
 * a lower rate far away; everyone keeps clear of her.
 */
export class Crowd {
  readonly group = new THREE.Group();
  readonly npcs: Npc[] = [];
  private protos = new Map<string, THREE.Object3D>();
  private clips: THREE.AnimationClip[] = [];
  /** From people.glb: the ground speed each locomotion clip covers per variant (m/s at rate 1, scale 1), and how each variant sits. */
  private clipSpeeds: Record<string, Record<string, number>> = {};
  private seats: { seatHeight?: Record<string, number>; hipsBack?: Record<string, number> } = {};
  private t = 0;
  ok = false;

  constructor(private fx: Fx, private audio: Audio, private groundY: (x: number, z: number) => number = () => 0) {
    this.group.name = "crowd";
  }

  async load(stalls: Stall[]): Promise<void> {
    const scene = await loadGLB(`${import.meta.env.BASE_URL}models/people.glb`);
    if (!scene) return;
    // Undo GLTFLoader's de-duplicated names so every clip binds to every variant.
    const anims: THREE.AnimationClip[] = (scene as any).userData.animations ?? [];
    const orig = new Map<string, string>();
    scene.traverse((o) => { if (o.userData.name) orig.set(o.name, o.userData.name); });
    for (const clip of anims) for (const t of clip.tracks) {
      const i = t.name.lastIndexOf(".");
      const node = t.name.slice(0, i);
      t.name = (orig.get(node) ?? node) + t.name.slice(i);
    }
    // Root translation is a small bob for the reference skeleton: drop it (heights differ).
    for (const clip of anims) clip.tracks = clip.tracks.filter((t) => !/^root\.position$/.test(t.name));
    scene.traverse((o) => { if (o.userData.name) o.name = o.userData.name; });
    this.clips = anims;
    const meta = (scene.userData?.people ?? {}) as any;
    this.clipSpeeds = meta.clipSpeed ?? {};
    this.seats = meta.seat ?? {};
    // A few tinted prototypes per variant; clones share their materials.
    for (const v of Object.keys(PALETTES) as Variant[]) {
      const src = scene.getObjectByName(`npc_${v}`);
      if (!src) continue;
      PALETTES[v].forEach(([main, accent], i) => {
        const p = skClone(src);
        // (Paper props people carry, like the old man's fan, are plain paper: only lanterns glow.)
        toonify(p, { tint: { cloth_main: main, cloth_accent: accent }, paperGlowNode: uniform(0) });
        this.protos.set(`${v}${i}`, p);
      });
    }
    this.ok = this.protos.size > 0;
    if (!this.ok) return;
    this.populate(stalls);
  }

  spawn(v: Variant, mode: Mode, x: number, z: number, heading: number): Npc {
    const n = PALETTES[v].length;
    const root = skClone(this.protos.get(`${v}${Math.floor(Math.random() * n)}`)!);
    root.traverse((o) => { if ((o as any).isSkinnedMesh) { o.frustumCulled = false; o.castShadow = true; } });
    // Heights vary: adults about ±7 %, kids more.
    const s = v === "kid" ? rand(0.86, 1.1) : v === "elder" ? rand(0.9, 1.0) : rand(0.92, 1.08);
    root.scale.setScalar(s);
    root.position.set(x, this.groundY(x, z), z);
    root.rotation.y = heading;
    this.group.add(root);
    const mixer = new THREE.AnimationMixer(root);
    const acts = new Map<string, THREE.AnimationAction>();
    for (const c of this.clips) acts.set(c.name, mixer.clipAction(c));
    const hand = root.getObjectByName("hand_R") ?? null;
    const head = (root.getObjectByName("head") as THREE.Bone) ?? null;
    let near: THREE.Object3D | null = null, far: THREE.Object3D | null = null;
    root.traverse((o) => { if (/_near$/.test(o.name)) near = o; else if (/_body$/.test(o.name)) far = o; });
    // Variety: one of the variant's hairstyles, and now and then glasses or sunglasses
    // (optional meshes in people.glb: npc_<v>_hair_<style>, npc_<v>_glasses, npc_<v>_sunglasses).
    const hairs: THREE.Object3D[] = [], specs: THREE.Object3D[] = [];
    root.traverse((o) => {
      if (/_hair_[a-z0-9]+$/.test(o.name)) hairs.push(o);
      else if (/_(sun)?glasses$/.test(o.name)) specs.push(o);
    });
    const pickHair = hairs.length ? Math.floor(Math.random() * hairs.length) : -1;
    hairs.forEach((o, i) => (o.visible = i === pickHair));
    // Faces: each person gets one of the variant's two looks; blink and smile are driven per frame.
    const faces: THREE.Mesh[] = [];
    const lookB = Math.random() < 0.5 ? 1 : 0;
    root.traverse((o) => {
      const m = o as THREE.Mesh;
      if (!m.isMesh || !m.morphTargetDictionary || !m.morphTargetInfluences) return;
      const i = m.morphTargetDictionary["face_b"];
      if (i !== undefined) m.morphTargetInfluences[i] = lookB;
      if (m.morphTargetDictionary["blink"] !== undefined) faces.push(m);
    });
    const r = Math.random();
    const wantSpecs = v === "kid" ? (r < 0.08 ? "sunglasses" : null) : v === "elder" ? (r < 0.45 ? "glasses" : null) : r < 0.16 ? "glasses" : r < 0.27 ? "sunglasses" : null;
    let glasses: string | null = null;
    for (const o of specs) {
      const kind = /_sunglasses$/.test(o.name) ? "sunglasses" : "glasses";
      o.visible = kind === wantSpecs;
      if (o.visible) glasses = kind;
    }
    const npc: Npc = { root, v, mode, mixer, acts, cur: null, pos: root.position, heading, speed: 0, lane: x, dir: -1, side: 0, hand, oneShot: 0, acc: Math.random(), next: rand(2, 8), look: null, head, headQ: head ? head.quaternion.clone() : null, scale: s, near, far, glasses, faces, blinkT: rand(1, 5), smile: 0 };
    this.npcs.push(npc);
    return npc;
  }

  /** A posed copy of every outfit prototype (for the loading-screen warm-up). */
  prototypes(): THREE.Object3D[] { return [...this.protos.values()].map((p) => skClone(p)); }

  has(name: string): boolean { return this.clips.some((c) => c.name === name); }

  /** Ground speed (m/s) `clip` covers on `n` at rate 1: the clip rate for a speed v is v / this. */
  clipSpeed(n: Npc, clip: string): number {
    const t = this.clipSpeeds[clip] ?? this.clipSpeeds[clip === "run" ? "run" : "walk"];
    return (t?.[n.v] ?? (clip === "run" ? WALK[n.v] * 2 : WALK[n.v])) * n.scale;
  }

  /** How `n` sits: the seat height its pose fits, and how far its hips are behind its feet (m). */
  seat(n: Npc): { h: number; back: number } {
    return { h: (this.seats.seatHeight?.[n.v] ?? 0.4) * n.scale, back: (this.seats.hipsBack?.[n.v] ?? 0.33) * n.scale };
  }

  /** Crossfades `n` to clip `name` (looping), or plays it once and holds the last frame. */
  play(n: Npc, name: string, fade = 0.4, rate = 1, once = false) {
    // Women have their own walk.
    if (name === "walk" && n.v === "woman" && n.acts.has("walk_f")) name = "walk_f";
    const a = n.acts.get(name);
    if (!a) return;
    a.setLoop(once ? THREE.LoopOnce : THREE.LoopRepeat, Infinity);
    a.clampWhenFinished = once;
    a.timeScale = rate;
    if (a === n.cur && !once) return;
    a.reset().play();
    if (n.cur && n.cur !== a) a.crossFadeFrom(n.cur, fade, false);
    n.cur = a;
  }

  private populate(stalls: Stall[]) {
    // Strolling groups: couples and friends, in both directions.
    const groups: Variant[][] = [["woman", "man"], ["woman", "woman"], ["woman", "woman", "kid"], ["man", "woman"], ["elder", "woman"], ["woman", "man"], ["man", "man"], ["woman", "woman", "woman"], ["elder", "elder"]];
    groups.forEach((g, gi) => {
      const dir = gi % 2 ? 1 : -1;
      const lane = (gi % 3 - 1) * 1.3 + rand(-0.2, 0.2);
      const z = rand(-90, 6);
      const speed = Math.min(...g.map((v) => (v === "kid" ? 0.8 : WALK[v]))) * rand(0.85, 1.0);
      g.forEach((v, i) => {
        const n = this.spawn(v, "stroll", lane, z, dir < 0 ? Math.PI : 0);
        n.dir = dir;
        n.lane = lane;
        n.side = (i - (g.length - 1) / 2) * 0.62;
        n.speed = speed;
        this.play(n, "walk", 0, speed / this.clipSpeed(n, "walk"));
        n.mixer.update(Math.random());
      });
    });
    // Chatting clusters near the food and shaved-ice stalls.
    const spots = stalls.filter((s) => !s.spot.task).slice(0, 4);
    for (const s of spots) {
      // Beside the counter, never on the spot where she stands to order.
      const c = s.use.clone().add(new THREE.Vector3(s.spot.side * -0.7, 0, (Math.random() < 0.5 ? -1 : 1) * rand(1.9, 2.5)));
      const who: Variant[] = Math.random() < 0.5 ? ["woman", "woman"] : ["man", "woman", "elder"];
      who.forEach((v, i) => {
        const a = (i / who.length) * Math.PI * 2 + rand(0, 1);
        const x = c.x + Math.sin(a) * 0.55, z = c.z + Math.cos(a) * 0.55;
        const n = this.spawn(v, "stand", x, z, Math.atan2(c.x - x, c.z - z));
        this.play(n, v === "elder" ? "fan" : i === 0 ? "talk" : "idle", 0);
        n.mixer.update(rand(0, 4));
        n.look = c.clone().setY(1.5);
      });
    }
    // Kids with sparklers, skipping up and down the street.
    for (let i = 0; i < 3; i++) {
      const n = this.spawn("kid", "kid", rand(-1.8, 1.8), rand(-80, 0), Math.random() < 0.5 ? 0 : Math.PI);
      n.dir = n.heading === 0 ? 1 : -1;
      n.lane = n.pos.x;
      n.speed = 0.85;
      this.play(n, "sparkler", 0, n.speed / this.clipSpeed(n, "sparkler"));
      // A sparkler: a thin wire in the right hand.
      if (n.hand) {
        const wire = new THREE.Mesh(new THREE.CylinderGeometry(0.003, 0.003, 0.3, 4).translate(0, 0.15, 0), new ToonMaterial({ color: "#3a3430", paint: 0 }));
        wire.position.set(0, 0.07, 0);
        n.hand.add(wire);
        (n as any).tip = wire;
      }
    }
    // A keeper behind every stall.
    for (const s of stalls) {
      const back = s.keeper.clone().add(s.front.clone().multiplyScalar(-0.15));
      const n = this.spawn(Math.random() < 0.8 ? "keeper" : "man", "keeper", back.x, back.z, Math.atan2(s.front.x, s.front.z));
      n.stall = s;
      this.play(n, "idle", 0);
      n.mixer.update(rand(0, 4));
    }
    // People already waiting on the beach for the fireworks.
    const beach: [number, number, Variant][] = [[-6, -114, "woman"], [-5.3, -114.4, "man"], [5, -113, "woman"], [5.6, -113.4, "kid"], [9, -116, "elder"], [-10, -116, "woman"], [-9.4, -116.2, "woman"]];
    for (const [x, z, v] of beach) {
      const n = this.spawn(v, "watch", x, z, Math.PI + rand(-0.2, 0.2));
      this.play(n, "idle", 0);
      n.mixer.update(rand(0, 4));
    }
  }

  /** A keeper calls out (with the bubble): plays the call, or a wave if she's right there. */
  keeperCall(s: Stall, near: boolean): void {
    const n = this.npcs.find((k) => k.stall === s);
    if (!n) return;
    this.play(n, near ? "wave" : "call", 0.3);
    n.oneShot = near ? 2 : 3;
  }

  update(dt: number, her: THREE.Vector3, cam: THREE.Vector3, show: boolean, circles: { x: number; z: number; r: number }[]): void {
    if (!this.ok) return;
    this.t += dt;
    circles.length = 0;
    for (const n of this.npcs) {
      const d = Math.hypot(n.pos.x - her.x, n.pos.z - her.z);
      if (n.mode === "stroll" || n.mode === "kid") this.walk(n, dt, her, d);
      else if (n.mode === "keeper") {
        if (n.oneShot > 0 && (n.oneShot -= dt) <= 0) this.play(n, "idle", 0.5);
      } else if (n.mode === "watch") this.play(n, show ? "lookup" : "idle", 1.2);
      if (d < 2.5) circles.push({ x: n.pos.x, z: n.pos.z, r: n.v === "kid" ? 0.2 : 0.26 });
      n.root.rotation.y = n.heading;
      // Animation LOD: close people at full rate, far ones a few times a second.
      const dc = Math.hypot(n.pos.x - cam.x, n.pos.z - cam.z);
      // Hidden when far, and when someone brushes right past the lens.
      n.root.visible = !n.hide && dc < 70 && dc > 0.75;
      if (!n.root.visible) continue;
      // Level of detail: the soft, detailed body up close, the simple one further off.
      if (n.near && n.far) {
        const close = dc < (n.near.visible ? 13 : 11);
        n.near.visible = close;
        n.far.visible = !close;
      }
      n.acc += dt;
      const step = dc < 18 ? 0 : dc < 35 ? 1 / 30 : 1 / 12;
      if (n.head && n.headQ) n.head.quaternion.copy(n.headQ);
      if (n.acc >= step) { n.mixer.update(n.acc); n.acc = 0; }
      if (n.head && n.headQ) n.headQ.copy(n.head.quaternion);
      // Blinks (a quick close-open every few seconds) and a smile that eases away.
      if (n.faces.length && dc < 16) {
        n.blinkT -= dt;
        if (n.blinkT < -0.14) n.blinkT = rand(2.2, 6);
        const b = n.blinkT < 0 ? Math.sin((-n.blinkT / 0.14) * Math.PI) : 0;
        n.smile = Math.max(0, n.smile - dt * 0.25);
        for (const f of n.faces) {
          f.morphTargetInfluences![f.morphTargetDictionary!["blink"]] = b;
          const si = f.morphTargetDictionary!["smile"];
          if (si !== undefined) f.morphTargetInfluences![si] = Math.min(1, n.smile);
        }
      }
      // Keepers and chatters glance at her when she's close.
      if (n.head && (n.mode === "keeper" || n.mode === "stand") && d < 4) this.glance(n, her, dt);
      const tip = (n as any).tip as THREE.Object3D | undefined;
      if (tip && dc < 30) {
        const p = tip.localToWorld(new THREE.Vector3(0, 0.3, 0));
        this.fx.sparkler(p, dt);
        if (dc < 6 && Math.random() < dt * 1.5) this.audio.fizz(p);
      }
    }
  }

  private walk(n: Npc, dt: number, her: THREE.Vector3, d: number) {
    // Follow the lane; step aside for her, and slow when she's right in front.
    const ahead = (her.z - n.pos.z) * n.dir;
    let x = n.lane + n.side;
    let slow = 1;
    if (ahead > 0 && ahead < 3 && Math.abs(her.x - x) < 0.9) {
      x += her.x > x ? -0.9 : 0.9;
      slow = ahead < 1.2 ? 0.35 : 0.8;
    }
    x = THREE.MathUtils.clamp(x, -2.6, 2.6);
    const sp = n.speed * slow;
    n.pos.z += n.dir * sp * dt;
    n.pos.x = damp(n.pos.x, x, 1.2, dt);
    const dx = (x - n.pos.x) * 1.2;
    n.heading = dampAngle(n.heading, Math.atan2(dx, n.dir * Math.max(0.3, sp)), 5, dt);
    // Cadence follows the speed actually walked (slowing for her included), so feet stay planted.
    if (n.cur) n.cur.timeScale = Math.max(0.3, sp / this.clipSpeed(n, n.cur.getClip().name));
    // Ends of the street: turn around out of sight (far from her).
    const far = Math.abs(n.pos.z - her.z) > 30;
    if ((n.pos.z < -94 && n.dir < 0) || (n.pos.z > 10 && n.dir > 0)) {
      if (far) { n.pos.z = n.dir < 0 ? 9 : -93; }
      else { n.dir *= -1; n.side *= -1; }
    }
    void d;
  }

  private glance(n: Npc, her: THREE.Vector3, _dt: number) {
    const h = n.head!;
    const hp = h.getWorldPosition(new THREE.Vector3());
    const a = Math.atan2(her.x - hp.x, her.z - hp.z) - n.heading;
    const yaw = THREE.MathUtils.clamp(Math.atan2(Math.sin(a), Math.cos(a)), -0.8, 0.8);
    h.rotateOnWorldAxis(new THREE.Vector3(0, 1, 0), yaw * 0.7);
  }
}
