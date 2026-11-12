import * as THREE from "three/webgpu";
import { loadGLB } from "../world/stalls";
import { toonify } from "../render/toonify";
import { ToonMaterial } from "../render/toon";
import { inkMask } from "../render/post";
import { Springs } from "./springs";

/**
 * Her: the Blender-built heroine in a yukata. Locomotion blends idle / walk / run by speed with
 * the clip rate matched to the ground speed (feet don't skate); poses (crouch, reach, look up)
 * and one-shots (throw, wave) layer over it with soft fades. On top of the clips: blinking,
 * a head that turns toward whatever is interesting nearby, and spring chains for sleeves, hair,
 * kanzashi and obi tails that lag her motion and sway in the wind. Never frozen.
 */
export type Pose = "none" | "crouch" | "reach" | "lookup";

const CLIP_SPEED: Record<string, number> = { walk: 1.1, run: 2.8 };
const damp = (a: number, b: number, k: number, dt: number) => b + (a - b) * Math.exp(-k * dt);

export class Heroine {
  readonly root = new THREE.Group();
  private model: THREE.Object3D | null = null;
  private mixer: THREE.AnimationMixer | null = null;
  private actions = new Map<string, THREE.AnimationAction>();
  private springs: Springs | null = null;
  private blinkMeshes: { mesh: THREE.Mesh; idx: number }[] = [];
  private smileMeshes: { mesh: THREE.Mesh; idx: number }[] = [];
  private bones = new Map<string, THREE.Bone>();
  private placeholder: THREE.Group | null = null;

  position = new THREE.Vector3();
  heading = Math.PI; // facing −Z
  speed = 0;
  pose: Pose = "none";
  private poseW = 0;
  private oneShot: THREE.AnimationAction | null = null;
  private blinkT = 2;
  private blinkK = 0;
  private doubleBlink = false;
  smile = 0;
  private smileCur = 0;
  /** World point she glances at (null = look ahead). */
  lookTarget: THREE.Vector3 | null = null;
  private lookYaw = 0;
  private lookPitch = 0;
  private idleLookT = 0;
  private idleLookYaw = 0;
  meta: any = {};

  async load(url: string): Promise<void> {
    const scene = await loadGLB(url);
    if (!scene) {
      this.makePlaceholder();
      return;
    }
    toonify(scene, { her: true });
    scene.traverse((o) => {
      const m = o as THREE.Mesh;
      if ((m as any).isSkinnedMesh) m.frustumCulled = false;
      if ((o as THREE.Bone).isBone) this.bones.set(o.name, o as THREE.Bone);
      if (m.isMesh && m.morphTargetDictionary) {
        const b = m.morphTargetDictionary["blink"];
        if (b !== undefined) this.blinkMeshes.push({ mesh: m, idx: b });
        const s = m.morphTargetDictionary["smile"];
        if (s !== undefined) this.smileMeshes.push({ mesh: m, idx: s });
      }
    });
    // glTF faces +Z; our heading 0 = +Z too.
    this.model = scene;
    this.root.add(scene);
    const clips: THREE.AnimationClip[] = (scene as any).userData.animations ?? [];
    this.mixer = new THREE.AnimationMixer(scene);
    for (const c of clips) {
      const a = this.mixer.clipAction(c);
      if (["throw", "wave"].includes(c.name)) {
        a.setLoop(THREE.LoopOnce, 1);
        a.clampWhenFinished = true;
      }
      this.actions.set(c.name, a);
    }
    for (const n of ["idle", "walk", "run"]) {
      const a = this.actions.get(n);
      if (a) { a.play(); a.setEffectiveWeight(n === "idle" ? 1 : 0); }
    }
    for (const n of ["crouch", "reach", "lookup"]) {
      const a = this.actions.get(n);
      if (a) { a.play(); a.setEffectiveWeight(0); }
    }
    const extras = scene.getObjectByProperty("type", "Bone")?.parent?.userData ?? {};
    this.meta = extras;
    this.springs = new Springs(scene, [
      { prefix: "sleeve_L", stiff: 40, gain: 1.1, wind: 0.8, limit: 0.6 },
      { prefix: "sleeve_R", stiff: 40, gain: 1.1, wind: 0.8, limit: 0.6 },
      { prefix: "hairSideL", stiff: 55, gain: 0.8, wind: 0.9 },
      { prefix: "hairSideR", stiff: 55, gain: 0.8, wind: 0.9 },
      { prefix: "hairBack", stiff: 45, gain: 0.9, wind: 1.0 },
      { prefix: "hairBun", stiff: 120, gain: 0.25, wind: 0.2, limit: 0.15 },
      { prefix: "kanzashi", stiff: 30, gain: 1.6, wind: 1.3, limit: 0.9 },
      { prefix: "obiTailL", stiff: 35, gain: 1.0, wind: 1.1 },
      { prefix: "obiTailR", stiff: 35, gain: 1.0, wind: 1.1 },
      { prefix: "skirtF", stiff: 80, gain: 0.4, wind: 0.4, limit: 0.25 },
      { prefix: "skirtB", stiff: 80, gain: 0.4, wind: 0.4, limit: 0.25 },
    ]);
    console.log(`[game] heroine: ${clips.length} clips (${clips.map((c) => c.name).join(", ")}), ${this.springs.count} spring bones, blink=${this.blinkMeshes.length > 0}`);
  }

  private makePlaceholder() {
    const g = new THREE.Group();
    const body = new THREE.Mesh(new THREE.CapsuleGeometry(0.2, 0.9, 6, 14), new ToonMaterial({ color: "#2f3f78" }));
    body.position.y = 0.7;
    const head = new THREE.Mesh(new THREE.SphereGeometry(0.14, 20, 14), new ToonMaterial({ color: "#f2cdb0", skin: true, soft: 0.08 }));
    head.position.y = 1.43;
    const hair = new THREE.Mesh(new THREE.SphereGeometry(0.15, 20, 14, 0, Math.PI * 2, 0, Math.PI * 0.6), new ToonMaterial({ color: "#4a2c22", hair: true }));
    hair.position.y = 1.45;
    for (const m of [body, head, hair]) { m.castShadow = true; inkMask(m.material as THREE.NodeMaterial, 0.5); }
    g.add(body, head, hair);
    this.placeholder = g;
    this.root.add(g);
  }

  bone(name: string): THREE.Bone | undefined { return this.bones.get(name); }

  /** Attaches an object to a bone (or the root if the bone is missing). */
  attach(boneName: string, obj: THREE.Object3D, offset = new THREE.Vector3(), rot = new THREE.Euler()): void {
    const b = this.bones.get(boneName);
    obj.position.copy(offset);
    obj.rotation.copy(rot);
    (b ?? this.root).add(obj);
    if (!b) obj.position.add(new THREE.Vector3(boneName.endsWith("_R") ? -0.25 : boneName === "head" ? 0.12 : 0.25, boneName === "head" ? 1.5 : 0.9, 0.1));
  }

  /** First bone whose name matches (e.g. /^(hand[._]?R|RightHand)$/i). */
  findBone(re: RegExp): THREE.Bone | undefined {
    for (const [n, b] of this.bones) if (re.test(n)) return b;
    return undefined;
  }

  /**
   * Holds an object on a body part. `offset` and `rot` are given in her own frame (+Z forward,
   * +Y up, +X her left) relative to the bone's current position, so they don't depend on how the
   * rig's bones are oriented. The object is then parented to the bone and follows it.
   */
  hold(part: "head" | "hand_R" | "hand_L", obj: THREE.Object3D, offset: THREE.Vector3, rot = new THREE.Euler()): void {
    const re = part === "head" ? /^(head|DEF[-_.]?head|mixamorig:?Head)$/i : part === "hand_R" ? /^(hand[._]?R|RightHand|mixamorig:?RightHand|DEF[-_.]?hand[._]R)$/i : /^(hand[._]?L|LeftHand|mixamorig:?LeftHand|DEF[-_.]?hand[._]L)$/i;
    const b = this.findBone(re);
    this.root.position.copy(this.position);
    this.root.rotation.y = this.heading;
    this.root.updateMatrixWorld(true);
    const base = b ? this.root.worldToLocal(b.getWorldPosition(new THREE.Vector3())) : new THREE.Vector3(part === "hand_R" ? -0.24 : part === "hand_L" ? 0.24 : 0, part === "head" ? 1.48 : 0.85, part === "head" ? 0 : 0.12);
    obj.position.copy(base).add(offset);
    obj.rotation.copy(rot);
    this.root.add(obj);
    obj.updateMatrixWorld(true);
    if (b) b.attach(obj);
  }

  setPose(p: Pose): void { this.pose = p; }

  play(name: "throw" | "wave"): number {
    const a = this.actions.get(name);
    if (!a) return 0.8;
    this.oneShot?.fadeOut(0.2);
    a.reset();
    a.setEffectiveWeight(1);
    a.fadeIn(0.18);
    a.play();
    this.oneShot = a;
    return a.getClip().duration;
  }

  update(dt: number, wind: THREE.Vector2, windK: number): void {
    this.root.position.copy(this.position);
    this.root.rotation.y = this.heading;
    if (!this.mixer) {
      // Placeholder breathes and bobs.
      if (this.placeholder) this.placeholder.position.y = Math.sin(performance.now() * 0.004) * 0.01 * (1 + this.speed);
      return;
    }
    // Locomotion weights.
    const s = this.speed;
    const wWalk = THREE.MathUtils.clamp(s / CLIP_SPEED.walk, 0, 1) * (1 - THREE.MathUtils.clamp((s - CLIP_SPEED.walk) / (CLIP_SPEED.run - CLIP_SPEED.walk), 0, 1));
    const wRun = THREE.MathUtils.clamp((s - CLIP_SPEED.walk) / (CLIP_SPEED.run - CLIP_SPEED.walk), 0, 1);
    const wIdle = 1 - THREE.MathUtils.clamp(s / 0.5, 0, 1);
    this.poseW = damp(this.poseW, this.pose === "none" ? 0 : 1, 5, dt);
    const shot = this.oneShot && this.oneShot.isRunning() ? Math.min(1, this.oneShot.getEffectiveWeight()) : 0;
    if (this.oneShot && !this.oneShot.isRunning()) { this.oneShot.fadeOut(0.3); this.oneShot = null; }
    const loco = (1 - this.poseW) * (1 - shot);
    const walk = this.actions.get("walk"), run = this.actions.get("run"), idle = this.actions.get("idle");
    const sum = Math.max(1e-3, wWalk + wRun + wIdle);
    idle?.setEffectiveWeight((wIdle / sum) * loco);
    walk?.setEffectiveWeight((wWalk / sum) * loco);
    run?.setEffectiveWeight((wRun / sum) * loco);
    // Match the stride to the ground speed (walk and run phase-locked).
    if (walk && run) {
      walk.timeScale = s > 0.05 ? THREE.MathUtils.clamp(s / CLIP_SPEED.walk, 0.6, 1.6) : 1;
      run.timeScale = s > 0.05 ? THREE.MathUtils.clamp(s / CLIP_SPEED.run, 0.6, 1.4) : 1;
    }
    for (const p of ["crouch", "reach", "lookup"] as const) this.actions.get(p)?.setEffectiveWeight(this.pose === p ? this.poseW * (1 - shot) : 0);
    this.mixer.update(dt);
    this.root.updateMatrixWorld(true);

    this.updateLook(dt);
    this.updateFace(dt);
    this.springs?.update(dt, wind, windK);
  }

  private updateLook(dt: number) {
    const head = this.bones.get("head"), neck = this.bones.get("neck");
    if (!head) return;
    let yaw = 0, pitch = 0;
    if (this.lookTarget) {
      const hp = head.getWorldPosition(new THREE.Vector3());
      const d = this.lookTarget.clone().sub(hp);
      const local = Math.atan2(d.x, d.z) - this.heading;
      yaw = Math.atan2(Math.sin(local), Math.cos(local));
      pitch = Math.atan2(d.y, Math.hypot(d.x, d.z));
      if (Math.abs(yaw) > 1.7) { yaw = 0; pitch = 0; }
    } else if (this.speed < 0.2 && this.pose === "none") {
      // Standing still: now and then she glances around.
      this.idleLookT -= dt;
      if (this.idleLookT <= 0) {
        this.idleLookT = 2.5 + Math.random() * 3.5;
        this.idleLookYaw = Math.random() < 0.35 ? 0 : (Math.random() * 2 - 1) * 0.5;
      }
      yaw = this.idleLookYaw;
    }
    yaw = THREE.MathUtils.clamp(yaw, -0.9, 0.9);
    pitch = THREE.MathUtils.clamp(pitch, -0.35, 0.5);
    this.lookYaw = damp(this.lookYaw, yaw, 3.2, dt);
    this.lookPitch = damp(this.lookPitch, pitch, 3.2, dt);
    // World-space turn about up, and a nod about her right axis, split over neck and head.
    const up = new THREE.Vector3(0, 1, 0);
    const right = new THREE.Vector3(Math.cos(this.heading), 0, -Math.sin(this.heading));
    for (const [b, k] of [[neck, 0.4], [head, 0.6]] as const) {
      if (!b) continue;
      const qw = b.getWorldQuaternion(new THREE.Quaternion());
      const q = new THREE.Quaternion().setFromAxisAngle(up, this.lookYaw * k).multiply(new THREE.Quaternion().setFromAxisAngle(right, -this.lookPitch * k));
      qw.premultiply(q);
      const qp = b.parent!.getWorldQuaternion(new THREE.Quaternion()).invert();
      b.quaternion.copy(qp.multiply(qw));
      b.updateMatrixWorld(true);
    }
  }

  private updateFace(dt: number) {
    this.blinkT -= dt;
    if (this.blinkT <= 0) {
      this.blinkK = 1;
      this.blinkT = this.doubleBlink ? 0.22 : 1.8 + Math.random() * 3.6;
      this.doubleBlink = !this.doubleBlink && Math.random() < 0.2;
    }
    this.blinkK = Math.max(0, this.blinkK - dt / 0.16);
    const b = Math.sin(this.blinkK * Math.PI);
    for (const { mesh, idx } of this.blinkMeshes) mesh.morphTargetInfluences![idx] = b;
    this.smileCur = damp(this.smileCur, this.smile, 3, dt);
    for (const { mesh, idx } of this.smileMeshes) mesh.morphTargetInfluences![idx] = this.smileCur;
  }

  resetSprings(): void { this.springs?.reset(); }
}
