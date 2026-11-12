import * as THREE from "three/webgpu";
import type { Game } from "./game";
import { Progress, type AchId } from "./state";
import { Hud } from "../ui/hud";
import { Audio } from "../audio/audio";
import { Fx } from "../fx/fx";
import { buildCats, type Cat } from "../world/cats";
import { Crowd } from "../actors/crowd";
import { GATES, SHORE, SPAWNS, TASKS, STREET, SLEEPING_CAT, type TaskId } from "../world/layout";
import type { Stall } from "../world/stalls";
import { MiniGame, toScreen, type Ctx } from "./mg/common";
import { Goldfish, Tub, goldfishBag } from "./mg/goldfish";
import { CandyApple, Masks, wearMask } from "./mg/pickers";
import { RingToss } from "./mg/ringtoss";
import { Lantern, prepareLantern, updateLantern, type LanternState } from "./mg/lantern";

const VERB: Record<TaskId, string> = {
  goldfish: "Scoop a goldfish",
  candyapple: "Buy a candy apple",
  ringtoss: "Play ring toss",
  masks: "Look at the masks",
  lantern: "Light a lantern",
};

interface Interactable { pos: THREE.Vector3; r: number; label: () => string | null; act: () => void }

/**
 * The festival itself: title card, the five stall tasks and their mini-games, lantern-gate
 * checkpoints, hidden cats, the sleeping cat, the fireworks finale, keeper call-outs, and the
 * sound of it all. Everything is quiet: a checklist, a fading "task n/5", small achievements.
 */
export class Play {
  readonly prog: Progress;
  readonly hud: Hud;
  readonly audio = new Audio();
  readonly fx = new Fx();
  readonly crowd: Crowd;
  private waved = new Set<Stall>();
  private items: Interactable[] = [];
  private mg: MiniGame | null = null;
  private mgStall: Stall | null = null;
  private mgWinT = 0;
  private walkIn: { from: THREE.Vector3; to: THREE.Vector3; h0: number; h1: number; t: number } | null = null;
  private tub: Tub | null = null;
  private lantern: LanternState | null = null;
  private cats!: Awaited<ReturnType<typeof buildCats>>;
  private petT = 0;
  private stepDist = 0;
  private stepLeft = false;
  private callT = new Map<Stall, number>();
  private bubbleT = new Map<Stall, number>();
  private showT = 0;
  private hintedShore = false;
  private began = false;
  private hintT = 0;
  private lookT = 0;
  private lookAt: THREE.Vector3 | null = null;

  constructor(private g: Game) {
    const persist = !g.params.has("fresh");
    this.prog = new Progress(persist);
    this.hud = new Hud(this.prog);
    this.fx.audio = this.audio;
    g.scene.add(this.fx.group);
    this.crowd = new Crowd(this.fx, this.audio, (x, z) => g.town.groundY(x, z));
    g.scene.add(this.crowd.group);
  }

  async init(): Promise<void> {
    const g = this.g;
    this.cats = await buildCats();
    g.scene.add(this.cats.group);
    await this.crowd.load(g.stalls.stalls);
    // Ambient: steam from the food stalls, the tub of goldfish, the lantern stall's dark lantern.
    this.fx.steamPoints = g.stalls.stalls.flatMap((s) => s.steam);
    for (const s of g.stalls.stalls) {
      if (s.spot.kind === "goldfish") {
        const tub = s.find("water_tub") as THREE.Mesh | undefined;
        if (tub) this.tub = new Tub(tub);
      }
      if (s.spot.kind === "lantern") this.lantern = prepareLantern(s);
      if (s.spot.task) {
        const st = s;
        const task = s.spot.task;
        this.items.push({
          pos: st.use, r: 1.5,
          label: () => (this.prog.has(task) ? null : VERB[task]),
          act: () => this.startTask(st),
        });
      }
    }
    this.items.push({
      pos: this.cats.sleeper.pos, r: 1.8,
      label: () => (this.petT > 0 ? null : "Pet the sleeping cat"),
      act: () => this.pet(),
    });
    this.dressStreet();
    // Restore a saved evening.
    const d = this.prog.data;
    const cp = Math.min(d.checkpoint, GATES.length);
    for (let i = 0; i < cp; i++) { g.gates[i].target = 1; g.gates[i].lit.value = 1; }
    g.rebakeLights();
    const sp = SPAWNS[cp];
    g.her.position.set(sp.x, g.town.groundY(sp.x, sp.z), sp.z);
    g.her.heading = Math.PI;
    g.rig.snap(g.her.position, g.her.heading);
    if (this.prog.has("goldfish")) goldfishBag(g);
    if (this.prog.has("candyapple")) this.restoreApple();
    if (this.prog.has("masks")) wearMask(g, Math.max(0, d.mask));
    if (this.prog.has("lantern")) this.lightLantern(true);

    this.hud.onTod = (p) => { g.setTod(p); this.hud.setTod(p); };
    this.hud.setTod(g.tod.preset);
    this.hud.onReset = () => { this.prog.reset(); location.reload(); };
    g.wind.onGust((k) => this.chimes(k));
    g.systems.push(this);
    (window as any).__play = this;
  }

  private furin: { o: THREE.Object3D; ph: number }[] = [];

  /** Wind chimes under the eaves and nobori banners by the stalls (kit pieces). */
  private dressStreet() {
    const g = this.g, kit = g.stalls.kit;
    const furin = kit.get("furin");
    if (furin) {
      for (const c of g.town.chimes) {
        if (c.z < -95) continue;
        const o = furin.clone(true);
        o.position.copy(c).add(new THREE.Vector3(0, -0.02, 0));
        o.rotation.y = Math.random() * 6.28;
        g.scene.add(o);
        this.furin.push({ o, ph: Math.random() * 6.28 });
      }
    }
    // The sleeping cat's stoop: three stone steps up to a landing (0.45 m) against the house.
    const steps = kit.get("steps");
    if (steps) {
      const o = steps.clone(true);
      o.position.set(-STREET.half + 0.755, 0, SLEEPING_CAT.z);
      o.rotation.y = Math.PI / 2;
      g.scene.add(o);
      this.cats.sleeper.root.position.y = 0.45;
      this.cats.sleeper.pos.y = 0.45;
      (g.player as any).colliders.push({ x0: -STREET.half, x1: -STREET.half + 1.51, z0: SLEEPING_CAT.z - 0.97, z1: SLEEPING_CAT.z + 0.97 });
    }
    const nobori = kit.get("nobori");
    if (nobori) {
      for (const s of g.stalls.stalls) {
        const o = nobori.clone(true);
        // Beside the stall, at the street edge of its frontage.
        o.position.set(s.root.position.x - s.spot.side * 1.15, 0, s.spot.z + 1.75);
        o.rotation.y = s.spot.side < 0 ? Math.PI / 2 : -Math.PI / 2;
        g.scene.add(o);
      }
    }
  }

  /** Title card → play. */
  begin(): void {
    if (this.began) return;
    this.began = true;
    this.audio.start();
    this.hud.show();
    this.hud.controlsHint(true);
    this.hintT = 9;
    if (this.prog.taskCount === 0) setTimeout(() => this.hud.say("Five things to do at the festival tonight…", 4), 1800);
  }

  // ------------------------------------------------------------------ tasks
  private startTask(s: Stall) {
    const g = this.g, task = s.spot.task!;
    const ctx: Ctx = { game: g, hud: this.hud, audio: this.audio, fx: this.fx, stall: s };
    let mg: MiniGame;
    if (task === "goldfish") {
      if (!this.tub) return;
      mg = new Goldfish(ctx, this.tub);
    } else if (task === "candyapple") mg = new CandyApple(ctx);
    else if (task === "ringtoss") mg = new RingToss(ctx);
    else if (task === "masks") mg = new Masks(ctx, (i) => { this.prog.data.mask = i; wearMask(g, i); });
    else mg = new Lantern(ctx, this.lantern!, () => this.lightLantern(false));
    this.mg = mg;
    this.mgStall = s;
    this.mgWinT = 0;
    g.player.enabled = false;
    const to = s.use.clone();
    to.y = g.her.position.y;
    const d = s.camTarget.clone().sub(to);
    this.walkIn = { from: g.her.position.clone(), to, h0: g.her.heading, h1: Math.atan2(d.x, d.z), t: 0 };
    g.rig.setShot(s.cam, s.camTarget);
    this.hud.setPrompt(null);
    this.hud.controlsHint(false);
    this.hud.say("Esc to step away", 2.5);
  }

  private endTask() {
    const g = this.g;
    this.mg?.end();
    this.mg = null;
    this.mgStall = null;
    this.walkIn = null;
    g.player.enabled = true;
    g.rig.setShot(null);
    this.hud.setGuide(null);
    g.her.lookTarget = null;
    g.her.smile = 0;
  }

  private completeTask(t: TaskId) {
    if (this.prog.has(t)) return;
    this.prog.data.tasks.push(t);
    this.prog.save();
    this.audio.taskChime();
    const n = this.prog.taskCount;
    this.hud.taskDone(n);
    if (n === 5) {
      this.award("tasks");
      setTimeout(() => this.hud.say("The fireworks are about to start · head down to the shore", 6), 3200);
    }
  }

  private award(id: AchId) {
    if (this.prog.hasAch(id)) return;
    this.prog.data.ach.push(id);
    this.prog.save();
    this.hud.achievement(id);
  }

  private restoreApple() {
    const s = this.g.stalls.stalls.find((x) => x.spot.kind === "candyapple");
    const a = s?.findAll("apple_")[0];
    if (!a) return;
    const held = a.clone(true);
    held.name = "held_apple";
    a.visible = false;
    this.g.her.hold("hand_R", held, new THREE.Vector3(0, 0.11, 0.03), new THREE.Euler(Math.PI - 0.2, 0, 0));
    this.g.carry.push(held);
  }

  private lightLantern(instant: boolean) {
    const L = this.lantern;
    if (!L) return;
    L.target = 1;
    if (instant) L.u.value = 1;
    if (L.flame) L.flame.visible = true;
    this.g.addLights([{ x: L.lightPos.x, y: L.lightPos.y - 0.2, z: L.lightPos.z, r: 1, g: 0.66, b: 0.36, k: 0.9, reach: 4.5 }]);
  }

  // ------------------------------------------------------------------ cats
  private pet() {
    const g = this.g, c = this.cats.sleeper;
    this.petT = 4;
    g.player.enabled = false;
    const d = c.pos.clone().sub(g.her.position);
    g.her.heading = Math.atan2(d.x, d.z);
    g.her.setPose("crouch");
    g.her.lookTarget = c.pos.clone().add(new THREE.Vector3(0, 0.15, 0));
    c.play("purr", 0.6);
    this.hud.setPrompt(null);
    // Frame the two of them from the street side.
    const side = new THREE.Vector3(1.9, 1.15, 1.5).add(c.pos).setY(1.15);
    g.rig.setShot(side, c.pos.clone().add(new THREE.Vector3(0.55, 0.35, 0)));
  }

  private updateCats(dt: number) {
    const g = this.g;
    this.cats.update(dt);
    if (this.petT > 0) {
      this.petT -= dt;
      g.her.smile = 1;
      if (this.petT <= 0) {
        g.her.setPose("none");
        g.her.lookTarget = null;
        g.her.smile = 0;
        g.player.enabled = true;
        g.rig.setShot(null);
        this.cats.sleeper.play("sleep", 1.2);
        this.prog.data.petted = true;
        this.award("pet");
      }
    }
    const her = g.her.position;
    for (const c of this.cats.hidden) {
      if (this.prog.data.cats.includes(c.id)) continue;
      if (Math.hypot(her.x - c.pos.x, her.z - c.pos.z) < 2.4) {
        this.prog.data.cats.push(c.id);
        this.prog.save();
        const n = this.prog.data.cats.length;
        this.hud.say(`You found a cat · ${n}/3`, 3.5);
        this.audio.blip("pop", c.pos);
        this.lookAt = c.pos.clone().add(new THREE.Vector3(0, 0.2, 0));
        this.lookT = 2.5;
        if (c.actions.has("look")) { c.play("look"); setTimeout(() => c.play("idle", 1), 3000); }
        if (n >= 3) this.award("cats");
        this.hud.renderAch();
      }
    }
  }

  // ------------------------------------------------------------------ the evening
  update(dt: number): void {
    const g = this.g, her = g.her.position, input = g.input;
    this.hud.update(dt);
    if (this.hintT > 0) {
      this.hintT -= dt;
      if (this.hintT <= 0 || g.player.distance > 14) { this.hintT = 0; this.hud.controlsHint(false); }
    }
    this.tub?.swim(dt, null);
    // Chimes swing on the breeze.
    const w = g.wind.value;
    for (const f of this.furin) {
      if (Math.abs(f.o.position.z - her.z) > 30) continue;
      f.o.rotation.x = Math.sin(g.time * 2.3 + f.ph) * 0.12 * w + w * 0.15;
      f.o.rotation.z = Math.sin(g.time * 1.7 + f.ph * 1.3) * 0.08 * w;
    }
    if (this.lantern) updateLantern(this.lantern, dt);
    // Gates: lanterns light up one after another.
    for (const gt of g.gates) gt.lit.value += (gt.target - gt.lit.value) * Math.min(1, dt * 0.9);

    // Mini-game in progress.
    if (this.mg) {
      if (this.walkIn && this.walkIn.t < 1) {
        const w = this.walkIn;
        w.t = Math.min(1, w.t + dt / 0.7);
        const e = w.t * w.t * (3 - 2 * w.t);
        her.lerpVectors(w.from, w.to, e);
        let dh = w.h1 - w.h0; dh = Math.atan2(Math.sin(dh), Math.cos(dh));
        g.her.heading = w.h0 + dh * e;
        g.her.speed = w.t < 1 ? 0.8 : 0;
      } else g.her.speed = 0;
      this.mg.update(dt);
      if (this.mg.won) {
        if (this.mgWinT === 0) this.completeTask(this.mg.task);
        this.mgWinT += dt;
        if (this.mgWinT > 1.6) this.endTask();
      } else if (input.hit("Escape") && this.mg.canQuit) this.endTask();
      this.levels(dt);
      this.crowd.update(dt, her, g.camera.position, this.fx.show, g.player.circles);
      this.fx.update(dt, her, g.wind.dir, g.wind.value);
      return;
    }

    // Checkpoints: walking under a gate lights it and saves.
    GATES.forEach((z, i) => {
      if (this.prog.data.checkpoint < i + 1 && her.z < z - 0.4 && Math.abs(her.x) < 3.6) {
        this.prog.data.checkpoint = i + 1;
        this.prog.save();
        g.gates[i].target = 1;
        g.rebakeLights();
        this.audio.gateBell(new THREE.Vector3(0, 4, z));
        this.hud.say("The lantern gate glows · progress saved", 3.5);
      }
    });

    // Prompts.
    let best: Interactable | null = null, bd = Infinity;
    if (this.petT <= 0) {
      for (const it of this.items) {
        const d = Math.hypot(it.pos.x - her.x, it.pos.z - her.z);
        if (d < it.r && d < bd && it.label()) { bd = d; best = it; }
      }
    }
    this.hud.setPrompt(best ? best.label() : null);
    if (best && (input.hit("KeyE") || input.hit("Enter"))) best.act();

    this.updateCats(dt);
    this.updateFinale(dt);
    this.updateGaze(dt);
    this.updateKeepers(dt);
    this.footsteps(dt);
    this.levels(dt);
    this.crowd.update(dt, her, g.camera.position, this.fx.show, g.player.circles);
    this.fx.update(dt, her, g.wind.dir, g.wind.value);
  }

  private updateFinale(dt: number) {
    const g = this.g, her = g.her.position;
    const onBeach = her.z < SHORE.fireworksZ;
    if (onBeach && this.prog.taskCount >= 5) {
      if (!this.fx.show) {
        this.fx.startShow();
        this.audio.setBand(false);
        this.hud.say("花火 · hanabi", 4);
        // Hanabi start after dark: the evening slips into night as the first shell goes up.
        if (g.tod.preset !== "night") { g.setTod("night"); this.hud.setTod("night"); }
        this.showT = 0;
      }
      this.showT += dt;
      if (this.showT > 24 && !this.prog.data.fireworks) {
        this.prog.data.fireworks = true;
        this.prog.save();
        this.award("fireworks");
      }
      const still = g.her.speed < 0.15;
      g.rig.lookUp = still ? 1 : 0.4;
      if (this.petT <= 0) g.her.setPose(still ? "lookup" : "none");
    } else {
      if (onBeach && !this.hintedShore && this.prog.taskCount < 5) {
        this.hintedShore = true;
        this.hud.say("The fireworks start once the festival tasks are done", 5);
      }
      if (this.fx.show && her.z > SHORE.promenadeZ1) { this.fx.stopShow(); this.audio.setBand(true); }
      g.rig.lookUp = 0;
      if (g.her.pose === "lookup") g.her.setPose("none");
    }
  }

  /** She looks at stalls, keepers and cats as she passes. */
  private updateGaze(dt: number) {
    const g = this.g, her = g.her.position;
    if (this.petT > 0) return;
    if (this.lookT > 0) { this.lookT -= dt; g.her.lookTarget = this.lookAt; return; }
    let best: THREE.Vector3 | null = null, bd = 4.2;
    for (const s of g.stalls.stalls) {
      const p = s.camTarget;
      const d = Math.hypot(p.x - her.x, p.z - her.z);
      // Only things ahead or beside her.
      const ang = Math.atan2(p.x - her.x, p.z - her.z) - g.her.heading;
      if (d < bd && Math.cos(ang) > -0.1) { bd = d; best = p; }
    }
    g.her.lookTarget = best;
  }

  private updateKeepers(dt: number) {
    const g = this.g, her = g.her.position;
    for (const s of g.stalls.stalls) {
      const d = Math.hypot(s.use.x - her.x, s.use.z - her.z);
      let t = (this.callT.get(s) ?? Math.random() * 4) - dt;
      let b = (this.bubbleT.get(s) ?? 0) - dt;
      if (d < 7 && t <= 0 && !(s.spot.task && this.prog.has(s.spot.task) && Math.random() < 0.5)) {
        t = 9 + Math.random() * 8;
        b = 3.6;
        this.audio.call(s.keeper.clone().setY(1.6));
        this.crowd.keeperCall(s, false);
      } else if (t <= 0) t = 2;
      // A wave the first time she comes up to a stall.
      if (d < 2.6 && !this.waved.has(s)) { this.waved.add(s); this.crowd.keeperCall(s, true); }
      else if (d > 6) this.waved.delete(s);
      this.callT.set(s, t);
      this.bubbleT.set(s, b);
      const key = `k${s.spot.z}`;
      if (b > 0 && d < 9) {
        const sc = toScreen(g, s.keeper.clone().setY(2.05));
        this.hud.bubble(key, s.spot.call, sc.behind ? null : sc.x, sc.y);
      } else this.hud.bubble(key, "", null);
    }
  }

  private footsteps(dt: number) {
    const g = this.g, her = g.her;
    const sp = her.speed;
    if (sp < 0.15) { this.stepDist = 0.3; return; }
    this.stepDist += sp * dt;
    const stride = sp > 1.8 ? 0.95 : 0.62;
    if (this.stepDist >= stride) {
      this.stepDist -= stride;
      this.stepLeft = !this.stepLeft;
      const z = her.position.z;
      const surface = z < SHORE.stepsZ1 ? "sand" : "stone";
      this.audio.step(her.position, surface, this.stepLeft, sp > 1.8);
    }
  }

  private chimes(k: number) {
    const her = this.g.her.position;
    const near = this.g.town.chimes.filter((c) => c.distanceTo(her) < 16).sort((a, b) => a.distanceTo(her) - b.distanceTo(her)).slice(0, 2 + Math.floor(k * 3));
    near.forEach((c, i) => setTimeout(() => this.audio.chime(c, 0.92 + ((c.x * 7.3 + c.z * 3.1) % 0.2)), 150 + i * (220 + Math.random() * 400)));
  }

  private levels(_dt: number) {
    const g = this.g, her = g.her.position;
    let music = 0, sizzle = 0;
    for (const s of g.stalls.stalls) {
      const d = Math.hypot(s.use.x - her.x, s.use.z - her.z);
      music = Math.max(music, THREE.MathUtils.clamp(1 - (d - 3) / 18, 0, 1));
      if (s.steam.length) sizzle = Math.max(sizzle, THREE.MathUtils.clamp(1 - (d - 1.5) / 5, 0, 1));
    }
    this.audio.update(g.camera, {
      wind: g.wind.value,
      crowd: her.z > SHORE.promenadeZ0 ? 0.85 : 0.35,
      sea: THREE.MathUtils.clamp((-her.z - 55) / 50, 0.05, 1),
      music,
      sizzle,
      purr: this.petT > 0 ? Math.min(1, this.petT, 4 - this.petT) : 0,
    });
  }

  // ------------------------------------------------------------------ debug / capture hooks
  debugComplete(ids: TaskId[] | "all" = "all"): void {
    for (const t of ids === "all" ? TASKS.map((x) => x.id) : ids) this.completeTask(t);
  }
  /** Gives her everything the tasks give (for capture). */
  debugDress(): void {
    goldfishBag(this.g);
    this.restoreApple();
    wearMask(this.g, 0);
  }
  debugStart(task: TaskId): void {
    const s = this.g.stalls.stalls.find((x) => x.spot.task === task);
    if (s) { this.g.her.position.copy(s.use); this.startTask(s); }
  }
  debugTeleport(x: number, z: number, heading = Math.PI): void {
    const g = this.g;
    g.her.position.set(x, g.town.groundY(x, z), z);
    g.her.heading = heading;
    g.rig.snap(g.her.position, heading);
  }
  get mini(): MiniGame | null { return this.mg; }
  get cat(): Cat { return this.cats.sleeper; }
}
