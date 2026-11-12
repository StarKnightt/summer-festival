import * as THREE from "three/webgpu";
import { U } from "../render/uniforms";
import { skyDome } from "../render/sky";
import { cloudCards } from "../render/clouds";
import { buildSea } from "../render/sea";
import { Post } from "../render/post";
import { bakeLanternField, type LightSpot } from "../render/toon";
import { TimeOfDay, parsePreset, type Preset } from "../world/timeofday";
import { buildTown, type Town } from "../world/town";
import { buildGates, type Gate } from "../world/gates";
import { buildStalls, type StallSet } from "../world/stalls";
import { Wind } from "../world/wind";
import { Input } from "../core/input";
import { CameraRig } from "../core/camera";
import { Heroine } from "../actors/heroine";
import { Player } from "./player";
import { STREET, SPAWNS } from "../world/layout";

export class Bus {
  private m = new Map<string, ((a: any) => void)[]>();
  on(k: string, f: (a: any) => void): void { (this.m.get(k) ?? this.m.set(k, []).get(k)!).push(f); }
  emit(k: string, a?: any): void { for (const f of this.m.get(k) ?? []) f(a); }
}

export interface System {
  update(dt: number): void;
}

/**
 * Owns the renderer, the world and the loop. Gameplay systems register themselves in
 * `systems` and are updated in order after the player and before the render.
 */
export class Game {
  renderer!: THREE.WebGPURenderer;
  readonly scene = new THREE.Scene();
  readonly camera = new THREE.PerspectiveCamera(55, innerWidth / innerHeight, 0.08, 4000);
  post!: Post;
  tod!: TimeOfDay;
  readonly sun = new THREE.DirectionalLight(0xffffff, 1);
  readonly wind = new Wind();
  input!: Input;
  rig = new CameraRig(this.camera);
  town!: Town;
  gates!: Gate[];
  stalls!: StallSet;
  readonly her = new Heroine();
  player!: Player;
  readonly systems: System[] = [];
  readonly params = new URLSearchParams(location.search);
  private lightSpots: LightSpot[] = [];
  private pixelRatio = 1;
  /** Seconds of play time (paused with the game). */
  time = 0;
  paused = false;
  readonly frameMs: number[] = [];
  private onFrame: ((dt: number) => void)[] = [];
  /** Props she carries (goldfish bag, candy apple, mask). */
  readonly carry: THREE.Object3D[] = [];
  /** Tiny event bus between systems (keeper calls → keeper waves, etc.). */
  readonly events = new Bus();
  /** Load progress 0…1 (title card bar). */
  onProgress: (k: number) => void = () => {};

  async init(): Promise<void> {
    const r = new THREE.WebGPURenderer({ antialias: false, powerPreference: "high-performance" });
    await r.init();
    this.renderer = r;
    const be = r.backend as any;
    const info = be.isWebGPUBackend ? be.adapter?.info : null;
    const gpu = { backend: be.isWebGPUBackend ? "webgpu" : "webgl2", vendor: info?.vendor ?? "", arch: info?.architecture ?? "", desc: info?.description ?? "" };
    (window as any).__gpu = gpu;
    if (this.params.has("debug") || (navigator as any).webdriver) console.log(`[gpu] ${gpu.backend} ${gpu.vendor} ${gpu.arch} ${gpu.desc}`);
    this.pixelRatio = Math.min(devicePixelRatio || 1, 1.5);
    r.setPixelRatio(this.pixelRatio);
    r.setSize(innerWidth, innerHeight);
    r.shadowMap.enabled = true;
    r.shadowMap.type = THREE.PCFShadowMap;
    document.body.appendChild(r.domElement);
    this.input = new Input(r.domElement);

    // Light: one sun/moon with a tight shadow box that follows her.
    const sun = this.sun;
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    Object.assign(sun.shadow.camera, { left: -22, right: 22, top: 22, bottom: -22, near: 1, far: 140 });
    sun.shadow.bias = -0.0006;
    sun.shadow.normalBias = 0.03;
    this.scene.add(sun, sun.target);
    this.scene.fog = new THREE.Fog(0xffffff, 40, 300);

    this.post = new Post(r, this.scene, this.camera);
    const start = parsePreset(this.params.get("tod")) ?? "sunset";
    const shadowDir = new THREE.Vector3();
    this.tod = new TimeOfDay({
      bloom: (s, rr, t) => this.post.setBloom(s, rr, t),
      fog: (c, n, f) => { const fog = this.scene.fog as THREE.Fog; fog.color.copy(c); fog.near = n; fog.far = f; },
      key: (_d, c, sd) => { sun.color.copy(c); shadowDir.copy(sd); },
      ambient: () => {},
    }, start);
    this.shadowDir = shadowDir;

    // World.
    const sky = skyDome();
    this.skyMesh = sky;
    this.scene.add(sky, cloudCards());
    this.town = buildTown();
    this.scene.add(this.town.group);
    this.scene.add(buildSea());
    this.gates = buildGates();
    for (const g of this.gates) this.scene.add(g.group);
    this.onProgress(0.3);
    this.stalls = await buildStalls();
    this.onProgress(0.55);
    this.scene.add(this.stalls.group);
    this.lightSpots = [...this.town.lights, ...this.stalls.lights];
    this.rebakeLights();

    // Her.
    await this.her.load(`${import.meta.env.BASE_URL}models/heroine.glb`);
    this.onProgress(0.8);
    this.scene.add(this.her.root);
    const colliders = [...this.town.colliders, ...this.stalls.colliders, ...this.gates.flatMap((g) => g.colliders)];
    this.player = new Player(this.her, colliders, this.town.groundY);
    const sp = SPAWNS[0];
    this.her.position.set(sp.x, 0, sp.z);
    this.rig.bounds = (p) => {
      // Stay in the street corridor / above the beach: no wide or through-wall views.
      if (p.z > -94) p.x = THREE.MathUtils.clamp(p.x, -STREET.half + 0.35, STREET.half - 0.35);
      p.z = Math.min(p.z, STREET.zStart + 1.5);
      p.y = Math.max(p.y, this.town.groundY(p.x, p.z) + 0.35);
      p.y = Math.min(p.y, p.z > -94 ? 3.2 : 6);
      return p;
    };
    this.rig.snap(this.her.position, this.her.heading);

    addEventListener("resize", () => this.resize());
    this.resize();
  }

  private shadowDir = new THREE.Vector3();
  private skyMesh!: THREE.Mesh;

  /** Gates light up: their lanterns join the light field. */
  rebakeLights(): void {
    const spots = [...this.lightSpots];
    for (const g of this.gates) if (g.target > 0.5) spots.push(...g.lights);
    bakeLanternField(spots);
  }

  addLights(spots: LightSpot[]): void {
    this.lightSpots.push(...spots);
    this.rebakeLights();
  }

  frame(fn: (dt: number) => void): void { this.onFrame.push(fn); }

  resize(): void {
    this.camera.aspect = innerWidth / innerHeight;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(innerWidth, innerHeight);
    this.post.resize(innerWidth, innerHeight, this.pixelRatio);
  }

  setTod(p: Preset, instant = false): void { this.tod.set(p, instant); }

  start(): void {
    let last = performance.now();
    let frames = 0;
    this.renderer.setAnimationLoop(() => {
      const now = performance.now();
      const raw = (now - last) / 1000;
      last = now;
      this.frameMs.push(raw * 1000);
      if (this.frameMs.length > 600) this.frameMs.shift();
      const dt = this.paused ? 0 : Math.min(raw, 1 / 20);
      this.step(dt);
      if (++frames === 8) (window as any).__ready = true;
    });
  }

  step(dt: number): void {
    this.time += dt;
    U.time.value = this.time;
    this.wind.update(dt);
    this.tod.update(dt);
    this.player.update(dt, this.input, this.rig.yaw);
    for (const s of this.systems) s.update(dt);
    for (const f of this.onFrame) f(dt);
    this.her.update(dt, this.wind.dir, this.wind.value);
    this.rig.update(dt, this.her.position, this.her.heading, this.her.speed, this.input);
    // Sun shadow box follows her.
    const c = this.her.position;
    this.sun.target.position.set(c.x, c.y, c.z - 6);
    this.sun.position.copy(this.sun.target.position).addScaledVector(this.shadowDir, 70);
    this.skyMesh.position.copy(this.camera.position);
    this.post.render();
    this.input.endFrame();
  }
}
