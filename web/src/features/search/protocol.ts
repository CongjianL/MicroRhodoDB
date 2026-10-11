/** Messages between the Search page and seqSearch.worker.ts. */
import type { Hit } from "./swCore";

export type WorkerRequest =
  | { type: "init"; id: number; fastaUrl: string; index: { accs: string[]; reviewed: number[]; rep: number[] } }
  | { type: "search"; id: number; sequence: string };

export type Phase = "load" | "prefilter" | "align" | "traceback";

export interface WorkerResult {
  queryLength: number;
  nSubjects: number;
  /** Number of prefiltered candidates that received a full Smith-Waterman score (300). */
  prefiltered: number;
  hits: Hit[];
}

export type WorkerResponse =
  | { type: "progress"; id: number; phase: Phase; done: number; total: number }
  | { type: "ready"; id: number; nSubjects: number }
  | { type: "result"; id: number; result: WorkerResult; ms: number }
  | { type: "error"; id: number; message: string };
