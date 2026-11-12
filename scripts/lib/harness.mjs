// Shared capture harness: a Vite server (dev or preview of dist/) + headless Chrome on the
// discrete GPU. Every exit path tears both down (see the user's background-process rule), and
// the GPU is asserted, never inferred from flags.
import { createServer, preview } from "vite";
import { chromium } from "playwright";
import os from "node:os";

export async function openGame({ dist = false, width = 1920, height = 1080, allowSoftware = process.argv.includes("--allow-software"), extraArgs = [] } = {}) {
  // Long CPU-side work stays polite: below-normal priority for this node process.
  try { os.setPriority(process.pid, 10); } catch {}
  let server, browser;
  const bye = async (code, why) => {
    if (why) console.error("[teardown]", why);
    try { await browser?.close(); } catch {}
    try { await server?.close?.(); } catch {}
    try { server?.httpServer?.close?.(); } catch {}
    process.exit(code);
  };
  process.on("SIGINT", () => bye(130, "interrupted"));
  process.on("SIGTERM", () => bye(143, "terminated"));
  process.on("uncaughtException", (e) => bye(1, e));
  process.on("unhandledRejection", (e) => bye(1, e));

  let url;
  if (dist) {
    server = await preview({ preview: { port: 0, strictPort: false, open: false }, logLevel: "error" });
    url = server.resolvedUrls.local[0];
  } else {
    server = await createServer({ server: { port: 0, strictPort: false, open: false, hmr: false }, logLevel: "error" });
    await server.listen();
    url = server.resolvedUrls.local[0];
  }

  browser = await chromium.launch({
    channel: "chrome",
    headless: true,
    args: [
      "--use-angle=d3d11",
      "--use-gl=angle",
      "--enable-gpu",
      "--enable-gpu-rasterization",
      "--ignore-gpu-blocklist",
      "--force_high_performance_gpu",
      "--enable-unsafe-webgpu",
      "--disable-background-timer-throttling",
      "--disable-renderer-backgrounding",
      "--disable-backgrounding-occluded-windows",
      ...extraArgs,
    ],
  });
  const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 1 });
  const errors = [];
  page.on("console", (m) => {
    const t = m.text();
    if (m.type() === "error" || /error|warn/i.test(m.type())) errors.push(`[${m.type()}] ${t}`);
    if (/^\[(gpu|game|perf)\]/.test(t)) console.log(t);
  });
  page.on("pageerror", (e) => errors.push(`[pageerror] ${e.message}`));

  // Assert the GPU before trusting anything this page renders.
  await page.goto(url + "gpu-probe.html").catch(() => {});
  const probe = await page.evaluate(async () => {
    const gl = document.createElement("canvas").getContext("webgl2");
    const dbg = gl?.getExtension("WEBGL_debug_renderer_info");
    const renderer = dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : "unknown";
    let gpu = null;
    try {
      const a = await navigator.gpu?.requestAdapter({ powerPreference: "high-performance" });
      if (a) gpu = { vendor: a.info?.vendor, arch: a.info?.architecture, desc: a.info?.description, fallback: a.info?.isFallbackAdapter ?? false };
    } catch {}
    return { renderer, gpu };
  });
  console.log("[gpu] webgl:", probe.renderer, "| webgpu:", JSON.stringify(probe.gpu));
  const soft = /swiftshader|llvmpipe|software|basic render/i;
  if (!allowSoftware && (soft.test(probe.renderer) || !probe.gpu || probe.gpu.fallback || !/nvidia/i.test(`${probe.gpu?.vendor} ${probe.renderer}`))) {
    await bye(2, `not on the discrete GPU: ${probe.renderer} / ${JSON.stringify(probe.gpu)}`);
  }
  return { page, url, errors, bye, browser };
}

export async function waitReady(page, timeout = 120000) {
  await page.waitForFunction(() => window.__ready === true || window.__fatal, null, { timeout });
  const fatal = await page.evaluate(() => window.__fatal);
  if (fatal) throw new Error("game failed: " + fatal);
}
