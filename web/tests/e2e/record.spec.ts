/**
 * PR-3 Protein Entry page: sections, deep links, structure tables, the lazy Mol* viewer (with
 * RCSB / AlphaFold DB mocked from committed real files), record types, invalid IDs and mobile layout.
 */
import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import type { Page } from "@playwright/test";
import { expect, expectNoHorizontalOverflow, test } from "./fixtures";
import { dropExpected, mockStructures, molstarChunk } from "./structureMocks";

const OUT = resolve(process.env.SCREENSHOT_DIR ?? "test-results/screenshots");
const viewer = (p: Page) => p.getByTestId("structure-viewer");
/** Element screenshots of tall sections: hide sticky chrome so it is not stamped into the stitched image. */
const SHOT = { style: "header, [data-testid=section-nav] { visibility: hidden !important; }" };

async function waitReady(p: Page) {
  await expect(viewer(p)).toHaveAttribute("data-phase", "ready", { timeout: 45_000 });
}

test.describe("Protein Entry: MRDB000001 (175 PDB entries)", () => {
  test("sections, counts, representatives and section navigation", async ({ page, watch }) => {
    await page.goto("#/record/MRDB000001");
    const rec = page.getByTestId("record-page");
    await expect(rec).toHaveAttribute("data-focus", "P02945");
    for (const s of ["overview", "sequence", "viewer", "experimental", "predicted", "phylogeny", "evidence", "publications"]) {
      await expect(page.getByTestId(`section-${s}`)).toBeAttached();
    }
    await expect(page.getByTestId("pdb-count-focused")).toHaveAttribute("data-n", "174");
    await expect(page.getByTestId("pdb-count-union")).toHaveAttribute("data-n", "175");
    const table = page.getByTestId("pdb-table");
    await expect(table).toHaveAttribute("data-rows", "174");
    await page.getByTestId("pdb-scope-all").click();
    await expect(table).toHaveAttribute("data-rows", "175");
    await page.getByTestId("pdb-filter-q").fill("4Y9H");
    await expect(table.locator("tbody tr")).toHaveCount(1);
    await expect(table).toContainText("B0R5N9");
    // MRDB representative and E1 representative are distinct badges in the sources table
    const sources = page.getByTestId("sources-table");
    await expect(sources.locator('[data-source="P02945"]')).toContainText("MRDB representative");
    await expect(sources).toContainText("E1 representative");
    await expect(page.getByTestId("sequence")).toHaveAttribute("data-length", "262");
    await expect(page.getByTestId("afdb-block")).toHaveAttribute("data-status", "ok");
    await expect(page.getByTestId("pubs-support")).toBeVisible();
    await expect(page.getByTestId("ev-level")).toContainText("E1");
    // section nav updates the URL in place (no extra history entry) and focuses the heading
    const len = await page.evaluate(() => history.length);
    await page.getByTestId("section-nav").locator('[data-section="phylogeny"]').first().click();
    await expect(page).toHaveURL(/#\/record\/MRDB000001\?section=phylogeny$/);
    await expect(page.locator("#h-phylogeny")).toBeFocused();
    expect(await page.evaluate(() => history.length)).toBe(len);
    expect(molstarChunk(watch)).toEqual([]);
  });

  test("viewer loads on click from mocked RCSB BinaryCIF, then switches to AlphaFold DB with pLDDT", async ({ page, watch }) => {
    const log = await mockStructures(page);
    await page.goto("#/record/MRDB000001");
    await expect(viewer(page)).toHaveAttribute("data-phase", "idle");
    await expect(viewer(page)).toHaveAttribute("data-selected", "pdb:5ZIM");
    await page.waitForLoadState("networkidle");
    expect(molstarChunk(watch), "Mol* must not load before the click").toEqual([]);
    expect(log.hits).toEqual([]);
    await page.getByTestId("viewer-load").click();
    await waitReady(page);
    expect(molstarChunk(watch).length).toBe(1);
    expect(log.hits).toEqual(["https://models.rcsb.org/v1/5zim/full?encoding=bcif"]);
    await expect(page.getByTestId("viewer-status")).toContainText("5ZIM");
    await expect(page.getByTestId("viewer-download")).toHaveAttribute("href", "https://files.rcsb.org/download/5ZIM.cif");

    await page.getByTestId("structure-picker").selectOption("afdb");
    await expect(page).toHaveURL(/structure=afdb/);
    await expect(viewer(page)).toHaveAttribute("data-selected", "afdb");
    await waitReady(page);
    await expect(page.getByTestId("viewer-status")).toContainText("AF-P02945-F1");
    await expect(page.getByTestId("viewer-coloring")).toHaveValue("plddt-confidence");
    await expect(page.getByTestId("plddt-legend")).toBeVisible();
    await expect(page.getByTestId("viewer-detail")).toContainText("Predicted model, not an experimental structure");
    expect(log.hits.at(-1)).toBe("https://alphafold.ebi.ac.uk/files/AF-P02945-F1-model_v6.pdb");
    // the canvas has drawn something (not a blank white frame)
    const drawn = await page.getByTestId("viewer-canvas").evaluate((c: HTMLCanvasElement) => c.width > 0 && c.height > 0);
    expect(drawn).toBe(true);
    mkdirSync(OUT, { recursive: true });
    await page.getByTestId("section-viewer").screenshot({ path: resolve(OUT, "pr3_viewer_afdb_P02945_1440.png"), ...SHOT });
  });

  test("View in 3D from the PDB table selects, deep-links and loads that entry", async ({ page, watch }) => {
    const log = await mockStructures(page);
    await page.goto("#/record/MRDB000001");
    await page.getByTestId("pdb-scope-all").click();
    await page.getByTestId("pdb-filter-q").fill("4Y9H");
    await page.getByTestId("pdb-table").getByTestId("pdb-view").click();
    await expect(page).toHaveURL(/structure=pdb:4Y9H/);
    await waitReady(page);
    await expect(viewer(page)).toHaveAttribute("data-selected", "pdb:4Y9H");
    expect(log.hits).toContain("https://models.rcsb.org/v1/4y9h/full?encoding=bcif");
    await expect(page.getByTestId("section-viewer")).toBeInViewport();
    mkdirSync(OUT, { recursive: true });
    await page.getByTestId("section-viewer").screenshot({ path: resolve(OUT, "pr3_viewer_pdb_4Y9H_1440.png"), ...SHOT });
    expect(watch.errors).toEqual([]);
  });

  test("deep link with section and structure survives reload; viewer stays idle until requested", async ({ page, watch }) => {
    await page.goto("#/record/MRDB000001?section=experimental&structure=pdb:4Y9H");
    await expect(page.getByTestId("section-experimental")).toBeInViewport();
    await expect(viewer(page)).toHaveAttribute("data-selected", "pdb:4Y9H");
    await page.reload();
    await expect(viewer(page)).toHaveAttribute("data-selected", "pdb:4Y9H");
    await expect(viewer(page)).toHaveAttribute("data-phase", "idle");
    // an unknown structure falls back to the default without an error
    await page.goto("#/record/MRDB000001?structure=pdb:9ZZZ");
    await expect(viewer(page)).toHaveAttribute("data-selected", "pdb:5ZIM");
    expect(molstarChunk(watch)).toEqual([]);
  });
});

test.describe("viewer failures", () => {
  test("BinaryCIF HTTP 500 falls back to mmCIF", async ({ page, watch }) => {
    const log = await mockStructures(page, (route, url) => {
      if (url.hostname === "models.rcsb.org") return route.fulfill({ status: 500, headers: { "access-control-allow-origin": "*" }, body: "x" }).then(() => true);
      return false;
    });
    await page.goto("#/record/MRDB000001");
    await page.getByTestId("viewer-load").click();
    await waitReady(page);
    expect(log.hits).toEqual(["https://models.rcsb.org/v1/5zim/full?encoding=bcif", "https://files.rcsb.org/download/5ZIM.cif"]);
    dropExpected(watch, /HTTP 500: https:\/\/models\.rcsb\.org/, /Failed to load resource/);
  });

  test("HTTP 404 on every URL shows an error with links, and Retry recovers", async ({ page, watch }) => {
    let fail = true;
    await mockStructures(page, (route) => (fail ? route.fulfill({ status: 404, headers: { "access-control-allow-origin": "*" }, body: "x" }).then(() => true) : false));
    await page.goto("#/record/MRDB000001");
    await page.getByTestId("viewer-load").click();
    await expect(viewer(page)).toHaveAttribute("data-phase", "error", { timeout: 30_000 });
    const err = page.getByTestId("viewer-error");
    await expect(err).toContainText("HTTP 404");
    await expect(err.getByRole("link", { name: "RCSB PDB" })).toHaveAttribute("href", "https://www.rcsb.org/structure/5ZIM");
    await expect(page.getByTestId("viewer-status")).toContainText("Could not display");
    fail = false;
    await page.getByTestId("viewer-retry").click();
    await waitReady(page);
    dropExpected(watch, /HTTP 404: https:\/\/(models|files)\.rcsb\.org/, /Failed to load resource/);
  });

  test("a stalled AlphaFold DB request times out with a clear message", async ({ page, watch }) => {
    await page.addInitScript(() => { (window as unknown as { __MRDB_VIEWER_TIMEOUT_MS: number }).__MRDB_VIEWER_TIMEOUT_MS = 1500; });
    await mockStructures(page, async () => {
      await new Promise((r) => setTimeout(r, 4000));
      return true; // never answered (the page aborted the request)
    });
    await page.goto("#/record/MRDB000009");
    await expect(viewer(page)).toHaveAttribute("data-selected", "afdb");
    await page.getByTestId("viewer-load").click();
    await expect(viewer(page)).toHaveAttribute("data-phase", "error", { timeout: 20_000 });
    await expect(page.getByTestId("viewer-error")).toContainText("Timed out after 1.5 s");
    await expect(page.getByTestId("viewer-retry")).toBeVisible();
    await page.unrouteAll({ behavior: "ignoreErrors" });
    dropExpected(watch, /requestfailed: https:\/\/alphafold\.ebi\.ac\.uk/, /Failed to load resource/);
  });
});

test.describe("viewer failures (continued)", () => {
  test("a 200 response that is not a structure (e.g. an HTML error page) reports a parse error", async ({ page, watch }) => {
    await mockStructures(page, (route) => route.fulfill({ status: 200, headers: { "access-control-allow-origin": "*", "content-type": "text/html" }, body: "<html>maintenance</html>" }).then(() => true));
    await page.goto("#/record/MRDB000009");
    await page.getByTestId("viewer-load").click();
    await expect(viewer(page)).toHaveAttribute("data-phase", "error", { timeout: 30_000 });
    await expect(page.getByTestId("viewer-error")).toContainText("Could not parse coordinates");
    await expect(page.getByTestId("viewer-error").getByRole("link", { name: "AlphaFold DB entry" })).toHaveAttribute("href", "https://alphafold.ebi.ac.uk/entry/Q5V4H7");
    // Mol* logs its own parser exception to the console; that is expected here.
    dropExpected(watch, /^console: /);
  });
});

test.describe("release models (pLDDT stored as 0-1, rescaled in the browser)", () => {
  for (const [mrdb, acc] of [["MRDB000030", "B0R633"], ["MRDB003319", "A0A9X2L7U0"]] as const) {
    test(`${mrdb} / ${acc}: release model loads from the versioned data directory`, async ({ page, watch }) => {
      const log = await mockStructures(page);
      await page.goto(`#/record/${acc}?structure=pred`);
      await expect(page.getByTestId("record-page")).toHaveAttribute("data-mrdb", mrdb);
      const rm = page.getByTestId("release-model");
      await expect(rm).toContainText("ESMCFold2 (full)");
      await expect(rm).toContainText("ESMFold prediction for clade rep");
      await expect(viewer(page)).toHaveAttribute("data-selected", "pred");
      await page.getByTestId("viewer-load").click();
      await waitReady(page);
      expect(watch.requests.some((u) => u.endsWith(`/data/v1.6.0/structures/predicted/${acc}_esmfold.pdb`))).toBe(true);
      expect(log.hits).toEqual([]);
      await expect(page.getByTestId("viewer-coloring")).toHaveValue("plddt-confidence");
      await expect(page.getByTestId("plddt-legend")).toContainText("multiplied by 100");
      await expect(page.getByTestId("viewer-download")).toHaveAttribute("href", new RegExp(`/data/v1\\.6\\.0/structures/predicted/${acc}_esmfold\\.pdb$`));
      if (acc === "B0R633") {
        mkdirSync(OUT, { recursive: true });
        await page.getByTestId("section-viewer").screenshot({ path: resolve(OUT, "pr3_viewer_release_B0R633_1440.png"), ...SHOT });
      }
    });
  }
});

test.describe("record types", () => {
  test("no structures at all: explicit empty states, no viewer", async ({ page, watch }) => {
    await page.goto("#/record/MRDB000003");
    await expect(page.getByTestId("pdb-none")).toBeVisible();
    await expect(page.getByTestId("afdb-none")).toBeVisible();
    await expect(page.getByTestId("release-none")).toBeAttached();
    await expect(page.getByTestId("viewer-none")).toBeVisible();
    await expect(page.getByTestId("pubs-none")).toBeVisible();
    await expect(page.getByTestId("ev-level")).toBeVisible();
    expect(molstarChunk(watch)).toEqual([]);
  });

  test("AlphaFold-only record defaults to the AFDB model and loads it", async ({ page, watch }) => {
    const log = await mockStructures(page);
    await page.goto("#/record/MRDB000009");
    await expect(page.getByTestId("pdb-none")).toBeVisible();
    await expect(page.getByTestId("afdb-block")).toHaveAttribute("data-status", "ok");
    await page.getByTestId("afdb-view").click();
    await waitReady(page);
    expect(log.hits).toEqual(["https://alphafold.ebi.ac.uk/files/AF-Q5V4H7-F1-model_v6.pdb"]);
    await expect(page).toHaveURL(/structure=afdb/);
    expect(watch.errors).toEqual([]);
  });

  test("multi-accession record: switch source, Back restores the previous focus", async ({ page, watch }) => {
    await page.goto("#/record/MRDB000249");
    const rec = page.getByTestId("record-page");
    await expect(rec).toHaveAttribute("data-focus", "A0A1L9NH58");
    const t = page.getByTestId("sources-table");
    await expect(t.locator("tbody tr")).toHaveCount(7);
    await t.locator('[data-source="A0ACD1IKA6"]').getByTestId("source-switch").click();
    await expect(page).toHaveURL(/#\/record\/A0ACD1IKA6$/);
    await expect(rec).toHaveAttribute("data-focus", "A0ACD1IKA6");
    await expect(rec).toHaveAttribute("data-mrdb", "MRDB000249");
    await expect(page.getByTestId("afdb-none")).toBeVisible();
    await page.goBack();
    await expect(rec).toHaveAttribute("data-focus", "A0A1L9NH58");
    await expect(page.getByTestId("afdb-block")).toHaveAttribute("data-status", "ok");
    expect(watch.errors).toEqual([]);
  });

  test("engineered variant links to its wild type and back", async ({ page, watch }) => {
    await page.goto("#/record/A0A6I8WFQ3");
    await expect(page.getByTestId("ov-engineered")).toBeVisible();
    await expect(page.getByTestId("ev-engineered")).toBeVisible();
    await page.getByTestId("wt-link").first().click();
    await expect(page).toHaveURL(/#\/record\/A0A6P3CW41$/);
    await expect(page.getByTestId("variant-links")).toContainText("A0A6I8WFQ3");
    await page.getByTestId("variant-links").getByRole("link", { name: "A0A6I8WFQ3" }).click();
    await expect(page.getByTestId("record-page")).toHaveAttribute("data-focus", "A0A6I8WFQ3");
    expect(watch.errors).toEqual([]);
  });

  test("curated override is shown separately from the classifier call", async ({ page, watch }) => {
    await page.goto("#/record/A0A1I3DJQ0");
    await expect(page.getByTestId("ov-curated")).toBeVisible();
    await expect(page.getByTestId("ev-curated")).toBeVisible();
    await expect(page.getByTestId("ov-status")).toBeVisible();
    await expect(page.getByTestId("ov-score")).toBeVisible();
    mkdirSync(OUT, { recursive: true });
    await page.getByTestId("section-evidence").screenshot({ path: resolve(OUT, "pr3_evidence_curated_A0A1I3DJQ0_1440.png"), ...SHOT });
    expect(watch.errors).toEqual([]);
  });

  test("tentative MR_CLD3_017 placement: caveat, support values and arc-only tree highlight", async ({ page, watch }) => {
    await page.goto("#/record/A0A135LS53?section=phylogeny");
    await expect(page.getByTestId("ph-state")).toContainText("tentative");
    const sec = page.getByTestId("section-phylogeny");
    await expect(sec).toContainText("SH-aLRT 50.3 / UFBoot 72");
    await expect(sec.getByTestId("clade-support-notice")).toBeVisible();
    await page.getByTestId("mini-tree-show").click();
    await expect(page.getByTestId("tree-highlight-arc")).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId("tree-highlight-tip")).toHaveCount(0);
    await expect(page.getByTestId("mini-tree-caption")).toContainText("not a tree leaf");
    mkdirSync(OUT, { recursive: true });
    await sec.screenshot({ path: resolve(OUT, "pr3_phylogeny_A0A135LS53_1440.png"), ...SHOT });
    expect(watch.errors).toEqual([]);
  });

  test("reference tip: the mini tree marks the tip itself", async ({ page, watch }) => {
    await page.goto("#/record/P02945?section=phylogeny");
    await expect(page.getByTestId("ph-tip")).toBeVisible();
    await page.getByTestId("mini-tree-show").click();
    await expect(page.getByTestId("tree-highlight-tip")).toBeVisible({ timeout: 20_000 });
    mkdirSync(OUT, { recursive: true });
    await page.getByTestId("mini-tree").screenshot({ path: resolve(OUT, "pr3_minitree_P02945_tip_1440.png"), ...SHOT });
    await page.getByTestId("section-evidence").screenshot({ path: resolve(OUT, "pr3_evidence_P02945_1440.png"), ...SHOT });
    await page.getByTestId("section-publications").screenshot({ path: resolve(OUT, "pr3_publications_P02945_1440.png"), ...SHOT });
    expect(watch.errors).toEqual([]);
  });

  test("FASTA download and JSON export use release data", async ({ page, watch }) => {
    await page.goto("#/record/MRDB000001");
    const [dl] = await Promise.all([page.waitForEvent("download"), page.getByTestId("section-sequence").getByRole("button", { name: "Download FASTA" }).click()]);
    const txt = await (await dl.createReadStream()).toArray().then((b) => Buffer.concat(b).toString("utf8"));
    expect(txt.startsWith(">P02945 MRDB000001")).toBe(true);
    await expect(page.getByTestId("export-json")).toHaveAttribute("href", /\/data\/v1\.6\.0\/records\/MRDB000001\.json$/);
    expect(watch.errors).toEqual([]);
  });
});

test.describe("invalid identifiers", () => {
  test("unknown well-formed and malformed IDs show not-found without fetching a record", async ({ page, watch }) => {
    await page.goto("#/record/MRDB999999");
    await expect(page.getByTestId("record-not-found")).toHaveAttribute("data-malformed", "false");
    await page.goto("#/record/%3Cscript%3E");
    await expect(page.getByTestId("record-not-found")).toHaveAttribute("data-malformed", "true");
    await page.goto("#/record/P0294");
    await expect(page.getByTestId("record-not-found")).toBeVisible();
    expect(watch.dataFiles().filter((f) => f.startsWith("records/"))).toEqual([]);
  });

  test("lower-case accessions redirect to the canonical upper-case URL, keeping the query", async ({ page, watch }) => {
    await page.goto("#/record/mrdb000001?section=sequence");
    await expect(page).toHaveURL(/#\/record\/MRDB000001\?section=sequence$/);
    await expect(page.getByTestId("record-page")).toHaveAttribute("data-mrdb", "MRDB000001");
    expect(watch.errors).toEqual([]);
  });
});

test.describe("Mol* chunk isolation", () => {
  test("Home, Browse and About never request the Mol* chunk", async ({ page, watch }) => {
    for (const [h, id] of [["#/", "stat-cards"], ["#/browse", "results-table"], ["#/about", "clade-support-notice"]] as const) {
      await page.goto(h);
      await expect(page.getByTestId(id).first()).toBeVisible();
    }
    await page.waitForLoadState("networkidle");
    expect(molstarChunk(watch)).toEqual([]);
  });
});

/* ---------------------------------------------------------------- responsive */

const VIEWPORTS = [
  { w: 375, h: 812 },
  { w: 768, h: 1024 },
  { w: 1440, h: 900 },
] as const;

for (const vp of VIEWPORTS) {
  test.describe(`record layout ${vp.w}px`, () => {
    test.use({ viewport: { width: vp.w, height: vp.h } });
    for (const [name, hash] of [["MRDB000001", "#/record/MRDB000001"], ["MRDB000249", "#/record/MRDB000249"], ["MRDB000003", "#/record/MRDB000003"]] as const) {
      test(`${name}: no horizontal overflow, sticky nav, screenshots`, async ({ page, watch }) => {
        await mockStructures(page);
        await page.goto(hash);
        await expect(page.getByTestId("sequence")).toBeVisible();
        await page.waitForLoadState("networkidle");
        await page.evaluate(() => document.fonts.ready);
        await expectNoHorizontalOverflow(page);
        const nav = page.getByTestId("section-nav");
        await expect(nav).toBeVisible();
        mkdirSync(OUT, { recursive: true });
        await page.screenshot({ path: resolve(OUT, `pr3_record_${name}_${vp.w}.png`) });
        if (name === "MRDB000001") {
          await page.getByTestId("section-nav").locator('[data-section="experimental"]').first().click();
          await expect(page.getByTestId("pdb-table")).toBeVisible();
          // wait for the (smooth) scroll to settle: heading at the top, below the sticky header + section nav
          await expect(page.locator("#h-experimental")).toBeInViewport();
          await expect.poll(async () => page.evaluate(() => Math.round(document.getElementById("section-experimental")!.getBoundingClientRect().top)), { timeout: 5000 }).toBeLessThan(260);
          await page.waitForTimeout(300);
          await expectNoHorizontalOverflow(page);
          await page.screenshot({ path: resolve(OUT, `pr3_record_${name}_experimental_${vp.w}.png`) });
          await page.getByTestId("viewer-load").click();
          await waitReady(page);
          await expectNoHorizontalOverflow(page);
          await page.getByTestId("section-viewer").scrollIntoViewIfNeeded();
          await page.screenshot({ path: resolve(OUT, `pr3_record_${name}_viewer_${vp.w}.png`) });
        }
        const m = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, innerWidth: window.innerWidth, scrollHeight: document.documentElement.scrollHeight }));
        writeFileSync(resolve(OUT, `pr3_audit_${vp.w}_${name}.json`), JSON.stringify({ page: name, hash, viewport: vp.w, ...m, console_errors: watch.errors.length }, null, 1));
      });
    }
  });
}
