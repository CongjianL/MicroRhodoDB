/**
 * PR-7c.2 Ecology and habitat: view-model tests on the exported sidecar (web/public/data/v1.6.1/habitat) plus
 * adversarial fixtures. The view model must show every exported item exactly once, never merge or resolve values,
 * keep host separate from physical habitat, link ENVO only for verified, unquarantined IDs, and reject files that do
 * not match the record file.
 */
import { readdirSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import type { HabitatItem, HabitatRecordFile, HabitatSourceEntry, HabitatSummary } from "../../src/data/habitatTypes";
import type { MrdbEntry } from "../../src/data/types";
import { SECTIONS } from "../../src/lib/entry";
import {
  GRADE_INFO, HABITAT_ROLES, NO_LINK_TEXT, accessionUrl, auditReasonText, auditStatusText, checkHabitatFile, doiUrl, envoLinks, envoUrl, habitatView,
  hostLabel, hostStatusText, itemUrl, missingnessText, pubmedUrl, sourceRows, valueText,
} from "../../src/lib/habitat";
import { safeExternalUrl } from "../../src/lib/safe";
import { WEB, json } from "./helpers";

const HAB_DIR = resolve(WEB, "public/data/v1.6.1/habitat/records");
const files = (): HabitatRecordFile[] =>
  readdirSync(HAB_DIR).filter((f) => f.endsWith(".json")).sort().map((f) => json<HabitatRecordFile>(`habitat/records/${f}`));
const entries = (): HabitatSourceEntry[] => files().flatMap((f) => f.sources);
const bySource = () => new Map(entries().map((e) => [e.source_acc, e]));
const allItems = (e: HabitatSourceEntry): HabitatItem[] => Object.values(e.items).flat() as HabitatItem[];

/** Every item the section renders, in the order of the view model's blocks. */
function shown(e: HabitatSourceEntry): HabitatItem[] {
  const v = habitatView(e);
  return [
    ...v.physical.flatMap((g) => g.items), ...v.nonstandard, ...v.literatureIsolate, ...v.literatureRejected, ...v.notUsable,
    ...v.host.flatMap((g) => g.items), ...v.hostNotUsable, ...v.hostDetail,
    ...v.collection, ...v.collectionMissing, ...v.organismContext,
  ];
}

const item = (over: Partial<HabitatItem>): HabitatItem => ({
  browser_url: "https://www.ebi.ac.uk/ena/browser/view/SAMN00000001",
  entity_accession: "SAMN00000001",
  envo_ids: [],
  evidence_id: "HE0123456789ab",
  evidence_source: "ena_biosample",
  field: "isolation_source",
  link_index: 0,
  linkage_route: "cds_protein_id",
  literature: null,
  mapping_confidence: "HIGH",
  quarantine: null,
  role: "isolation_source",
  source_url: null,
  value: "soil",
  value_status: "usable",
  ...over,
} as HabitatItem);

// Fixtures are mutated deliberately (tampered files), so clones are untyped.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const clone = (x: unknown): any => JSON.parse(JSON.stringify(x));

describe("PR-7c.2 record section registration", () => {
  it("adds Ecology and habitat after Evidence, keeping all existing sections in order", () => {
    expect(SECTIONS.map((s) => s.id)).toEqual(["overview", "sequence", "experimental", "predicted", "phylogeny", "evidence", "habitat", "publications"]);
    expect(SECTIONS.find((s) => s.id === "habitat")?.label).toBe("Ecology and habitat");
  });
});

describe("PR-7c.2 sidecar coverage", () => {
  it("has one habitat file per MRDB record file and one entry per source record (5299 / 5466)", () => {
    const fs = files();
    expect(fs.length).toBe(5299);
    expect(entries().length).toBe(5466);
    for (const f of fs) {
      const rec = json<MrdbEntry>(`records/${f.mrdb_acc}.json`);
      const srcs = rec.sources.map((s) => s.source_acc);
      for (const a of srcs) {
        const c = checkHabitatFile(f, rec.mrdb_acc, srcs, a);
        expect(c.ok, `${f.mrdb_acc}/${a}`).toBe(true);
      }
      expect(f.sources.filter((s) => s.is_mrdb_representative).map((s) => s.source_acc)).toEqual([rec.representative_source_acc]);
    }
  });

  it("renders every exported item exactly once and drops nothing on real data (59,086 items)", () => {
    let total = 0;
    for (const e of entries()) {
      const v = habitatView(e);
      expect(v.dropped, e.source_acc).toBe(0);
      const ids = shown(e).map((i) => i.evidence_id);
      const want = allItems(e).map((i) => i.evidence_id);
      expect(new Set(ids).size, e.source_acc).toBe(ids.length);
      expect([...ids].sort(), e.source_acc).toEqual([...want].sort());
      total += ids.length;
    }
    expect(total).toBe(59086);
  });

  it("never shows a host value as physical habitat or organism context as the sampling habitat", () => {
    for (const e of entries()) {
      const v = habitatView(e);
      for (const g of v.physical) for (const i of g.items) expect(HABITAT_ROLES.physical as readonly string[]).toContain(i.role);
      for (const g of v.host) for (const i of g.items) expect(i.role).toBe("host");
      for (const i of v.organismContext) expect(i.literature?.scope).toBe("organism");
      for (const i of v.literatureIsolate) expect(i.literature?.scope).toBe("isolate");
    }
  });

  it("groups usable physical values by reporting record without merging distinct values", () => {
    for (const e of entries()) {
      const v = habitatView(e);
      const usable = (e.items.physical as HabitatItem[]).filter((i) => ["isolation_source", "env_broad_scale", "env_local_scale", "env_medium"].includes(i.role) && i.value_status === "usable");
      expect(v.physical.reduce((n, g) => n + g.items.length, 0)).toBe(usable.length);
      for (const g of v.physical) for (const i of g.items) expect(`${i.evidence_source}|${i.entity_accession}`).toBe(g.key);
    }
  });
});

describe("PR-7c.2 grade, host and missingness wording", () => {
  it("matches the audit counts", () => {
    const es = entries();
    const n = (f: (e: HabitatSourceEntry) => boolean) => es.filter(f).length;
    const grades = Object.fromEntries(Object.keys(GRADE_INFO).map((g) => [g, n((e) => e.grade === g)]));
    expect(grades).toEqual({ DIRECT_SAMPLE: 2523, VERIFIED_ISOLATE: 17, ORGANISM_CONTEXT_ONLY: 36, AMBIGUOUS: 59, NOT_REPORTED: 2831, LOOKUP_FAILED: 0, NOT_SEARCHED: 0 });
    expect(n((e) => habitatView(e).missing !== null)).toBe(2831);
    expect(n((e) => habitatView(e).hostOnly !== null)).toBe(186);
    expect(n((e) => habitatView(e).noLink)).toBe(18);
    expect(n((e) => habitatView(e).ambiguity !== null)).toBe(59);
    expect(n((e) => habitatView(e).hostAmbiguity !== null)).toBe(84);
    expect(n((e) => habitatView(e).hostTissue)).toBe(23);
    expect(n((e) => e.host_association_status === "REPORTED")).toBe(671);
    expect(n((e) => e.has_usable_physical_habitat)).toBe(2540);
  });

  it("keys missingness wording on the not-reported scope and link status", () => {
    const es = entries().filter((e) => e.grade === "NOT_REPORTED");
    const texts = new Map<string, number>();
    for (const e of es) texts.set(missingnessText(e)!, (texts.get(missingnessText(e)!) ?? 0) + 1);
    const ends = (suffix: string) => [...texts].filter(([t]) => t.endsWith(suffix)).reduce((a, [, c]) => a + c, 0);
    // scopes: 2796 literature not reviewed, 23 inaccessible, 12 reviewed and not reported (audit not_reported_scope)
    expect(ends("; literature not reviewed.")).toBe(2796);
    expect(ends("; literature not accessible.")).toBe(23);
    expect(ends("; not reported in the reviewed literature either.")).toBe(12);
    expect([...texts].filter(([t]) => t.startsWith("No traceable INSDC")).reduce((a, [, c]) => a + c, 0)).toBe(12);
    expect(texts.size).toBe(6);
    const q = bySource().get("Q53461")!;
    expect(missingnessText(q)).toBe("No traceable INSDC or sample link; sample records could not be checked; literature not reviewed.");
    expect(hostStatusText(q)).toBe(NO_LINK_TEXT);
    // without a sample link the host badge never reads as a checked "not reported"
    const noLinkHost = entries().filter((x) => x.sample_link === "none" && x.host_association_status === "NOT_REPORTED");
    expect(noLinkHost.length).toBe(18);
    for (const e of noLinkHost) expect(hostLabel(e.host_association_status, e.sample_link)).toBe("Host not reported (no sample link)");
    expect(hostLabel("NOT_REPORTED", "traceable")).toBe("Host not reported");
    expect(hostLabel("REPORTED", "traceable")).toBe("Host reported");
    // a grade other than NOT_REPORTED never gets missingness wording
    for (const e of entries().filter((x) => x.grade !== "NOT_REPORTED")) expect(missingnessText(e)).toBeNull();
  });

  it("states the host-only case without calling the host a habitat", () => {
    const e = entries().find((x) => x.flags.includes("host_association_only") && x.host_association_status === "REPORTED")!;
    const v = habitatView(e);
    expect(v.hostOnly).toBe("Physical habitat not reported; host reported.");
    expect(v.physical).toEqual([]);
    expect(v.host.length).toBeGreaterThan(0);
    expect(hostStatusText(e)).toContain("not a physical habitat");
  });

  it("shows the literature-versus-database conflict for A0A411LJN5 and per-source grades for multi-source records", () => {
    const e = bySource().get("A0A411LJN5")!;
    expect(e.grade).toBe("AMBIGUOUS");
    expect(habitatView(e).ambiguity?.label).toBe("Literature differs from database");
    const multi = files().filter((f) => f.sources.length > 1);
    expect(multi.length).toBe(129);
    expect(multi.filter((f) => f.source_grades_differ).length).toBe(43);
    for (const f of multi) {
      for (const s of f.sources) {
        const rows = sourceRows(f, s.source_acc);
        expect(rows.filter((r) => r.current).map((r) => r.source_acc)).toEqual([s.source_acc]);
        expect(rows.map((r) => r.grade)).toEqual(f.sources.map((x) => x.grade));
      }
      expect(f.source_grades_differ).toBe(new Set(f.sources.map((s) => s.grade)).size > 1);
    }
  });

  it("puts invalid placeholders and quarantined identifiers in the not-usable or text-only path", () => {
    const t = habitatView(bySource().get("A0ABS3TAH3")!);
    expect(t.notUsable.filter((i) => i.value_status === "invalid_placeholder").length).toBe(6);
    const q = habitatView(bySource().get("A0A6N7QP32")!);
    const qi = q.physical.flatMap((g) => g.items).filter((i) => i.quarantine);
    expect(qi.map((i) => [i.value, i.quarantine])).toEqual([["00000316", "unprefixed_numeric_identifier"], ["00000316", "unprefixed_numeric_identifier"]]);
    for (const i of qi) expect(envoLinks(i)).toEqual([]);
  });
});

describe("PR-7c.2 ENVO and URL safety", () => {
  it("links ENVO only for well-formed IDs and never for a quarantined item (real data)", () => {
    let links = 0;
    const quarantinedRecords = new Set<string>();
    for (const e of entries()) {
      for (const i of allItems(e)) {
        const l = envoLinks(i);
        if (i.quarantine) {
          quarantinedRecords.add(e.source_acc);
          expect(l).toEqual([]);
        } else {
          expect(l.map((x) => x.id)).toEqual(i.envo_ids);
        }
        for (const x of l) expect(x.url).toMatch(/^https:\/\/purl\.obolibrary\.org\/obo\/ENVO_\d{8}$/);
        links += l.length;
      }
    }
    expect(quarantinedRecords.size).toBe(7);
    expect(links).toBeGreaterThan(0);
  });

  it("rejects malformed ENVO IDs", () => {
    for (const bad of ["ENVO_00000447", "ENVO:0000447", "envo:00000447", "ENVO:00000447 ", "00000316", "ENVO:00000447javascript:"]) expect(envoUrl(bad)).toBeNull();
    expect(envoUrl("ENVO:00000447")).toBe("https://purl.obolibrary.org/obo/ENVO_00000447");
    expect(envoLinks(item({ envo_ids: ["ENVO:00000447"], quarantine: "envo_id_not_found_in_ols" }))).toEqual([]);
    expect(envoLinks(item({ envo_ids: ["ENVO:00000447", "bad"] }))).toEqual([{ id: "ENVO:00000447", url: "https://purl.obolibrary.org/obo/ENVO_00000447" }]);
  });

  it("links sidecar URLs only when https on an allowlisted host", () => {
    for (const bad of ["javascript:alert(1)", "data:text/html,x", "http://www.ebi.ac.uk/x", "https://evil.example/x", "//www.ebi.ac.uk/x", "/relative", "https://user:pw@www.ebi.ac.uk/x", "https://www.ebi.ac.uk.evil.example/x"]) {
      expect(itemUrl(bad), bad).toBeNull();
    }
    expect(itemUrl("https://www.ncbi.nlm.nih.gov/biosample/SAMN13193768")).not.toBeNull();
    for (const e of entries()) for (const i of allItems(e)) {
      expect(itemUrl(i.browser_url), i.evidence_id).toBe(i.browser_url);
      if (i.source_url) expect(itemUrl(i.source_url), i.evidence_id).toBe(i.source_url);
    }
    expect(safeExternalUrl("javascript:alert(1)")).toBeUndefined();
  });

  it("builds accession, PubMed and DOI links only from validated patterns", () => {
    expect(accessionUrl("biosamples", "SAMN13193768")).toBe("https://www.ebi.ac.uk/ena/browser/view/SAMN13193768");
    expect(accessionUrl("embl_protein_ids", "KAK5528741")).toBe("https://www.ebi.ac.uk/ena/browser/view/KAK5528741");
    expect(accessionUrl("biosamples", "javascript:alert(1)")).toBeNull();
    expect(accessionUrl("unknown", "SAMN1")).toBeNull();
    expect(pubmedUrl("1 OR 1")).toBeNull();
    expect(doiUrl("javascript:alert(1)")).toBeNull();
    expect(doiUrl("10.1002/mbo3.1365")).toBe("https://doi.org/10.1002/mbo3.1365");
    for (const bad of ["10.1002", "10.12/x", "10.1002/a b", "x10.1002/mbo3.1365", "10.1002/"]) expect(doiUrl(bad), bad).toBeNull();
    for (const bad of ["SAMN", "xSAMN13193768", "SAMN13193768/../x", "SAMX13193768", "SAMN1319376a"]) {
      expect(accessionUrl("biosamples", bad), bad).toBeNull();
    }
    expect(accessionUrl("bioprojects", "PRJNA1/x")).toBeNull();
    expect(accessionUrl("assemblies", "GCA_000001405")).toBeNull();
    for (const e of entries()) {
      for (const [k, list] of Object.entries(e.accessions)) for (const a of list as string[]) expect(accessionUrl(k, a), `${k}:${a}`).not.toBeNull();
    }
  });
});

describe("PR-7c.2 adversarial fixtures", () => {
  const base = (): HabitatSourceEntry => clone(bySource().get("A0A6N7QP32")!);

  it("drops fabricated or malformed evidence IDs, unknown roles and items in the wrong group", () => {
    const e = base();
    const n0 = allItems(e).length;
    (e.items.physical as HabitatItem[]).push(item({ evidence_id: "HEzzzzzzzzzzzz" }), item({ evidence_id: "XX0123456789ab" }), item({ evidence_id: "HE0123456789abc" }));
    (e.items.physical as HabitatItem[]).push(item({ evidence_id: "HE00000000000a", role: "host", field: "host", value: "Homo sapiens" }));
    (e.items.physical as HabitatItem[]).push(item({ evidence_id: "HE00000000000b", role: "made_up_role" as HabitatItem["role"] }));
    (e.items.host as HabitatItem[]).push(item({ evidence_id: "HE00000000000c", role: "isolation_source" }));
    (e.items.organism_context as HabitatItem[]).push(item({ evidence_id: "HL00000000000d", role: "organism_context", evidence_source: "ena_biosample" }));
    const v = habitatView(e);
    expect(v.dropped).toBe(6);
    expect(shown(e).length).toBe(n0);
    expect(shown(e).some((i) => i.value === "Homo sapiens")).toBe(false);
  });

  it("rejects missing, wrong, merged or incomplete habitat files", () => {
    const f = clone(json<HabitatRecordFile>("habitat/records/MRDB000004.json"));
    const srcs = ["B0R2U4", "P0DMH7"];
    expect(checkHabitatFile(f, "MRDB000004", srcs, "P0DMH7").ok).toBe(true);
    expect(checkHabitatFile(null, "MRDB000004", srcs, "P0DMH7")).toEqual({ ok: false, reason: "missing" });
    expect(checkHabitatFile(f, "MRDB000005", srcs, "P0DMH7")).toEqual({ ok: false, reason: "mrdb_mismatch" });
    const merged = clone(f);
    merged.sources = [merged.sources[0]];
    expect(checkHabitatFile(merged, "MRDB000004", srcs, "B0R2U4")).toEqual({ ok: false, reason: "source_mismatch" });
    const dup = clone(f);
    dup.sources = [dup.sources[0], dup.sources[0]];
    expect(checkHabitatFile(dup, "MRDB000004", srcs, "B0R2U4").ok).toBe(false);
    const extra = clone(f);
    extra.sources.push({ ...clone(f.sources[0]), source_acc: "Q00000" });
    expect(checkHabitatFile(extra, "MRDB000004", srcs, "B0R2U4").ok).toBe(false);
    const foreign = clone(f);
    foreign.sources[1].mrdb_acc = "MRDB000005";
    expect(checkHabitatFile(foreign, "MRDB000004", srcs, "B0R2U4").ok).toBe(false);
    expect(checkHabitatFile(f, "MRDB000004", srcs, "NOT_A_SOURCE").ok).toBe(false);
    expect(checkHabitatFile({ ...f, sources: null } as unknown as HabitatRecordFile, "MRDB000004", srcs, "B0R2U4")).toEqual({ ok: false, reason: "malformed" });
  });

  it("shows an empty field as an explicit empty value, never as an absent field", () => {
    expect(valueText(item({ value: null, value_status: "reported_missing" }))).toBe("(empty value)");
    const empties = entries().flatMap(allItems).filter((i) => i.value === null);
    expect(empties.length).toBe(19);
    for (const i of empties) expect(i.value_status).toBe("reported_missing");
  });
});

describe("PR-7c.2 summary (About these data)", () => {
  it("summary metrics are consistent with the per-record files", () => {
    const s = json<HabitatSummary>("habitat/summary.json");
    const m = new Map(s.metrics.map((x) => [x.id, x]));
    expect(m.get("physical_habitat_usable")?.numerator).toBe(entries().filter((e) => e.has_usable_physical_habitat).length);
    expect(m.get("host_association_only")?.numerator).toBe(entries().filter((e) => e.flags.includes("host_association_only")).length);
    expect(m.get("no_traceable_sample_link")?.numerator).toBe(18);
    for (const x of s.metrics) {
      expect(x.numerator).toBeLessThanOrEqual(x.denominator);
      expect(x.percent).toBeCloseTo(Math.round((x.numerator / x.denominator) * 10000) / 100, 2);
    }
  });

  it("audit status and reason are shown without internal state codes", () => {
    const s = json<HabitatSummary>("habitat/summary.json");
    expect(auditStatusText(s.audit_status)).toBe("partial");
    expect(auditStatusText("PR7C1_AUDIT_COMPLETE")).toBe("complete");
    expect(auditStatusText("UNEXPECTED")).toBe("not stated");
    const reason = auditReasonText(s.audit_status_reason);
    expect(reason).not.toMatch(/[A-Z]{2,}_[A-Z]{2,}/);
    expect(reason).toContain("24 of the 110");
    expect(auditReasonText("a literature LOOKUP_FAILED; 0 LOOKUP_FAILED")).toBe("a literature lookups failed; 0 lookup failed");
  });
});
