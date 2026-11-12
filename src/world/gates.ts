// @ts-nocheck -- TSL node graphs: @types/three node typings reject valid swizzles/overloads.
import * as THREE from "three/webgpu";
import { uniform, instanceIndex, float, smoothstep } from "three/tsl";
import { Builder, solid } from "./geo";
import { GATES } from "./layout";
import { woodMaterial } from "../render/surfaces";
import { lanternPaper } from "../render/townMats";
import { lanternSwing, type LightSpot } from "../render/toon";
import { lanternGeometry } from "./town";
import { U } from "../render/uniforms";

/**
 * Lantern gates spanning the street: lacquered red posts, a double crossbeam, seven lanterns
 * hanging under the top beam and a stone lantern at each foot. Each gate has a `lit` uniform
 * (0…1): its lanterns light up one after another as it rises, and stay lit (saved progress).
 */
export interface Gate {
  z: number;
  lit: { value: number };
  target: number;
  group: THREE.Group;
  lights: LightSpot[];
  colliders: { x0: number; x1: number; z0: number; z1: number }[];
}

const POST_X = 3.55;

export function buildGates(): Gate[] {
  return GATES.map((z, gi) => {
    const group = new THREE.Group();
    group.name = `gate_${gi}`;
    const b = new Builder();
    const red = "#a8322a", dark = "#2a1e1a", stone = "#8e8a84";
    for (const s of [-1, 1]) {
      b.cyl(0.17, 0.2, 4.6, red, s * POST_X, 2.3, z, 12);
      b.cyl(0.26, 0.28, 0.35, dark, s * POST_X, 0.17, z, 12);
      // Stone lantern (toro) beside the post.
      const lx = s * (POST_X + 0.65);
      b.box(0.5, 0.12, 0.5, stone, lx, 0.06, z);
      b.cyl(0.08, 0.1, 0.75, stone, lx, 0.5, z, 8);
      b.box(0.42, 0.08, 0.42, stone, lx, 0.92, z);
      b.box(0.34, 0.3, 0.34, "#efe2c4", lx, 1.11, z);
      b.add(new THREE.ConeGeometry(0.36, 0.26, 4), stone, lx, 1.39, z, 0, Math.PI / 4, 0);
    }
    // Top beam (kasagi) with upturned ends, then the tie beam (nuki).
    b.box(POST_X * 2 + 1.4, 0.24, 0.34, dark, 0, 4.72, z);
    b.box(POST_X * 2 + 1.2, 0.26, 0.3, red, 0, 4.5, z);
    for (const s of [-1, 1]) b.box(0.6, 0.18, 0.34, dark, s * (POST_X + 0.85), 4.86, z, 0, 0, s * 0.25);
    b.box(POST_X * 2 + 0.6, 0.2, 0.18, red, 0, 3.75, z);
    // Name plaque (blank painted board).
    b.box(0.7, 0.55, 0.08, dark, 0, 4.12, z + 0.06);
    b.box(0.58, 0.43, 0.02, "#d9b65a", 0, 4.12, z + 0.11);
    group.add(solid(b.build(), woodMaterial()));

    const lit = uniform(0);
    const n = 7;
    // Lantern i lights when lit passes i/n; dim but visible before.
    const k = smoothstep(float(instanceIndex).div(n), float(instanceIndex).add(1).div(n), lit);
    const glow = U.lantern.mul(float(0.12).add(k.mul(0.88))).add(k.mul(0.35));
    const mat = lanternPaper(glow);
    lanternSwing(mat, 0.7);
    const im = new THREE.InstancedMesh(lanternGeometry(), mat, n);
    const m4 = new THREE.Matrix4();
    for (let i = 0; i < n; i++) {
      const x = -POST_X + 0.55 + (i / (n - 1)) * (POST_X * 2 - 1.1);
      m4.makeScale(1.35, 1.35, 1.35).setPosition(x, 3.62, z);
      im.setMatrixAt(i, m4);
      im.setColorAt(i, new THREE.Color(i % 2 ? "#f3e7cf" : "#d84b33"));
    }
    im.frustumCulled = false;
    group.add(im);
    const lights: LightSpot[] = [];
    for (let i = 0; i < n; i += 2) lights.push({ x: -POST_X + 0.55 + (i / (n - 1)) * (POST_X * 2 - 1.1), y: 3.3, z, r: 1, g: 0.6, b: 0.3, k: 0.9, reach: 6 });
    for (const s of [-1, 1]) lights.push({ x: s * (POST_X + 0.65), y: 1.1, z, r: 1, g: 0.7, b: 0.4, k: 0.5, reach: 3 });
    const colliders = [-1, 1].map((s) => ({ x0: s * POST_X - 0.3, x1: s * POST_X + 0.3, z0: z - 0.3, z1: z + 0.3 }))
      .concat([-1, 1].map((s) => ({ x0: s * (POST_X + 0.65) - 0.3, x1: s * (POST_X + 0.65) + 0.3, z0: z - 0.3, z1: z + 0.3 })));
    return { z, lit, target: 0, group, lights, colliders };
  });
}
