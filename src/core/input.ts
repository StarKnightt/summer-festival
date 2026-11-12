/**
 * Keyboard + mouse state. A click on the canvas locks the pointer, and the mouse then looks
 * around freely until Esc releases it; dragging still orbits when unlocked. Mini-games take
 * the cursor back (captureMouse), which releases the lock. The wheel zooms a little.
 */
export class Input {
  readonly keys = new Set<string>();
  private pressed = new Set<string>();
  mouseX = 0;
  mouseY = 0;
  /** Normalised device coords of the pointer (−1…1). */
  ndcX = 0;
  ndcY = 0;
  dragX = 0;
  dragY = 0;
  wheel = 0;
  down = false;
  clicked = false;
  released = false;
  private dragging = false;
  private capture = false;
  /** True while a mini-game owns the mouse (no camera look; the pointer lock is released). */
  get captureMouse(): boolean { return this.capture; }
  set captureMouse(v: boolean) {
    this.capture = v;
    if (v && this.locked) document.exitPointerLock();
  }
  /** Off until play begins (the title card needs its cursor). */
  lockEnabled = false;
  get locked(): boolean { return document.pointerLockElement === this.el; }

  constructor(private el: HTMLElement) {
    addEventListener("keydown", (e) => {
      if ((e.target as HTMLElement)?.tagName === "INPUT") return;
      const k = e.code;
      if (!this.keys.has(k)) this.pressed.add(k);
      this.keys.add(k);
      if (["Space", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(k)) e.preventDefault();
    });
    addEventListener("keyup", (e) => this.keys.delete(e.code));
    addEventListener("blur", () => this.keys.clear());
    el.addEventListener("pointerdown", (e) => {
      this.down = true;
      this.clicked = true;
      if (this.locked) return;
      this.dragging = !this.captureMouse;
      this.move(e);
      el.setPointerCapture(e.pointerId);
      if (!this.captureMouse && this.lockEnabled && e.button === 0) {
        try { (el.requestPointerLock() as any)?.catch?.(() => {}); } catch {}
      }
    });
    el.addEventListener("pointermove", (e) => {
      if (this.locked) {
        this.dragX += e.movementX;
        this.dragY += e.movementY;
        return;
      }
      if (this.dragging) {
        this.dragX += e.movementX;
        this.dragY += e.movementY;
      }
      this.move(e);
    });
    el.addEventListener("pointerup", (e) => {
      this.down = false;
      this.released = true;
      this.dragging = false;
      try { el.releasePointerCapture(e.pointerId); } catch {}
    });
    el.addEventListener("wheel", (e) => { this.wheel += Math.sign(e.deltaY); e.preventDefault(); }, { passive: false });
    el.addEventListener("contextmenu", (e) => e.preventDefault());
  }

  private move(e: PointerEvent) {
    this.mouseX = e.clientX;
    this.mouseY = e.clientY;
    const r = this.el.getBoundingClientRect();
    this.ndcX = ((e.clientX - r.left) / r.width) * 2 - 1;
    this.ndcY = -((e.clientY - r.top) / r.height) * 2 + 1;
  }

  /** Pressed this frame (edge). */
  hit(code: string): boolean {
    return this.pressed.has(code);
  }

  axis(): { x: number; y: number; run: boolean } {
    const k = this.keys;
    const x = (k.has("KeyD") || k.has("ArrowRight") ? 1 : 0) - (k.has("KeyA") || k.has("ArrowLeft") ? 1 : 0);
    const y = (k.has("KeyW") || k.has("ArrowUp") ? 1 : 0) - (k.has("KeyS") || k.has("ArrowDown") ? 1 : 0);
    return { x, y, run: k.has("ShiftLeft") || k.has("ShiftRight") };
  }

  /** Call at the end of each frame. */
  endFrame(): void {
    this.pressed.clear();
    this.dragX = this.dragY = 0;
    this.wheel = 0;
    this.clicked = false;
    this.released = false;
  }
}
