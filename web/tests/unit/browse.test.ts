import { describe, expect, it } from "vitest";
import {
  activeFilterKeys, applyFilters, DEFAULT_STATE, filterQuery, parseBrowse, serializeBrowse, sortRows, statusesForGroup,
  type BrowseState,
} from "../../src/lib/browse";
import { distCount, distribution, mv } from "../../src/lib/summary";
import { rows, summary } from "./helpers";

const P = (q: string) => parseBrowse(new URLSearchParams(q));

describe("Browse URL state", () => {
  it("defaults to Type-I members with engineered constructs hidden", () => {
    const { state, ignored } = P("");
    expect(state).toEqual(DEFAULT_STATE);
    expect(ignored).toEqual([]);
    expect(serializeBrowse(state)).toBe("");
  });

  it("round-trips a fully specified state through the canonical query string", () => {
    const s: BrowseState = {
      ...DEFAULT_STATE, group: "all", status: "typeI_member_core", q: "halo rhodopsin", func: "proton_pump",
      evidence: "E1", clade: "MR_CLD3_017", tent: true, sub: "MR_CLD3_017.01", state: "tentative", domain: "none",
      motif: "DTE", residue: "K", pdb: true, pdbid: "1C3W", afdb: "0", conflict: true, curated: true, eng: true, pub: true,
      lin: "Bacteroidota", lmin: 200, lmax: 400, sort: "length", dir: "desc", page: 3, size: 100,
    };
    const q = serializeBrowse(s);
    const back = P(q);
    expect(back.ignored).toEqual([]);
    expect(back.state).toEqual(s);
    expect(serializeBrowse(back.state)).toBe(q);
  });

  it("reports invalid parameters instead of silently applying them", () => {
    const { state, ignored } = P("evidence=E9&group=foo&clade=XYZ&page=0&size=7&domain=Viruses&bogus=1&sort=nope&eng=maybe");
    expect(state).toEqual(DEFAULT_STATE);
    expect(ignored.map((x) => x.key).sort()).toEqual(["bogus", "clade", "domain", "eng", "evidence", "group", "page", "size", "sort"].sort());
  });

  it("accepts status=<group name> as an alias for group (spec example status=member)", () => {
    expect(P("status=member").state.group).toBe("member");
    expect(P("status=candidate").state).toMatchObject({ group: "candidate", status: "" });
    expect(P("status=typeI_member_curated").state).toMatchObject({ group: "member", status: "typeI_member_curated" });
    expect(P("status=all").ignored).toEqual([{ key: "status", value: "all" }]);
  });

  it("filterQuery excludes sort and paging; activeFilterKeys excludes population controls", () => {
    const s = { ...P("group=all&eng=1&func=sensory&sort=length&page=2").state };
    expect(filterQuery(s)).toBe("group=all&func=sensory&eng=1");
    expect(activeFilterKeys(s)).toEqual(["func"]);
  });
});

describe("Browse filtering on the exported index", () => {
  const all = rows();
  const S = summary();
  const count = (q: string) => applyFilters(all, P(q).state).length;

  it("index has 5,466 source records and 5,299 MRDB accessions", () => {
    expect(all.length).toBe(mv(S, "records_total"));
    expect(all.length).toBe(5466);
    expect(new Set(all.map((r) => r.mrdb_acc)).size).toBe(5299);
  });

  it("default view = Type-I members minus engineered constructs (3,085)", () => {
    const members = mv(S, "typeI_members");
    const engMembers = all.filter((r) => r.membership_group === "member" && r.is_engineered).length;
    expect(count("")).toBe(members - engMembers);
    expect(count("")).toBe(3085);
    expect(count("eng=1")).toBe(members);
  });

  it("group tabs (engineered included) reproduce the membership_group distribution", () => {
    const d = distribution(S, "membership_group");
    for (const g of ["member", "candidate", "boundary", "outgroup", "rejected"]) {
      expect(count(`group=${g}&eng=1`)).toBe(distCount(d, g));
    }
    expect(count("group=all&eng=1")).toBe(5466);
    expect(count("group=all")).toBe(mv(S, "records_counted"));
  });

  it("evidence and function filters over counted records reproduce the summary distributions", () => {
    const ev = distribution(S, "evidence_level_counted");
    for (const e of ["E1", "E2", "E3", "E4", "E5"]) expect(count(`group=all&evidence=${e}`)).toBe(distCount(ev, e));
    const fc = distribution(S, "func_class_counted");
    for (const it of fc.items) expect(count(`group=all&func=${it.key}`)).toBe(it.value);
  });

  it("domain=none selects records without an assigned domain", () => {
    const d = distribution(S, "tax_domain_counted");
    expect(count("group=all&domain=none")).toBe(distCount(d, null));
    expect(count("group=all&domain=Archaea")).toBe(distCount(d, "Archaea"));
  });

  it("every status of a group is covered by statusesForGroup", () => {
    const groups = new Map<string, Set<string>>();
    for (const r of all) (groups.get(r.membership_group) ?? groups.set(r.membership_group, new Set()).get(r.membership_group)!).add(r.membership_status);
    for (const [g, ss] of groups) for (const s of ss) expect(statusesForGroup(g as never)).toContain(s);
  });

  it("PDB, AFDB, publications and length filters", () => {
    expect(count("group=all&eng=1&pdb=1")).toBe(mv(S, "records_with_pdb"));
    expect(count("group=all&eng=1&afdb=1")).toBe(mv(S, "records_with_afdb"));
    expect(count("group=all&eng=1&pdbid=1C3W")).toBe(1);
    expect(applyFilters(all, P("group=all&eng=1&pdbid=1C3W").state)[0].source_acc).toBe("P02945");
    const lr = applyFilters(all, P("group=all&eng=1&lmin=250&lmax=260").state);
    expect(lr.every((r) => r.length >= 250 && r.length <= 260)).toBe(true);
  });
});

describe("sorting", () => {
  const all = rows();
  it("is stable, numeric for numbers, and puts missing values last in both directions", () => {
    for (const dir of ["asc", "desc"] as const) {
      const s = sortRows(all, "membership_score", dir);
      const vals = s.map((r) => r.membership_score);
      const firstNull = vals.findIndex((v) => v === null);
      if (firstNull >= 0) expect(vals.slice(firstNull).every((v) => v === null)).toBe(true);
      const nums = vals.filter((v): v is number => v !== null);
      for (let i = 1; i < nums.length; i++) expect(dir === "asc" ? nums[i] >= nums[i - 1] : nums[i] <= nums[i - 1]).toBe(true);
    }
    const byLen = sortRows(all, "length", "asc");
    for (let i = 1; i < byLen.length; i++) {
      if (byLen[i].length === byLen[i - 1].length) expect(byLen[i]._i).toBeGreaterThan(byLen[i - 1]._i);
    }
    expect(sortRows(all, "", "asc")).toBe(all);
  });
});
