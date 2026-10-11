import { describe, expect, it } from "vitest";
import { escapeHtml, safeExternalUrl } from "../../src/lib/safe";
import { CSP, CSP_DIRECTIVES } from "../../csp.config";
import { parseHash } from "../../src/app/routes";

describe("PR-6 output hardening", () => {
  it("keeps http(s), mailto and relative URLs unchanged", () => {
    for (const u of ["https://doi.org/10.1/x", "http://example.org/a?b=1", "mailto:a@b.org", "data/v1.6.0/phylogeny/README.md", "./x.tsv", "#/record/P02945"])
      expect(safeExternalUrl(u)).toBe(u);
  });
  it("drops script-capable and unknown schemes", () => {
    for (const u of ["javascript:alert(1)", " JavaScript:alert(1)", "java\tscript:alert(1)", "data:text/html,<script>alert(1)</script>", "vbscript:x", "file:///etc/passwd", "", null, undefined])
      expect(safeExternalUrl(u as string)).toBeUndefined();
  });
  it("escapes HTML metacharacters for tooltip HTML", () => {
    expect(escapeHtml(`<img src=x onerror="a('b')">&`)).toBe("&lt;img src=x onerror=&quot;a(&#39;b&#39;)&quot;&gt;&amp;");
  });
});

describe("PR-6 CSP", () => {
  it("allows no inline or eval script, no plugins, and only the three structure hosts", () => {
    expect(CSP_DIRECTIVES["script-src"]).toEqual(["'self'"]);
    expect(CSP).not.toMatch(/unsafe-eval|script-src[^;]*unsafe-inline/);
    expect(CSP_DIRECTIVES["object-src"]).toEqual(["'none'"]);
    expect(CSP_DIRECTIVES["connect-src"]).toEqual(["'self'", "https://models.rcsb.org", "https://files.rcsb.org", "https://alphafold.ebi.ac.uk"]);
  });
});

describe("PR-6 malformed routes never throw", () => {
  const nasty = ["#/record/%E0%A4%A", "#/record/<script>alert(1)</script>", "#/browse?clade=%", "#/%", "#//////", "#/record/" + "A".repeat(5000),
    "#/clade/%3Cimg%20src%3Dx%3E", "#/browse?" + "q=x&".repeat(2000), "#/phylogeny?tip=%ZZ", "#/search?q=%00", "#/record/P02945/extra/parts", "#\u0000"];
  for (const h of nasty) it(`parses ${h.slice(0, 40)}`, () => { expect(() => parseHash(h)).not.toThrow(); });
});
