/** PR-3 Protein Entry page model: deep links, structure options, PDB table, pLDDT rescaling, publications, integrity sweep. */
import { readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import type { MrdbEntry, PubLink, RecordsIndex, SourceRecord } from "../../src/data/types";
import {
  DEFAULT_PDB_FILTER,
  defaultStructure,
  fasta,
  filterSortPdb,
  focusedRows,
  groupPublications,
  meanCaBfactor,
  parseRecordQuery,
  parseStructureParam,
  recordQueryString,
  rescalePlddt,
  resolveSelection,
  sameSel,
  sequenceLines,
  structureOptions,
  unionRows,
  variantsOf,
} from "../../src/lib/entry";
import { treeHighlight } from "../../src/features/entry/PhylogenySection";
import { OUTGROUP_KEY } from "../../src/features/tree/TreePreview";
import { WEB, json, readData, tips } from "./helpers";

const rec = (acc: string) => json<MrdbEntry>(`records/${acc}.json`);
const srcOf = (e: MrdbEntry, acc: string) => e.sources.find((s) => s.source_acc === acc)!;

describe("deep-link parameters", () => {
  it("parses structure selections and rejects malformed ones", () => {
    expect(parseStructureParam("pdb:5zim")).toEqual({ kind: "pdb", id: "5ZIM" });
    expect(parseStructureParam("AFDB")).toEqual({ kind: "afdb" });
    expect(parseStructureParam("pred")).toEqual({ kind: "pred" });
    for (const bad of [null, "", "pdb:", "pdb:ABCD", "pdb:12345", "5ZIM", "alphafold"]) expect(parseStructureParam(bad)).toBeNull();
  });
  it("parses sections and ignores unknown ones", () => {
    const q = parseRecordQuery(new URLSearchParams("section=phylogeny&structure=pdb:1C3W"));
    expect(q).toEqual({ section: "phylogeny", structure: { kind: "pdb", id: "1C3W" } });
    expect(parseRecordQuery(new URLSearchParams("section=nope")).section).toBeNull();
  });
  it("serialises canonically (section first, readable ':')", () => {
    expect(recordQueryString({ structure: { kind: "pdb", id: "5ZIM" }, section: "experimental" })).toBe("section=experimental&structure=pdb:5ZIM");
    expect(recordQueryString({ structure: { kind: "afdb" } })).toBe("structure=afdb");
    expect(recordQueryString({})).toBe("");
    const round = parseRecordQuery(new URLSearchParams(recordQueryString({ section: "predicted", structure: { kind: "pred" } })));
    expect(round).toEqual({ section: "predicted", structure: { kind: "pred" } });
  });
  it("compares selections", () => {
    expect(sameSel({ kind: "pdb", id: "5ZIM" }, { kind: "pdb", id: "5ZIM" })).toBe(true);
    expect(sameSel({ kind: "pdb", id: "5ZIM" }, { kind: "pdb", id: "1C3W" })).toBe(false);
    expect(sameSel({ kind: "afdb" }, { kind: "pred" })).toBe(false);
    expect(sameSel(null, null)).toBe(true);
  });
});

describe("structure options and default selection", () => {
  it("MRDB000001: focused P02945 has 174 PDB entries, union 175, default is the representative 5ZIM", () => {
    const e = rec("MRDB000001");
    const p = srcOf(e, "P02945");
    expect(p.structures.experimental.length).toBe(174);
    expect(unionRows(e).length).toBe(175);
    expect(e.pdb_union.length).toBe(175);
    expect(defaultStructure(p)).toEqual({ kind: "pdb", id: "5ZIM" });
    const opts = structureOptions(e, p);
    // 175 PDB (focused first, then the other source's extra entry) + AFDB
    expect(opts.filter((o) => o.group === "experimental").length).toBe(175);
    expect(opts.slice(0, 174).every((o) => o.detail.includes("P02945"))).toBe(true);
    expect(opts.find((o) => o.key === "pdb:4Y9H")?.detail).toContain("B0R5N9");
    expect(opts.filter((o) => o.group === "afdb").length).toBe(1);
    const o = opts.find((x) => x.key === "pdb:5ZIM")!;
    expect(o.urls[0].url).toBe("https://models.rcsb.org/v1/5zim/full?encoding=bcif");
    expect(o.urls[1].url).toBe("https://files.rcsb.org/download/5ZIM.cif");
  });
  it("falls back to AFDB, then the release model, then nothing", () => {
    const afOnly = srcOf(rec("MRDB000009"), "Q5V4H7");
    expect(afOnly.structures.experimental.length).toBe(0);
    expect(defaultStructure(afOnly)).toEqual({ kind: "afdb" });

    const e30 = rec("MRDB000030");
    const b = srcOf(e30, "B0R633");
    const opts = structureOptions(e30, b);
    const pred = opts.find((o) => o.group === "release")!;
    expect(pred.rescalePlddt).toBe(true);
    expect(pred.urls[0].url).toBe("structures/predicted/B0R633_esmfold.pdb");
    expect(pred.label).toBe("Release model · ESMCFold2 (full)");

    const none = rec("MRDB000003");
    expect(structureOptions(none, none.sources[0]).filter((o) => o.group !== "afdb").length).toBe(0);
  });
  it("resolves unknown requests to the default and then the first option", () => {
    const e = rec("MRDB000001");
    const p = srcOf(e, "P02945");
    const opts = structureOptions(e, p);
    expect(resolveSelection(opts, { kind: "pdb", id: "9ZZZ" }, defaultStructure(p))?.key).toBe("pdb:5ZIM");
    expect(resolveSelection(opts, { kind: "afdb" }, defaultStructure(p))?.key).toBe("afdb");
    expect(resolveSelection(opts, { kind: "pred" }, null)?.key).toBe(opts[0].key);
    expect(resolveSelection([], { kind: "afdb" }, null)).toBeNull();
  });
});

describe("experimental-structure table", () => {
  const e = rec("MRDB000001");
  const rows = unionRows(e);
  it("default sort is resolution ascending; non-numeric resolutions last in both directions; stable ties", () => {
    const asc = filterSortPdb(rows, DEFAULT_PDB_FILTER);
    const firstNon = asc.findIndex((r) => typeof r.resolution_A !== "number");
    expect(firstNon).toBeGreaterThan(0);
    expect(asc.slice(firstNon).every((r) => typeof r.resolution_A !== "number")).toBe(true);
    const nums = asc.slice(0, firstNon).map((r) => r.resolution_A as number);
    expect(nums).toEqual([...nums].sort((a, b) => a - b));
    const desc = filterSortPdb(rows, { ...DEFAULT_PDB_FILTER, dir: "desc" });
    expect(desc.slice(firstNon).every((r) => typeof r.resolution_A !== "number")).toBe(true);
    expect(filterSortPdb([...rows].reverse(), DEFAULT_PDB_FILTER).map((r) => r.pdb_id)).toEqual(asc.map((r) => r.pdb_id));
  });
  it("filters by method, retinal and free text (PDB ID, ligand, source)", () => {
    const nmr = filterSortPdb(rows, { ...DEFAULT_PDB_FILTER, method: "SOLUTION NMR" });
    expect(nmr.every((r) => r.method === "SOLUTION NMR")).toBe(true);
    const yes = filterSortPdb(rows, { ...DEFAULT_PDB_FILTER, retinal: "yes" }).length;
    const no = filterSortPdb(rows, { ...DEFAULT_PDB_FILTER, retinal: "no" }).length;
    expect(yes + no).toBe(rows.length);
    expect(filterSortPdb(rows, { ...DEFAULT_PDB_FILTER, q: "5zim" }).map((r) => r.pdb_id)).toContain("5ZIM");
    expect(filterSortPdb(rows, { ...DEFAULT_PDB_FILTER, q: "B0R5N9" }).map((r) => r.pdb_id)).toEqual(["4Y9H"]);
  });
  it("union rows list every linked source and OR the flags", () => {
    const e92 = rec("MRDB000092");
    const u = unionRows(e92).find((r) => r.pdb_id === "6CSM");
    expect(u?.sources.sort()).toEqual(e92.sources.filter((s) => s.structures.experimental.some((p) => p.pdb_id === "6CSM")).map((s) => s.source_acc).sort());
  });
});

describe("release-model pLDDT rescaling (in memory only)", () => {
  for (const [mrdb, acc] of [["MRDB000030", "B0R633"], ["MRDB003319", "A0A9X2L7U0"]] as const) {
    it(`${acc}: B-factors 0-1 become 0-100 and the CA mean matches mean_plddt`, () => {
      const m = srcOf(rec(mrdb), acc).structures.predicted[0];
      const raw = readData(m.file);
      expect(meanCaBfactor(raw)).toBeLessThanOrEqual(1);
      const scaled = rescalePlddt(raw);
      const bs = scaled.split("\n").filter((l) => l.startsWith("ATOM  ")).map((l) => Number.parseFloat(l.slice(60, 66)));
      expect(Math.min(...bs)).toBeGreaterThanOrEqual(0);
      expect(Math.max(...bs)).toBeLessThanOrEqual(100);
      expect(Math.abs(meanCaBfactor(scaled) - m.mean_plddt)).toBeLessThan(0.1);
      // Only the B-factor column changes; line count and widths are preserved.
      const a = raw.split("\n");
      const b = scaled.split("\n");
      expect(b.length).toBe(a.length);
      a.forEach((l, i) => {
        expect(b[i].length).toBe(l.length);
        expect(b[i].slice(0, 60)).toBe(l.slice(0, 60));
      });
    });
  }
});

describe("publications", () => {
  const link = (o: Partial<PubLink>): PubLink => ({
    assertion_id: 1, publication_id: 1, counts_as_support: true, link_role: "support", title: null, journal: null, year: null, doi: null, pmid: null,
    ...o,
  } as PubLink);
  it("groups by publication, support first, newest first, undated last, ties by id", () => {
    const g = groupPublications([
      link({ assertion_id: 5, publication_id: 3, year: 2001 }),
      link({ assertion_id: 2, publication_id: 2, year: null }),
      link({ assertion_id: 4, publication_id: 1, year: 2010 }),
      link({ assertion_id: 3, publication_id: 1, year: 2010 }),
      link({ assertion_id: 6, publication_id: 4, year: 2010 }),
      link({ assertion_id: 7, publication_id: 9, year: 2020, counts_as_support: false, link_role: "compilation" }),
    ]);
    expect(g.support.map((p) => p.publication_id)).toEqual([1, 4, 3, 2]);
    expect(g.support[0].links.map((l) => l.assertion_id)).toEqual([3, 4]);
    expect(g.other.map((p) => p.publication_id)).toEqual([9]);
  });
});

describe("sequence helpers", () => {
  it("blocks of 10, 6 per line, FASTA wrapped at 60 with release header", () => {
    const e = rec("MRDB000001");
    const p = srcOf(e, "P02945");
    const lines = sequenceLines(p.sequence);
    expect(lines[0].start).toBe(1);
    expect(lines[1].start).toBe(61);
    expect(lines.flatMap((l) => l.blocks).join("")).toBe(p.sequence);
    const fa = fasta(e, [p]);
    expect(fa.startsWith(">P02945 MRDB000001")).toBe(true);
    expect(fa).toContain("release=v1.6.0");
    expect(fa.split("\n").slice(1).filter(Boolean).every((l) => l.length <= 60)).toBe(true);
    expect(fa.split("\n").slice(1).join("")).toBe(p.sequence);
  });
  it("lists engineered variants of a wild type", () => {
    const ev = json<{ engineered: { source_acc: string; wild_type_acc: string }[] }>("evidence-index.json");
    expect(variantsOf(ev.engineered, "A0A6P3CW41")).toContain("A0A6I8WFQ3");
    expect(variantsOf(ev.engineered, "NOPE")).toEqual([]);
  });
});

describe("tree highlight", () => {
  it("highlights the reference tip for P02945", () => {
    const e = rec("MRDB000001");
    const h = treeHighlight(e, srcOf(e, "P02945"), tips());
    expect(h?.tip).toBeTruthy();
    expect(tips().tips.some((t) => t.tip === h!.tip)).toBe(true);
  });
  it("highlights only the clade arc for placed records (never a tip)", () => {
    const e3 = rec("MRDB000003");
    const placed = e3.sources[0];
    expect(placed.phylogeny.is_reference_tip).toBe(false);
    expect(placed.phylogeny.clade_state).toBe("confident");
    expect(treeHighlight(e3, placed, tips())).toMatchObject({ tip: null, group: placed.phylogeny.clade_id });
    const e15 = rec("MRDB000015");
    const tent = srcOf(e15, "A0A135LS53");
    expect(tent.phylogeny.clade_state).toBe("tentative");
    const h = treeHighlight(e15, tent, tips());
    expect(h).toMatchObject({ tip: null, group: tent.phylogeny.tentative_clade_id });
    expect(h!.label).toMatch(/tentative/);
    expect(OUTGROUP_KEY).toBe("outgroup");
  });
});

/* ---------------------------------------------------------------- integrity sweep over all record files */

describe("integrity sweep: every record file against records-index.json", () => {
  const ri = json<RecordsIndex>("records-index.json");
  const col = Object.fromEntries((ri.columns as readonly string[]).map((c, i) => [c, i]));
  const idx = new Map<string, unknown[]>(ri.rows.map((r) => [(r as unknown[])[col.source_acc] as string, r as unknown[]]));
  const dir = resolve(WEB, "public/data/v1.6.0/records");
  const files = readdirSync(dir).filter((f) => f.endsWith(".json"));
  const releaseSources = new Set<string>();
  let nSources = 0;
  let nOptsChecked = 0;

  it("covers 5,299 MRDB entries and 5,466 source records", () => {
    expect(files.length).toBe(5299);
    expect(idx.size).toBe(5466);
  });

  it("per-source PDB links, union, flags, AFDB and release models are consistent", () => {
    const problems: string[] = [];
    for (const f of files) {
      const e = JSON.parse(readFileSync(resolve(dir, f), "utf8")) as MrdbEntry;
      const union = unionRows(e).map((r) => r.pdb_id).sort();
      if (JSON.stringify(union) !== JSON.stringify([...e.pdb_union].sort())) problems.push(`${e.mrdb_acc}: union`);
      for (const s of e.sources as SourceRecord[]) {
        nSources++;
        const row = idx.get(s.source_acc);
        if (!row) { problems.push(`${s.source_acc}: missing from index`); continue; }
        const exp = s.structures.experimental;
        if (exp.length !== row[col.n_pdb]) problems.push(`${s.source_acc}: n_pdb`);
        const ids = exp.map((p) => p.pdb_id).sort();
        if (JSON.stringify(ids) !== JSON.stringify([...((row[col.pdb_ids] as string[] | null) ?? [])].sort())) problems.push(`${s.source_acc}: pdb_ids`);
        if (new Set(ids).size !== ids.length) problems.push(`${s.source_acc}: duplicate PDB`);
        if (exp.filter((p) => p.is_rep).length > 1) problems.push(`${s.source_acc}: >1 rep`);
        if (focusedRows(s).length !== exp.length) problems.push(`${s.source_acc}: focused rows`);
        const opts = structureOptions(e, s);
        nOptsChecked++;
        if (opts.filter((o) => o.group === "experimental").length !== e.pdb_union.length) problems.push(`${s.source_acc}: options vs union`);
        const af = opts.some((o) => o.group === "afdb");
        if (af !== (s.structures.afdb.status === "ok" && !!s.structures.afdb.model_url)) problems.push(`${s.source_acc}: afdb option`);
        if (s.structures.predicted.length) releaseSources.add(s.source_acc);
        if ((s.structures.predicted.length > 0) !== Boolean(row[col.has_predicted])) problems.push(`${s.source_acc}: has_predicted`);
        const def = defaultStructure(s);
        if (def && !opts.some((o) => sameSel(o.sel, def))) problems.push(`${s.source_acc}: default not an option`);
        if (!def && opts.some((o) => o.group !== "experimental")) problems.push(`${s.source_acc}: default missing`);
        const sup = groupPublications(s.publications).support.reduce((n, g) => n + g.links.length, 0);
        if (sup !== row[col.n_support_links]) problems.push(`${s.source_acc}: n_support_links ${sup} vs ${row[col.n_support_links]}`);
      }
    }
    expect(problems.slice(0, 20)).toEqual([]);
    expect(nSources).toBe(5466);
    expect(nOptsChecked).toBe(5466);
    expect([...releaseSources].sort()).toEqual(["A0A9X2L7U0", "B0R633"]);
  });
});
