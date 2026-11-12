import { Game } from "./game/game";
import { Play } from "./game/play";

const title = document.getElementById("title")!;
const bar = title.querySelector(".bar i") as HTMLElement;
const setBar = (k: number) => { bar.style.transform = `scaleX(${k})`; };

async function boot() {
  setBar(0.08);
  const game = new Game();
  (window as any).__game = game;
  game.onProgress = setBar;
  await game.init();
  const play = new Play(game);
  await play.init();
  setBar(1);
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
