import * as THREE from "three/webgpu";
import { MiniGame, type Ctx } from "./common";
import { ToonMaterial } from "../../render/toon";
import { Builder, solid } from "../../world/geo";
import { woodMaterial } from "../../render/surfaces";
import type { Site } from "./gallery";

export interface Shrine extends Site { root: THREE.Group; box: THREE.Object3D; stick: THREE.Object3D; collider: { x0: number; x1: number; z0: number; z1: number } }

/** Rank (best first), name, and the line on the slip. */
export const FORTUNES: [string, string, string, number][] = [
  ["大吉", "Great blessing", "Everything you reach for tonight comes easily.", 14],
  ["中吉", "Middle blessing", "A good evening gets better with company.", 22],
  ["小吉", "Small blessing", "Something sweet is waiting just down the street.", 22],
  ["吉", "Blessing", "Take your time; the lanterns will wait for you.", 22],
  ["末吉", "Blessing to come", "Not yet, but soon: look up when the sky goes dark.", 14],
  ["凶", "Bad luck", "Tie it to the rack and leave it behind you.", 6],
];

/**
 * A little wayside shrine (hokora) between the houses' fronts and the street: a stone base, a
 * small roofed wooden shrine with an offering box and a bell rope, a rack of tied paper slips,
 * and a stand with the six-sided omikuji box you shake a numbered stick out of.
 */
export function buildShrine(side: -1 | 1, z: number): Shrine {
  const b = new Builder();
  const red = "#b8322a", dark = "#3a2820", stone = "#9d968c";
  // Stone plinth, shrine body, gabled roof.
  b.box(1.5, 0.3, 1.0, stone, 0, 0.15, -0.3);
  b.box(1.2, 0.14, 0.8, "#aaa398", 0, 0.37, -0.3);
  b.box(0.8, 0.75, 0.55, "#8a6444", 0, 0.82, -0.32);
  b.box(0.5, 0.5, 0.03, dark, 0, 0.8, -0.04);
  for (const sx of [-1, 1]) b.box(0.62, 0.05, 0.95, "#4a5a52", sx * 0.27, 1.34, -0.3, 0, 0, sx * -0.5);
  b.box(0.08, 0.08, 1.0, dark, 0, 1.5, -0.3);
  // A small red torii over the path to it.
  for (const sx of [-1, 1]) b.box(0.09, 1.9, 0.09, red, sx * 0.85, 0.95, 0.55);
  b.box(2.1, 0.1, 0.12, red, 0, 1.92, 0.55);
  b.box(1.85, 0.07, 0.09, red, 0, 1.66, 0.55);
  // Offering box, and the rack of tied fortunes.
  b.box(0.5, 0.3, 0.3, "#6a4430", 0, 0.59, 0.12);
  for (const y of [0.9, 1.15, 1.4]) b.box(0.9, 0.02, 0.02, dark, -1.3, y, -0.25);
  for (const sx of [-1, 1]) b.box(0.05, 1.5, 0.05, dark, -1.3 + sx * 0.45, 0.75, -0.25);
  for (let i = 0; i < 16; i++) b.box(0.035, 0.1, 0.012, "#f6f1e6", -1.68 + (i % 8) * 0.105, [0.85, 1.1, 1.35][i % 3], -0.25, 0, 0, (i % 5 - 2) * 0.12);
  // The stand for the omikuji box.
  b.box(0.42, 0.04, 0.42, "#b08860", 1.1, 0.92, 0.25);
  for (const sx of [-1, 1]) for (const sz of [-1, 1]) b.box(0.04, 0.9, 0.04, "#7a5536", 1.1 + sx * 0.17, 0.45, 0.25 + sz * 0.17);
  const root = new THREE.Group();
  root.name = "shrine";
  root.add(solid(b.build(), woodMaterial()));
  // The box itself (six-sided, red, a hole in the top) and the stick that slides out of it.
  const box = new THREE.Group();
  const body = new THREE.Mesh(new THREE.CylinderGeometry(0.075, 0.075, 0.26, 6), new ToonMaterial({ color: "#c0392f", paint: 0.2, rim: 0.4 }));
  body.castShadow = true;
  const band = new THREE.Mesh(new THREE.CylinderGeometry(0.077, 0.077, 0.05, 6), new ToonMaterial({ color: "#f2e6c8", paint: 0 }));
  box.add(body, band);
  box.position.set(1.1, 1.07, 0.25);
  const stick = new THREE.Mesh(new THREE.BoxGeometry(0.012, 0.2, 0.004), new ToonMaterial({ color: "#e8d8b0", paint: 0 }));
  stick.visible = false;
  box.add(stick);
  root.add(box);
  // A bell on a rope under the eave.
  const bell = new THREE.Mesh(new THREE.SphereGeometry(0.05, 12, 10), new ToonMaterial({ color: "#d9b24a", paint: 0, rim: 0.7 }));
  bell.position.set(0, 1.22, 0.12);
  root.add(bell);
  const x = side * 3.75;
  root.position.set(x, 0, z);
  root.rotation.y = side < 0 ? Math.PI / 2 : -Math.PI / 2;
  root.updateMatrixWorld(true);
  const local = (lx: number, ly: number, lz: number) => root.localToWorld(new THREE.Vector3(lx, ly, lz));
  const use = local(1.1, 0, 0.95); use.y = 0;
  return {
    root, box, stick, use, keeper: use.clone(),
    cam: local(1.75, 1.5, 1.75), camTarget: local(1.05, 1.1, 0.25), front: new THREE.Vector3(-side, 0, 0),
    // Solid from the house front out to the torii and the stand.
    collider: { x0: Math.min(x - side * 0.85, side * 4.6), x1: Math.max(x - side * 0.85, side * 4.6), z0: z - 1.85, z1: z + 1.4 },
  };
}

/**
 * Drawing a fortune: press E (or click) to shake the box; on the third shake a stick drops out
 * and the slip is read: its rank, and one line. The best one drawn tonight is remembered.
 */
export class Omikuji extends MiniGame {
  readonly task = null;
  private shakes = 0;
  private shakeT = 0;
  private t = 0;
  private doneT = -1;
  result = -1;
  private home: THREE.Vector3;

  constructor(c: Ctx, private s: Shrine, private draws: () => number) {
    super(c);
    this.home = s.box.position.clone();
    s.stick.visible = false;
    c.game.her.setPose("reach");
    c.audio.blip("coin", s.use);
  }

  update(dt: number): void {
    const c = this.c, input = c.game.input, s = this.s;
    this.t += dt;
    if (this.doneT < 0) {
      c.hud.setGuide("Shake the box · press E", null, "●".repeat(this.shakes) + "○".repeat(3 - this.shakes));
      if (this.t > 0.5 && this.shakeT <= 0 && (input.hit("KeyE") || input.hit("Enter") || input.clicked)) {
        this.shakes++;
        this.shakeT = 0.55;
        c.audio.blip("clack", s.use);
        setTimeout(() => c.audio.blip("clack", s.use), 140);
      }
      if (this.shakeT > 0) {
        this.shakeT -= dt;
        const k = Math.max(0, this.shakeT / 0.55);
        s.box.position.copy(this.home).add(new THREE.Vector3(0, 0.1 * k + Math.abs(Math.sin(this.shakeT * 28)) * 0.03 * k, 0));
        s.box.rotation.set(Math.sin(this.shakeT * 30) * 0.5 * k, 0, 2.2 * k);
        if (this.shakeT <= 0 && this.shakes >= 3) {
          // Weighted draw.
          const total = FORTUNES.reduce((a, f) => a + f[3], 0);
          let r = Math.random() * total;
          this.result = FORTUNES.findIndex((f) => (r -= f[3]) < 0);
          if (this.result < 0) this.result = 3;
          this.doneT = 0;
          s.stick.visible = true;
          c.audio.blip("pop", s.use);
        }
      } else { s.box.position.copy(this.home); s.box.rotation.set(0, 0, 0); }
    } else {
      this.doneT += dt;
      s.box.position.copy(this.home);
      s.box.rotation.set(0, 0, 0.5);
      s.stick.position.set(0, 0.13 + Math.min(1, this.doneT * 4) * 0.12, 0);
      const f = FORTUNES[this.result];
      c.hud.setGuide(`<b style="font-size:1.5em">${f[0]}</b> · ${f[1]}<br><span style="opacity:.85">${f[2]}</span>${this.draws() > 0 ? `<br><small style="opacity:.6">fortune ${this.draws() + 1} tonight</small>` : ""}`);
      if (this.result <= 1) c.game.her.smile = 1;
      if (this.doneT > 0.6 && this.result === 0 && this.doneT < 0.7) c.fx.sparkle(s.box.getWorldPosition(new THREE.Vector3()).add(new THREE.Vector3(0, 0.3, 0)), new THREE.Color(1, 0.85, 0.5), 30, 0.8);
      if (this.doneT > 4.2 || (this.doneT > 1.2 && (input.hit("KeyE") || input.hit("Enter") || input.clicked))) this.won = true;
    }
  }

  get canQuit(): boolean { return true; }

  end(): void {
    this.s.box.position.copy(this.home);
    this.s.box.rotation.set(0, 0, 0);
    this.s.stick.visible = false;
  }
}
