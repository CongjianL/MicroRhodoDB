/**
 * Main-thread client for the search worker: lazy creation, progress callbacks, cancellation by
 * terminating the worker (a fresh one is created for the next search) and error recovery.
 */
import type { Phase, WorkerRequest, WorkerResponse, WorkerResult } from "./protocol";
import { dataTimeoutMs } from "../../data/fetchText";

export interface IndexFlags { accs: string[]; reviewed: number[]; rep: number[] }

export class SearchClient {
  private worker: Worker | null = null;
  private ready: Promise<number> | null = null;
  private seq = 0;
  /** Reason of the last failure, reported if a call arrives after the worker was torn down. */
  private lastError: Error | null = null;
  private pending = new Map<number, { resolve: (v: unknown) => void; reject: (e: Error) => void; onProgress?: (p: Phase, d: number, t: number) => void }>();

  constructor(private fastaUrl: () => Promise<string>, private flags: () => Promise<IndexFlags>) {}

  private spawn(): Worker {
    const w = new Worker(new URL("./seqSearch.worker.ts", import.meta.url), { type: "module", name: "mrdb-seqsearch" });
    w.onmessage = (ev: MessageEvent<WorkerResponse>) => {
      const m = ev.data;
      const p = this.pending.get(m.id);
      if (!p) return;
      if (m.type === "progress") p.onProgress?.(m.phase, m.done, m.total);
      else {
        this.pending.delete(m.id);
        if (m.type === "error") p.reject(new Error(m.message));
        else if (m.type === "ready") p.resolve(m.nSubjects);
        else p.resolve({ result: m.result, ms: m.ms });
      }
    };
    w.onerror = (ev) => {
      ev.preventDefault();
      this.fail(new Error(ev.message || "The search worker failed to start or crashed."));
    };
    return w;
  }

  private fail(e: Error) {
    this.lastError = e;
    for (const p of this.pending.values()) p.reject(e);
    this.pending.clear();
    this.worker?.terminate();
    this.worker = null;
    this.ready = null;
  }

  private call<T>(msg: Omit<WorkerRequest, "id"> & { type: WorkerRequest["type"] }, onProgress?: (p: Phase, d: number, t: number) => void): Promise<T> {
    const id = ++this.seq;
    return new Promise<T>((resolve, reject) => {
      // The worker can fail to load (e.g. its script is unavailable) before the corpus URL resolves.
      if (!this.worker) { reject(this.lastError ?? new Error("The search worker is not available.")); return; }
      this.pending.set(id, { resolve: resolve as (v: unknown) => void, reject, onProgress });
      this.worker.postMessage({ ...msg, id } as WorkerRequest);
    });
  }

  /** Load the corpus in the worker (once). */
  init(onProgress?: (p: Phase, d: number, t: number) => void): Promise<number> {
    if (!this.ready) {
      this.lastError = null;
      this.worker = this.spawn();
      this.ready = Promise.all([this.fastaUrl(), this.flags()]).then(([fastaUrl, index]) =>
        this.call<number>({ type: "init", fastaUrl, index, timeoutMs: dataTimeoutMs() } as Omit<WorkerRequest, "id">, onProgress));
      this.ready.catch(() => this.fail(new Error("initialisation failed")));
    }
    return this.ready;
  }

  async search(sequence: string, onProgress?: (p: Phase, d: number, t: number) => void): Promise<{ result: WorkerResult; ms: number }> {
    await this.init(onProgress);
    return this.call({ type: "search", sequence } as Omit<WorkerRequest, "id">, onProgress);
  }

  /** Cancel whatever is running: the worker is terminated and pending promises reject with "cancelled". */
  cancel() {
    this.fail(new Error("cancelled"));
  }

  dispose() {
    this.cancel();
  }
}
