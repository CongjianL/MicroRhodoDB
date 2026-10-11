/**
 * PR-6a: dependency-free, timeout-aware text download shared by the data loaders (main thread) and the
 * sequence-search worker. No React or import.meta use, so it is importable from a Web Worker.
 *
 * The limit is an inactivity (idle) timeout covering the whole transfer: it starts with the request, is
 * restarted whenever the headers or a body chunk arrive and is cleared only when the body is complete. A
 * server that never answers, or that sends headers and then stalls mid-body, therefore fails with
 * "Timed out while loading ..." instead of leaving the page loading forever (PR-6 covered headers only).
 * A slow connection that is still delivering data is never cut off.
 *
 * Transport: XMLHttpRequest (available on the main thread and in dedicated workers). Its progress events
 * give body-level activity without a streaming reader. A fetch() + ReadableStream reader was tried first,
 * but Chromium reports such requests as net::ERR_ABORTED in DevTools whenever the script finishes reading
 * before the network loader signals completion (the data are complete, but every page load showed failed
 * requests; see PR6A_AUTO_ACCEPTANCE_REPORT.md). The fetch()-based path is kept only as a fallback for
 * environments without XMLHttpRequest (e.g. Node-based unit tests).
 *
 * Tests may shorten the default via window.__MRDB_DATA_TIMEOUT_MS (main thread) or pass timeoutMs (worker).
 */
export class DataError extends Error {
  constructor(message: string, readonly status?: number) {
    super(message);
  }
}

export const DEFAULT_DATA_TIMEOUT_MS = 45_000;

export const dataTimeoutMs = (): number => {
  const t = (globalThis as { __MRDB_DATA_TIMEOUT_MS?: unknown }).__MRDB_DATA_TIMEOUT_MS;
  return typeof t === "number" && t > 0 ? t : DEFAULT_DATA_TIMEOUT_MS;
};

const timedOutError = (url: string) => new DataError(`Timed out while loading ${url}`);
const networkError = (url: string) => new DataError(`Network error while loading ${url}`);
const httpError = (url: string, status: number) => new DataError(`HTTP ${status} while loading ${url}`, status);

/** Fetch a same-origin data file as text; HTTP errors, network errors and inactivity time-outs become DataError. */
export function fetchText(url: string, timeoutMs: number = dataTimeoutMs()): Promise<string> {
  return typeof XMLHttpRequest === "function" ? viaXhr(url, timeoutMs) : viaFetch(url, timeoutMs);
}

function viaXhr(url: string, timeoutMs: number): Promise<string> {
  return new Promise<string>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let settled = false;
    const finish = (fn: () => void) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      fn();
    };
    const arm = () => {
      clearTimeout(timer);
      timer = setTimeout(() => finish(() => { xhr.abort(); reject(timedOutError(url)); }), timeoutMs);
    };
    xhr.open("GET", url, true);
    xhr.responseType = "text";
    xhr.onreadystatechange = () => { if (!settled && xhr.readyState >= 2) arm(); }; // headers / first bytes
    xhr.onprogress = () => { if (!settled) arm(); };                                  // every body chunk
    xhr.onload = () => finish(() => {
      if (xhr.status >= 200 && xhr.status < 300) resolve(xhr.responseText);
      else if (xhr.status === 0) reject(networkError(url));
      else reject(httpError(url, xhr.status));
    });
    xhr.onerror = () => finish(() => reject(networkError(url)));
    xhr.onabort = () => finish(() => reject(networkError(url)));
    xhr.ontimeout = () => finish(() => reject(timedOutError(url)));
    arm();
    try {
      xhr.send();
    } catch {
      finish(() => reject(networkError(url)));
    }
  });
}

async function viaFetch(url: string, timeoutMs: number): Promise<string> {
  const ctl = new AbortController();
  let timedOut = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const arm = () => {
    clearTimeout(timer);
    timer = setTimeout(() => { timedOut = true; ctl.abort(); }, timeoutMs);
  };
  const fail = (): never => { throw timedOut ? timedOutError(url) : networkError(url); };
  // Rejects when the timer fires, so a pending fetch() or body read is abandoned even if the
  // implementation does not propagate the abort signal into the body stream.
  const aborted = new Promise<never>((_, reject) => {
    ctl.signal.addEventListener("abort", () => reject(new Error("aborted")), { once: true });
  });
  aborted.catch(() => undefined);
  arm();
  try {
    let res: Response;
    try {
      res = await Promise.race([fetch(url, { credentials: "same-origin", signal: ctl.signal }), aborted]);
    } catch {
      return fail();
    }
    if (!res.ok) {
      ctl.abort(); // do not keep downloading an error body
      throw httpError(url, res.status);
    }
    if (!res.body) {
      try { return await Promise.race([res.text(), aborted]); } catch { return fail(); }
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let out = "";
    try {
      for (;;) {
        arm(); // restart the inactivity timer before waiting for each chunk
        const { done, value } = await Promise.race([reader.read(), aborted]);
        if (done) break;
        out += decoder.decode(value, { stream: true });
      }
    } catch {
      reader.cancel().catch(() => undefined);
      return fail();
    }
    if (timedOut) return fail();
    return out + decoder.decode();
  } finally {
    clearTimeout(timer);
  }
}
