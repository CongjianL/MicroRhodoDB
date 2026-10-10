import { describe, expect, it } from "vitest";
import { canonicalRedirect, href, parseHash, routeForQuery, routeTitle } from "../../src/app/routes";

describe("parseHash", () => {
  it("maps root and empty hashes to Home (legacy root #/ now opens Home)", () => {
    for (const h of ["", "#", "#/", "/"]) expect(parseHash(h)).toEqual({ name: "home" });
  });
  it("keeps legacy record deep links (MRDB and source accessions)", () => {
    expect(parseHash("#/record/MRDB000001")).toEqual({ name: "record", accession: "MRDB000001" });
    expect(parseHash("#/record/P02945")).toEqual({ name: "record", accession: "P02945" });
    expect(parseHash("#/record/P02945%20")).toEqual({ name: "record", accession: "P02945" });
    expect(parseHash("#/record/")).toMatchObject({ name: "not-found" });
  });
  it("parses Browse queries", () => {
    const r = parseHash("#/browse?evidence=E1&group=all");
    expect(r.name).toBe("browse");
    if (r.name === "browse") {
      expect(r.params.get("evidence")).toBe("E1");
      expect(r.params.get("group")).toBe("all");
    }
    expect(parseHash("#/browse/x")).toMatchObject({ name: "not-found" });
  });
  it("routes About, clades, planned pages and unknown paths", () => {
    expect(parseHash("#/about")).toEqual({ name: "about" });
    expect(parseHash("#/clade/MR_CLD3_017")).toEqual({ name: "clade", cladeId: "MR_CLD3_017" });
    for (const p of ["phylogeny", "structures", "search", "downloads", "statistics", "evidence", "watchlist", "methods", "citation", "help"]) {
      expect(parseHash(`#/${p}`)).toEqual({ name: "planned", page: p });
    }
    expect(parseHash("#/novel")).toEqual({ name: "planned", page: "watchlist" });
    expect(parseHash("#/nonsense")).toMatchObject({ name: "not-found" });
    expect(parseHash("#/about/extra/deep")).toMatchObject({ name: "not-found" });
  });
  it("redirects legacy #/novel to #/watchlist", () => {
    expect(canonicalRedirect("#/novel")).toBe("#/watchlist");
    expect(canonicalRedirect("#/novel?x=1")).toBe("#/watchlist");
    expect(canonicalRedirect("#/browse")).toBeNull();
  });
  it("href builders round-trip through parseHash", () => {
    expect(parseHash(href.record("MRDB000011"))).toEqual({ name: "record", accession: "MRDB000011" });
    expect(parseHash(href.clade("MR_CLD3_B01"))).toEqual({ name: "clade", cladeId: "MR_CLD3_B01" });
    expect(parseHash(href.home())).toEqual({ name: "home" });
    expect(routeTitle({ name: "planned", page: "search" })).toMatch(/planned/);
  });
});

describe("routeForQuery (universal search)", () => {
  it("opens record routes for MRDB and UniProt accessions (case-insensitive)", () => {
    expect(routeForQuery("MRDB000001")).toBe("#/record/MRDB000001");
    expect(routeForQuery(" p02945 ")).toBe("#/record/P02945");
    expect(routeForQuery("A0A135LS53")).toBe("#/record/A0A135LS53");
  });
  it("opens Browse over all records (engineered included) for everything else", () => {
    expect(routeForQuery("1C3W")).toBe("#/browse?group=all&eng=1&pdbid=1C3W");
    expect(routeForQuery("mr_cld3_017")).toBe("#/browse?group=all&eng=1&clade=MR_CLD3_017");
    expect(routeForQuery("MR_CLD3_017.01")).toBe("#/browse?group=all&eng=1&sub=MR_CLD3_017.01");
    expect(routeForQuery("halobacterium")).toBe("#/browse?group=all&eng=1&q=halobacterium");
    expect(routeForQuery("")).toBe("#/browse");
  });
  it("does not treat purely numeric 4-character strings as PDB IDs", () => {
    expect(routeForQuery("1234")).toBe("#/browse?group=all&eng=1&q=1234");
  });
});
