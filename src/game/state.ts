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
  /** Replays and side activities: how many, or the best so far, by name. */
  counts: Record<string, number>;
  /** The player turned the guide off. */
  guideOff: boolean;
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
    this.data.counts ??= {};
    this.data.guideOff ??= false;
  }

  static empty(): SaveData {
    return { v: 1, checkpoint: 0, tasks: [], cats: [], ach: [], petted: false, fireworks: false, mask: -1, counts: {}, guideOff: false };
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
  count(k: string): number { return this.data.counts[k] ?? 0; }
  /** Adds one to a count and saves; returns the new value. */
  bump(k: string): number { const n = this.count(k) + 1; this.data.counts[k] = n; this.save(); return n; }
  /** Keeps the better of the stored value and `v` (`lower` = smaller is better). */
  best(k: string, v: number, lower = false): number {
    const cur = this.data.counts[k];
    const b = cur === undefined ? v : lower ? Math.min(cur, v) : Math.max(cur, v);
    this.data.counts[k] = b;
    this.save();
    return b;
  }
}
