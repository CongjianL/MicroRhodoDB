/// <reference lib="webworker" />
/**
 * Sequence-search Web Worker. Loads corpus.fasta once (URL supplied by the page), joins it with the
 * records-index tie-break flags sent by the page, and runs the legacy-equivalent search off the main
 * thread. Cancellation = the page terminates this worker; errors are posted back as messages.
 */
import { Prefilter, buildCorpus, parseCorpus, search, type Corpus } from "./swCore";
import type { WorkerRequest, WorkerResponse } from "./protocol";

let corpus: Corpus | null = null;
let pf: Prefilter | null = null;
const post = (m: WorkerResponse) => (self as unknown as DedicatedWorkerGlobalScope).postMessage(m);

self.onmessage = async (ev: MessageEvent<WorkerRequest>) => {
  const msg = ev.data;
  try {
    if (msg.type === "init") {
      if (!corpus) {
        post({ type: "progress", id: msg.id, phase: "load", done: 0, total: 1 });
        const res = await fetch(msg.fastaUrl, { credentials: "same-origin" });
        if (!res.ok) throw new Error(`HTTP ${res.status} while loading corpus.fasta`);
        corpus = buildCorpus(parseCorpus(await res.text()), msg.index);
        pf = new Prefilter();
      }
      post({ type: "ready", id: msg.id, nSubjects: corpus.seqs.length });
      return;
    }
    if (msg.type === "search") {
      if (!corpus || !pf) throw new Error("worker not initialised");
      const t0 = performance.now();
      const r = search(msg.sequence, corpus, pf, (phase, done, total) => post({ type: "progress", id: msg.id, phase, done, total }));
      post({ type: "result", id: msg.id, result: { ...r, prefiltered: r.prefiltered.length }, ms: performance.now() - t0 });
    }
  } catch (e) {
    post({ type: "error", id: msg.id, message: e instanceof Error ? e.message : String(e) });
  }
};
