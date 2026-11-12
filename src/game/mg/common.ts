import * as THREE from "three/webgpu";
import type { Game } from "../game";
import type { Hud } from "../../ui/hud";
import type { Audio } from "../../audio/audio";
import type { Fx } from "../../fx/fx";
import type { Stall } from "../../world/stalls";
import type { TaskId } from "../../world/layout";

export interface Ctx {
  game: Game;
  hud: Hud;
  audio: Audio;
  fx: Fx;
  stall: Stall;
}

/**
 * A stall mini-game. The director walks her to the counter, frames the stall's camera and hands
 * over the mouse; the game sets `won` when it's done and the director plays the chime and leaves.
 */
export abstract class MiniGame {
  won = false;
  /** The checklist task this completes, or null for things that are just for fun. */
  abstract readonly task: TaskId | null;
  constructor(protected c: Ctx) {}
  abstract update(dt: number): void;
  /** Called when leaving (won or Esc). Clean up props that should not stay. */
  end(): void {}
  /** Whether she can leave with Esc right now. */
  get canQuit(): boolean { return !this.won; }
}

const _ray = new THREE.Raycaster();
const _v2 = new THREE.Vector2();

/** Ray from the camera through the pointer. */
export function pointerRay(g: Game): THREE.Ray {
  _v2.set(g.input.ndcX, g.input.ndcY);
  _ray.setFromCamera(_v2, g.camera);
  return _ray.ray;
}

/** Where the pointer ray meets the horizontal plane y = h (world), or null. */
export function pointerOnPlane(g: Game, h: number): THREE.Vector3 | null {
  const r = pointerRay(g);
  const p = new THREE.Vector3();
  return r.intersectPlane(new THREE.Plane(new THREE.Vector3(0, 1, 0), -h), p) ? p : null;
}

/** The object under the pointer among `objs` (the root of each list entry), or null. */
export function pick<T extends THREE.Object3D>(g: Game, objs: T[]): T | null {
  _v2.set(g.input.ndcX, g.input.ndcY);
  _ray.setFromCamera(_v2, g.camera);
  const hits = _ray.intersectObjects(objs.filter((o) => o.visible), true);
  if (!hits.length) return null;
  let o: THREE.Object3D | null = hits[0].object;
  while (o && !objs.includes(o as T)) o = o.parent;
  return (o as T) ?? null;
}

/** Projects a world point to CSS pixels. */
export function toScreen(g: Game, p: THREE.Vector3): { x: number; y: number; behind: boolean } {
  const v = p.clone().project(g.camera);
  return { x: (v.x * 0.5 + 0.5) * innerWidth, y: (-v.y * 0.5 + 0.5) * innerHeight, behind: v.z > 1 };
}

export const damp = (a: number, b: number, k: number, dt: number) => b + (a - b) * Math.exp(-k * dt);
