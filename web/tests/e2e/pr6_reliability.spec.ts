/**
 * PR-6 security and reliability: malformed routes and injection payloads, external-link hygiene, CSP
 * compatibility (no securitypolicyviolation on any route or in the Mol* viewer), failure injection
 * (data outages, truncated JSON, hung requests, structure-host outages), repeated interactions,
 * legacy deep links, keyboard focus visibility and the text alternative of the tree.
 *
 * Tests that inject failures use plain Playwright (failed requests are the point) and assert on
 * uncaught page errors only; all other tests use the strict fixture (no console errors at all).
 */
import { test as raw, expect as rawExpect, type Page } from "@playwright/test";
import { expect, test } from "./fixtures";
import { ROUTES } from "./pr6Routes";
import { mockStructures } from "./structureMocks";

/** Collect CSP violations and an XSS canary in the page. */
async function instrument(page: Page) {
  await page.addInitScript(() => {
    (window as unknown as { __csp: string[] }).__csp = [];
    document.addEventListener("securitypolicyviolation", (e) => {
      (window as unknown as { __csp: string[] }).__csp.push(`${e.violatedDirective} ${e.blockedURI}`);
    });
  });
}
const cspViolations = (page: Page) => page.evaluate(() => (window as unknown as { __csp: string[] }).__csp);

function pageErrors(page: Page) {
  const errs: string[] = [];
  page.on("pageerror", (e) => errs.push(e.message));
  return errs;
}

test.describe("PR-6 security", () => {
  test("CSP meta is present in the production build; every mandatory route renders with zero CSP violations", async ({ page, watch }) => {
    await instrument(page);
    await page.goto("#/");
    const csp = await page.locator('meta[http-equiv="Content-Security-Policy"]').getAttribute("content");
    expect(csp).toContain("script-src 'self'");
    expect(csp).toContain("object-src 'none'");
    for (const r of ROUTES) {
      await page.goto(r.hash);
      await r.ready(page);
    }
    await page.goto("#/search?mode=sequence");
    await page.getByTestId("seq-example").click();
    await page.getByTestId("seq-run").click();
    await expect(page.getByTestId("seq-results")).toBeVisible({ timeout: 30_000 });
    expect(await cspViolations(page)).toEqual([]);
    expect(watch.errors).toEqual([]);
  });

  test("Mol* viewer (mocked RCSB) loads under the CSP without violations", async ({ page, watch }) => {
    await instrument(page);
    await mockStructures(page);
    await page.goto("#/record/MRDB000001");
    await page.getByTestId("viewer-load").click();
    await expect(page.getByTestId("viewer-status")).toContainText(/Showing/, { timeout: 45_000 });
    expect(await cspViolations(page)).toEqual([]);
    expect(watch.errors).toEqual([]);
  });

  test("external links: rel=noopener noreferrer on every target=_blank; no script URLs anywhere", async ({ page, watch }) => {
    for (const r of ROUTES) {
      await page.goto(r.hash);
      await r.ready(page);
      const bad = await page.evaluate(() => [...document.querySelectorAll("a")].flatMap((a) => {
        const out: string[] = [];
        const h = a.getAttribute("href") ?? "";
        if (/^\s*(javascript|data|vbscript):/i.test(h)) out.push(`script URL ${h}`);
        if (a.target === "_blank") {
          const rel = (a.getAttribute("rel") ?? "").split(/\s+/);
          if (!rel.includes("noopener") || !rel.includes("noreferrer")) out.push(`rel missing on ${h}`);
        }
        return out;
      }));
      expect(bad, r.hash).toEqual([]);
    }
    expect(watch.errors).toEqual([]);
  });

  const PAYLOAD = `"><img src=x onerror="window.__xss=1"><script>window.__xss=2</script>`;
  test("injection payloads in routes, Browse and Search are rendered as text and never executed", async ({ page, watch }) => {
    const enc = encodeURIComponent(PAYLOAD);
    for (const h of [`#/record/${enc}`, `#/clade/${enc}`, `#/browse?group=all&q=${enc}`, `#/browse?clade=${enc}&func=${enc}&ev=${enc}`,
      `#/search?q=${enc}`, `#/phylogeny?tip=${enc}&placement=${enc}`, `#/${enc}`]) {
      await page.goto(h);
      await page.waitForLoadState("networkidle");
      await expect(page.locator("h1")).toHaveCount(1);
      expect(await page.evaluate(() => (window as unknown as { __xss?: number }).__xss), h).toBeUndefined();
      expect(await page.locator("img[src=x]").count(), h).toBe(0);
    }
    await page.goto("#/search");
    await page.getByTestId("text-q").fill(PAYLOAD);
    await page.waitForTimeout(400);
    expect(await page.evaluate(() => (window as unknown as { __xss?: number }).__xss)).toBeUndefined();
    expect(watch.errors).toEqual([]);
  });

  test("malformed and hostile routes render not-found / record-not-found without uncaught errors", async ({ page, watch }) => {
    const cases: [string, string][] = [
      ["#/record/%E0%A4%A", "record-not-found"], ["#/record/ZZZ999", "record-not-found"], ["#/record/MRDB999999", "record-not-found"],
      ["#/record/" + "A".repeat(3000), "record-not-found"], ["#/record/P02945.1", "record-not-found"],
      ["#/clade/MR_CLD3_999", "not-found"], ["#/%", "not-found"], ["#/browse/extra", "not-found"], ["#/record/P02945/a/b", "not-found"],
    ];
    for (const [h, tid] of cases) {
      await page.goto(h);
      await expect(page.getByTestId(tid), h).toBeVisible();
    }
    // Hostile Browse parameters are ignored or treated as filters with zero matches, never thrown.
    for (const h of ["#/browse?group=%ZZ&page=-5&size=1e9&sort=__proto__", "#/browse?page=999999", "#/phylogeny?layout=xx&sh=abc&uf=-1&node=99999999"]) {
      await page.goto(h);
      await expect(page.locator("h1")).toHaveCount(1);
    }
    expect(watch.errors).toEqual([]);
  });
});

test.describe("PR-6 legacy deep links (old site/app.js routes)", () => {
  test("#/record (MRDB, source, lower case, trailing slash), #/search, #/novel, #/about, #/ and index.html", async ({ page, watch }) => {
    for (const [h, focus] of [["#/record/MRDB000001", "P02945"], ["#/record/P02945", "P02945"], ["#/record/p02945", "P02945"], ["#/record/P02945/", "P02945"]] as const) {
      await page.goto(h);
      await expect(page.getByTestId("record-page"), h).toBeVisible();
      await expect(page.getByTestId("sequence")).toBeVisible();
      if (h.startsWith("#/record/P") || h.startsWith("#/record/p")) await expect(page.getByTestId("record-page")).toHaveAttribute("data-focus", focus);
    }
    await page.goto("#/record/p02945");
    await expect(page).toHaveURL(/#\/record\/P02945$/);
    await page.goto("#/search");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(/Search/);
    await page.goto("#/novel");
    await expect(page).toHaveURL(/#\/watchlist$/);
    await page.goto("#/about");
    await expect(page.getByTestId("clade-support-notice")).toBeVisible();
    await page.goto("#/");
    await expect(page.getByTestId("stat-cards")).toBeVisible();
    await page.goto("index.html#/record/MRDB000001");
    await expect(page.getByTestId("sequence")).toBeVisible();
    expect(watch.errors).toEqual([]);
  });
});

raw.describe("PR-6 failure injection (uncaught errors only)", () => {
  raw("data outage: summary.json 503 on Home shows an error with Retry; Retry recovers", async ({ page }) => {
    const errs = pageErrors(page);
    let fail = true;
    await page.route("**/data/v1.6.0/summary.json", (r) => (fail ? r.fulfill({ status: 503, body: "down" }) : r.fallback()));
    await page.goto("#/");
    const alert = page.getByRole("alert").filter({ hasText: /Could not load/ }).first();
    await rawExpect(alert).toBeVisible();
    fail = false;
    await alert.getByRole("button", { name: "Retry" }).click();
    await rawExpect(page.getByTestId("stat-cards")).toBeVisible();
    rawExpect(errs).toEqual([]);
  });

  raw("truncated JSON (records-index) on Browse shows an error state, not a crash", async ({ page }) => {
    const errs = pageErrors(page);
    await page.route("**/data/v1.6.0/records-index.json", (r) => r.fulfill({ status: 200, contentType: "application/json", body: '{"columns":["a"' }));
    await page.goto("#/browse");
    await rawExpect(page.getByRole("alert").filter({ hasText: /Invalid or truncated data/ }).first()).toBeVisible();
    await rawExpect(page.getByRole("navigation", { name: "Primary", exact: true })).toBeVisible();
    rawExpect(errs).toEqual([]);
  });

  raw("hung data request times out into an error state (timeout shortened for the test)", async ({ page }) => {
    const errs = pageErrors(page);
    await page.addInitScript(() => { (window as unknown as { __MRDB_DATA_TIMEOUT_MS: number }).__MRDB_DATA_TIMEOUT_MS = 1500; });
    await page.route("**/data/v1.6.0/structures-index.json", () => { /* never answer */ });
    await page.goto("#/structures");
    await rawExpect(page.getByRole("alert").filter({ hasText: /Timed out/ }).first()).toBeVisible({ timeout: 10_000 });
    rawExpect(errs).toEqual([]);
  });

  raw("network failure of a record file shows an error; the rest of the site keeps working", async ({ page }) => {
    const errs = pageErrors(page);
    await page.route("**/data/v1.6.0/records/MRDB000001.json", (r) => r.abort("internetdisconnected"));
    await page.goto("#/record/MRDB000001");
    await rawExpect(page.getByRole("alert").first()).toBeVisible();
    await page.getByRole("navigation", { name: "Primary", exact: true }).getByRole("link", { name: "Browse" }).click();
    await rawExpect(page.getByTestId("results-table")).toBeVisible();
    await page.goto("#/statistics");
    await rawExpect(page.getByTestId("chart-evidence-level")).toBeVisible();
    rawExpect(errs).toEqual([]);
  });

  raw("RCSB and AlphaFold DB outage: viewer error with Retry and external links; page stays usable", async ({ page }) => {
    const errs = pageErrors(page);
    await page.route(/^https:\/\/(models\.rcsb\.org|files\.rcsb\.org|alphafold\.ebi\.ac\.uk)\//, (r) => r.fulfill({ status: 503, body: "unavailable" }));
    await page.goto("#/record/MRDB000001");
    await page.getByTestId("viewer-load").click();
    const err = page.getByTestId("viewer-error");
    await rawExpect(err).toBeVisible({ timeout: 30_000 });
    await rawExpect(err.getByTestId("viewer-retry")).toBeVisible();
    await err.getByTestId("viewer-retry").click();
    await rawExpect(err).toBeVisible({ timeout: 30_000 });
    await rawExpect(page.getByTestId("sequence")).toBeVisible();
    rawExpect(errs).toEqual([]);
  });

  raw("sequence-search worker script unavailable: a visible error, no uncaught exception", async ({ page }) => {
    const errs = pageErrors(page);
    await page.route(/seqSearch\.worker.*\.js$/, (r) => r.fulfill({ status: 404, body: "" }));
    await page.goto("#/search?mode=sequence");
    await page.getByTestId("seq-example").click();
    await page.getByTestId("seq-run").click();
    // Reported in the polite live region with the real cause, not an internal TypeError.
    const err = page.getByTestId("seq-status").getByTestId("seq-error");
    await rawExpect(err).toBeVisible({ timeout: 30_000 });
    await rawExpect(err).not.toContainText(/postMessage|Cannot read properties/);
    await rawExpect(page.getByTestId("seq-run")).toBeEnabled();
    rawExpect(errs).toEqual([]);
  });
});

test.describe("PR-6 repeated interactions and resource use", () => {
  test("rapid navigation across all routes (3 rounds) and back/forward: no errors, bounded JS heap", async ({ page, watch }) => {
    const cdp = await page.context().newCDPSession(page);
    const heap = async () => {
      await cdp.send("HeapProfiler.collectGarbage");
      return (await cdp.send("Runtime.getHeapUsage")).usedSize / 1048576;
    };
    const sizes: number[] = [];
    for (let round = 0; round < 3; round++) {
      for (const r of ROUTES) {
        await page.goto(r.hash);
        await r.ready(page);
      }
      sizes.push(await heap());
    }
    for (let i = 0; i < 10; i++) await page.goBack();
    for (let i = 0; i < 10; i++) await page.goForward();
    await expect(page.locator("h1")).toHaveCount(1);
    // Heap after round 3 must not grow by more than 25% over round 1 (all data files are cached once per load).
    expect(sizes[2], `heap MB per round ${sizes.map((s) => s.toFixed(1)).join(", ")}`).toBeLessThan(sizes[0] * 1.25);
    console.log(`HEAP_MB ${sizes.map((s) => s.toFixed(1)).join(" ")}`);
    expect(watch.errors).toEqual([]);
  });

  test("tree: 20 layout/colour toggles and 30 zoom steps stay consistent", async ({ page, watch }) => {
    await page.goto("#/phylogeny");
    const canvas = page.getByTestId("tree-canvas");
    await expect(canvas).toHaveAttribute("data-visible-leaves", "472");
    for (let i = 0; i < 10; i++) {
      await page.getByTestId("layout-radial").click();
      await expect(canvas).toHaveAttribute("data-layout", "radial");
      await page.getByTestId("layout-rect").click();
      await expect(canvas).toHaveAttribute("data-layout", "rect");
    }
    for (let i = 0; i < 15; i++) await page.getByTestId("zoom-in").click();
    for (let i = 0; i < 15; i++) await page.getByTestId("zoom-out").click();
    await expect(canvas).toHaveAttribute("data-visible-leaves", "472");
    expect(watch.errors).toEqual([]);
  });

  test("sequence search: start/cancel 5 times then a full run gives the golden top hit", async ({ page, watch }) => {
    await page.goto("#/search?mode=sequence");
    await page.getByTestId("seq-example").click();
    for (let i = 0; i < 5; i++) {
      await page.getByTestId("seq-run").click();
      const cancel = page.getByTestId("seq-cancel");
      if (await cancel.isVisible().catch(() => false)) await cancel.click();
    }
    await page.getByTestId("seq-run").click();
    await expect(page.getByTestId("seq-results")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("seq-results").locator("tbody tr").first()).toContainText("P02945");
    expect(watch.errors).toEqual([]);
  });
});

test.describe("PR-6 keyboard and alternatives", () => {
  for (const r of ROUTES.filter((x) => ["home", "browse", "record_P02945", "phylogeny", "statistics", "search_seq", "structures"].includes(x.name))) {
    test(`${r.name}: first 30 Tab stops are visible and show a focus indicator`, async ({ page, watch }) => {
      await page.goto(r.hash);
      await r.ready(page);
      const problems: string[] = [];
      for (let i = 0; i < 30; i++) {
        await page.keyboard.press("Tab");
        const f = await page.evaluate(() => {
          const el = document.activeElement as HTMLElement | null;
          if (!el || el === document.body) return null;
          const cs = getComputedStyle(el);
          const rect = el.getBoundingClientRect();
          return {
            tag: el.tagName + (el.getAttribute("data-testid") ? `[${el.getAttribute("data-testid")}]` : "") + " " + (el.textContent ?? "").trim().slice(0, 30),
            indicator: (cs.outlineStyle !== "none" && parseFloat(cs.outlineWidth) > 0) || cs.boxShadow !== "none",
            visible: rect.width > 0 && rect.height > 0 && cs.visibility !== "hidden",
          };
        });
        if (!f) continue;
        if (!f.indicator) problems.push(`no focus indicator: ${f.tag}`);
        if (!f.visible) problems.push(`invisible focus target: ${f.tag}`);
      }
      expect(problems).toEqual([]);
      expect(watch.errors).toEqual([]);
    });
  }

  test("tree canvas has a label and a text alternative; the Clade Explorer table lists all 19 groups", async ({ page, watch }) => {
    await page.goto("#/phylogeny");
    const canvas = page.getByTestId("tree-canvas");
    await expect(canvas).toHaveAttribute("aria-describedby", "tree-text-alt");
    await expect(page.getByTestId("tree-text-alt")).toContainText("Text alternative");
    await page.getByTestId("tree-text-alt").getByRole("button", { name: "Clade Explorer table" }).click();
    await expect(page.locator("#ce-h")).toBeFocused();
    await expect(page.getByTestId("clade-explorer").locator("tbody tr")).toHaveCount(19);
    expect(watch.errors).toEqual([]);
  });
});
