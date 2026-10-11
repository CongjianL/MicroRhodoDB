/**
 * Static data loaders for the export contract (WEB_DATA_CONTRACT.md, schema 1.4.0; PR-5 adds downloads.json and loaders for the
 * structures, watchlist and publication indexes used by the explorer pages; PR-4a adds formal assignment counts to clades.json; PR-4 adds
 * phylogeny/explorer.json, the IQ-TREE run1 support source and a clearly labelled DERIVED Newick).
 *
 * Every file is fetched lazily, at most once per page load, from the release-versioned
 * directory named by data/current.json (e.g. data/v1.6.0/). URLs contain the release, so
 * browser caching is release-keyed. Lightweight pages (Home, About) never call
 * loadRecordsIndex/loadAccessions/loadRecord/loadCorpusFasta.
 */
import { useEffect, useState } from "react";
import { DataError, fetchText } from "./fetchText";
import type {
  Accessions, Clades, CladeTips, Current, Downloads, EvidenceIndex, Explorer, ExportManifest, Manifest, MrdbEntry, Publications,
  RecordsIndex, StructuresIndex, Summary, Tips, Vocabulary, Watchlist,
} from "./types";

const BASE = import.meta.env.BASE_URL; // "/MicroRhodoDB/site/"
const cache = new Map<string, Promise<unknown>>();

export { DataError, dataTimeoutMs, fetchText } from "./fetchText";

function parseJson<T>(body: string, url: string): T {
  try {
    return JSON.parse(body) as T;
  } catch {
    throw new DataError(`Invalid or truncated data in ${url}`);
  }
}

function once<T>(key: string, load: () => Promise<T>): Promise<T> {
  let p = cache.get(key) as Promise<T> | undefined;
  if (!p) {
    p = load();
    cache.set(key, p);
    p.catch(() => cache.delete(key)); // allow retry after failure
  }
  return p;
}

export function loadCurrent(): Promise<Current> {
  return once("current", async () => {
    const c = parseJson<Current>(await fetchText(`${BASE}data/current.json`), `${BASE}data/current.json`);
    if (!/^data\/v\d+\.\d+\.\d+\/$/.test(c.path)) throw new DataError(`Unexpected data path ${c.path}`);
    return c;
  });
}

async function releaseUrl(rel: string): Promise<string> {
  const c = await loadCurrent();
  return `${BASE}${c.path}${rel}`;
}

function json<T>(rel: string): Promise<T> {
  return once(rel, async () => {
    const url = await releaseUrl(rel);
    return parseJson<T>(await fetchText(url), url);
  });
}

function text(rel: string): Promise<string> {
  return once(rel, async () => fetchText(await releaseUrl(rel)));
}

export const loadManifest = () => json<Manifest>("manifest.json");
export const loadSummary = () => json<Summary>("summary.json");
export const loadClades = () => json<Clades>("clades.json");
export const loadVocabulary = () => json<Vocabulary>("vocabulary.json");
export const loadCladeTips = () => json<CladeTips>("phylogeny/clade_tips.json");
export const loadTips = () => json<Tips>("phylogeny/tips.json");
export const loadNewick = () => text("phylogeny/MR_RT_003.rooted.treefile");
/* Phylogeny explorer / clade pages (PR-4): node table aligned to the rooted Newick by preorder. */
export const loadExplorer = () => json<Explorer>("phylogeny/explorer.json");

/* Heavy files: Browse / Record only. */
export const loadRecordsIndex = () => json<RecordsIndex>("records-index.json");
export const loadAccessions = () => json<Accessions>("accessions.json");
export const loadCorpusFasta = () => text("sequences/corpus.fasta");

/* Record page, fetched on demand (engineered wild-type -> variant links, evidence policy texts). */
export const loadEvidenceIndex = () => json<EvidenceIndex>("evidence-index.json");

/* PR-5 explorer pages (each fetched only by the page that needs it). */
export const loadStructuresIndex = () => json<StructuresIndex>("structures-index.json");
export const loadWatchlist = () => json<Watchlist>("watchlist.json");
export const loadPublications = () => json<Publications>("publications.json");
export const loadDownloads = () => json<Downloads>("downloads.json");
export const loadExportManifest = () => json<ExportManifest>("export_manifest.json");

/** Absolute URL of a release-relative file (e.g. structures/predicted/<acc>_esmfold.pdb). */
export const releaseFileUrl = (rel: string) => releaseUrl(rel);

export function loadRecord(mrdbAcc: string): Promise<MrdbEntry | null> {
  if (!/^MRDB\d{6}$/.test(mrdbAcc)) return Promise.resolve(null);
  return once(`records/${mrdbAcc}`, async () => {
    const url = await releaseUrl(`records/${mrdbAcc}.json`);
    let body: string;
    try {
      body = await fetchText(url);
    } catch (e) {
      if (e instanceof DataError && e.status === 404) return null;
      throw e;
    }
    return parseJson<MrdbEntry>(body, url);
  });
}

/** Parse corpus.fasta ("> SOURCE MRDB" headers, one sequence line) into source_acc -> sequence. */
export function parseCorpusFasta(fa: string): Map<string, string> {
  const out = new Map<string, string>();
  let cur: string | null = null;
  let buf: string[] = [];
  for (const line of fa.split("\n")) {
    if (line.startsWith(">")) {
      if (cur) out.set(cur, buf.join(""));
      cur = line.slice(1).split(/\s+/)[0];
      buf = [];
    } else if (line) buf.push(line.trim());
  }
  if (cur) out.set(cur, buf.join(""));
  return out;
}

export type Resource<T> =
  | { state: "loading" }
  | { state: "error"; error: Error; retry: () => void }
  | { state: "ready"; data: T };

/** React hook around a loader. `deps` re-trigger loading. */
export function useResource<T>(loader: () => Promise<T>, deps: unknown[] = []): Resource<T> {
  const [res, setRes] = useState<Resource<T>>({ state: "loading" });
  const [nonce, setNonce] = useState(0);
  useEffect(() => {
    let alive = true;
    setRes({ state: "loading" });
    loader().then(
      (data) => alive && setRes({ state: "ready", data }),
      (error: Error) => alive && setRes({ state: "error", error, retry: () => setNonce((n) => n + 1) }),
    );
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);
  return res;
}

/** Combine several resources: ready only when all are ready. */
export function all<T extends unknown[]>(...rs: { [K in keyof T]: Resource<T[K]> }): Resource<T> {
  for (const r of rs) if (r.state === "error") return r as Resource<T>;
  for (const r of rs) if (r.state === "loading") return { state: "loading" };
  return { state: "ready", data: rs.map((r) => (r as { data: unknown }).data) as T };
}
