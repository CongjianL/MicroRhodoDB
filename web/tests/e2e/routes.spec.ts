import { expect, test } from "./fixtures";

test.describe("Routing, history and static assets under /MicroRhodoDB/site/", () => {
  test("repository-root redirect reaches the site and all assets load from the base path", async ({ page, watch }) => {
    const assets: string[] = [];
    page.on("response", (r) => { if (/\/assets\//.test(r.url())) assets.push(`${r.status()} ${new URL(r.url()).pathname}`); });
    await page.goto("/MicroRhodoDB/");
    await expect(page).toHaveURL(/\/MicroRhodoDB\/site\/(index\.html)?(#\/)?$/);
    await expect(page.getByTestId("stat-cards")).toBeVisible();
    expect(assets.length).toBeGreaterThan(0);
    for (const a of assets) expect(a).toMatch(/^200 \/MicroRhodoDB\/site\/assets\//);
    const fav = await page.request.get("favicon.svg");
    expect(fav.status()).toBe(200);
    expect(watch.errors).toEqual([]);
  });

  test("legacy record deep links: MRDB accession and source accession", async ({ page, watch }) => {
    await page.goto("#/record/MRDB000001");
    const rec = page.getByTestId("record-page");
    await expect(rec).toHaveAttribute("data-mrdb", "MRDB000001");
    await expect(page.getByTestId("sources-table")).toContainText("P02945");
    await expect(page.getByTestId("sources-table")).toContainText("B0R5N9");
    await page.goto("#/record/P02945");
    await expect(rec).toHaveAttribute("data-mrdb", "MRDB000001");
    await expect(rec).toHaveAttribute("data-focus", "P02945");
    await expect(page.getByTestId("pdb-table")).toBeVisible();
    await page.getByTestId("pdb-filter-q").fill("1C3W");
    await expect(page.getByTestId("pdb-table")).toContainText("1C3W");
    // MRDB representative and E1 representative are shown as distinct concepts
    await expect(rec).toContainText(/MRDB representative/i);
    await expect(rec).toContainText(/E1 representative/i);
    await page.goto("#/record/q9f7p4");
    await expect(rec).toHaveAttribute("data-mrdb", "MRDB000011");
    await expect(page).toHaveURL(/#\/record\/Q9F7P4$/);
    expect(watch.errors).toEqual([]);
  });

  test("tentative placements on records carry the MR_CLD3_017 caveat", async ({ page, watch }) => {
    await page.goto("#/record/A0A135LS53");
    const rec = page.getByTestId("record-page");
    await expect(rec).toContainText("tentative");
    await expect(rec).toContainText("MR_CLD3_017");
    await expect(rec).toContainText("SH-aLRT 50.3 / UFBoot 72");
    await page.getByTestId("record-clade-link").click();
    await expect(page).toHaveURL(/#\/clade\/MR_CLD3_017$/);
    const cp = page.getByTestId("clade-page");
    await expect(cp).toContainText("SH-aLRT 50.3 / UFBoot 72 (fails thresholds)");
    await expect(cp.getByTestId("clade-support-notice")).toContainText("legacy v1.6.0 assignment");
    await page.goBack();
    await expect(page.getByTestId("record-page")).toBeVisible();
    expect(watch.errors).toEqual([]);
  });

  test("unknown accessions and paths show not-found pages without errors", async ({ page, watch }) => {
    await page.goto("#/record/ZZZ999");
    await expect(page.getByTestId("record-not-found")).toBeVisible();
    await page.goto("#/record/MRDB999999");
    await expect(page.getByTestId("record-not-found")).toBeVisible();
    await page.goto("#/does-not-exist");
    await expect(page.getByTestId("not-found")).toBeVisible();
    expect(watch.errors).toEqual([]);
  });

  test("#/novel redirects to #/watchlist without an extra history entry; planned pages are labelled", async ({ page, watch }) => {
    await page.goto("#/about");
    await page.evaluate(() => { location.hash = "#/novel"; });
    await expect(page).toHaveURL(/#\/watchlist$/);
    await expect(page.getByTestId("planned-watchlist")).toBeVisible();
    await page.goBack();
    await expect(page).toHaveURL(/#\/about$/);
    for (const p of ["phylogeny", "structures", "search", "downloads", "statistics", "evidence", "methods", "citation", "help"]) {
      await page.goto(`#/${p}`);
      const n = page.getByTestId("planned-notice").first();
      await expect(n).toBeVisible();
      await expect(n).toContainText(/Planned/);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    }
    await page.goto("#/clade/MR_CLD3_017");
    await expect(page.getByTestId("clade-page")).toContainText("SH-aLRT 50.3 / UFBoot 72");
    expect(watch.errors).toEqual([]);
  });

  test("header navigation, history and refresh", async ({ page, watch }) => {
    await page.goto("#/");
    const nav = page.getByRole("navigation", { name: "Primary", exact: true });
    await nav.getByRole("link", { name: "Browse" }).click();
    await expect(page).toHaveURL(/#\/browse$/);
    await expect(page.getByTestId("browse-count")).toHaveText("3,085");
    await expect(nav.getByRole("link", { name: "Browse" })).toHaveAttribute("aria-current", "page");
    await nav.getByRole("link", { name: "About" }).click();
    await expect(page).toHaveURL(/#\/about$/);
    await page.goBack();
    await expect(page).toHaveURL(/#\/browse$/);
    await page.goBack();
    await expect(page.getByTestId("stat-cards")).toBeVisible();
    await page.goto("#/browse?group=all&evidence=E2");
    await page.reload();
    await expect(page.getByTestId("browse-count")).toHaveText("109");
    await page.goto("#/record/P02945");
    await page.reload();
    await expect(page.getByTestId("record-page")).toHaveAttribute("data-focus", "P02945");
    expect(watch.errors).toEqual([]);
  });

  test("keyboard: skip link and visible focus", async ({ page, watch }) => {
    await page.goto("#/");
    await expect(page.getByTestId("stat-cards")).toBeVisible();
    await page.keyboard.press("Tab");
    const skip = page.getByRole("link", { name: /skip to/i });
    await expect(skip).toBeFocused();
    const outline = await skip.evaluate((el) => getComputedStyle(el).outlineStyle + " " + getComputedStyle(el).boxShadow);
    expect(outline).not.toBe("none none");
    await page.keyboard.press("Enter");
    await expect(page.locator("#main")).toBeFocused();
    expect(watch.errors).toEqual([]);
  });
});
