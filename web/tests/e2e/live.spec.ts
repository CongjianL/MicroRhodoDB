/**
 * @live smoke test against the real RCSB PDB and AlphaFold DB endpoints (no mocks).
 * Excluded by default; run with E2E_LIVE=1 npx playwright test --grep @live
 */
import { expect, test } from "./fixtures";

test("@live MRDB000001: 5ZIM from RCSB and AF-P02945-F1 from AlphaFold DB render", async ({ page, watch }) => {
  test.setTimeout(120_000);
  await page.goto("#/record/MRDB000001");
  const v = page.getByTestId("structure-viewer");
  await page.getByTestId("viewer-load").click();
  await expect(v).toHaveAttribute("data-phase", "ready", { timeout: 60_000 });
  await expect(page.getByTestId("viewer-status")).toContainText("5ZIM");
  await page.getByTestId("structure-picker").selectOption("afdb");
  await expect(v).toHaveAttribute("data-selected", "afdb");
  await expect(v).toHaveAttribute("data-phase", "ready", { timeout: 60_000 });
  await expect(page.getByTestId("viewer-coloring")).toHaveValue("plddt-confidence");
  const status = await page.getByTestId("viewer-status").textContent();
  test.info().annotations.push({ type: "live-status", description: status ?? "" });
  expect(watch.errors).toEqual([]);
});
