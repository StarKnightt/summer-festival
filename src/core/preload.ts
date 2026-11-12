/**
 * Fetches the model files up front, streaming, so the loader can show real progress (bytes
 * received of bytes total). loadGLB() picks the buffers up from here instead of fetching again.
 */
const buffers = new Map<string, Promise<ArrayBuffer>>();

export function preloaded(url: string): Promise<ArrayBuffer> | undefined {
  return buffers.get(url);
}

/** Starts fetching every url; `onProgress` gets 0…1 over all of them as bytes arrive. */
export function preload(urls: string[], onProgress: (k: number) => void): Promise<void> {
  const got = new Map<string, number>();
  const size = new Map<string, number>();
  // A guess per file until its Content-Length is known, so the bar doesn't jump.
  const GUESS = 2_500_000;
  const report = () => {
    let a = 0, b = 0;
    for (const u of urls) { const s = size.get(u) ?? GUESS; b += s; a += Math.min(s, got.get(u) ?? 0); }
    onProgress(b > 0 ? a / b : 1);
  };
  const one = async (url: string): Promise<ArrayBuffer> => {
    const res = await fetch(url);
    if (!res.ok || !res.body) throw new Error(`${url}: ${res.status}`);
    const len = Number(res.headers.get("content-length")) || 0;
    if (len) size.set(url, len);
    const reader = res.body.getReader();
    const chunks: Uint8Array[] = [];
    let n = 0;
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
      n += value.byteLength;
      got.set(url, n);
      if (!len) size.set(url, Math.max(n, GUESS));
      report();
    }
    size.set(url, n);
    report();
    const out = new Uint8Array(n);
    let o = 0;
    for (const c of chunks) { out.set(c, o); o += c.byteLength; }
    return out.buffer;
  };
  const all = urls.map((u) => {
    const p = one(u);
    buffers.set(u, p);
    p.catch(() => buffers.delete(u));
    return p;
  });
  return Promise.allSettled(all).then(() => undefined);
}
