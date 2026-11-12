import { preloaded } from "../core/preload";
import * as THREE from "three/webgpu";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { STALLS, stallX, STALL_W, STALL_D, type StallSpot } from "./layout";
import { toonify } from "../render/toonify";
import { Builder, solid } from "./geo";
import { woodMaterial } from "../render/surfaces";
import { ToonMaterial, type LightSpot } from "../render/toon";

/**
 * Festival stalls (yatai) placed along the street from the Blender stall kit (stalls.glb). Each
 * stall exposes its empties in world space: where the keeper stands, where the player stands to
 * use it, the mini-game camera, and steam / mist emitters.
 */
export interface Stall {
  spot: StallSpot;
  root: THREE.Object3D;
  /** World points (copied from the kit's empties). */
  keeper: THREE.Vector3;
  use: THREE.Vector3;
  cam: THREE.Vector3;
  camTarget: THREE.Vector3;
  steam: THREE.Vector3[];
  /** Facing of the counter front (unit, toward the street). */
  front: THREE.Vector3;
  find(name: string): THREE.Object3D | undefined;
  findAll(prefix: string): THREE.Object3D[];
}

export interface StallSet {
  group: THREE.Group;
  stalls: Stall[];
  /** Kit pieces for other systems (cloned on demand). */
  kit: Map<string, THREE.Object3D>;
  lights: LightSpot[];
  colliders: { x0: number; x1: number; z0: number; z1: number }[];
}

export async function loadGLB(url: string): Promise<THREE.Group | null> {
  try {
    const pre = preloaded(url);
    const buf = pre ? await pre.catch(() => null) : null;
    const loader = new GLTFLoader();
    const gltf = buf ? await loader.parseAsync(buf, url.slice(0, url.lastIndexOf("/") + 1)) : await loader.loadAsync(url);
    (gltf.scene as any).userData.animations = gltf.animations;
    return gltf.scene;
  } catch (e) {
    console.warn("[game] could not load", url, e);
    return null;
  }
}

export async function buildStalls(): Promise<StallSet> {
  const group = new THREE.Group();
  group.name = "stalls";
  const kit = new Map<string, THREE.Object3D>();
  const scene = await loadGLB(`${import.meta.env.BASE_URL}models/stalls.glb`);
  if (scene) {
    toonify(scene);
    for (const c of [...scene.children]) kit.set(c.name, c);
  }
  const stalls: Stall[] = [];
  const lights: LightSpot[] = [];
  const colliders: StallSet["colliders"] = [];
  for (const spot of STALLS) {
    const name = `stall_${spot.kind}`;
    const proto = kit.get(name);
    const root = proto ? proto.clone(true) : placeholderStall(spot);
    root.name = `${name}@${spot.z}`;
    const x = stallX(spot.side);
    root.position.set(x, 0, spot.z);
    // Kit stalls face +Z; turn them toward the street.
    root.rotation.y = spot.side < 0 ? Math.PI / 2 : -Math.PI / 2;
    group.add(root);
    root.updateMatrixWorld(true);
    const front = new THREE.Vector3(-spot.side, 0, 0);
    const wp = (n: string, fallback: THREE.Vector3) => {
      // GLTFLoader de-duplicates names across the file (keeper, keeper_1, …): anchors carry
      // userData.anchor, so search by that first.
      let o: THREE.Object3D | undefined;
      root.traverse((c) => { if (!o && (c.userData?.anchor === n || c.name === n)) o = c; });
      return o ? o.getWorldPosition(new THREE.Vector3()) : fallback.clone();
    };
    const keeper = wp("keeper", new THREE.Vector3(x + spot.side * 0.45, 0, spot.z));
    const use = wp("use", new THREE.Vector3(x - spot.side * (STALL_D / 2 + 1.0), 0, spot.z));
    const cam = wp("cam", new THREE.Vector3(x - spot.side * (STALL_D / 2 + 2.0), 1.75, spot.z + 0.4));
    const camTarget = wp("cam_target", new THREE.Vector3(x, 1.0, spot.z));
    use.y = 0;
    keeper.y = 0;
    const steam: THREE.Vector3[] = [];
    root.traverse((o) => { if (/^fx_(steam|mist)/.test(o.name)) steam.push(o.getWorldPosition(new THREE.Vector3())); });
    stalls.push({
      spot, root, keeper, use, cam, camTarget, steam, front,
      find: (n) => root.getObjectByName(n),
      findAll: (p) => { const a: THREE.Object3D[] = []; root.traverse((o) => { if (o.name.startsWith(p)) a.push(o); }); return a; },
    });
    // Warm bulb light under each awning.
    lights.push({ x: x - spot.side * 0.4, y: 2.3, z: spot.z, r: 1, g: 0.72, b: 0.42, k: 0.75, reach: 4.5 });
    colliders.push({ x0: Math.min(x - STALL_D / 2, x + STALL_D / 2) - 0.05, x1: Math.max(x - STALL_D / 2, x + STALL_D / 2), z0: spot.z - STALL_W / 2, z1: spot.z + STALL_W / 2 });
  }
  return { group, stalls, kit, lights, colliders };
}

/** Until the kit exists: a simple yatai so the street still reads. */
function placeholderStall(spot: StallSpot): THREE.Object3D {
  const b = new Builder();
  const w = STALL_W, d = STALL_D;
  const wood = "#7a5536";
  for (const sx of [-1, 1]) for (const sz of [-1, 1]) b.box(0.1, 2.5, 0.1, wood, sx * (w / 2 - 0.08), 1.25, sz * (d / 2 - 0.08));
  b.box(w, 0.9, 0.5, "#8a6444", 0, 0.45, d / 2 - 0.25);
  b.box(w + 0.1, 0.06, 0.6, "#b08860", 0, 0.92, d / 2 - 0.25);
  const awn = { goldfish: "#d8463a", candyapple: "#e47a9a", shavedice: "#3c74b8", ringtoss: "#3f8a56", masks: "#e08a2c", lantern: "#3a3f78", food_a: "#c9502e", food_b: "#a8742c" }[spot.kind];
  for (let i = 0; i < 6; i++) b.box(w / 6, 0.05, d + 0.5, i % 2 ? "#f2ead8" : awn, -w / 2 + (i + 0.5) * (w / 6), 2.55, 0.15, 0, -0.18);
  b.box(w, 0.35, 0.03, awn, 0, 2.3, d / 2 + 0.35);
  const g = new THREE.Group();
  g.add(solid(b.build(), woodMaterial()));
  const keeper = new THREE.Object3D(); keeper.name = "keeper"; keeper.position.set(0, 0, -0.35); g.add(keeper);
  const use = new THREE.Object3D(); use.name = "use"; use.position.set(0, 0, d / 2 + 1.0); g.add(use);
  const cam = new THREE.Object3D(); cam.name = "cam"; cam.position.set(0.3, 1.8, d / 2 + 2.2); g.add(cam);
  const ct = new THREE.Object3D(); ct.name = "cam_target"; ct.position.set(0, 1.0, 0); g.add(ct);
  void ToonMaterial;
  return g;
}
