import type { TaskId } from "../world/layout";

/** Saved progress: checkpoints, tasks, cats, achievements. Stored locally in the browser. */
export interface SaveData {
  v: 1;
  checkpoint: number;
  tasks: TaskId[];
  cats: string[];
  ach: string[];
  petted: boolean;
  fireworks: boolean;
  mask: number;
}

const KEY = "summer-festival/save/v1";

export const ACHIEVEMENTS = [
  { id: "tasks", title: "Festival Spirit", desc: "Finish all five festival tasks", icon: "🏮" },
  { id: "cats", title: "Cat Spotter", desc: "Find the three hidden cats", icon: "🐾" },
  { id: "fireworks", title: "Hanabi", desc: "Watch the fireworks over the sea", icon: "🎆" },
  { id: "pet", title: "Gentle Hands", desc: "Pet the sleeping cat", icon: "💤" },
] as const;
export type AchId = (typeof ACHIEVEMENTS)[number]["id"];

export class Progress {
  data: SaveData;
  private listeners: (() => void)[] = [];
  readonly fresh: boolean;

  constructor(private persist = true) {
    let d: SaveData | null = null;
    if (persist) {
      try { d = JSON.parse(localStorage.getItem(KEY) || "null"); } catch {}
    }
    this.fresh = !d || d.v !== 1;
    this.data = d && d.v === 1 ? d : Progress.empty();
  }

  static empty(): SaveData {
    return { v: 1, checkpoint: 0, tasks: [], cats: [], ach: [], petted: false, fireworks: false, mask: -1 };
  }

  onChange(fn: () => void): void { this.listeners.push(fn); }

  save(): void {
    if (this.persist) {
      try { localStorage.setItem(KEY, JSON.stringify(this.data)); } catch {}
    }
    for (const f of this.listeners) f();
  }

  reset(): void {
    this.data = Progress.empty();
    this.save();
  }

  has(t: TaskId): boolean { return this.data.tasks.includes(t); }
  get taskCount(): number { return this.data.tasks.length; }
  hasAch(a: AchId): boolean { return this.data.ach.includes(a); }
}
