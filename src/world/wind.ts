import * as THREE from "three/webgpu";
import { U } from "../render/uniforms";

/**
 * The sea breeze: a slow base that comes and goes, with gusts rolling up the street from the
 * shore. Everything that sways reads `U.wind` / `U.windDir`; wind chimes ring on gust peaks.
 */
export class Wind {
  value = 0.3;
  readonly dir = new THREE.Vector2(0.25, 0.97).normalize();
  private t = Math.random() * 100;
  private gust = 0;
  private gustT = 3;
  private listeners: ((k: number) => void)[] = [];

  /** Calls `fn` on each gust; returns a function that stops listening. */
  onGust(fn: (strength: number) => void): () => void {
    this.listeners.push(fn);
    return () => { const i = this.listeners.indexOf(fn); if (i >= 0) this.listeners.splice(i, 1); };
  }

  update(dt: number): void {
    this.t += dt;
    const base = 0.28 + 0.12 * Math.sin(this.t * 0.11) + 0.06 * Math.sin(this.t * 0.37 + 1.3);
    this.gustT -= dt;
    if (this.gustT <= 0) {
      this.gustT = 5 + Math.random() * 9;
      this.gust = 0.4 + Math.random() * 0.45;
      for (const f of this.listeners) f(this.gust);
    }
    this.gust = Math.max(0, this.gust - dt * 0.22);
    const g = this.gust * this.gust * (3 - 2 * this.gust);
    this.value = Math.min(1, base + g * 0.7);
    const a = Math.atan2(0.97, 0.25) + Math.sin(this.t * 0.05) * 0.25;
    this.dir.set(Math.cos(a), Math.sin(a));
    U.wind.value = this.value;
    U.windDir.value.copy(this.dir);
  }
}
