/**
 * Export correctness against the legacy v1.6.0 browser (site/app.js downloadTSV / fastaRecord).
 * Allowed, documented differences (WEB_DATA_CONTRACT.md oracle mappings):
 *   T1 numbers at full precision (legacy rounded membership_score/e2_identity to 3 dp, afdb_global_plddt to 1 dp)
 *   T2 booleans: legacy 0/1 integers == PR-2 "1"/"0" cells
 *   T3 legacy "" == PR-2 null (both written as empty cells)
 *   T4 clade_confidence derived from clade_state
 */
import { describe, expect, it } from "vitest";
import { parseCorpusFasta } from "../../src/data/loaders";
import { applyFilters, DEFAULT_STATE, filterQuery, parseBrowse } from "../../src/lib/browse";
import {
  EXTRA_TSV_COLUMNS, exportFilename, exportIds, fastaHeader, fnv1a, LEGACY_TSV_COLUMNS, selectionManifest, toFasta, toTSV, toUniqueFasta,
  tsvCell, TSV_COLUMNS, wrap60,
} from "../../src/lib/exporters";
import { legacy, legacyRows, manifest, readData, rows, v161Changes } from "./helpers";

const ROUNDED: Record<string, number> = { membership_score: 3, e2_identity: 3, afdb_global_plddt: 1 };

describe("TSV export", () => {
  const D = legacy();
  const R = legacyRows();
  const bySrc = new Map(rows().map((r) => [r.source_acc, r]));
  const ordered = R.map((l) => bySrc.get(String(l.source_acc))!);

  it("keeps the 39 legacy columns in legacy order, then appends PR-2 columns", () => {
    expect([...LEGACY_TSV_COLUMNS]).toEqual(D.columns);
    expect(TSV_COLUMNS.slice(0, 39)).toEqual(D.columns);
    expect(TSV_COLUMNS.slice(39)).toEqual([...EXTRA_TSV_COLUMNS]);
    expect(new Set(TSV_COLUMNS).size).toBe(TSV_COLUMNS.length);
  });

  it("every legacy cell of all 5,466 rows is reproduced modulo T1-T4", () => {
    const tsv = toTSV(ordered);
    const lines = tsv.split("\n");
    expect(lines.at(-1)).toBe("");
    expect(lines.length - 2).toBe(5466);
    expect(lines[0].split("\t")).toEqual(TSV_COLUMNS);
    const diffs: string[] = [];
    for (let i = 0; i < R.length; i++) {
      const cells = lines[i + 1].split("\t");
      expect(cells.length).toBe(TSV_COLUMNS.length);
      D.columns.forEach((c, j) => {
        const lv = R[i][c];
        const legacyCell = lv === null || lv === undefined ? "" : String(lv);
        const ours = cells[j];
        if (ours === legacyCell) return;
        if (v161Changes().get(String(R[i].source_acc))?.has(c)) return; // changed by a signed v1.6.1 decision
        if (c in ROUNDED && ours !== "" && legacyCell !== "") {
          if (Math.abs(Number(ours) - Number(legacyCell)) <= 0.5 * 10 ** -ROUNDED[c] + 1e-9) return;
        }
        diffs.push(`${R[i].source_acc}.${c}: legacy=${JSON.stringify(legacyCell)} pr2=${JSON.stringify(ours)}`);
      });
    }
    expect(diffs.slice(0, 20)).toEqual([]);
  });

  it("encodes missing values, booleans, arrays and embedded whitespace safely", () => {
    expect(tsvCell(null)).toBe("");
    expect(tsvCell(undefined)).toBe("");
    expect(tsvCell(true)).toBe("1");
    expect(tsvCell(false)).toBe("0");
    expect(tsvCell(["1C3W", "1M0K"])).toBe("1C3W;1M0K");
    expect(tsvCell("a\tb\nc")).toBe("a b c");
    expect(tsvCell(0.12345678)).toBe("0.12345678");
  });
});

describe("FASTA exports", () => {
  const D = legacy();
  const R = legacyRows();
  const seqs = parseCorpusFasta(readData("sequences/corpus.fasta"));
  const bySrc = new Map(rows().map((r) => [r.source_acc, r]));

  it("corpus.fasta holds every source record with the legacy sequence", () => {
    expect(seqs.size).toBe(5466);
    R.forEach((l) => expect(seqs.get(String(l.source_acc))).toBe(D.seqs[l._i]));
  });

  it("source-record FASTA is byte-identical to the legacy export for all records", () => {
    const legacyFasta = R.map((r) =>
      `>${r.mrdb_acc} ${r.source_acc} status=${r.membership_status} evidence=${r.evidence_level} ` +
      `func=${r.func_class} clade=${r.clade_display || "none"} engineered=${r.is_engineered}\n` +
      D.seqs[r._i].replace(/(.{60})/g, "$1\n").replace(/\n$/, "") + "\n").join("");
    const ours = toFasta(R.map((l) => bySrc.get(String(l.source_acc))!), seqs);
    // Records changed by a signed v1.6.1 decision differ only in header annotations (status, evidence, func):
    // their accessions and sequence lines must still match the v1.6.0 legacy export.
    const changed = v161Changes();
    const split = (t: string) => t.split(/^(?=>)/m);
    const L = split(legacyFasta), O = split(ours);
    expect(O.length).toBe(L.length);
    for (let i = 0; i < L.length; i++) {
      const acc = R[i].source_acc as string;
      if (!changed.has(acc)) { expect(O[i], acc).toBe(L[i]); continue; }
      const [lh, ...ls] = L[i].split("\n"), [oh, ...os] = O[i].split("\n");
      expect(os.join("\n"), acc).toBe(ls.join("\n"));
      expect(oh.split(" ").slice(0, 2), acc).toEqual(lh.split(" ").slice(0, 2));
    }
  });

  it("headers mark tentative placements as TENTATIVE:<clade>", () => {
    const t = rows().find((r) => r.source_acc === "A0A135LS53")!;
    expect(fastaHeader(t)).toContain("clade=TENTATIVE:MR_CLD3_017");
    expect(wrap60("A".repeat(120))).toBe(`${"A".repeat(60)}\n${"A".repeat(60)}`);
  });

  it("unique MRDB FASTA has one entry per MRDB accession in the selection", () => {
    const all = rows();
    const { text, n } = toUniqueFasta(all, seqs);
    expect(n).toBe(5299);
    expect((text.match(/^>/gm) ?? []).length).toBe(5299);
    expect(text).toContain(">MRDB000001 selected_source_records=");
    const sel = all.filter((r) => r.mrdb_acc === "MRDB000001");
    const one = toUniqueFasta(sel, seqs);
    expect(one.n).toBe(1);
    expect(one.text.split("\n")[0]).toBe(`>MRDB000001 selected_source_records=${sel.map((r) => r.source_acc).join(",")}`);
  });

  it("refuses to export when a sequence is missing", () => {
    expect(() => toFasta(rows().slice(0, 1), new Map())).toThrow(/No sequence/);
  });
});

describe("file names and selection manifest", () => {
  it("file names encode release, selection id, export id and count", () => {
    const q = filterQuery(parseBrowse(new URLSearchParams("evidence=E1&group=all")).state);
    expect(q).toBe("group=all&evidence=E1");
    expect(fnv1a("")).toBe("811c9dc5");
    const ids = exportIds(q, "", "asc");
    expect(ids.selection_id).toBe(fnv1a(q));
    expect(ids.sort_token).toBe("index");
    expect(ids.export_id).toBe(fnv1a(`${q}\u0000sort=index`));
    const base = `microrhododb_v1.6.0_browse_${fnv1a(q)}_${ids.export_id}`;
    expect(exportFilename("1.6.0", "records_tsv", 88, ids)).toBe(`${base}_88_source_records.tsv`);
    expect(exportFilename("1.6.0", "records_fasta", 88, ids)).toBe(`${base}_88_source_records.fasta`);
    expect(exportFilename("1.6.0", "mrdb_fasta", 80, ids)).toBe(`${base}_80_mrdb_sequences.fasta`);
    expect(exportFilename("1.6.0", "manifest", 88, ids)).toBe(`${base}_selection.json`);
  });

  // PR-3a regression: PR-2 named files only by the filter hash, so two sort orders produced files with
  // different row order but identical names.
  it("same filters with different sort orders keep selection_id but get distinct export_id and file names", () => {
    const q = "group=all&evidence=E1";
    const variants = [exportIds(q, "", "asc"), exportIds(q, "length", "asc"), exportIds(q, "length", "desc"), exportIds(q, "mrdb_acc", "asc")];
    expect(new Set(variants.map((v) => v.selection_id)).size).toBe(1);
    expect(new Set(variants.map((v) => v.export_id)).size).toBe(variants.length);
    expect(new Set(variants.map((v) => v.sort_token))).toEqual(new Set(["index", "length:asc", "length:desc", "mrdb_acc:asc"]));
    for (const kind of ["records_tsv", "records_fasta", "mrdb_fasta", "manifest"] as const) {
      expect(new Set(variants.map((v) => exportFilename("1.6.0", kind, 88, v))).size).toBe(variants.length);
    }
    // Different filters give different selection ids even with the same sort.
    expect(exportIds("group=all", "length", "asc").selection_id).not.toBe(variants[1].selection_id);
  });

  it("sort direction is ignored when no sort key is set (index order)", () => {
    expect(exportIds("group=all", "", "asc")).toEqual(exportIds("group=all", "", "desc"));
    expect(exportIds("group=all", "length", "bogus").sort_token).toBe("length:asc");
  });

  it("selection manifest lists exactly the file names the menu writes", () => {
    const st = parseBrowse(new URLSearchParams("group=all&evidence=E1")).state;
    const sel = applyFilters(rows(), st);
    const m = manifest();
    const q = filterQuery(st);
    for (const [key, dir] of [["", "asc"], ["length", "desc"], ["length", "asc"]] as const) {
      const sm = selectionManifest({
        release: m.dataset_release, releaseDate: m.release_date, schemaVersion: m.schema_version,
        websiteVersion: m.website_version, dbSha: m.source_db.sha256, filterQ: q, sortKey: key, sortDir: dir,
        rows: sel, now: new Date("2026-10-10T00:00:00Z"),
      });
      const ids = exportIds(q, key, dir);
      const nM = new Set(sel.map((r) => r.mrdb_acc)).size;
      expect(sm.selection_id).toBe(ids.selection_id);
      expect(sm.export_id).toBe(ids.export_id);
      expect(sm.sort_token).toBe(ids.sort_token);
      expect(sm.sort).toEqual(key ? { key, dir } : null);
      expect(sm.files).toEqual({
        records_tsv: exportFilename(m.dataset_release, "records_tsv", sel.length, ids),
        records_fasta: exportFilename(m.dataset_release, "records_fasta", sel.length, ids),
        mrdb_fasta: exportFilename(m.dataset_release, "mrdb_fasta", nM, ids),
        manifest: exportFilename(m.dataset_release, "manifest", sel.length, ids),
      });
      for (const f of Object.values(sm.files)) expect(f).toContain(`_${ids.selection_id}_${ids.export_id}_`);
    }
  });

  it("manifest records counts, provenance and filters", () => {
    const st = parseBrowse(new URLSearchParams("group=all&evidence=E1")).state;
    const sel = applyFilters(rows(), st);
    const m = manifest();
    const sm = selectionManifest({
      release: m.dataset_release, releaseDate: m.release_date, schemaVersion: m.schema_version,
      websiteVersion: m.website_version, dbSha: m.source_db.sha256, filterQ: filterQuery(st), sortKey: "", sortDir: "asc",
      rows: sel, now: new Date("2026-10-10T00:00:00Z"),
    });
    expect(sm.n_source_records).toBe(88);
    expect(sm.n_engineered_in_selection).toBe(0);
    expect(sm.filters).toEqual({ group: "all", evidence: "E1" });
    expect(sm.source_db_sha256).toBe("b8215cffa9d2fdab1e65b904f4bafbe9edf6578aed7b4fb028a890850e704c2d");
    expect(sm.tsv_columns).toEqual(TSV_COLUMNS);
    expect(DEFAULT_STATE.group).toBe("member");
  });
});
