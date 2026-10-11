/**
 * PR-7 rollback smoke test: the pre-redesign site (legacy commit, restored by rollback R1 or R2) is served and works.
 * Run with SMOKE_LEGACY=1 and SMOKE_ARTIFACT=<legacy artifact> (local drill) or SMOKE_BASE_URL (after a real rollback).
 */
import { expect, test } from "@playwright/test";

test("legacy site: root redirect, browse table rendered from data.js, no errors", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  page.on("console", (m) => { if (m.type() === "error") errors.push(`console: ${m.text()}`); });
  page.on("response", (r) => { if (r.status() >= 400) errors.push(`HTTP ${r.status()} ${r.url()}`); });
  await page.goto("../");
  await expect(page).toHaveURL(/\/MicroRhodoDB\/site\/(index\.html)?(#.*)?$/);
  await expect(page).toHaveTitle(/MicroRhodoDB - Type-I microbial rhodopsin knowledgebase/);
  await expect(page.locator("#tb tr").first()).toBeVisible();
  expect(await page.locator("#tb tr").count()).toBeGreaterThan(10);
  for (const f of ["app.js", "data.js", "style.css"]) expect((await page.request.get(f)).status()).toBe(200);
  // The redesigned site's provenance file must not exist on the legacy site.
  expect((await page.request.get("BUILD_INFO.json")).status()).toBe(404);
  expect(errors).toEqual([]);
});
