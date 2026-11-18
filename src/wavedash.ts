// Wavedash platform hooks. Every call is a no-op when window.Wavedash is absent (GitHub Pages,
// local dev), so the same build runs everywhere.
//
// Wavedash.init() is what reveals the game from behind Wavedash's loading screen: without it the
// page sits at "Still Loading 0%" forever. The platform defines Wavedash before our code runs,
// but if it ever shows up late, keep looking for a while instead of silently skipping init.

type WavedashSdk = {
  init(config?: object): boolean;
  updateLoadProgressZeroToOne(progress: number): void;
};

const sdk = (): WavedashSdk | undefined => (window as unknown as { Wavedash?: WavedashSdk }).Wavedash;

let initialized = false;

export const wavedash = {
  progress(p: number): void {
    if (initialized) return;
    try {
      sdk()?.updateLoadProgressZeroToOne(Math.min(1, Math.max(0, p)));
    } catch {}
  },

  ready(tries = 0): void {
    if (initialized) return;
    const s = sdk();
    if (!s) {
      if (tries < 100) setTimeout(() => wavedash.ready(tries + 1), 100);
      return;
    }
    initialized = true;
    try {
      s.updateLoadProgressZeroToOne(1);
      s.init({ debug: false });
    } catch {}
  },
};
