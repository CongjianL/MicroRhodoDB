/**
 * Shared E2E fixture: every test fails on any console error, uncaught page error, failed request
 * or HTTP >= 400 response, and records which data files were requested.
 */
import { test as base, expect, type Page } from "@playwright/test";

export interface Watch {
  errors: string[];
  requests: string[];
  /** Data files requested relative to data/v1.6.0/ (e.g. "summary.json", "records/MRDB000001.json"). */
  dataFiles: () => string[];
}

export const HEAVY = [/^records-index\.json$/, /^accessions\.json$/, /^records\//, /^sequences\//, /^publications\.json$/, /^structures-index\.json$/, /^evidence-index\.json$/];

export const test = base.extend<{ watch: Watch }>({
  watch: async ({ page }, use) => {
    const errors: string[] = [];
    const requests: string[] = [];
    page.on("console", (m) => { if (m.type() === "error") errors.push(`console: ${m.text()}`); });
    page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
    page.on("requestfailed", (r) => {
      // Aborted blob: downloads are not failures.
      if (!r.url().startsWith("blob:")) errors.push(`requestfailed: ${r.url()} ${r.failure()?.errorText}`);
    });
    page.on("response", (r) => { if (r.status() >= 400) errors.push(`HTTP ${r.status()}: ${r.url()}`); });
    page.on("request", (r) => requests.push(r.url()));
    const dataFiles = () => requests
      .map((u) => new URL(u).pathname.match(/\/data\/v\d+\.\d+\.\d+\/(.+)$/)?.[1])
      .filter((x): x is string => !!x);
    await use({ errors, requests, dataFiles });
    expect(errors, "console errors / failed requests").toEqual([]);
  },
});

export { expect };

/** Fetch a JSON data file from the served release directory (the same file the app reads). */
export async function dataJson<T>(page: Page, rel: string): Promise<T> {
  const r = await page.request.get(`data/v1.6.0/${rel}`);
  expect(r.ok()).toBe(true);
  return (await r.json()) as T;
}

export const fmt = (n: number) => n.toLocaleString("en-US");

/** No horizontal page overflow: document scroll width never exceeds the viewport. */
export async function expectNoHorizontalOverflow(page: Page) {
  const m = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(m.sw, `scrollWidth ${m.sw} > innerWidth ${m.iw}`).toBeLessThanOrEqual(m.iw);
}

export const visible = (page: Page, testId: string) => page.locator(`[data-testid="${testId}"]:visible`);
