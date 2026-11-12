import * as THREE from "three/webgpu";
import { MiniGame, pointerRay, damp, type Ctx } from "./common";
import { ToonMaterial, paperGlow } from "../../render/toon";
import { switchGlow } from "../../render/toonify";
import type { Stall } from "../../world/stalls";
import { inkMask } from "../../render/post";

/**
 * The lantern stall's own lantern starts dark. `prepareLantern` swaps its paper for a switchable
 * glow and hides the candle flame; `lightLantern` brings both up (instantly when loading a save).
 */
export interface LanternState { u: { value: number }; mats: { m: THREE.Material & { color: THREE.Color }; c: THREE.Color }[]; flame: THREE.Object3D | null; wickTop: THREE.Vector3; lightPos: THREE.Vector3; target: number }

export function prepareLantern(stall: Stall): LanternState {
  const sw = switchGlow(0);
  const mats: LanternState["mats"] = [];
  const lamp = stall.find("lantern_light");
  lamp?.traverse((o) => {
    const m = o as THREE.Mesh;
    if (!m.isMesh) return;
    const src = m.material as any;
    if (!/^paper/i.test(src?.name ?? "")) return;
    const nm = new ToonMaterial({ color: src.color, paint: 0, rim: 0.3, soft: 0.1, name: src.name });
    paperGlow(nm, sw.node, new THREE.Color("#ffb060"), 2.6);
    m.material = nm;
    mats.push({ m: nm as any, c: nm.color.clone() });
  });
  const wick = stall.find("candle_wick");
  const flame = stall.find("flame") ?? null;
  if (flame) flame.visible = false;
  const wickTop = wick ? wick.getWorldPosition(new THREE.Vector3()).add(new THREE.Vector3(0, 0.087 * wick.getWorldScale(new THREE.Vector3()).y, 0)) : stall.camTarget.clone().add(new THREE.Vector3(0, -0.1, 0));
  const lightPos = lamp ? lamp.getWorldPosition(new THREE.Vector3()) : stall.camTarget.clone();
  return { u: sw.u, mats, flame, wickTop, lightPos, target: 0 };
}

export function updateLantern(s: LanternState, dt: number): void {
  s.u.value = damp(s.u.value, s.target, 1.6, dt);
  // Unlit paper is a dull, shadowed grey-cream; it warms up as the candle catches.
  for (const { m, c } of s.mats) m.color.copy(c).multiplyScalar(0.38 + 0.62 * s.u.value);
}

/**
 * Light a lantern: strike a match (click), bring its flame to the candle wick and hold it there
 * while the breeze nudges your hand. A match burns for a few seconds; strike another if it goes.
 */
export class Lantern extends MiniGame {
  readonly task = "lantern" as const;
  private match = new THREE.Group();
  private flame: THREE.Mesh;
  private burning = 0;
  private progress = 0;
  private matches = 0;
  private t = 0;
  private tip = new THREE.Vector3();
  private litT = -1;
  private sway = new THREE.Vector3();
  private gust = 0;

  constructor(c: Ctx, private st: LanternState, private onLit: () => void) {
    super(c);
    const stick = new THREE.Mesh(new THREE.CylinderGeometry(0.0022, 0.0022, 0.07, 5), new ToonMaterial({ color: "#e8d4a8", paint: 0 }));
    stick.position.y = -0.035;
    const head = new THREE.Mesh(new THREE.SphereGeometry(0.0045, 8, 6), new ToonMaterial({ color: "#a82a22", paint: 0 }));
    this.flame = new THREE.Mesh(new THREE.SphereGeometry(0.006, 10, 8).scale(1, 2.2, 1).translate(0, 0.01, 0), new THREE.MeshBasicNodeMaterial({ color: new THREE.Color(1.0, 0.62, 0.25).multiplyScalar(3) }));
    inkMask(this.flame.material as any, 0);
    this.flame.visible = false;
    this.match.add(stick, head, this.flame);
    this.match.rotation.z = 0.5;
    c.game.scene.add(this.match);
    c.game.input.captureMouse = true;
    c.game.wind.onGust((k) => { this.gust = Math.max(this.gust, k); });
  }

  update(dt: number): void {
    const g = this.c.game, input = g.input;
    this.t += dt;
    // The match sits where the pointer is, at the depth of the wick, nudged by the breeze.
    const ray = pointerRay(g);
    const d = g.camera.position.distanceTo(this.st.wickTop);
    const want = ray.origin.clone().addScaledVector(ray.direction, d);
    const right = new THREE.Vector3(1, 0, 0).applyQuaternion(g.camera.quaternion);
    this.gust *= Math.exp(-dt * 0.9);
    const w = (Math.sin(this.t * 1.7) * 0.008 + Math.sin(this.t * 4.3) * 0.004) + this.gust * 0.03 * Math.sin(this.t * 2.6);
    this.sway.copy(right).multiplyScalar(w).add(new THREE.Vector3(0, Math.sin(this.t * 2.1) * 0.004, 0));
    this.match.position.lerp(want.add(this.sway), 1 - Math.exp(-14 * dt));
    this.match.updateMatrixWorld(true);
    this.tip.set(0, 0.012, 0).applyMatrix4(this.flame.matrixWorld);

    if (this.litT >= 0) {
      this.litT += dt;
      this.flame.scale.setScalar(Math.max(0.01, 1 - this.litT * 1.5));
      if (this.litT > 1.6) this.won = true;
      return;
    }
    // Strike.
    if (input.clicked && this.burning <= 0) {
      this.burning = 7;
      this.matches++;
      this.flame.visible = true;
      this.c.audio.blip("match", this.match.position);
      this.c.fx.sparkle(this.match.position, new THREE.Color(1, 0.6, 0.3), 8, 0.4);
    }
    if (this.burning > 0) {
      this.burning -= dt;
      const flick = 1 + Math.sin(this.t * 31) * 0.1 + Math.sin(this.t * 17) * 0.08;
      this.flame.scale.set(flick, flick * (1 + this.gust * 0.3), flick);
      this.flame.rotation.z = -this.sway.x * 8;
      if (this.burning <= 0) { this.flame.visible = false; this.c.audio.blip("fail"); }
      const dist = this.tip.distanceTo(this.st.wickTop);
      if (dist < 0.028) this.progress += dt / 1.1;
      else this.progress = Math.max(0, this.progress - dt * 0.6);
    } else this.progress = Math.max(0, this.progress - dt * 0.6);

    if (this.progress >= 1) {
      this.litT = 0;
      this.burning = 0;
      if (this.st.flame) this.st.flame.visible = true;
      this.st.target = 1;
      this.onLit();
      this.c.fx.sparkle(this.st.wickTop, new THREE.Color(1, 0.75, 0.4), 16, 0.4);
      this.c.hud.setGuide("The lantern glows", null);
      this.c.game.her.smile = 1;
      return;
    }
    const line = this.burning > 0 ? "Bring the flame to the wick and hold it steady" : this.matches ? "The match went out · click to strike another" : "Click to strike a match";
    this.c.hud.setGuide(line, this.progress > 0 || this.burning > 0 ? this.progress : null, this.burning > 0 ? `${Math.ceil(this.burning)}s` : "");
    this.c.game.her.lookTarget = this.st.wickTop;
  }

  end(): void {
    this.match.removeFromParent();
    this.c.game.input.captureMouse = false;
    this.c.game.her.lookTarget = null;
  }
}
