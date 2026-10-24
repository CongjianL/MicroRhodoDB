/**
 * PR-5a browser regression tests: the links actually rendered on Statistics, Home and Search open Browse
 * views whose record count equals the number shown next to the link (every linked category of the
 * membership-status, evidence, clade-state and crosstab views), the clade-state drilldown keeps the
 * members + candidates population, and Search only says "same records" when the sets are identical.
 * Exact accession-set equality is proven in tests/unit/pr5a.test.ts against the DB-derived golden.
 */
import type { Page } from "@playwright/test";
import { expect, test } from "./fixtures";

interface Link { href: string; value: number; label: string }

async function chartLinks(page: Page, testId: string): Promise<Link[]> {
  const chart = page.getByTestId(testId);
  await chart.locator("details > summary").first().click();
  return chart.locator("tbody tr[data-key]").evaluateAll((trs) =>
    trs.flatMap((tr) => {
      const a = tr.querySelector("th a") as HTMLAnchorElement | null;
      return a ? [{ href: a.getAttribute("href")!, value: Number(tr.getAttribute("data-value")), label: a.textContent ?? "" }] : [];
    }));
}

async function expectBrowseCount(page: Page, l: Link) {
  await page.goto(l.href);
  await expect(page.getByTestId("ignored-params")).toHaveCount(0);
  await expect(page.getByTestId("browse-count"), `${l.label} ${l.href}`).toHaveText(l.value.toLocaleString("en-US"), { timeout: 30_000 });
}

test.describe("PR-5a drilldowns", () => {
  test("membership status (both denominators): every linked status opens exactly its counted records", async ({ page }) => {
    for (const scope of ["All source records", "Counted records"]) {
      await page.goto("#/statistics");
      await page.getByRole("group", { name: "Membership denominator" }).getByRole("button", { name: scope }).click();
      const links = await chartLinks(page, "chart-membership-status");
      expect(links.length).toBe(9);
      for (const l of links) {
        expect(l.href).toContain("group=all");
        await expectBrowseCount(page, l);
      }
    }
  });

  test("clade state over members + candidates keeps the 4,465 population (and all-records scope keeps 5,466)", async ({ page }) => {
    await page.goto("#/statistics");
    const mc = await chartLinks(page, "chart-clade-state");
    expect(mc.reduce((a, b) => a + b.value, 0)).toBe(4465);
    for (const l of mc) {
      expect(l.href).toContain("group=member_candidate");
      await expectBrowseCount(page, l);
    }
    await expect(page.getByTestId("browse-scope")).toContainText("Members + candidates");
    await page.goto("#/statistics");
    await page.getByRole("group", { name: "Clade denominator" }).getByRole("button", { name: "All source records" }).click();
    const all = await chartLinks(page, "chart-clade-state");
    expect(all.reduce((a, b) => a + b.value, 0)).toBe(5466);
    for (const l of all) await expectBrowseCount(page, l);
  });

  test("evidence (both denominators) and the evidence x membership crosstab", async ({ page }) => {
    for (const scope of ["Counted records", "All source records"]) {
      await page.goto("#/statistics");
      await page.getByRole("group", { name: "Evidence denominator" }).getByRole("button", { name: scope }).click();
      for (const l of await chartLinks(page, "chart-evidence-level")) await expectBrowseCount(page, l);
    }
    await page.goto("#/statistics");
    const cells = await page.getByTestId("crosstab-evidence-membership").locator("tbody td a").evaluateAll((as) =>
      as.map((a) => ({ href: a.getAttribute("href")!, value: Number((a.textContent ?? "").replace(/,/g, "")), label: a.textContent ?? "" })));
    expect(cells.reduce((a, b) => a + b.value, 0)).toBe(5460);
    for (const l of cells) await expectBrowseCount(page, l);
  });

  test("Home: stat cards, membership groups and functional classes open their counted records", async ({ page }) => {
    await page.goto("#/");
    const cards = [["stat-records", 5466], ["stat-members", 3091], ["stat-e1", 88]] as const;
    const hrefs: Link[] = [];
    for (const [id, n] of cards) {
      const h = await page.getByTestId(id).locator("a").first().getAttribute("href");
      expect(h, id).toBeTruthy();
      hrefs.push({ href: h!, value: n, label: id });
    }
    const funcs = await page.getByTestId("func-links").locator("a[data-func]").evaluateAll((as) =>
      as.map((a) => ({ href: a.getAttribute("href")!, value: Number((a.querySelector("[data-testid^=func-count]")?.textContent ?? "").replace(/,/g, "")), label: a.getAttribute("data-func") ?? "" })));
    for (const l of [...hrefs, ...funcs]) await expectBrowseCount(page, l);
  });

  test("Browse offers the Members + candidates population tab", async ({ page }) => {
    await page.goto("#/browse?group=member_candidate&eng=1");
    await expect(page.getByTestId("group-tabs").locator('[aria-pressed="true"]')).toHaveAttribute("data-group", "member_candidate");
    await expect(page.getByTestId("browse-count")).toHaveText("4,465", { timeout: 30_000 });
  });
});

test.describe("PR-5a Search -> Browse", () => {
  test("MR_CLD3_017: formal view = 1,646 (not the same as the search); incl. tentative = the same 2,243", async ({ page }) => {
    await page.goto("#/search?q=MR_CLD3_017");
    await expect(page.getByTestId("text-total")).toHaveText("2,243", { timeout: 30_000 });
    const formal = page.locator('[data-testid="browse-option"][data-query="group=all&clade=MR_CLD3_017&eng=1"]');
    const tent = page.locator('[data-testid="browse-option"][data-query="group=all&clade=MR_CLD3_017&tent=1&eng=1"]');
    await expect(formal).toHaveAttribute("data-same", "0");
    await expect(formal).toHaveAttribute("data-n", "1646");
    await expect(formal).toContainText("not the same set");
    await expect(tent).toHaveAttribute("data-same", "1");
    await expect(tent).toContainText("the same records as this search");
    for (const opt of await page.getByTestId("browse-option").all()) {
      const same = await opt.getAttribute("data-same");
      if (same === "1") await expect(opt).not.toContainText("not the same");
      else await expect(opt).not.toContainText("the same records as this search");
    }
    await formal.locator("a").click();
    await expect(page.getByTestId("browse-count")).toHaveText("1,646", { timeout: 30_000 });
    await page.goBack();
    await tent.locator("a").click();
    await expect(page.getByTestId("browse-count")).toHaveText("2,243", { timeout: 30_000 });
  });

  test("PDB ID search maps to the PDB filter with identical records", async ({ page }) => {
    await page.goto("#/search?q=1C3W");
    const p = page.locator('[data-testid="browse-option"][data-query="group=all&pdbid=1C3W&eng=1"]');
    await expect(p).toHaveAttribute("data-same", "1", { timeout: 30_000 });
    const n = Number(await p.getAttribute("data-n"));
    await expect(page.getByTestId("text-total")).toHaveText(n.toLocaleString("en-US"));
  });
});
