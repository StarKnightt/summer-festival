import { TASKS, type TaskId } from "../world/layout";
import { ACHIEVEMENTS, type Progress } from "../game/state";
import { PRESETS, type Preset } from "../world/timeofday";

const el = <K extends keyof HTMLElementTagNameMap>(tag: K, cls = "", html = "") => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html) e.innerHTML = html;
  return e;
};

const TOD_ICON: Record<Preset, string> = { morning: "🌅", day: "☀", sunset: "🌇", night: "🌙" };

/**
 * The quiet HUD: a small checklist, a fading "task n/5", small achievement pops, an achievements
 * list behind a corner icon, time-of-day buttons, an interaction prompt, mini-game guidance and
 * keeper call-out bubbles. Everything fades; nothing pops or flashes.
 */
export class Hud {
  private tasks = el("div", "hud", "");
  private toast = el("div", "hud");
  private achpop = el("div", "hud");
  private corner = el("div", "hud");
  private achlist = el("div", "hud");
  private prompt = el("div", "hud");
  private mg = el("div", "hud");
  private note = el("div", "hud");
  private controls = el("div", "hud");
  private toastT = 0;
  private popQueue: string[] = [];
  private popT = -2;
  private noteT = 0;
  private bubbles = new Map<string, HTMLDivElement>();
  onTod: (p: Preset) => void = () => {};
  onReset: () => void = () => {};

  constructor(private prog: Progress) {
    this.tasks.id = "tasks";
    this.toast.id = "toast";
    this.achpop.id = "achpop";
    this.corner.id = "corner";
    this.achlist.id = "achlist";
    this.prompt.id = "prompt";
    this.mg.id = "mg";
    this.note.id = "note";
    this.controls.id = "controls";
    this.tasks.innerHTML = `<h3>Festival</h3><ul>${TASKS.map((t) => `<li data-t="${t.id}"><i class="box"></i><span>${t.label}</span></li>`).join("")}</ul><div class="finale">Fireworks soon, down at the shore…</div>`;
    this.mg.innerHTML = `<div class="line"></div><div class="meter"><i></i></div><div class="pips"></div>`;
    this.controls.innerHTML = `<span><b>WASD</b>walk</span><span><b>Shift</b>run</span><span><b>Drag</b>look</span><span><b>E</b>interact</span>`;
    for (const p of PRESETS) {
      const b = el("button", "", TOD_ICON[p]);
      b.title = p[0].toUpperCase() + p.slice(1);
      b.setAttribute("aria-label", `Time of day: ${p}`);
      b.dataset.p = p;
      b.addEventListener("click", (e) => { e.stopPropagation(); this.onTod(p); });
      this.corner.append(b);
    }
    this.corner.append(el("i", "sep"));
    const ab = el("button", "", "✦");
    ab.title = "Achievements";
    ab.setAttribute("aria-label", "Achievements");
    ab.addEventListener("click", (e) => { e.stopPropagation(); this.achlist.classList.toggle("on"); this.renderAch(); });
    this.corner.append(ab);
    for (const b of this.corner.querySelectorAll("button")) b.addEventListener("pointerdown", (e) => e.stopPropagation());
    this.achlist.addEventListener("pointerdown", (e) => e.stopPropagation());
    document.body.append(this.tasks, this.toast, this.achpop, this.corner, this.achlist, this.prompt, this.mg, this.note, this.controls);
    prog.onChange(() => this.renderTasks());
    this.renderTasks();
    this.renderAch();
  }

  show(): void {
    this.tasks.classList.add("on");
    this.corner.classList.add("on");
  }

  setTod(p: Preset): void {
    for (const b of this.corner.querySelectorAll<HTMLButtonElement>("button[data-p]")) b.classList.toggle("sel", b.dataset.p === p);
  }

  controlsHint(on: boolean): void { this.controls.classList.toggle("on", on); }

  renderTasks(): void {
    for (const li of this.tasks.querySelectorAll<HTMLLIElement>("li")) li.classList.toggle("done", this.prog.has(li.dataset.t as TaskId));
    this.tasks.classList.toggle("all", this.prog.taskCount >= 5 && !this.prog.data.fireworks);
  }

  renderAch(): void {
    this.achlist.innerHTML = `<h3>Achievements</h3>${ACHIEVEMENTS.map((a) => `<div class="a ${this.prog.hasAch(a.id) ? "got" : ""}"><span class="ic">${a.icon}</span><div><div class="t">${a.title}</div><div class="d">${a.desc}${a.id === "cats" ? ` (${this.prog.data.cats.length}/3)` : ""}</div></div></div>`).join("")}<button class="reset">start the festival over</button>`;
    this.achlist.querySelector(".reset")!.addEventListener("click", () => this.onReset());
  }

  taskDone(n: number): void {
    this.toast.innerHTML = `task ${n}/5<small>${n === 5 ? "all done" : "done"}</small>`;
    this.toast.classList.add("on");
    this.toastT = 2.8;
  }

  achievement(id: string): void {
    this.popQueue.push(id);
  }

  setPrompt(text: string | null): void {
    if (text) this.prompt.innerHTML = `<b>E</b>${text}`;
    this.prompt.classList.toggle("on", !!text);
  }

  /** Mini-game guidance line, optional meter (0..1) and pips text. */
  setGuide(text: string | null, meter: number | null = null, pips = ""): void {
    this.mg.classList.toggle("on", !!text);
    if (text) (this.mg.querySelector(".line") as HTMLElement).innerHTML = text;
    const m = this.mg.querySelector(".meter") as HTMLElement;
    m.classList.toggle("on", meter !== null);
    if (meter !== null) (m.firstElementChild as HTMLElement).style.width = `${Math.round(meter * 100)}%`;
    (this.mg.querySelector(".pips") as HTMLElement).textContent = pips;
  }

  say(text: string, secs = 4): void {
    this.note.textContent = text;
    this.note.classList.add("on");
    this.noteT = secs;
  }

  /** A call-out bubble at a screen position (null hides it). */
  bubble(key: string, text: string, x: number | null, y = 0): void {
    let b = this.bubbles.get(key);
    if (!b) {
      b = el("div", "bubble hud") as HTMLDivElement;
      document.body.append(b);
      this.bubbles.set(key, b);
    }
    if (x === null) { b.classList.remove("on"); return; }
    if (b.textContent !== text) b.textContent = text;
    b.style.left = `${x}px`;
    b.style.top = `${y}px`;
    b.classList.add("on");
  }

  update(dt: number): void {
    if (this.toastT > 0 && (this.toastT -= dt) <= 0) this.toast.classList.remove("on");
    if (this.noteT > 0 && (this.noteT -= dt) <= 0) this.note.classList.remove("on");
    // A pop shows for 4.2 s, then 1.2 s of quiet before the next one.
    if (this.popT > -1.2) {
      this.popT -= dt;
      if (this.popT <= 0) this.achpop.classList.remove("on");
    } else if (this.popQueue.length) {
      const id = this.popQueue.shift()!;
      const a = ACHIEVEMENTS.find((x) => x.id === id)!;
      this.achpop.innerHTML = `<span class="ic">${a.icon}</span><div><div class="k">achievement</div><div class="t">${a.title}</div></div>`;
      this.achpop.classList.add("on");
      this.popT = 4.2;
      this.renderAch();
    }
  }
}
