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
  EXTRA_TSV_COLUMNS, exportFilename, fastaHeader, fnv1a, LEGACY_TSV_COLUMNS, selectionManifest, toFasta, toTSV, toUniqueFasta,
  tsvCell, TSV_COLUMNS, wrap60,
} from "../../src/lib/exporters";
import { legacy, legacyRows, manifest, readData, rows } from "./helpers";

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
    expect(ours === legacyFasta).toBe(true);
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
  it("file names encode release, selection hash and count", () => {
    const q = filterQuery(parseBrowse(new URLSearchParams("evidence=E1&group=all")).state);
    expect(q).toBe("group=all&evidence=E1");
    expect(fnv1a("")).toBe("811c9dc5");
    expect(exportFilename("1.6.0", "records_tsv", 88, q)).toBe(`microrhododb_v1.6.0_browse_${fnv1a(q)}_88_source_records.tsv`);
    expect(exportFilename("1.6.0", "manifest", 88, q)).toBe(`microrhododb_v1.6.0_browse_${fnv1a(q)}_selection.json`);
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
    expect(sm.source_db_sha256).toBe("379a254356c6489a2b9e0600d501d76d22bc8e3ced4cfbdd5160fb00c3dce17f");
    expect(sm.tsv_columns).toEqual(TSV_COLUMNS);
    expect(DEFAULT_STATE.group).toBe("member");
  });
});
