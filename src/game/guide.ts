import * as THREE from "three/webgpu";
import type { Game } from "./game";
import type { Hud } from "../ui/hud";
import { toScreen } from "./mg/common";
import { noOutline } from "../render/townMats";
import { SHORE } from "../world/layout";

export interface GuideTarget { pos: THREE.Vector3; top: THREE.Vector3; label: string }

const N = 16;
const STEP = 0.55;

/**
 * A soft guide to the next unfinished thing. When the target is on screen (and not yet close) a
 * small pin hangs over it; when it isn't, an arrow sits at the edge of the screen toward it; and
 * a faint trail of warm dots drifts along the ground for the next few metres of the way there
 * (down the street, by the steps if the beach is in between). All of it fades out as she gets
 * close, where the stall's own marker takes over. G turns it off and on.
 */
export class Guide {
  on = true;
  private dots: THREE.InstancedMesh;
  private a = 0;
  private flow = 0;
  private m4 = new THREE.Matrix4();
  private col = new THREE.Color();
  /** Path dots visible right now (for the test bot). */
  shown = 0;

  constructor(private g: Game, private hud: Hud) {
    const geo = new THREE.CircleGeometry(0.1, 16).rotateX(-Math.PI / 2);
    const mat = new THREE.MeshBasicNodeMaterial({ color: "#ffffff", transparent: true, blending: THREE.AdditiveBlending, depthWrite: false });
    noOutline(mat);
    this.dots = new THREE.InstancedMesh(geo, mat, N);
    this.dots.frustumCulled = false;
    this.dots.renderOrder = 4;
    this.dots.name = "guide_path";
    for (let i = 0; i < N; i++) { this.dots.setMatrixAt(i, this.m4.makeScale(0, 0, 0)); this.dots.setColorAt(i, this.col.setRGB(0, 0, 0)); }
    g.scene.add(this.dots);
  }

  /** The way from her to the target as a polyline (the steps are the only way on or off the beach). */
  private route(from: THREE.Vector3, to: THREE.Vector3): THREE.Vector3[] {
    const pts = [from.clone()];
    const top = SHORE.promenadeZ1 + 0.6, bottom = SHORE.stepsZ1 - 0.6;
    const fromBeach = from.z < SHORE.promenadeZ1 - 0.4, toBeach = to.z < SHORE.promenadeZ1 - 0.4;
    if (fromBeach && !toBeach) pts.push(new THREE.Vector3(0, 0, Math.min(bottom, from.z + 0.01)), new THREE.Vector3(0, 0, top));
    else if (!fromBeach && toBeach) pts.push(new THREE.Vector3(0, 0, top), new THREE.Vector3(0, 0, bottom));
    const last = pts[pts.length - 1];
    // Along the middle of the street, turning in to the stall only over the last couple of metres.
    if (!toBeach && Math.abs(last.z - to.z) > 3) {
      const dir = Math.sign(last.z - to.z);
      const lane = THREE.MathUtils.clamp(last.x, -1.4, 1.4) * 0.5 + Math.sign(to.x) * 0.5;
      if (Math.abs(last.z - to.z) > 6) pts.push(new THREE.Vector3(lane, 0, last.z - dir * 3));
      pts.push(new THREE.Vector3(lane, 0, to.z + dir * 2.2));
    }
    pts.push(to.clone());
    return pts;
  }

  toggle(): boolean {
    this.on = !this.on;
    return this.on;
  }

  update(dt: number, target: GuideTarget | null, hide: boolean): void {
    const g = this.g, her = g.her.position;
    let want = 0, dist = 0;
    let pts: THREE.Vector3[] = [];
    if (target && this.on && !hide) {
      pts = this.route(her, target.pos);
      for (let i = 1; i < pts.length; i++) dist += Math.hypot(pts[i].x - pts[i - 1].x, pts[i].z - pts[i - 1].z);
      // Fades out over the last few metres.
      want = THREE.MathUtils.clamp((dist - 7) / 3, 0, 1);
    }
    this.a += (want - this.a) * Math.min(1, dt * 2.5);
    const a = this.a;
    this.flow = (this.flow + dt * 0.7) % STEP;
    // Ground trail: dots from just ahead of her feet, drifting toward the target.
    this.shown = 0;
    let seg = 1, segStart = 0;
    for (let i = 0; i < N; i++) {
      const s = 1.1 + i * STEP + this.flow;
      let k = 0;
      if (a > 0.01 && pts.length > 1 && s < dist - 0.6) {
        while (seg < pts.length - 1 && s > segStart + Math.hypot(pts[seg].x - pts[seg - 1].x, pts[seg].z - pts[seg - 1].z)) {
          segStart += Math.hypot(pts[seg].x - pts[seg - 1].x, pts[seg].z - pts[seg - 1].z);
          seg++;
        }
        const len = Math.hypot(pts[seg].x - pts[seg - 1].x, pts[seg].z - pts[seg - 1].z) || 1;
        const u = Math.min(1, (s - segStart) / len);
        const x = pts[seg - 1].x + (pts[seg].x - pts[seg - 1].x) * u, z = pts[seg - 1].z + (pts[seg].z - pts[seg - 1].z) * u;
        // Bright near her, fading with distance; the first dot eases in as it appears.
        const along = (s - 1.1) / (N * STEP);
        k = a * 1.5 * Math.min(1, (s - 1.1) / 0.5) * (1 - along) * (1 - along * 0.3);
        this.m4.makeScale(1 - along * 0.35, 1, 1 - along * 0.35).setPosition(x, g.town.groundY(x, z) + 0.035, z);
        this.dots.setMatrixAt(i, this.m4);
        if (k > 0.02) this.shown++;
      } else this.dots.setMatrixAt(i, this.m4.makeScale(0, 0, 0));
      this.dots.setColorAt(i, this.col.setRGB(1.0 * k, 0.74 * k, 0.42 * k));
    }
    this.dots.instanceMatrix.needsUpdate = true;
    if (this.dots.instanceColor) this.dots.instanceColor.needsUpdate = true;
    this.dots.visible = a > 0.01;

    // Pin over the target when it's in view, an arrow at the screen edge when it isn't.
    if (!target || a < 0.02) { this.hud.pin(null); this.hud.arrow(null); return; }
    const sc = toScreen(g, target.top);
    const m = 70;
    const inView = !sc.behind && sc.x > m && sc.x < innerWidth - m && sc.y > m && sc.y < innerHeight - m;
    const straight = Math.hypot(target.pos.x - her.x, target.pos.z - her.z);
    if (inView) {
      this.hud.pin({ x: sc.x, y: sc.y, a, text: `${target.label} · ${Math.round(straight)} m` });
      this.hud.arrow(null);
    } else {
      // Direction from the middle of the screen; a point behind the camera projects mirrored.
      let dx = sc.x - innerWidth / 2, dy = sc.y - innerHeight / 2;
      if (sc.behind) { dx = -dx; dy = Math.abs(dy) + innerHeight; }
      const ang = Math.atan2(dy, dx);
      const rx = innerWidth / 2 - m, ry = innerHeight / 2 - m;
      const t = 1 / Math.max(Math.abs(Math.cos(ang)) / rx, Math.abs(Math.sin(ang)) / ry);
      this.hud.pin(null);
      this.hud.arrow({ x: innerWidth / 2 + Math.cos(ang) * t, y: innerHeight / 2 + Math.sin(ang) * t, ang, a, text: target.label });
    }
  }
}
