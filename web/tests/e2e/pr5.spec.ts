/**
 * PR-5 / Gate G5: Statistics, Evidence, Structures, Watchlist, Search, Downloads, Methods, Citation, Help.
 * Chart totals reconcile with the release, the watchlist is isolated, search golden cases hold, and no
 * page claims to compute the official membership score.
 */
import { expect, test } from "./fixtures";
import { mockStructures, molstarChunk } from "./structureMocks";

const SECTIONS = ["statistics", "evidence", "structures", "watchlist", "search", "downloads", "methods", "citation", "help"];

test.describe("PR-5 section pages", () => {
  test("every section page renders an h1 and never claims to be the official classifier", async ({ page, watch }) => {
    for (const p of SECTIONS) {
      await page.goto(`#/${p}`);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      await page.waitForLoadState("networkidle");
      const text = (await page.locator("main").innerText()).toLowerCase();
      expect(text, `${p} claims an official classification`).not.toMatch(/official (membership )?classifier(?! is)|computes the official membership score/);
    }
    expect(molstarChunk(watch)).toEqual([]);
  });

  test("Statistics: frozen denominators and 12/12 runtime reconciliation", async ({ page, watch }) => {
    await page.goto("#/statistics");
    await expect(page.getByTestId("stat-records-total")).toContainText("5,466");
    await page.waitForLoadState("networkidle");
    const before = watch.dataFiles().filter((f) => f === "records-index.json");
    await expect(page.getByTestId("stat-records-counted")).toContainText("5,460");
    await expect(page.getByTestId("stat-mrdb")).toContainText("5,299");
    await page.getByTestId("load-recount").click();
    await expect(page.getByTestId("recon-status")).toContainText("12 of 12", { timeout: 30_000 });
    expect(watch.dataFiles()).toContain("records-index.json");
    expect.soft(before, "records index fetched before the recount was requested").toEqual([]);
    await expect(page.getByTestId("crosstab-total")).toContainText("5,460");
  });

  test("Evidence: E1 counted 88 vs total 91 (engineered toggle)", async ({ page }) => {
    await page.goto("#/evidence");
    await expect(page.getByTestId("e1-row-count")).toContainText("88");
    await page.getByTestId("e1-include-engineered").check();
    await expect(page.getByTestId("e1-row-count")).toContainText("91");
  });

  test("Structures: release provenance warning; Mol* loads only on click", async ({ page, watch }) => {
    const log = await mockStructures(page);
    await page.goto("#/structures");
    await expect(page.getByTestId("pdb-table")).toBeVisible();
    await page.getByTestId("tab-release").click();
    await expect(page.getByTestId("release-models")).toBeVisible();
    await expect(page.getByTestId("release-provenance-warning").first()).toBeVisible();
    await page.getByTestId("tab-pdb").click();
    await page.waitForLoadState("networkidle");
    expect(molstarChunk(watch), "Mol* must not load before the click").toEqual([]);
    expect(log.hits).toEqual([]);
    await page.getByTestId("pdb-filter-q").fill("5ZIM");
    await page.getByTestId("view-pdb-5ZIM").click();
    await expect(page.getByTestId("structure-viewer")).toBeVisible();
    await expect(page.getByTestId("structure-viewer")).toHaveAttribute("data-phase", "ready", { timeout: 60_000 });
    expect(molstarChunk(watch).length).toBe(1);
    expect(log.hits[0]).toMatch(/5zim/i);
  });

  test("Watchlist: isolated, 181 candidates, no membership/evidence columns", async ({ page, watch }) => {
    await page.goto("#/watchlist");
    await expect(page.getByTestId("watchlist-isolation")).toContainText(/not admitted/i);
    await expect(page.getByTestId("wl-count")).toContainText("181");
    const headers = (await page.getByTestId("wl-table").locator("th").allInnerTexts()).join(" | ").toLowerCase();
    expect(headers).not.toMatch(/membership|evidence|mrdb accession/);
    expect(watch.dataFiles().filter((f) => /^records-index\.json$|^records\//.test(f))).toEqual([]);
  });

  test("Text search: accession and PDB golden cases", async ({ page }) => {
    await page.goto("#/search?q=P02945");
    await expect(page.getByTestId("text-hit-P02945")).toBeVisible();
    await page.goto("#/search?q=1C3W");
    await expect(page.getByTestId("text-hit-P02945")).toBeVisible();
    await expect(page.getByTestId("text-hit-P02945").locator("[data-field]")).toHaveAttribute("data-field", /pdb/);
  });

  test("Sequence search: worker example, validation codes, cancel, not-a-classifier notice", async ({ page }) => {
    await page.goto("#/search?mode=sequence");
    await expect(page.getByTestId("seq-not-classifier")).toContainText("does not compute the official membership score");
    await page.getByTestId("seq-example").click();
    await expect(page.getByTestId("seq-input")).not.toHaveValue("");
    await page.getByTestId("seq-run").click();
    const top = page.getByTestId("seq-hit-1");
    await expect(top).toBeVisible({ timeout: 90_000 });
    await expect(top).toHaveAttribute("data-acc", "P02945");
    await expect(top).toHaveAttribute("data-identity", "1");

    const cases: [string, string][] = [
      ["MKLLV", "too_short"],
      ["ACGTACGTACGTACGTACGTACGTACGTACGTACGTACGT", "nucleotide"],
      [">a\nMKVLLAGLLLAAGSALAQNGT\n>b\nMKVLLAGLLLAAGSALAQNGT", "multi_record"],
      ["M".repeat(5001), "too_long"],
    ];
    for (const [seq, code] of cases) {
      await page.getByTestId("seq-input").fill(seq);
      await page.getByTestId("seq-run").click();
      await expect(page.getByTestId("seq-invalid").locator("[data-code]")).toHaveAttribute("data-code", code);
    }
    await page.getByTestId("seq-example").click();
    await expect(page.getByTestId("seq-input")).not.toHaveValue("");
    await page.getByTestId("seq-run").click();
    await page.getByTestId("seq-cancel").click();
    await expect(page.getByTestId("seq-cancelled")).toBeVisible();
  });

  test("Downloads: 39 release files listed, export manifest linked but not fetched", async ({ page, watch }) => {
    await page.goto("#/downloads");
    await expect(page.getByTestId("dl-release-files")).toBeVisible();
    await expect(page.locator('[data-testid^="dl-file-"]')).toHaveCount(39);
    await page.waitForLoadState("networkidle");
    expect(watch.dataFiles().filter((f) => f === "export_manifest.json")).toEqual([]);
  });

  test("Citation: no DOI minted; BibTeX cites the dataset version, not the website version", async ({ page }) => {
    await page.goto("#/citation");
    await expect(page.getByTestId("cite-doi")).toContainText("none minted");
    const bib = await page.getByTestId("cite-bibtex").innerText();
    expect(bib).toContain("1.6.0");
    expect(bib).not.toContain("2.0.0");
    expect(bib).not.toMatch(/doi\s*=/);
  });
});
