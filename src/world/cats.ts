import * as THREE from "three/webgpu";
import { clone as skClone } from "three/addons/utils/SkeletonUtils.js";
import { loadGLB } from "./stalls";
import { toonify } from "../render/toonify";
import { ToonMaterial } from "../render/toon";
import { HIDDEN_CATS, SLEEPING_CAT } from "./layout";

export interface Cat {
  id: string;
  root: THREE.Object3D;
  pos: THREE.Vector3;
  mixer: THREE.AnimationMixer | null;
  actions: Map<string, THREE.AnimationAction>;
  play(name: string, fade?: number): void;
}

/**
 * The town's cats (cats.glb): a ginger tabby asleep on a step (pet it) and three hidden cats to
 * find. Each one is a skinned clone with its own mixer, idling on loop so none is ever frozen.
 */
export async function buildCats(): Promise<{ group: THREE.Group; sleeper: Cat; hidden: Cat[]; update(dt: number): void }> {
  const group = new THREE.Group();
  group.name = "cats";
  const scene = await loadGLB(`${import.meta.env.BASE_URL}models/cats.glb`);
  const clips: THREE.AnimationClip[] = (scene as any)?.userData.animations ?? [];
  if (scene) toonify(scene);

  const make = (kind: "cat_sleep" | "cat_sit" | "cat_loaf", id: string, x: number, y: number, z: number, ry: number, idle: string): Cat => {
    const proto = scene?.getObjectByName(kind);
    const root = proto ? skClone(proto) : placeholderCat(kind);
    root.position.set(x, y, z);
    root.rotation.y = ry;
    root.traverse((o) => { if ((o as any).isSkinnedMesh) o.frustumCulled = false; });
    group.add(root);
    const mixer = proto ? new THREE.AnimationMixer(root) : null;
    const actions = new Map<string, THREE.AnimationAction>();
    if (mixer) for (const c of clips.filter((c) => c.name.startsWith(kind + "_"))) actions.set(c.name.slice(kind.length + 1), mixer.clipAction(c));
    let cur: THREE.AnimationAction | null = null;
    const cat: Cat = {
      id, root, pos: new THREE.Vector3(x, y, z), mixer, actions,
      play(name, fade = 0.5) {
        const a = actions.get(name);
        if (!a || a === cur) return;
        a.reset().play();
        if (cur) a.crossFadeFrom(cur, fade, false);
        cur = a;
      },
    };
    cat.play(idle, 0);
    // Different phases so two cats of a kind don't move in step.
    mixer?.update(Math.random() * 4);
    return cat;
  };

  const sleeper = make("cat_sleep", "sleeper", SLEEPING_CAT.x, SLEEPING_CAT.y, SLEEPING_CAT.z, SLEEPING_CAT.ry, "sleep");
  const hidden = HIDDEN_CATS.map((c) => make(c.kind, c.id, c.x, c.y, c.z, c.ry, c.kind === "cat_sit" ? "idle" : "idle"));
  const all = [sleeper, ...hidden];
  return {
    group, sleeper, hidden,
    update(dt) { for (const c of all) c.mixer?.update(dt); },
  };
}

function placeholderCat(kind: string): THREE.Object3D {
  const g = new THREE.Group();
  const m = new ToonMaterial({ color: kind === "cat_loaf" ? "#2a2628" : kind === "cat_sleep" ? "#d8873a" : "#f0e6da", paint: 0.2 });
  const body = new THREE.Mesh(new THREE.SphereGeometry(0.13, 14, 10), m);
  body.scale.set(1, 0.7, 1.4);
  body.position.y = 0.1;
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.08, 14, 10), m);
  head.position.set(0, 0.17, 0.16);
  g.add(body, head);
  return g;
}
