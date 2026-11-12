import * as THREE from "three/webgpu";
import type { Game } from "./game";
import type { Hud } from "../ui/hud";
import type { Audio } from "../audio/audio";
import type { Crowd, Npc } from "../actors/crowd";
import type { Moments } from "../actors/moments";
import { toScreen } from "./mg/common";
import { ToonMaterial } from "../render/toon";

export type Emote = "wave" | "bow" | "cheer" | "photo";
export const EMOTES: { key: string; id: Emote; label: string }[] = [
  { key: "Digit1", id: "wave", label: "wave" },
  { key: "Digit2", id: "bow", label: "bow" },
  { key: "Digit3", id: "cheer", label: "cheer" },
  { key: "Digit4", id: "photo", label: "photo" },
];

const rand = (a: number, b: number) => a + Math.random() * (b - a);
const pick = <T,>(a: T[]): T => a[Math.floor(Math.random() * a.length)];

/** Two-line exchanges for people standing together. */
const CHATS: [string, string][] = [
  ["Did you try the takoyaki yet?", "Twice. Don't tell anyone."],
  ["The fireworks start after dark, right?", "Down at the shore. Let's get a good spot."],
  ["It's so warm tonight.", "Shaved ice, then?"],
  ["I haven't worn this yukata in years.", "It still suits you."],
  ["I lost at ring toss again.", "Third time's the charm."],
  ["Listen, you can hear the wind chimes.", "And the sea, if you wait."],
  ["Who's minding the shop?", "Nobody. It's festival night."],
  ["My goldfish needs a name.", "Kintaro. Obviously."],
  ["The lanterns look lovely this year.", "They lit the gates one by one."],
  ["Are the kids still running about?", "With sparklers. Of course."],
];
/** What a passer-by says as she goes by. */
const PASSING: Record<string, string[]> = {
  woman: ["Good evening!", "What a pretty yukata.", "Enjoy the festival!", "Mind the step by the shore."],
  man: ["Evening!", "Nice night for it.", "The yakisoba's good tonight.", "Fireworks soon."],
  elder: ["Lovely evening, isn't it?", "Take your time, dear.", "It gets busier every year."],
  kid: ["Hi!", "Look, look, sparklers!", "Did you see the goldfish?"],
};
const MASK_LINES = ["Whoa, cool mask!", "Where did you get that mask?"];
/** Replies to her emotes. */
const REPLY: Record<Emote, { clip: string; lines: Record<string, string[]> }> = {
  wave: { clip: "wave", lines: { any: ["Hello!", "Hi there!", "Good evening!"], kid: ["Hiii!", "Hello!"] } },
  bow: { clip: "bow", lines: { any: ["Good evening.", "And to you.", "How polite!"], kid: ["Um… hello!"] } },
  cheer: { clip: "cheer", lines: { any: ["Ha ha, that's the spirit!", "Yeah! Festival!", "Ha ha!"], kid: ["Yaaay!"] } },
  photo: { clip: "peace", lines: { any: ["Cheese!", "Did I blink?", "Send me that one!"], kid: ["Peace!"] } },
};

interface Line { key: string; n: Npc; text: string; t: number; pri: number }

/**
 * Talking and gesturing. Her emotes (wave, bow, cheer, take a photo) and what people nearby do
 * about them; and the crowd's own voices: chatting groups trading lines, a word from someone
 * walking past. At most two speech bubbles are ever up at once (shopkeepers' calls count).
 */
export class Social {
  private lines: Line[] = [];
  private chatT = rand(3, 6);
  private passCool = new Map<Npc, number>();
  private passT = 2;
  private queue: { t: number; fn: () => void }[] = [];
  private emoteT = 0;
  private phone: THREE.Group | null = null;
  private phoneT = 0;
  private flashed = false;
  /** How many shopkeeper bubbles are showing (set by the director each frame). */
  keeperBubbles = 0;
  /** Emotes done so far, for the test bot. */
  readonly done: Emote[] = [];

  constructor(private g: Game, private hud: Hud, private audio: Audio, private crowd: Crowd, private moments: () => Moments | null) {}

  get busy(): boolean { return this.emoteT > 0; }

  /** A bubble over someone's head. Low-priority lines are dropped when two are already up. */
  say(n: Npc, text: string, secs = 2.8, pri = 0): boolean {
    const mine = this.lines.find((l) => l.n === n);
    if (mine) { mine.text = text; mine.t = secs; mine.pri = pri; return true; }
    const room = 2 - this.keeperBubbles;
    if (this.lines.length >= Math.max(1, room)) {
      const weakest = [...this.lines].sort((a, b) => a.pri - b.pri || a.t - b.t)[0];
      if (!weakest || weakest.pri >= pri) return false;
      this.hud.bubble(weakest.key, "", null);
      this.lines.splice(this.lines.indexOf(weakest), 1);
    }
    const key = ["c0", "c1", "c2"].find((k) => !this.lines.some((l) => l.key === k))!;
    this.lines.push({ key, n, text, t: secs, pri });
    return true;
  }

  emote(id: Emote): void {
    const g = this.g, her = g.her;
    if (this.emoteT > 0) return;
    const clip = id === "photo" ? "point" : id;
    const dur = her.play(clip);
    this.emoteT = Math.min(2.6, Math.max(1.4, dur));
    this.done.push(id);
    if (id === "photo") {
      // A phone held up in her right hand; the shutter goes part-way through.
      if (!this.phone) {
        this.phone = new THREE.Group();
        const body = new THREE.Mesh(new THREE.BoxGeometry(0.068, 0.14, 0.009), new ToonMaterial({ color: "#f2e8ea", paint: 0, rim: 0.5 }));
        const screen = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.125, 0.002), new THREE.MeshBasicNodeMaterial({ color: "#bfe6ff" }));
        screen.position.z = -0.0055;
        this.phone.add(body, screen);
      }
      g.scene.add(this.phone);
      this.phoneT = this.emoteT;
      this.flashed = false;
    }
    if (id === "cheer") her.smile = 1;
    // People near her and roughly in front answer after a beat.
    const fx = Math.sin(her.heading), fz = Math.cos(her.heading);
    const near = this.crowd.npcs
      .filter((n) => n.root.visible && (n.mode === "stroll" || n.mode === "stand" || n.mode === "kid" || n.mode === "keeper"))
      .map((n) => ({ n, d: Math.hypot(n.pos.x - her.position.x, n.pos.z - her.position.z), dot: ((n.pos.x - her.position.x) * fx + (n.pos.z - her.position.z) * fz) }))
      .filter((o) => o.d < 6 && o.d > 0.3 && o.dot > -0.5)
      .sort((a, b) => a.d - b.d)
      .slice(0, 3);
    const r = REPLY[id];
    near.forEach((o, i) => {
      this.queue.push({ t: (id === "photo" ? 0.3 : 0.55) + i * 0.3, fn: () => {
        const n = o.n;
        n.smile = 1;
        if (n.mode === "keeper") { if (n.stall) this.crowd.keeperCall(n.stall, true); }
        else this.moments()?.react(n, r.clip, id === "bow" ? 2.0 : 2.4);
        if (i === 0) this.say(n, pick(r.lines[n.v] ?? r.lines.any), 2.6, 2);
      } });
    });
  }

  update(dt: number, her: THREE.Vector3, quiet: boolean, masked: boolean): void {
    const g = this.g;
    if (this.emoteT > 0) this.emoteT -= dt;
    for (const q of this.queue) q.t -= dt;
    for (const q of this.queue.filter((q) => q.t <= 0)) q.fn();
    this.queue = this.queue.filter((q) => q.t > 0);
    // The phone follows her hand, screen toward her.
    if (this.phone?.parent) {
      this.phoneT -= dt;
      const h = g.her.bone("hand_R");
      if (h) h.getWorldPosition(this.phone.position);
      this.phone.position.y += 0.06;
      this.phone.rotation.set(0, g.her.heading, 0);
      if (!this.flashed && this.phoneT < this.emoteT * 0.5 + 0.2) {
        this.flashed = true;
        this.hud.flash();
        this.audio.blip("clack", this.phone.position);
      }
      if (this.phoneT <= 0) this.phone.removeFromParent();
    }
    if (!quiet) this.chatter(dt, her, masked);
    // Draw the bubbles.
    for (const l of this.lines) l.t -= dt;
    for (const l of this.lines.filter((l) => l.t <= 0 || !l.n.root.visible)) this.hud.bubble(l.key, "", null);
    this.lines = this.lines.filter((l) => l.t > 0 && l.n.root.visible);
    // Never more than two bubbles up, shopkeepers' calls included: the least important go.
    const room = Math.max(0, 2 - this.keeperBubbles);
    while (this.lines.length > room) {
      const w = [...this.lines].sort((x, y) => x.pri - y.pri || x.t - y.t)[0];
      this.hud.bubble(w.key, "", null);
      this.lines.splice(this.lines.indexOf(w), 1);
    }
    for (const l of this.lines) {
      const p = l.n.head ? l.n.head.getWorldPosition(new THREE.Vector3()) : l.n.pos.clone().setY(l.n.pos.y + 1.5);
      p.y += 0.32;
      const sc = toScreen(g, p);
      this.hud.bubble(l.key, l.text, sc.behind || quiet ? null : sc.x, sc.y);
    }
  }

  private chatter(dt: number, her: THREE.Vector3, masked: boolean) {
    for (const [n, c] of this.passCool) { if (c - dt <= 0) this.passCool.delete(n); else this.passCool.set(n, c - dt); }
    // Groups standing together: one says something, the other answers.
    this.chatT -= dt;
    if (this.chatT <= 0) {
      this.chatT = rand(6, 10);
      const standing = this.crowd.npcs.filter((n) => n.mode === "stand" && n.root.visible && Math.hypot(n.pos.x - her.x, n.pos.z - her.z) < 9 && !toScreen(this.g, n.pos).behind);
      if (standing.length) {
        const a = pick(standing);
        const b = standing.find((n) => n !== a && Math.hypot(n.pos.x - a.pos.x, n.pos.z - a.pos.z) < 2);
        const [q, ans] = pick(CHATS);
        if (this.say(a, q, 2.8) && b) this.queue.push({ t: 2.4, fn: () => { this.say(b, ans, 2.8); b.smile = 0.8; } });
      }
    }
    // Someone walking past her.
    this.passT -= dt;
    if (this.passT > 0) return;
    for (const n of this.crowd.npcs) {
      if ((n.mode !== "stroll" && n.mode !== "kid") || this.passCool.has(n) || !n.root.visible) continue;
      const d = Math.hypot(n.pos.x - her.x, n.pos.z - her.z);
      if (d > 3 || d < 0.8) continue;
      const toward = Math.cos(Math.atan2(her.x - n.pos.x, her.z - n.pos.z) - n.heading);
      if (toward < 0.5) continue;
      this.passCool.set(n, rand(40, 80));
      if (Math.random() < 0.45) {
        const line = n.v === "kid" && masked && Math.random() < 0.7 ? pick(MASK_LINES) : pick(PASSING[n.v] ?? PASSING.woman);
        if (this.say(n, line, 2.4)) { n.smile = 0.8; this.passT = rand(5, 9); break; }
      }
    }
  }

  /** Hides every bubble (entering a mini-game, the title card). */
  clear(): void {
    for (const l of this.lines) this.hud.bubble(l.key, "", null);
    this.lines = [];
  }
}
