#!/usr/bin/env node
/**
 * Generate golden sequence-search results by running the LEGACY v1.6.0 browser search code
 * (site/app.js, unmodified) against the LEGACY data bundle (site/data.js) in a Node vm sandbox.
 *
 * The PR-5 Web Worker (web/src/features/search/swCore.ts) must reproduce these hits exactly
 * (same top-10 accessions, order, scores, identity and coverage). Regenerate only if the legacy
 * method changes, in which case the browser method gets a new explicit method version.
 *
 * Usage: node web/scripts/legacy_seqsearch_golden.mjs [--check]
 * Output: tests/data/web_seqsearch_golden_v160.json
 */
import { readFileSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import vm from "node:vm";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const REPO = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const OUT = resolve(REPO, "tests/data/web_seqsearch_golden_v160.json");

const appSrc = readFileSync(resolve(REPO, "site/app.js"), "utf8");
const start = appSrc.indexOf('const AA = "ARNDCQEGHILKMFPSTWYVBZX*";');
const end = appSrc.indexOf("function runSearch()");
if (start < 0 || end < 0) throw new Error("legacy search block not found in site/app.js");
const block = appSrc.slice(start, end);

const ctx = { window: {} };
vm.createContext(ctx);
vm.runInContext(readFileSync(resolve(REPO, "site/data.js"), "utf8"), ctx);
const D = ctx.window.MRDB;
const C = D.columns;
ctx.R = D.rows.map((r, i) => { const o = Object.fromEntries(C.map((c, j) => [c, r[j]])); o._i = i; return o; });
ctx.SEQ = D.seqs;
// Legacy block plus the body of runSearch() (verbatim logic, DOM output replaced by a return value).
vm.runInContext(block + `
function legacySearch(text) {
  const qs = parseQuery(text);
  if (qs.length < 20) return { error: "too_short", length: qs.length };
  if (!ENC) ENC = SEQ.map(encode);
  const q = encode(qs);
  const qk = new Set(); for (let i = 0; i + KMER <= qs.length; i++) qk.add(qs.substr(i, KMER));
  const pre = SEQ.map((s, idx) => { let c = 0; const seen = new Set();
    for (let i = 0; i + KMER <= s.length; i++) { const k = s.substr(i, KMER); if (qk.has(k) && !seen.has(k)) { seen.add(k); c++; } }
    return [c, idx]; }).sort((a, b) => b[0] - a[0]).slice(0, PREFILTER);
  const scored = pre.map(([c, idx]) => ({idx, score: swScore(q, ENC[idx])}));
  scored.sort((a, b) => b.score - a.score || (R[b.idx].reviewed - R[a.idx].reviewed) ||
    (R[b.idx].is_mrdb_representative - R[a.idx].is_mrdb_representative) ||
    (R[a.idx].source_acc < R[b.idx].source_acc ? -1 : 1));
  const hits = scored.slice(0, TOP).map(h => Object.assign(h, swAlign(q, ENC[h.idx])));
  return { length: qs.length, prefilter: pre.map(p => p[1]), hits };
}
this.legacySearch = legacySearch;
`, ctx);

function readFasta(p) {
  const out = [];
  let cur = null;
  for (const line of readFileSync(p, "utf8").split(/\r?\n/)) {
    if (line.startsWith(">")) { cur = { id: line.slice(1).trim().split(/\s+/)[0], text: line + "\n" }; out.push(cur); }
    else if (cur && line.trim()) cur.text += line.trim() + "\n";
  }
  return out;
}

const queries = readFasta(resolve(REPO, "tests/data/cli_queries_12.faa"));
const iP = ctx.R.findIndex((r) => r.source_acc === "P02945");
queries.unshift({ id: "P02945", text: ">P02945 bacteriorhodopsin example\n" + D.seqs[iP] + "\n" });

const round = (x) => Math.round(x * 1e6) / 1e6;
const cases = queries.map((qq) => {
  const r = ctx.legacySearch(qq.text);
  const pf = r.prefilter.map((i) => ctx.R[i].source_acc);
  return {
    query_id: qq.id,
    query_fasta: qq.text,
    query_length: r.length,
    prefilter_sha256: createHash("sha256").update(pf.join("\n")).digest("hex"),
    hits: r.hits.map((h, k) => ({
      rank: k + 1,
      source_acc: ctx.R[h.idx].source_acc,
      mrdb_acc: ctx.R[h.idx].mrdb_acc,
      score: h.score,
      identity: round(h.identity),
      qcov: round(h.qcov),
      scov: round(h.scov),
      alen: h.alen,
    })),
  };
});

const golden = {
  method: "legacy-v1.6.0: 3-mer prefilter (distinct shared 3-mers, top 300, stable order) + Gotoh Smith-Waterman, BLOSUM62, gap open 11, gap extend 1; top 10",
  generated_by: "web/scripts/legacy_seqsearch_golden.mjs (site/app.js + site/data.js, unmodified, Node vm)",
  site_app_js_sha256: createHash("sha256").update(appSrc).digest("hex"),
  site_data_js_sha256: createHash("sha256").update(readFileSync(resolve(REPO, "site/data.js"))).digest("hex"),
  n_records: D.seqs.length,
  cases,
};
const text = JSON.stringify(golden, null, 1) + "\n";
if (process.argv.includes("--check")) {
  const prev = readFileSync(OUT, "utf8");
  if (prev !== text) { console.error("golden differs from legacy output"); process.exit(1); }
  console.log(`golden OK (${cases.length} cases)`);
} else {
  writeFileSync(OUT, text);
  console.log(`wrote ${OUT} (${cases.length} cases)`);
  for (const c of cases) console.log(c.query_id, c.query_length, c.hits[0].source_acc, c.hits[0].score, (100 * c.hits[0].identity).toFixed(1));
}
