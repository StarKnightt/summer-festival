// Screenshot(s) of the game. Usage:
//   node scripts/shoot.mjs [--dist] [--q "tod=night&spawn=2"] [--out shots/x.png] [--wait 4000] [--js "expr"]
import { openGame, waitReady } from "./lib/harness.mjs";
import fs from "node:fs";
import path from "node:path";

const arg = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
const q = arg("--q", "");
const out = arg("--out", "shots/shot.png");
const wait = +arg("--wait", "3000");
const js = arg("--js", "");

const { page, url, errors, bye } = await openGame({ dist: process.argv.includes("--dist") });
await page.goto(url + (q ? "?" + q : ""));
try {
  await waitReady(page);
  if (js) console.log("[js]", JSON.stringify(await page.evaluate(js)));
  await page.waitForTimeout(wait);
  fs.mkdirSync(path.dirname(out), { recursive: true });
  await page.screenshot({ path: out });
  console.log("[shot]", out);
} catch (e) {
  console.error(String(e));
}
const fatal = await page.evaluate(() => window.__fatal).catch(() => null);
if (fatal) console.error("[fatal]", fatal);
for (const e of errors.slice(0, 30)) console.log(e);
await bye(errors.some((e) => /pageerror/.test(e)) || fatal ? 1 : 0);
