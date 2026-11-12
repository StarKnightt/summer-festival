import * as THREE from "three/webgpu";
import { Game } from "./game/game";
import { Play } from "./game/play";

import { preload } from "./core/preload";

const title = document.getElementById("title")!;
const bar = title.querySelector(".bar i") as HTMLElement;
const pct = title.querySelector(".pct") as HTMLElement;

// Loader: nine paper lanterns on a cord; each one lights up as the loading passes it.
const N = 9;
const lanterns: SVGGElement[] = [];
{
  const W = 1600, H = 300;
  const cord = (x: number) => 40 + 70 * Math.sin((x / W) * Math.PI);
  const pts = Array.from({ length: 33 }, (_, i) => { const x = (i / 32) * (W + 40) - 20; return `L${x.toFixed(0)} ${cord(x).toFixed(1)}`; }).join(" ");
  let svg = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMin slice" aria-hidden="true"><defs>`
    + `<radialGradient id="lnLit" cx="50%" cy="45%" r="60%"><stop offset="0" stop-color="#fff3d2"/><stop offset="0.55" stop-color="#ffbf6e"/><stop offset="1" stop-color="#e2733e"/></radialGradient>`
    + `<radialGradient id="lnGlow"><stop offset="0" stop-color="rgba(255,190,110,0.55)"/><stop offset="1" stop-color="rgba(255,170,90,0)"/></radialGradient></defs>`
    + `<path d="M-20 ${cord(-20).toFixed(1)} ${pts}" stroke="rgba(30,18,30,0.7)" stroke-width="2" fill="none"/>`;
  for (let i = 0; i < N; i++) {
    const x = ((i + 0.5) / N) * W, y = cord(x);
    const r = 26 + (i % 2) * 4, h = r * 1.5, cy = y + 21 + h / 2;
    svg += `<g class="ln" style="animation-delay:${(-i * 0.73).toFixed(2)}s">`
      + `<line x1="${x}" y1="${y}" x2="${x}" y2="${y + 16}" stroke="rgba(30,18,30,0.7)" stroke-width="1.5"/>`
      + `<circle class="glow" cx="${x}" cy="${cy}" r="${r * 2.6}" fill="url(#lnGlow)"/>`
      + `<rect class="cap" x="${x - r * 0.5}" y="${y + 14}" width="${r}" height="7" rx="2"/>`
      + `<ellipse class="paper" cx="${x}" cy="${cy}" rx="${r}" ry="${h / 2}"/>`
      + [0.3, 0.55, 0.78].map((k) => `<ellipse class="rib" cx="${x}" cy="${cy}" rx="${r * k}" ry="${h / 2}"/>`).join("")
      + `<rect class="cap" x="${x - r * 0.5}" y="${y + 19 + h}" width="${r}" height="7" rx="2"/>`
      + `<line x1="${x}" y1="${y + 26 + h}" x2="${x}" y2="${y + 44 + h}" stroke="rgba(200,60,50,0.8)" stroke-width="2"/></g>`;
  }
  const host = title.querySelector(".lanterns")!;
  host.innerHTML = svg + "</svg>";
  lanterns.push(...host.querySelectorAll<SVGGElement>(".ln"));
  const burst = title.querySelector(".burst")!;
  for (let i = 0; i < 24; i++) {
    const e = document.createElement("i");
    e.style.setProperty("--a", `${(i / 24) * 360}deg`);
    burst.append(e);
  }
}

// Progress: 70 % the model bytes as they arrive, 30 % the setup stages after them.
let bytesK = 0, stageK = 0, shown = 0;
const setBar = () => {
  const k = Math.max(shown, Math.min(1, bytesK * 0.7 + stageK * 0.3));
  shown = k;
  bar.style.transform = `scaleX(${k})`;
  pct.textContent = k >= 1 ? "ready" : `loading the festival · ${Math.floor(k * 100)}%`;
  const lit = Math.floor(k * N + 0.15);
  lanterns.forEach((l, i) => l.classList.toggle("lit", i < lit));
  title.querySelector(".burst")!.classList.toggle("on", k >= 1);
};
const base = import.meta.env.BASE_URL;
const models = preload(["heroine", "stalls", "people", "cats"].map((m) => `${base}models/${m}.glb`), (k) => { bytesK = k; setBar(); });

async function boot() {
  const game = new Game();
  (window as any).__game = game;
  (window as any).__THREE = { Raycaster: THREE.Raycaster };
  game.onProgress = (k) => { stageK = k; setBar(); };
  await models;
  await game.init();
  const play = new Play(game);
  await play.init();
  play.warmUp();
  bytesK = 1; stageK = 1; setBar();
  game.start();
  // The world renders behind the title card; it clears on the first click or key.
  title.classList.add("scene");
  setTimeout(() => title.classList.add("ready"), 400);
  const go = () => {
    if (!title.classList.contains("ready")) return;
    title.classList.add("gone");
    play.begin();
    removeEventListener("pointerdown", go);
    removeEventListener("keydown", go);
  };
  addEventListener("pointerdown", go);
  addEventListener("keydown", go);
  if (game.params.has("play")) { title.classList.add("ready"); go(); }
}

boot().catch((e) => {
  console.error(e);
  (window as any).__fatal = String(e?.stack ?? e);
  const f = document.createElement("div");
  f.className = "fatal";
  f.textContent = /webgpu|adapter/i.test(String(e)) ? "This festival needs a browser with WebGPU (recent Chrome or Edge)." : "Something went wrong loading the festival. Please reload.";
  document.body.append(f);
});
