/**
 * PR-4 Clade Explorer pages (#/clade/<id>): all 17 level-1 clades and 2 backbone groups, a subclade,
 * the MR_CLD3_017 legacy flag (corrected run1 50.3/72 vs stored 100/100), tips that are absent from
 * the corpus, and unknown ids. Values are compared with clades.json / explorer.json, not hard-coded.
 */
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";
import { dataJson, expect, expectNoHorizontalOverflow, fmt, test } from "./fixtures";

const OUT = resolve(process.env.SCREENSHOT_DIR ?? "test-results/screenshots");

interface Clade {
  clade_id: string; kind?: string; n_tips_in_tree?: number; n_tips: number; n_records_confident?: number; n_records_tentative?: number; n_E1: number;
  support_audit: { iqtree_run1_sh_alrt: number; iqtree_run1_ufboot: number; iqtree_run1_meets_support_thresholds: boolean; db_label: string };
}
interface Clades { level1: Clade[]; subclades: (Clade & { parent_clade_id: string })[] }

test.describe("Clade Explorer pages", () => {
  test("every level-1 clade and backbone group page renders its tips, subtree and support", async ({ page, watch }) => {
    test.setTimeout(180_000);
    await page.goto("#/about");
    const clades = await dataJson<Clades>(page, "clades.json");
    expect(clades.level1.length).toBe(19);
    for (const c of clades.level1) {
      await page.goto(`#/clade/${c.clade_id}`);
      const cp = page.getByTestId("clade-page");
      await expect(cp).toHaveAttribute("data-clade", c.clade_id);
      const n = c.n_tips_in_tree ?? c.n_tips;
      await expect(cp.getByTestId("clade-ntips")).toContainText(String(n));
      await expect(page.getByTestId("clade-tree-canvas")).toHaveAttribute("data-visible-leaves", String(n));
      await expect(page.getByTestId("clade-member")).toHaveCount(n);
      const a = c.support_audit;
      await expect(cp.getByTestId("clade-support")).toContainText(`SH-aLRT ${a.iqtree_run1_sh_alrt} / UFBoot ${a.iqtree_run1_ufboot}`);
      const legacy = !a.iqtree_run1_meets_support_thresholds;
      await expect(cp).toHaveAttribute("data-legacy", legacy ? "true" : "false");
      await expect(cp.getByTestId("clade-legacy-banner")).toHaveCount(legacy ? 1 : 0);
      await expect(cp.getByTestId("clade-records")).toContainText(`${fmt(c.n_records_confident ?? 0)} / ${fmt(c.n_records_tentative ?? 0)}`);
    }
    expect(clades.level1.filter((c) => !c.support_audit.iqtree_run1_meets_support_thresholds).map((c) => c.clade_id)).toEqual(["MR_CLD3_017"]);
    expect(watch.errors).toEqual([]);
  });

  test("MR_CLD3_017: legacy banner, corrected vs stored label, 6 subclades, 4 counted E1 records, placements", async ({ page, watch }) => {
    await page.goto("#/clade/MR_CLD3_017");
    const cp = page.getByTestId("clade-page");
    await expect(cp.getByTestId("clade-legacy-banner")).toContainText("SH-aLRT 50.3 / UFBoot 72");
    await expect(cp.getByTestId("clade-legacy-banner")).toContainText("legacy v1.6.0 assignment");
    await expect(cp.getByTestId("clade-support")).toContainText("fails thresholds");
    await expect(cp.getByTestId("clade-db-label")).toContainText("100/100");
    await expect(cp.getByTestId("clade-db-label")).toContainText("differs from run1");
    await expect(cp.getByTestId("clade-robustness")).toContainText("min_cross_replicate_jaccard < 0.8");
    await expect(cp.getByTestId("clade-subclades").locator("tbody tr")).toHaveCount(6);
    await expect(cp.getByTestId("clade-e1").locator("tbody tr")).toHaveCount(4);
    await expect(cp.getByTestId("clade-ne1")).toContainText("4");
    await expect(cp.getByTestId("clade-placements")).toContainText("assigned 1,546");
    await expect(cp.getByTestId("clade-placements")).toContainText("distant_assigned 597");
    await expect(cp.getByTestId("clade-function")).toContainText("they are not tips of the tree");
    // subtree legend counts are those of the 100 tips below the MRCA
    const n = await cp.getByTestId("legend-ingroup").locator("li span.tabular-nums").allInnerTexts();
    expect(n.reduce((s, x) => s + Number(x), 0)).toBe(100);
    await expect(cp.getByTestId("legend-outgroup-title")).toHaveCount(0);
    // links into the explorer and Browse
    await expect(cp.getByTestId("clade-browse")).toHaveAttribute("href", /#\/browse\?.*clade=MR_CLD3_017/);
    await cp.getByTestId("clade-in-tree").click();
    await expect(page).toHaveURL(/#\/phylogeny\?.*clade=MR_CLD3_017/);
    await expect(page.getByTestId("tree-canvas")).toBeVisible();
    expect(watch.errors).toEqual([]);
  });

  test("subclade page carries the parent's legacy note; backbone group page has no clade claims", async ({ page, watch }) => {
    await page.goto("#/clade/MR_CLD3_017.01");
    const cp = page.getByTestId("clade-page");
    await expect(cp).toHaveAttribute("data-legacy", "true");
    await expect(cp.getByTestId("clade-legacy-banner")).toContainText("This subclade itself meets the thresholds");
    await expect(page.getByTestId("clade-member")).toHaveCount(21);
    await expect(page.getByRole("navigation", { name: /breadcrumb/i }).getByRole("link", { name: "MR_CLD3_017" })).toBeVisible();

    await page.goto("#/clade/MR_CLD3_B01");
    await expect(page.getByTestId("clade-page")).toHaveAttribute("data-legacy", "false");
    await expect(page.getByTestId("clade-page")).toContainText(/backbone group/i);
    await expect(page.getByTestId("clade-member")).toHaveCount(4);
    expect(watch.errors).toEqual([]);
  });

  test("MR_CLD3_001 lists the 2 reference tips that are not in the corpus without inventing entries", async ({ page, watch }) => {
    await page.goto("#/clade/MR_CLD3_001");
    for (const acc of ["QBQ84355", "QBQ84358"]) {
      const row = page.locator(`[data-testid=clade-member][data-acc="${acc}"]`);
      await expect(row).toContainText(/not in corpus/i);
      await expect(row.locator('a[href*="#/record/"]')).toHaveCount(0);
    }
    expect(watch.errors).toEqual([]);
  });

  test("unknown clade ids show the not-found page; #/clade opens the explorer", async ({ page, watch }) => {
    await page.goto("#/clade/MR_CLD3_999");
    await expect(page.getByTestId("not-found")).toBeVisible();
    await page.goto("#/clade");
    await expect(page.getByTestId("tree-canvas")).toBeVisible();
    expect(watch.errors).toEqual([]);
  });

  for (const w of [375, 768, 1440]) {
    test(`responsive ${w}px clade page has no horizontal overflow`, async ({ page, watch }) => {
      await page.setViewportSize({ width: w, height: 900 });
      await page.goto("#/clade/MR_CLD3_017");
      await expect(page.getByTestId("clade-tree-canvas")).toBeVisible();
      await page.evaluate(() => document.fonts.ready);
      await expectNoHorizontalOverflow(page);
      mkdirSync(OUT, { recursive: true });
      await page.screenshot({ path: resolve(OUT, `pr4_clade_017_${w}.png`) });
      expect(watch.errors).toEqual([]);
    });
  }
});
