/**
 * PR-7 deployment smoke tests for a built artifact (served like GitHub Pages) or the live site (read-only).
 * Covers: root redirect + base path, BUILD_INFO provenance, every mandatory route, MRDB and source-accession deep
 * links, PDB and predicted-structure loading, the MR_CLD3_017 warning and corrected run1 support, responsive layout
 * and accessibility (axe serious/critical), missing-data and external-outage behaviour, security headers in HTML
 * (CSP) and network confinement. External structure services are answered from committed fixtures.
 * See playwright.smoke.config.ts for targets and environment variables.
 */
import AxeBuilder from "@axe-core/playwright";
import { test as raw, expect as rawExpect, type Page } from "@playwright/test";
import { expect, expectNoHorizontalOverflow, test } from "../e2e/fixtures";
import { ROUTES } from "../e2e/pr6Routes";
import { mockStructures } from "../e2e/structureMocks";

const EXPECT_COMMIT = process.env.SMOKE_EXPECT_COMMIT;
const viewer = (p: Page) => p.getByTestId("structure-viewer");
const MANDATORY = ["home", "browse", "record_P02945", "phylogeny", "clade_017", "structures", "statistics", "evidence",
  "watchlist", "search_text", "search_seq", "downloads", "methods", "citation", "help"];

interface BuildInfo { source_commit: string; dataset_release: string; base_path: string; schema_version: string;
  website_version: string; source_db: { sha256: string; bytes: number }; content_sha256: string }

test.describe("deployment artifact: entry, base path and provenance", () => {
  test("repository root redirects to site/; every asset is served from /MicroRhodoDB/site/", async ({ page, watch }) => {
    const assets: string[] = [];
    page.on("response", (r) => { if (/\/assets\//.test(r.url())) assets.push(`${r.status()} ${new URL(r.url()).pathname}`); });
    await page.goto("../");
    await expect(page).toHaveURL(/\/MicroRhodoDB\/site\/(index\.html)?(#\/)?$/);
    await expect(page.getByTestId("stat-cards")).toBeVisible();
    expect(assets.length).toBeGreaterThan(0);
    for (const a of assets) expect(a).toMatch(/^200 \/MicroRhodoDB\/site\/assets\//);
    expect(watch.errors).toEqual([]);
  });

  test("BUILD_INFO.json identifies commit, dataset, schema and source DB; the footer shows the same build", async ({ page, watch }) => {
    const r = await page.request.get("BUILD_INFO.json");
    expect(r.status()).toBe(200);
    const bi = (await r.json()) as BuildInfo;
    expect(bi.source_commit).toMatch(/^[0-9a-f]{40}$/);
    if (EXPECT_COMMIT) expect(bi.source_commit).toBe(EXPECT_COMMIT);
    expect(bi.dataset_release).toBe("1.6.1");
    expect(bi.base_path).toBe("/MicroRhodoDB/site/");
    expect(bi.schema_version).toBe("1.4.0");
    expect(bi.source_db.sha256).toBe("b8215cffa9d2fdab1e65b904f4bafbe9edf6578aed7b4fb028a890850e704c2d");
    expect(bi.source_db.bytes).toBe(33_525_760);
    await page.goto("#/");
    const build = page.getByTestId("footer-build");
    await expect(build).toContainText(bi.source_commit.slice(0, 7));
    await expect(build).not.toContainText(/Development build/);
    await expect(page.getByTestId("footer-website-version")).toHaveText(bi.website_version);
    expect(watch.errors).toEqual([]);
  });

  test("the HTML ships a restrictive Content-Security-Policy and no test or sandbox endpoints", async ({ page }) => {
    const html = await (await page.request.get("index.html")).text();
    expect(html).toMatch(/http-equiv="Content-Security-Policy"/);
    expect(html).toMatch(/default-src 'self'/);
    expect(html).not.toMatch(/__test__|localhost:|\/workspace\/|\/mnt\//);
    expect((await page.request.get("../__test__/stall?path=index.html")).status()).toBe(404);
  });
});

test.describe("mandatory routes", () => {
  for (const r of ROUTES.filter((x) => MANDATORY.includes(x.name) || x.name === "not_found")) {
    test(`${r.name} renders (one h1, no errors, no horizontal overflow)`, async ({ page, watch }) => {
      await page.goto(r.hash);
      await r.ready(page);
      await expect(page.locator("h1")).toHaveCount(1);
      await expectNoHorizontalOverflow(page);
      expect(watch.errors).toEqual([]);
    });
  }

  test("only same-origin requests during a sweep of every route (no third-party calls without user action)", async ({ page, watch }) => {
    const origins = new Set<string>();
    page.on("request", (q) => origins.add(new URL(q.url()).origin));
    for (const r of ROUTES) {
      await page.goto(r.hash);
      await r.ready(page);
    }
    const self = new URL(page.url()).origin;
    expect([...origins].filter((o) => o !== self && !o.startsWith("data:") && o !== "null")).toEqual([]);
    expect(watch.errors).toEqual([]);
  });
});

test.describe("deep links and scientific warnings", () => {
  test("MRDB and source-accession deep links resolve to the same record", async ({ page, watch }) => {
    const rec = page.getByTestId("record-page");
    await page.goto("#/record/MRDB000001");
    await expect(rec).toHaveAttribute("data-mrdb", "MRDB000001");
    await expect(page.getByTestId("sources-table")).toContainText("P02945");
    await page.goto("#/record/P02945");
    await expect(rec).toHaveAttribute("data-mrdb", "MRDB000001");
    await expect(rec).toHaveAttribute("data-focus", "P02945");
    await page.goto("#/record/q9f7p4");
    await expect(rec).toHaveAttribute("data-mrdb", "MRDB000011");
    await expect(page).toHaveURL(/#\/record\/Q9F7P4$/);
    expect(watch.errors).toEqual([]);
  });

  test("MR_CLD3_017: tentative caveat, corrected run1 support 50.3/72, legacy-assignment banner", async ({ page, watch }) => {
    await page.goto("#/record/A0A135LS53");
    const rec = page.getByTestId("record-page");
    await expect(rec).toContainText("tentative");
    await expect(rec).toContainText("SH-aLRT 50.3 / UFBoot 72");
    await page.goto("#/clade/MR_CLD3_017");
    const cp = page.getByTestId("clade-page");
    await expect(cp.getByTestId("clade-support")).toContainText("SH-aLRT 50.3 / UFBoot 72");
    await expect(cp.getByTestId("clade-support")).toContainText("fails thresholds");
    await expect(cp.getByTestId("clade-legacy-banner")).toBeVisible();
    await page.goto("#/");
    await expect(page.getByTestId("support-MR_CLD3_017")).toHaveText(/SH-aLRT 50\.3 \/ UFBoot 72/);
    expect(watch.errors).toEqual([]);
  });
});

test.describe("structures", () => {
  test("experimental PDB structure and AlphaFold DB prediction load in the viewer", async ({ page, watch }) => {
    await mockStructures(page);
    await page.goto("#/record/MRDB000001");
    await page.getByTestId("viewer-load").click();
    await expect(viewer(page)).toHaveAttribute("data-phase", "ready", { timeout: 60_000 });
    await page.getByTestId("structure-picker").selectOption("afdb");
    await expect(page.getByTestId("viewer-status")).toContainText("AF-P02945-F1", { timeout: 60_000 });
    await expect(viewer(page)).toHaveAttribute("data-phase", "ready", { timeout: 60_000 });
    expect(watch.errors).toEqual([]);
  });
});

raw.describe("failure behaviour (expected failed requests; uncaught errors are not allowed)", () => {
  const pageErrors = (page: Page) => {
    const errs: string[] = [];
    page.on("pageerror", (e) => errs.push(e.message));
    return errs;
  };

  raw("missing data file: error with Retry, Retry recovers", async ({ page }) => {
    const errs = pageErrors(page);
    let fail = true;
    await page.route("**/data/v1.6.1/summary.json", (r) => (fail ? r.fulfill({ status: 404, body: "missing" }) : r.fallback()));
    await page.goto("#/");
    const alert = page.getByRole("alert").filter({ hasText: /Could not load/ }).first();
    await rawExpect(alert).toBeVisible();
    fail = false;
    await alert.getByRole("button", { name: "Retry" }).click();
    await rawExpect(page.getByTestId("stat-cards")).toBeVisible();
    rawExpect(errs).toEqual([]);
  });

  raw("RCSB PDB and AlphaFold DB unavailable: viewer error with Retry; the record stays usable", async ({ page }) => {
    const errs = pageErrors(page);
    await page.route(/^https:\/\/(models\.rcsb\.org|files\.rcsb\.org|alphafold\.ebi\.ac\.uk)\//, (r) => r.fulfill({ status: 503, body: "unavailable" }));
    await page.goto("#/record/MRDB000001");
    await page.getByTestId("viewer-load").click();
    const err = page.getByTestId("viewer-error");
    await rawExpect(err).toBeVisible({ timeout: 45_000 });
    await rawExpect(err.getByTestId("viewer-retry")).toBeVisible();
    await rawExpect(page.getByTestId("sequence")).toBeVisible();
    rawExpect(errs).toEqual([]);
  });
});

const SMOKE_A11Y = ["home", "browse", "record_P02945", "phylogeny", "clade_017", "statistics", "downloads", "citation"];
for (const vp of [{ w: 375, h: 812 }, { w: 1440, h: 900 }]) {
  test.describe(`responsive and accessibility ${vp.w}px`, () => {
    test.use({ viewport: { width: vp.w, height: vp.h } });
    for (const r of ROUTES.filter((x) => SMOKE_A11Y.includes(x.name))) {
      test(`${r.name}: no overflow, no serious/critical axe violations`, async ({ page, watch }) => {
        await page.goto(r.hash);
        await r.ready(page);
        await page.waitForLoadState("networkidle");
        await expectNoHorizontalOverflow(page);
        const res = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
        const bad = res.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => `${v.id} (${v.nodes.length})`);
        expect(bad).toEqual([]);
        expect(watch.errors).toEqual([]);
      });
    }
  });
}
