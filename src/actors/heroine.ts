import { Locomotion, Layers, LookIK, ccd, type ClipInfo } from "./animsys";
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

/** Natural head range on top of the clip: ~70° either side, less up and down. */
const HEAD_YAW = 1.22;
const HEAD_UP = 0.45;
const HEAD_DOWN = 0.4;
/** Poses held by weight over the locomotion layer. */
const POSES = ["crouch", "reach", "lookup"] as const;
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
  /**
   * Bones that get procedural offsets on top of the clips (head and neck look, spring chains),
   * with their pure animated pose from the last frame. The mixer skips writing a bone whose
   * blended value hasn't changed (static poses, or bones with no track), so without restoring
   * this first the offsets would stack up frame after frame: the head spun round or sank into
   * the body after a held pose.
   */
  /** Head bone's rest (bind) transform in her root frame: head-worn items are placed against it. */
  private headRest: THREE.Matrix4 | null = null;
  private procBones: { bone: THREE.Bone; q: THREE.Quaternion; p: THREE.Vector3; s: THREE.Vector3 }[] = [];
  private placeholder: THREE.Group | null = null;

  position = new THREE.Vector3();
  heading = Math.PI; // facing −Z
  speed = 0;
  pose: Pose = "none";
  private poseW = 0;
  private loco: Locomotion | null = null;
  private layers: Layers | null = null;
  private lookIK: LookIK | null = null;
  private lookW = 0;
  private glanceT = 2;
  private glance = 0;
  /** A point her right hand reaches for (IK over the reach pose); null lets the arm be. */
  reachTarget: THREE.Vector3 | null = null;
  private reachW = 0;
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
  /** Body turn (rad) she wants this frame to look at something beyond her neck's range; the player applies it. */
  bodyTurn = 0;
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
    this.root.updateMatrixWorld(true);
    const hb = this.bones.get("head");
    if (hb) this.headRest = this.root.matrixWorld.clone().invert().multiply(hb.matrixWorld);
    const clips: THREE.AnimationClip[] = (scene as any).userData.animations ?? [];
    this.mixer = new THREE.AnimationMixer(scene);
    // Base clips; the additive ones (add_*) become layers below.
    for (const c of clips) if (!c.name.startsWith("add_")) this.actions.set(c.name, this.mixer.clipAction(c));
    const info: Record<string, ClipInfo> = (scene.userData?.clips as any) ?? {};
    this.loco = new Locomotion(this.actions, info);
    this.layers = new Layers(this.mixer, clips, (scene.userData?.additiveReference as string) ?? "add_ref");
    for (const n of POSES) {
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
    const proc = new Set<THREE.Bone>();
    for (const n of ["head", "neck"]) { const b = this.bones.get(n); if (b) proc.add(b); }
    for (const b of this.springs.bones) proc.add(b);
    for (const n of ["spine2", "upperarm_R", "forearm_R"]) { const b = this.bones.get(n); if (b) proc.add(b); }
    this.lookIK = new LookIK(this.bones, this.headRest);
    this.procBones = [...proc].map((bone) => ({ bone, q: bone.quaternion.clone(), p: bone.position.clone(), s: bone.scale.clone() }));
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
    if (part === "head" && b && this.headRest) {
      // Against the rest pose, not wherever the head happens to be turned right now: a mask put on
      // while she glanced sideways used to end up over her face.
      const restPos = new THREE.Vector3().setFromMatrixPosition(this.headRest);
      const m = new THREE.Matrix4().compose(restPos.add(offset), new THREE.Quaternion().setFromEuler(rot), new THREE.Vector3(1, 1, 1));
      m.premultiply(this.headRest.clone().invert());
      m.decompose(obj.position, obj.quaternion, obj.scale);
      b.add(obj);
      return;
    }
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

  has(name: string): boolean { return this.actions.has(name); }

  /** Plays a clip once over the base pose (throw, wave, bow, eat, cheer, ...); returns its length. */
  play(name: string): number {
    const a = this.actions.get(name);
    if (!a) return 0.8;
    a.setLoop(THREE.LoopOnce, 1);
    a.clampWhenFinished = true;
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
    // Layers by weight: a held pose and a one-shot both take from the locomotion layer.
    const s = this.speed;
    this.poseW = damp(this.poseW, this.pose === "none" ? 0 : 1, 5, dt);
    const shot = this.oneShot && this.oneShot.isRunning() ? Math.min(1, this.oneShot.getEffectiveWeight()) : 0;
    if (this.oneShot && !this.oneShot.isRunning()) { this.oneShot.fadeOut(0.3); this.oneShot = null; }
    this.loco?.update(dt, s, (1 - this.poseW) * (1 - shot));
    for (const p of POSES) this.actions.get(p)?.setEffectiveWeight(this.pose === p ? this.poseW * (1 - shot) : 0);
    // Additive glances to either side while she strolls or stands (not while looking at
    // something, running, or busy).
    let side = 0;
    if (!this.lookTarget && this.pose === "none" && shot < 0.1 && s < (this.loco?.vWalk ?? 1) * 1.3) {
      this.glanceT -= dt;
      if (this.glanceT <= 0) {
        this.glanceT = 2.2 + Math.random() * 3.6;
        this.glance = Math.random() < 0.4 ? 0 : (Math.random() < 0.5 ? -1 : 1) * (0.35 + Math.random() * 0.4);
      }
      side = this.glance;
    } else this.glanceT = 0.8;
    this.layers?.look(dt, side);
    for (const b of this.procBones) { b.bone.quaternion.copy(b.q); b.bone.position.copy(b.p); b.bone.scale.copy(b.s); }
    this.mixer.update(dt);
    for (const b of this.procBones) { b.q.copy(b.bone.quaternion); b.p.copy(b.bone.position); b.s.copy(b.bone.scale); }
    this.root.updateMatrixWorld(true);

    this.updateLook(dt);
    this.updateFace(dt);
    this.springs?.update(dt, wind, windK);
  }

  /** A small nod or head shake on top of whatever she's doing. */
  nod(): void { this.layers?.once("nod"); }
  shake(): void { this.layers?.once("shake"); }

  /** Where her face points right now, in world space. */
  faceDir(): THREE.Vector3 { return this.lookIK?.forward() ?? new THREE.Vector3(Math.sin(this.heading), 0, Math.cos(this.heading)); }

  /** The head's facing relative to her body right now (radians; for tests). */
  get headYaw(): number { return this.lookIK?.yawNow(this.heading) ?? 0; }

  private updateLook(dt: number) {
    const head = this.bones.get("head");
    if (!head) return;
    let yaw = 0, pitch = 0, want = 0;
    this.bodyTurn = 0;
    if (this.lookTarget) {
      const hp = head.getWorldPosition(new THREE.Vector3());
      const d = this.lookTarget.clone().sub(hp);
      const local = Math.atan2(d.x, d.z) - this.heading;
      yaw = Math.atan2(Math.sin(local), Math.cos(local));
      pitch = Math.atan2(d.y, Math.hypot(d.x, d.z));
      want = 1;
      // Further round than a neck turns: she turns her body (when standing), never her head past it.
      if (Math.abs(yaw) > HEAD_YAW && this.speed < 0.2 && this.pose === "none") {
        this.bodyTurn = yaw - Math.sign(yaw) * HEAD_YAW * 0.8;
      }
      // Behind her: she doesn't try.
      if (Math.abs(yaw) > 2.4) { yaw = 0; pitch = 0; want = 0; }
    }
    yaw = THREE.MathUtils.clamp(yaw, -HEAD_YAW, HEAD_YAW);
    pitch = THREE.MathUtils.clamp(pitch, -HEAD_DOWN, HEAD_UP);
    this.lookYaw = damp(this.lookYaw, yaw, 3.2, dt);
    this.lookPitch = damp(this.lookPitch, pitch, 3.2, dt);
    this.lookW = damp(this.lookW, want, 3, dt);
    // IK down the upper spine, neck and head, each held to its own limit from the clip's pose.
    this.lookIK?.solve(this.heading, this.lookYaw, this.lookPitch, this.lookW);
    // Right hand to a point (CCD over upper arm and forearm), on top of the reach pose.
    this.reachW = damp(this.reachW, this.reachTarget ? 1 : 0, 5, dt);
    const ua = this.bones.get("upperarm_R"), fa = this.bones.get("forearm_R"), hand = this.bones.get("hand_R");
    if (this.reachTarget && ua && fa && hand) this.reachGoal.copy(this.reachTarget);
    if (this.reachW > 0.01 && ua && fa && hand) ccd([fa, ua], hand, this.reachGoal, [1.9, 1.5], this.reachW, 8);
  }
  private reachGoal = new THREE.Vector3();

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

  /** Back to plain idle/walk after a task: no held pose, one-shots faded out, head looking ahead. */
  resetPose(): void {
    this.pose = "none";
    this.lookTarget = null;
    this.reachTarget = null;
    this.bodyTurn = 0;
    this.smile = 0;
    this.root.visible = true;
    if (this.oneShot) { this.oneShot.fadeOut(0.3); this.oneShot = null; }
    for (const [n, a] of this.actions) {
      if (n === "idle" || n === "walk" || n === "run" || (POSES as readonly string[]).includes(n)) continue;
      if (!a.isRunning()) { a.stop(); a.setEffectiveWeight(0); }
    }
  }
}
