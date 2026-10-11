/**
 * PR-5 gate G5 (search golden cases): the Web Worker search core reproduces the legacy v1.6.0 browser
 * search exactly. Golden hits were produced by the unmodified legacy code (site/app.js) on the legacy
 * data bundle (site/data.js) by web/scripts/legacy_seqsearch_golden.mjs; here the PR-5 core runs on the
 * exported corpus.fasta + records-index.json flags, as the worker does.
 */
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import {
  B62, METHOD, Prefilter, buildCorpus, encode, legacyParse, parseCorpus, parseQuery, search, swAlign, swScore,
} from "../../src/features/search/swCore";
import { REPO, readData, rows } from "./helpers";

interface GoldenHit { rank: number; source_acc: string; mrdb_acc: string; score: number; identity: number; qcov: number; scov: number; alen: number }
interface GoldenCase { query_id: string; query_fasta: string; query_length: number; prefilter_sha256: string; hits: GoldenHit[] }
const golden = JSON.parse(readFileSync(resolve(REPO, "tests/data/web_seqsearch_golden_v160.json"), "utf8")) as { cases: GoldenCase[]; n_records: number };

const R = rows();
const corpus = buildCorpus(parseCorpus(readData("sequences/corpus.fasta")), {
  accs: R.map((r) => r.source_acc),
  reviewed: R.map((r) => (r.reviewed ? 1 : 0)),
  rep: R.map((r) => (r.is_mrdb_representative ? 1 : 0)),
});
const pf = new Prefilter();
const r6 = (x: number) => Math.round(x * 1e6) / 1e6;

describe("legacy golden cases", () => {
  it("covers 13 queries over the full 5,466-record corpus", () => {
    expect(golden.cases).toHaveLength(13);
    expect(golden.n_records).toBe(5466);
    expect(corpus.seqs).toHaveLength(5466);
  });

  for (const c of golden.cases) {
    it(`${c.query_id}: identical prefilter, ranking, scores, identity and coverage`, () => {
      const p = parseQuery(c.query_fasta);
      expect(p.ok).toBe(true);
      if (!p.ok) return;
      expect(p.sequence).toBe(legacyParse(c.query_fasta));
      expect(p.sequence.length).toBe(c.query_length);
      const res = search(p.sequence, corpus, pf);
      const pfAccs = res.prefiltered.map((i) => corpus.accs[i]).join("\n");
      expect(createHash("sha256").update(pfAccs).digest("hex")).toBe(c.prefilter_sha256);
      expect(res.hits.map((h) => ({
        rank: h.rank, source_acc: h.source_acc, mrdb_acc: R[h.idx].mrdb_acc, score: h.score,
        identity: r6(h.identity), qcov: r6(h.qcov), scov: r6(h.scov), alen: h.alen,
      }))).toEqual(c.hits);
      for (const h of res.hits) {
        // aligned strings are consistent with the reported statistics
        expect(h.qAln.length).toBe(h.alen);
        expect(h.sAln.length).toBe(h.alen);
        expect([...h.mid].filter((x) => x === "|").length).toBe(Math.round(h.identity * h.alen));
        expect(h.qAln.replace(/-/g, "")).toBe(p.sequence.slice(h.qStart - 1, h.qEnd));
        expect(h.sAln.replace(/-/g, "")).toBe(corpus.seqs[h.idx].slice(h.sStart - 1, h.sEnd));
      }
    });
  }

  it("P02945 example returns itself at 100% identity and full coverage", () => {
    const i = corpus.accs.indexOf("P02945");
    const res = search(corpus.seqs[i], corpus, pf);
    expect(res.hits[0].source_acc).toBe("P02945");
    expect(res.hits[0].identity).toBe(1);
    expect(res.hits[0].qcov).toBe(1);
    expect(res.hits[0].scov).toBe(1);
  });
});

describe("alignment primitives", () => {
  it("BLOSUM62 is symmetric 24 x 24 and swScore equals swAlign score", () => {
    expect(B62).toHaveLength(24);
    for (let a = 0; a < 24; a++) for (let b = 0; b < 24; b++) expect(B62[a][b]).toBe(B62[b][a]);
    const a = "MLELLPTAVEGVSQAQITGRPEWIWLALGTALMGLGTLYFLVKG";
    const b = "MLELLPTAVEGVSQITGRPEWIWLAGTALMGLGTLYFLVKGW";
    expect(swAlign(encode(a), encode(b), a, b).score).toBe(swScore(encode(a), encode(b)));
  });
  it("affine gaps: one 3-residue gap costs 11 + 2 x 1", () => {
    const a = "WWWWWWWWWWCCCWWWWWWWWWW";
    const b = "WWWWWWWWWWWWWWWWWWWW";
    const al = swAlign(encode(a), encode(b), a, b);
    expect(al.score).toBe(20 * 11 - 13);
    expect(al.qAln).toBe(a);
    expect(al.sAln).toBe("WWWWWWWWWW---WWWWWWWWWW");
  });
});

describe("query validation (PR-5; valid input parsed exactly as legacy)", () => {
  const seq = "MLELLPTAVEGVSQAQITGRPEWIWLALGTALMGLGTLYFLVKG";
  it("accepts plain text and one FASTA record", () => {
    for (const t of [seq, `>q1 test\n${seq}`, `  ${seq.slice(0, 20)}\n${seq.slice(20)}  `, seq.toLowerCase()]) {
      const p = parseQuery(t);
      expect(p.ok).toBe(true);
      if (p.ok) expect(p.sequence).toBe(legacyParse(t));
    }
  });
  it("rejects empty, multi-record, short, long and nucleotide input with reasons", () => {
    const code = (t: string) => { const p = parseQuery(t); return p.ok ? "ok" : p.error.code; };
    expect(code("   ")).toBe("empty");
    expect(code(`>a\n${seq}\n>b\n${seq}`)).toBe("multi_record");
    expect(code(`${seq}\n>b\n${seq}`)).toBe("multi_record");
    expect(code("MLELLPTAVEG")).toBe("too_short");
    expect(code("A".repeat(METHOD.maxLength + 1).replace(/A/g, "L"))).toBe("too_long");
    expect(code("L".repeat(METHOD.maxLength))).toBe("ok");
    expect(code("ATGGCTAGCTAGGATCGATCGATCGTAGCTAGCTAGNNACGT")).toBe("nucleotide");
  });
  it("warns about non-standard letters and ignored characters", () => {
    const p = parseQuery(`${seq}XBZU-.`);
    expect(p.ok).toBe(true);
    if (p.ok) {
      expect(p.warnings.join(" ")).toMatch(/non-letter/);
      expect(p.warnings.join(" ")).toMatch(/X \u00d71/);
      expect(p.sequence).toBe(`${seq}XBZU`);
    }
  });
  it("prefilter keeps 300 of 5,466 candidates and is stable for ties", () => {
    const res = pf.run("WWWWWWWWWWWWWWWWWWWW", corpus.seqs);
    expect(res).toHaveLength(METHOD.prefilter);
    const zeroTail = res.filter((i) => !corpus.seqs[i].includes("WWW"));
    expect(zeroTail).toEqual([...zeroTail].sort((a, b) => a - b));
  });
});
