/**
 * PR-6a: the data-loading timeout covers stalled response bodies in a real browser.
 * The test server (scripts/serve_e2e.py) exposes test-only endpoints: /__test__/stall sends the headers and
 * the first 64 bytes of a file and then goes silent; /__test__/drip sends the complete file slowly in chunks.
 * Requests for the real data file are redirected there with route.continue({ url }).
 * Raw @playwright/test is used because these tests intentionally produce failed requests.
 */
import { test, expect, type Page } from "@playwright/test";

const SHORT = 1500; // shortened inactivity limit for the test (production default: 45 s)

function pageErrors(page: Page) {
  const errs: string[] = [];
  page.on("pageerror", (e) => errs.push(e.message));
  return errs;
}
const shorten = (page: Page) =>
  page.addInitScript((ms) => { (window as unknown as { __MRDB_DATA_TIMEOUT_MS: number }).__MRDB_DATA_TIMEOUT_MS = ms; }, SHORT);

test.describe("PR-6a stalled response bodies", () => {
  test("a data file whose body stalls after the headers ends in a timeout error with Retry; Retry recovers", async ({ page, baseURL }) => {
    const errs = pageErrors(page);
    await shorten(page);
    const origin = new URL(baseURL!).origin;
    let stall = true;
    await page.route("**/data/v1.6.0/structures-index.json", (r) =>
      stall ? r.continue({ url: `${origin}/__test__/stall?path=data/v1.6.0/structures-index.json` }) : r.continue());
    const t0 = Date.now();
    await page.goto("#/structures");
    const alert = page.getByRole("alert").filter({ hasText: /Timed out while loading .*structures-index\.json/ }).first();
    await expect(alert).toBeVisible({ timeout: 15_000 });
    expect(Date.now() - t0).toBeLessThan(15_000);
    await expect(page.getByRole("navigation", { name: "Primary", exact: true })).toBeVisible();
    stall = false;
    await alert.getByRole("button", { name: "Retry" }).click();
    await expect(page.getByTestId("pdb-table")).toBeVisible({ timeout: 15_000 });
    expect(errs).toEqual([]);
  });

  test("a slow body that keeps delivering data is not cut off (inactivity limit, not total limit)", async ({ page, baseURL }) => {
    const errs = pageErrors(page);
    await shorten(page);
    const origin = new URL(baseURL!).origin;
    // 6 chunks, 700 ms apart: ~4.2 s in total (> 1.5 s limit), but every gap is < 1.5 s.
    await page.route("**/data/v1.6.0/structures-index.json", (r) =>
      r.continue({ url: `${origin}/__test__/drip?path=data/v1.6.0/structures-index.json&chunks=6&gap_ms=700` }));
    const t0 = Date.now();
    await page.goto("#/structures");
    await expect(page.getByTestId("pdb-table")).toBeVisible({ timeout: 20_000 });
    expect(Date.now() - t0).toBeGreaterThan(SHORT);
    await expect(page.getByRole("alert").filter({ hasText: /Timed out/ })).toHaveCount(0);
    expect(errs).toEqual([]);
  });

  test("the sequence-search corpus download stalling mid-body is reported, not left loading", async ({ page, baseURL }) => {
    const errs = pageErrors(page);
    await shorten(page);
    const origin = new URL(baseURL!).origin;
    await page.context().route("**/data/v1.6.0/sequences/corpus.fasta", (r) =>
      r.continue({ url: `${origin}/__test__/stall?path=data/v1.6.0/sequences/corpus.fasta` }));
    await page.goto("#/search?mode=sequence");
    await page.getByTestId("seq-example").click();
    // The example loads asynchronously; clicking Run before it arrives would search an empty query.
    await expect(page.getByTestId("seq-input")).not.toHaveValue("");
    await page.getByTestId("seq-run").click();
    const err = page.getByTestId("seq-status").getByTestId("seq-error");
    await expect(err).toBeVisible({ timeout: 20_000 });
    await expect(err).toContainText(/Timed out while loading .*corpus\.fasta/);
    await expect(page.getByTestId("seq-run")).toBeEnabled();
    expect(errs).toEqual([]);
  });
});

test.describe("PR-6a data transport", () => {
  test("ordinary page loads finish every data request (no net::ERR_ABORTED from the body reader)", async ({ page }) => {
    // Regression: a fetch()+ReadableStream implementation made Chromium report most small data files as
    // net::ERR_ABORTED although their content had been read. The XHR transport must finish every request.
    const failed: string[] = [];
    const finished: string[] = [];
    page.on("requestfailed", (r) => failed.push(`${r.url()} ${r.failure()?.errorText}`));
    page.on("requestfinished", (r) => { if (r.url().includes("/data/")) finished.push(r.url()); });
    for (const route of ["#/browse", "#/statistics", "#/record/P02945"]) {
      await page.goto(route);
      await page.waitForLoadState("networkidle");
    }
    await page.reload();
    await page.waitForLoadState("networkidle");
    expect(failed).toEqual([]);
    expect(finished.length).toBeGreaterThan(5);
  });
});
