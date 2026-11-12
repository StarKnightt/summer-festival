// @ts-nocheck -- TSL node graphs: @types/three node typings reject valid swizzles/overloads.
import * as THREE from "three/webgpu";
import { Fn, vec3, float, sin, positionWorld, diffuseColor, mix, uniform } from "three/tsl";
import { ToonMaterial, paperGlow, windCloth } from "./toon";
import { inkMask } from "./post";
import { U } from "./uniforms";

export interface ToonifyOpts {
  /** The heroine: moonlit fill and rim at night, warm brown ink. */
  her?: boolean;
  /** Glow strength node for paper_ materials (default: the time-of-day lantern glow). */
  paperGlowNode?: any;
  castShadow?: boolean;
  receiveShadow?: boolean;
  /** Per-instance colour multiply on cloth_main etc. (crowd). */
  tint?: Record<string, THREE.ColorRepresentation>;
}

/**
 * Replaces every material on a loaded GLB with the matching toon material by name prefix
 * (see tools/blender/CONTRACT.md): skin, hair, face/eye, cloth_, wood_, paper_ (glows from inside),
 * glow_ (emissive), water_, fabric_flag_ and wind_* objects (ripple in the wind).
 */
export function toonify(root: THREE.Object3D, o: ToonifyOpts = {}): void {
  const cache = new Map<string, THREE.Material>();
  root.traverse((obj) => {
    const mesh = obj as THREE.Mesh;
    if (!mesh.isMesh) return;
    mesh.castShadow = o.castShadow ?? true;
    mesh.receiveShadow = o.receiveShadow ?? true;
    const wind = /^wind_/i.test(mesh.name) || /^wind_/i.test(mesh.parent?.name ?? "");
    const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
    const out = mats.map((src: any) => {
      const key = `${src.uuid}|${wind}|${mesh.geometry.attributes.color ? 1 : 0}`;
      const hit = cache.get(key);
      if (hit) return hit;
      const m = convert(src, mesh, wind, o);
      cache.set(key, m);
      return m;
    });
    mesh.material = Array.isArray(mesh.material) ? out : out[0];
  });
}

function convert(src: any, mesh: THREE.Mesh, wind: boolean, o: ToonifyOpts): THREE.Material {
  const name: string = (src.name || "").toLowerCase();
  const color = src.color ? src.color.clone() : new THREE.Color(1, 1, 1);
  const tint = o.tint && Object.entries(o.tint).find(([k]) => name.startsWith(k));
  if (tint) color.multiply(new THREE.Color(tint[1]));
  const map = src.map ?? null;
  if (map) map.colorSpace = THREE.SRGBColorSpace;
  const vertexColors = !!mesh.geometry.attributes.color;
  const her = !!o.her;
  const base = { color, map, vertexColors, name: src.name, side: src.side ?? THREE.FrontSide, transparent: src.transparent, alphaTest: src.alphaTest || (map && src.transparent ? 0.5 : 0) };

  if (name.startsWith("glow")) {
    const m = new THREE.MeshBasicNodeMaterial({ color, map, vertexColors });
    m.colorNode = Fn(() => diffuseColor.rgb.mul(2.6).mul(sin(U.time.mul(17.0).add(positionWorld.x.mul(9.0))).mul(0.08).add(0.92)))();
    inkMask(m, 0);
    return m;
  }
  if (name.startsWith("water")) {
    const m = new THREE.MeshBasicNodeMaterial({ color, transparent: true, opacity: 0.85 });
    m.colorNode = Fn(() => mix(vec3(0.16, 0.42, 0.6), vec3(0.5, 0.8, 0.9), sin(positionWorld.x.mul(9.0).add(U.time.mul(2.0))).mul(0.05).add(0.15)).mul(U.worldTint.mul(0.7).add(0.3)))();
    inkMask(m, 0);
    return m;
  }
  let opts: any = { paint: 0.45, rim: 0.5 };
  if (name.startsWith("skin")) opts = { skin: true, soft: 0.08, paint: 0, rim: 0.35, her };
  else if (name.startsWith("hair")) opts = { hair: true, paint: 0.15, rim: 0.6, her, soft: 0.04 };
  else if (name.startsWith("face") || name.startsWith("eye") || name.startsWith("brow") || name.startsWith("lash") || name.startsWith("mouth")) opts = { flat: true };
  else if (name.startsWith("cloth") || name.startsWith("fabric")) opts = { paint: 0.3, rim: 0.55, her, soft: her ? 0.03 : 0 };
  else if (name.startsWith("fur")) opts = { paint: 0.25, rim: 0.6, soft: 0.05 };
  else if (name.startsWith("paper")) opts = { paint: 0.0, rim: 0.3, soft: 0.1 };
  else if (name.startsWith("metal") || name.startsWith("plastic")) opts = { paint: 0.1, rim: 0.7 };
  const m = new ToonMaterial({ ...base, ...opts });
  if (name.startsWith("paper")) paperGlow(m, o.paperGlowNode ?? U.lantern, new THREE.Color("#ffb060"), 2.2);
  if (wind || name.startsWith("fabric_flag")) {
    mesh.geometry.computeBoundingBox();
    const bb = mesh.geometry.boundingBox!;
    windCloth(m, bb.max.y, Math.max(0.05, bb.max.y - bb.min.y), 1);
  }
  if (her) inkMask(m, 0.5);
  if (opts.flat) inkMask(m, her ? 0.5 : 1);
  return m;
}

/** A glow node for one paper lantern set that can be switched on (0..1 uniform). */
export function switchGlow(initial = 0) {
  const u = uniform(initial);
  return { u, node: U.lantern.mul(float(0.15).add(u.mul(0.85))).add(u.mul(0.4)) };
}
