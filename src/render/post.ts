// @ts-nocheck -- TSL node graphs: @types/three node typings reject valid swizzles/overloads.
import * as THREE from "three/webgpu";
import {
  pass, mrt, output, normalView, packNormalToRGB, unpackRGBToNormal, vec2, vec3, vec4, float, Fn, uniform, screenUV,
  max, min, abs, length, smoothstep, mix, dot, perspectiveDepthToViewZ, clamp, fract, sin, floor, screenCoordinate,
  mx_noise_float, select,
} from "three/tsl";
import { bloom } from "three/addons/tsl/display/BloomNode.js";
import { U } from "./uniforms";

/**
 * Scene (MSAA, MRT colour + view normal / ink mask) → ink outlines from depth and normal edges
 * (bay-ride's: the Laplacian of 1/z is zero on planes, so only creases and silhouettes ink) →
 * bloom (lanterns, sun, fireworks) → warm grade with split tone, soft shoulder, vignette and a
 * faint paper grain → sRGB.
 *
 * Ink mask (normal.a): 1 = ink, 0.5 = her (warm brown, thinner far off), 0 = never inked
 * (particles, steam, water, sky).
 */
export class Post {
  readonly pipeline: THREE.RenderPipeline;
  readonly bloomNode: ReturnType<typeof bloom>;
  private readonly near = uniform(0.1);
  private readonly far = uniform(800);
  private readonly res = uniform(new THREE.Vector2(1920, 1080));
  readonly inkWidth = uniform(1.25);

  constructor(private renderer: THREE.WebGPURenderer, scene: THREE.Scene, private camera: THREE.PerspectiveCamera, samples = 4) {
    const scenePass = pass(scene, camera, { samples });
    scenePass.setMRT(mrt({ output, normal: vec4(packNormalToRGB(normalView), 1.0) }));
    const colorTex = scenePass.getTextureNode("output");
    const normalTex = scenePass.getTextureNode("normal");
    const depthTex = scenePass.getTextureNode("depth");

    const near = this.near, far = this.far, res = this.res, inkW = this.inkWidth;
    const invZ = (uv: any) => float(1).div(perspectiveDepthToViewZ(depthTex.sample(uv).r, near, far).negate().max(1e-3));

    const inked = Fn(() => {
      const uv = screenUV;
      const col = colorTex.sample(uv).rgb.toVar();
      const nC = normalTex.sample(uv);
      const iC = invZ(uv);
      const dC = float(1).div(iC);
      const her = abs(nC.a.sub(0.5)).lessThan(0.1);
      const px = vec2(inkW).div(res).mul(select(her, mix(1.0, 0.8, smoothstep(5.0, 25.0, dC)), float(1.0)));
      const eD = float(0).toVar();
      const eN = float(0).toVar();
      const mask = nC.a.toVar();
      const nCd = unpackRGBToNormal(nC.rgb);
      const offs = [vec2(1, 0), vec2(0, 1), vec2(0.7071, 0.7071), vec2(0.7071, -0.7071)];
      for (const o of offs) {
        const u1 = uv.add(o.mul(px)), u2 = uv.sub(o.mul(px));
        const n1 = normalTex.sample(u1), n2 = normalTex.sample(u2);
        const i1 = invZ(u1), i2 = invZ(u2);
        const ok = min(n1.a, n2.a).greaterThan(0.01);
        eD.assign(max(eD, select(ok, abs(i1.add(i2).sub(iC.mul(2.0))).div(iC), float(0))));
        const dn = length(unpackRGBToNormal(n1.rgb).sub(nCd)).add(length(unpackRGBToNormal(n2.rgb).sub(nCd)));
        eN.assign(max(eN, select(ok, dn, float(0))));
        mask.assign(max(mask, select(ok, max(n1.a, n2.a), float(0))));
      }
      const e = max(smoothstep(0.06, 0.18, eD), smoothstep(0.7, 1.2, eN)).toVar();
      e.mulAssign(select(nC.a.lessThan(0.01), float(0), clamp(mask.mul(2.0), 0.0, 1.0)));
      e.mulAssign(float(1).sub(smoothstep(40.0, 260.0, dC).mul(0.8)));
      const inkCol = select(her, mix(col.mul(0.25), vec3(0.09, 0.045, 0.035), 0.7), mix(col.mul(0.22), vec3(0.11, 0.08, 0.1), 0.55));
      return mix(col, inkCol, e.mul(0.9));
    })();

    this.bloomNode = bloom(inked, 0.3, 0.5, 0.95);

    const graded = Fn(() => {
      const c = inked.add(this.bloomNode.rgb).mul(U.gradeMul).toVar();
      const l = dot(c, vec3(0.2126, 0.7152, 0.0722));
      c.assign(mix(vec3(l), c, U.sat));
      c.mulAssign(mix(vec3(0.96, 1.0, 1.04), vec3(1.0, 0.945, 0.85).mul(1.04), smoothstep(0.08, 0.75, l)));
      // Soft shoulder.
      c.assign(c.div(max(c.sub(0.85), 0.0).mul(0.8).add(1.0)));
      // Vignette.
      const q = screenUV.sub(0.5).mul(vec2(res.x.div(res.y), 1.0));
      c.mulAssign(mix(1.0, 0.8, smoothstep(0.45, 1.05, length(q))));
      // Paper grain (screen space, very subtle).
      const fc = screenCoordinate.xy;
      const paper = mx_noise_float(vec3(fc.mul(0.35), 0.0)).mul(0.25).add(0.5).mul(0.5)
        .add(mx_noise_float(vec3(fc.mul(0.09).add(7.0), 0.0)).mul(0.25).add(0.5).mul(0.5));
      c.mulAssign(paper.mul(0.04).add(0.978));
      const h = fract(sin(dot(floor(fc), vec2(12.9898, 78.233))).mul(43758.5453));
      c.addAssign(h.sub(0.5).mul(0.004));
      return vec4(max(c, vec3(0)), 1.0);
    })();

    this.pipeline = new THREE.RenderPipeline(renderer);
    this.pipeline.outputNode = graded;
  }

  setBloom(strength: number, radius: number, threshold: number): void {
    this.bloomNode.strength.value = strength;
    this.bloomNode.radius.value = radius;
    this.bloomNode.threshold.value = threshold;
  }

  resize(w: number, h: number, pr: number): void {
    this.res.value.set(w * pr, h * pr);
    this.inkWidth.value = Math.max(1.0, 1.25 * (h * pr) / 1080);
  }

  render(): void {
    this.near.value = this.camera.near;
    this.far.value = this.camera.far;
    this.pipeline.render();
  }
}

/** Per-material MRT override: what the ink pass sees for this surface. */
export function inkMask(m: THREE.NodeMaterial, k: number): void {
  m.mrtNode = mrt({ normal: vec4(packNormalToRGB(normalView), float(k)) });
}
