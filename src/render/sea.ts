// @ts-nocheck -- TSL node graphs: @types/three node typings reject valid swizzles/overloads.
import * as THREE from "three/webgpu";
import {
  Fn, float, vec2, vec3, vec4, dot, mix, smoothstep, max, min, abs, normalize, clamp, exp, pow, length, reflect,
  positionWorld, positionLocal, cameraPosition, mx_noise_float, sin, cos, fract, varying, fwidth,
} from "three/tsl";
import { U } from "./uniforms";
import { skyColor } from "./sky";
import { inkMask } from "./post";
import { SHORE } from "../world/layout";

/**
 * The bay at the bottom of the street, after bay-ride's painted water: wave trains as a sum of
 * directional sines (analytic normals), body colour from the shallows over the sand to deep blue,
 * a Fresnel sky reflection through the same sky function, the sun's (or moon's) glitter path,
 * and a lacy foam line where the swash runs up the beach. The fireworks light the water too.
 */
const WAVES: [number, number, number, number, number][] = [
  // dirX, dirZ (toward shore is +Z), wavelength, amplitude, speed
  [0.05, 1.0, 9.0, 0.09, 1.0],
  [0.35, 0.94, 5.3, 0.05, 1.1],
  [-0.4, 0.92, 3.7, 0.035, 1.2],
  [0.7, 0.71, 2.3, 0.018, 1.3],
  [-0.8, 0.6, 1.4, 0.009, 1.5],
  [0.2, -0.98, 0.9, 0.005, 1.7],
];

const beachH = (x: any, z: any) => {
  const t = max(z.negate().sub(108.0), 0.0);
  return float(SHORE.beachY).sub(t.mul(0.04)).sub(max(z.negate().sub(125.0), 0.0).mul(0.08)).add(sin(x.mul(0.08)).mul(0.05));
};

export function buildSea(): THREE.Mesh {
  const g = new THREE.PlaneGeometry(2400, 1400, 160, 120).rotateX(-Math.PI / 2);
  // Denser near the shore: squash the grid toward z = 0 then shift.
  const p = g.attributes.position as THREE.BufferAttribute;
  for (let i = 0; i < p.count; i++) {
    const z = p.getZ(i); // −700 … 700
    const t = (z + 700) / 1400; // 0 far … 1 near
    p.setZ(i, -116 - Math.pow(1 - t, 2.2) * 1400);
    const x = p.getX(i);
    p.setX(i, x * (0.08 + 0.92 * Math.pow(1 - t, 1.2)));
  }
  g.computeBoundingSphere();

  const m = new THREE.MeshBasicNodeMaterial({ transparent: true, depthWrite: true, fog: false });
  inkMask(m, 0);
  const T = U.time;

  const waveSum = (xz: any, withNormal: boolean) => {
    let h: any = float(0);
    let dx: any = float(0), dz: any = float(0);
    for (const [ax, az, L, A, sp] of WAVES) {
      const k = (2 * Math.PI) / L;
      const c = Math.sqrt(9.8 / k) * 0.55 * sp;
      const ph = xz.x.mul(ax * k).add(xz.y.mul(az * k)).sub(T.mul(k * c));
      h = h.add(sin(ph).mul(A));
      if (withNormal) {
        const d = cos(ph).mul(A * k);
        dx = dx.add(d.mul(ax));
        dz = dz.add(d.mul(az));
      }
    }
    return { h, dx, dz };
  };

  const vH = varying(float(0), "vSeaH");
  m.positionNode = Fn(() => {
    const pl = positionLocal.toVar();
    const near = smoothstep(-500.0, -140.0, pl.z);
    const { h } = waveSum(pl.xz, false);
    const depthK = smoothstep(0.0, 1.2, float(SHORE.seaY).sub(beachH(pl.x, pl.z)));
    vH.assign(h);
    pl.y.assign(float(SHORE.seaY).add(h.mul(near).mul(depthK.mul(0.8).add(0.2))));
    return pl;
  })();

  m.colorNode = Fn(() => {
    const wp = positionWorld;
    const xz = wp.xz;
    const dist = length(wp.sub(cameraPosition));
    const { dx, dz } = waveSum(xz, true);
    // Fine ripples, faded by footprint (no shimmer far off).
    const fade = float(1).sub(smoothstep(30.0, 160.0, dist));
    const rip = vec2(
      mx_noise_float(vec3(xz.mul(1.3).add(vec2(T.mul(0.3), T.mul(0.5))), 0.0)),
      mx_noise_float(vec3(xz.mul(1.3).add(vec2(5.2, T.mul(-0.4))), 1.0)),
    ).mul(0.12).mul(fade);
    const far = smoothstep(150.0, 600.0, dist);
    const N = normalize(vec3(dx.negate().add(rip.x), 1.0, dz.negate().add(rip.y)).mul(vec3(float(1).sub(far.mul(0.7)), 1.0, float(1).sub(far.mul(0.7)))));
    const V = normalize(cameraPosition.sub(wp));
    const NdV = max(dot(N, V), 0.0);
    const fres = float(0.02).add(pow(float(1).sub(NdV), 5.0).mul(0.98));
    const R = reflect(V.negate(), N);
    const refl = skyColor(normalize(vec3(R.x, max(R.y, 0.02), R.z))).mul(U.waterRefl);
    // Body: shallow over the sand, deep further out.
    const depth = max(float(SHORE.seaY).sub(beachH(xz.x, xz.y)), 0.0);
    const deepK = smoothstep(0.0, 3.0, depth).mul(0.7).add(smoothstep(-160.0, -400.0, xz.y).mul(0.3));
    const body = mix(U.waterShallow, U.waterDeep, clamp(deepK, 0.0, 1.0));
    const col = mix(body, refl, clamp(fres.mul(1.1), 0.0, 0.85)).toVar();
    // Glitter path toward the sun / moon.
    const Hh = normalize(V.add(U.glintDir));
    const nh = max(dot(N, Hh), 0.0);
    const spread = U.glintShape.x;
    const glit = pow(nh, float(1).div(spread.mul(spread)).mul(0.9)).mul(U.glint);
    const sparkle = smoothstep(0.55, 0.95, mx_noise_float(vec3(xz.mul(3.0), T.mul(1.6))).mul(0.5).add(0.5)).mul(fade.mul(0.6).add(0.4));
    col.addAssign(U.glintCol.mul(glit.mul(sparkle.mul(3.0).add(0.4))).mul(1.6));
    col.addAssign(U.glintCol.mul(pow(nh, 30.0)).mul(U.glintShape.y).mul(U.glint));
    // Fireworks light the water: a soft reflected bloom toward the burst.
    const toF = normalize(U.flashPos.sub(wp));
    const fl = pow(max(dot(R, toF), 0.0), 12.0).mul(1.4).add(pow(max(dot(R, toF), 0.0), 2.0).mul(0.15));
    col.addAssign(U.flashCol.mul(fl));
    // Foam: the swash line running up and back, and lace behind it.
    const swash = sin(T.mul(0.55)).mul(0.5).add(0.5);
    const edge = depth.sub(swash.mul(0.08));
    const lace = smoothstep(0.35, 0.75, mx_noise_float(vec3(xz.mul(vec2(1.6, 3.2)), T.mul(0.25))).mul(0.5).add(0.5));
    const foamLine = float(1).sub(smoothstep(0.0, 0.06, edge));
    const foamBand = float(1).sub(smoothstep(0.03, 0.35, edge)).mul(lace);
    const foam = clamp(foamLine.add(foamBand.mul(0.8)), 0.0, 1.0);
    const foamCol = mix(U.sunColor.mul(0.5).add(U.mid.mul(0.35)), vec3(0.95, 0.94, 0.9), 0.5).mul(U.worldTint.mul(0.6).add(0.45));
    col.assign(mix(col, foamCol, foam.mul(0.85)));
    // Haze toward the horizon (same sky).
    const dir = normalize(wp.sub(cameraPosition));
    col.assign(mix(col, skyColor(normalize(vec3(dir.x, 0.02, dir.z))), smoothstep(200.0, 1300.0, dist).mul(0.85)));
    // Alpha: clear right at the edge of the swash.
    const a = smoothstep(-0.02, 0.05, edge.add(0.08));
    return vec4(col, a);
  })();
  const mesh = new THREE.Mesh(g, m);
  mesh.frustumCulled = false;
  mesh.name = "sea";
  mesh.renderOrder = 1;
  return mesh;
}

export { abs, min, exp, fract, fwidth, vec4 };
