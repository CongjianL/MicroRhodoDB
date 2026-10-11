/**
 * PR-6a: the data-loading timeout covers stalled response bodies (not only response headers), is an
 * inactivity timeout (slow but progressing downloads succeed), and keeps the PR-6 error semantics.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { DEFAULT_DATA_TIMEOUT_MS, DataError, dataTimeoutMs, fetchText } from "../../src/data/fetchText";

const enc = new TextEncoder();
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** A body that sends `first` and then never sends anything again (headers already delivered). */
function stalledBody(first: string, onCancel: () => void) {
  return new ReadableStream<Uint8Array>({
    start(c) { c.enqueue(enc.encode(first)); },
    cancel() { onCancel(); },
  });
}

/** A body that drips `chunks` with `gapMs` between them, then closes. */
function drippingBody(chunks: string[], gapMs: number) {
  let i = 0;
  return new ReadableStream<Uint8Array>({
    async pull(c) {
      if (i >= chunks.length) { c.close(); return; }
      await sleep(gapMs);
      c.enqueue(enc.encode(chunks[i++]));
    },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  delete (globalThis as { __MRDB_DATA_TIMEOUT_MS?: number }).__MRDB_DATA_TIMEOUT_MS;
});

describe("PR-6a fetchText inactivity timeout", () => {
  it("rejects with a timeout when the body stalls after the headers arrive, and cancels the body", { timeout: 5000 }, async () => {
    let cancelled = false;
    vi.stubGlobal("fetch", async () => new Response(stalledBody('{"columns":["a"', () => { cancelled = true; }), { status: 200 }));
    const t0 = Date.now();
    await expect(fetchText("/data/v1.6.0/records-index.json", 150)).rejects.toThrow("Timed out while loading /data/v1.6.0/records-index.json");
    expect(Date.now() - t0).toBeLessThan(2000);
    await sleep(0);
    expect(cancelled).toBe(true);
  });

  it("rejects with a timeout when the headers never arrive (fetch ignores the signal)", async () => {
    vi.stubGlobal("fetch", () => new Promise<Response>(() => { /* never */ }));
    await expect(fetchText("/x.json", 100)).rejects.toThrow(/^Timed out while loading \/x\.json$/);
  });

  it("does not cut off a slow download that keeps delivering data (idle, not total, limit)", async () => {
    const chunks = Array.from({ length: 8 }, (_, i) => `"c${i}",`);
    vi.stubGlobal("fetch", async () => new Response(drippingBody(chunks, 40), { status: 200 }));
    const t0 = Date.now();
    const out = await fetchText("/slow.json", 150); // total ~320 ms > 150 ms limit, every gap < limit
    expect(Date.now() - t0).toBeGreaterThan(150);
    expect(out).toBe(chunks.join(""));
  });

  it("times out when a dripping body stops mid-way", { timeout: 5000 }, async () => {
    let i = 0;
    const body = new ReadableStream<Uint8Array>({
      async pull(c) { if (i < 2) { await sleep(20); c.enqueue(enc.encode(`x${i++}`)); } else { await new Promise(() => { /* stall */ }); } },
    });
    vi.stubGlobal("fetch", async () => new Response(body, { status: 200 }));
    await expect(fetchText("/half.json", 120)).rejects.toThrow("Timed out");
  });

  it("keeps HTTP and network error semantics", async () => {
    vi.stubGlobal("fetch", async () => new Response("nope", { status: 404 }));
    const e = await fetchText("/missing.json", 1000).catch((x) => x);
    expect(e).toBeInstanceOf(DataError);
    expect((e as DataError).status).toBe(404);
    expect((e as Error).message).toBe("HTTP 404 while loading /missing.json");

    const broken = new ReadableStream<Uint8Array>({ start(c) { c.enqueue(enc.encode("{")); c.error(new TypeError("reset")); } });
    vi.stubGlobal("fetch", async () => new Response(broken, { status: 200 }));
    await expect(fetchText("/reset.json", 1000)).rejects.toThrow("Network error while loading /reset.json");

    vi.stubGlobal("fetch", async () => { throw new TypeError("Failed to fetch"); });
    await expect(fetchText("/offline.json", 1000)).rejects.toThrow("Network error while loading /offline.json");
  });

  it("returns the complete body and clears its timer on success", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    try {
      vi.stubGlobal("fetch", async () => new Response('{"ok":true}', { status: 200 }));
      await expect(fetchText("/ok.json", 1000)).resolves.toBe('{"ok":true}');
      expect(vi.getTimerCount()).toBe(0);
    } finally {
      vi.useRealTimers();
    }
  });

  it("uses a 45 s default that tests can shorten via window.__MRDB_DATA_TIMEOUT_MS", () => {
    expect(DEFAULT_DATA_TIMEOUT_MS).toBe(45_000);
    expect(dataTimeoutMs()).toBe(45_000);
    (globalThis as { __MRDB_DATA_TIMEOUT_MS?: number }).__MRDB_DATA_TIMEOUT_MS = 1500;
    expect(dataTimeoutMs()).toBe(1500);
    (globalThis as { __MRDB_DATA_TIMEOUT_MS?: unknown }).__MRDB_DATA_TIMEOUT_MS = "bad";
    expect(dataTimeoutMs()).toBe(45_000);
  });
});

/**
 * Minimal XMLHttpRequest double driven by a script: `headersAfter` ms until headers (readyState 2),
 * then one progress event per chunk every `gapMs`, then load. `stallAfter` stops after N chunks.
 */
function fakeXhrClass(opts: { status?: number; chunks?: string[]; gapMs?: number; headersAfter?: number | null; stallAfter?: number; error?: boolean }) {
  const created: FakeXhr[] = [];
  class FakeXhr {
    readyState = 0; status = 0; responseText = ""; responseType = "";
    aborted = false; method = ""; url = "";
    onreadystatechange: (() => void) | null = null; onprogress: (() => void) | null = null;
    onload: (() => void) | null = null; onerror: (() => void) | null = null;
    onabort: (() => void) | null = null; ontimeout: (() => void) | null = null;
    constructor() { created.push(this); }
    open(m: string, u: string) { this.method = m; this.url = u; this.readyState = 1; }
    abort() { if (this.aborted) return; this.aborted = true; this.readyState = 4; this.status = 0; this.onabort?.(); }
    async send() {
      if (opts.headersAfter === null) return; // headers never arrive
      await sleep(opts.headersAfter ?? 5);
      if (this.aborted) return;
      if (opts.error) { this.readyState = 4; this.onreadystatechange?.(); this.onerror?.(); return; }
      this.status = opts.status ?? 200; this.readyState = 2; this.onreadystatechange?.();
      const chunks = opts.chunks ?? ["ok"];
      for (let i = 0; i < chunks.length; i++) {
        if (opts.stallAfter !== undefined && i >= opts.stallAfter) return; // body stalls
        await sleep(opts.gapMs ?? 5);
        if (this.aborted) return;
        this.readyState = 3; this.responseText += chunks[i]; this.onprogress?.();
      }
      this.readyState = 4; this.onreadystatechange?.(); this.onload?.();
    }
  }
  return { FakeXhr, created };
}

describe("PR-6a fetchText via XMLHttpRequest (browser and worker transport)", () => {
  it("uses XMLHttpRequest when available and returns the complete body without leaving a timer", async () => {
    const { FakeXhr, created } = fakeXhrClass({ chunks: ['{"a":', "1}"] });
    vi.stubGlobal("XMLHttpRequest", FakeXhr);
    vi.stubGlobal("fetch", () => { throw new Error("fetch must not be used when XMLHttpRequest exists"); });
    await expect(fetchText("/data/v1.6.0/manifest.json", 1000)).resolves.toBe('{"a":1}');
    expect(created).toHaveLength(1);
    expect(created[0].method).toBe("GET");
    expect(created[0].url).toBe("/data/v1.6.0/manifest.json");
    expect(created[0].aborted).toBe(false);
  });

  it("times out and aborts when the body stalls after the headers", { timeout: 5000 }, async () => {
    const { FakeXhr, created } = fakeXhrClass({ chunks: ["{", '"x"', "}"], stallAfter: 1 });
    vi.stubGlobal("XMLHttpRequest", FakeXhr);
    const t0 = Date.now();
    await expect(fetchText("/stall.json", 150)).rejects.toThrow(/^Timed out while loading \/stall\.json$/);
    expect(Date.now() - t0).toBeLessThan(2000);
    expect(created[0].aborted).toBe(true);
  });

  it("times out when the headers never arrive", { timeout: 5000 }, async () => {
    const { FakeXhr } = fakeXhrClass({ headersAfter: null });
    vi.stubGlobal("XMLHttpRequest", FakeXhr);
    await expect(fetchText("/never.json", 100)).rejects.toThrow("Timed out while loading /never.json");
  });

  it("does not cut off a slow body that keeps progressing (idle, not total, limit)", async () => {
    const chunks = Array.from({ length: 8 }, (_, i) => `c${i};`);
    const { FakeXhr } = fakeXhrClass({ chunks, gapMs: 40 });
    vi.stubGlobal("XMLHttpRequest", FakeXhr);
    const t0 = Date.now();
    await expect(fetchText("/slow.json", 150)).resolves.toBe(chunks.join(""));
    expect(Date.now() - t0).toBeGreaterThan(150);
  });

  it("keeps HTTP and network error semantics", async () => {
    vi.stubGlobal("XMLHttpRequest", fakeXhrClass({ status: 404, chunks: ["nope"] }).FakeXhr);
    const e = await fetchText("/missing.json", 1000).catch((x) => x);
    expect(e).toBeInstanceOf(DataError);
    expect((e as DataError).status).toBe(404);
    expect((e as Error).message).toBe("HTTP 404 while loading /missing.json");
    vi.stubGlobal("XMLHttpRequest", fakeXhrClass({ error: true }).FakeXhr);
    await expect(fetchText("/offline.json", 1000)).rejects.toThrow("Network error while loading /offline.json");
  });
});
