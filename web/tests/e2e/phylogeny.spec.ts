/**
 * PR-4 Phylogeny explorer (#/phylogeny): layouts, colour modes, corrected run1 support (17 rerooting
 * discrepancies, MR_CLD3_017, root split), tip / clade / placement deep links, search, subtree and
 * collapse, keyboard, downloads (byte-identical frozen files, DERIVED Newick, SVG / PNG figure) and
 * the narrow-screen layout. Every test fails on console errors or failed requests (fixtures.ts).
 */
import { createHash } from "node:crypto";
import { mkdirSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import type { Page } from "@playwright/test";
import { dataJson, expect, expectNoHorizontalOverflow, test } from "./fixtures";

const REPO = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
const OUT = resolve(process.env.SCREENSHOT_DIR ?? "test-results/screenshots");
const sha256 = (b: Buffer) => createHash("sha256").update(b).digest("hex");
const canvas = (page: Page) => page.getByTestId("tree-canvas");

/** Select a node through the same pointer path a click takes (hit circles overlap at full view). */
async function selectPre(page: Page, pre: number) {
  const hit = page.locator(`[data-testid="tree-hits"] [data-pre="${pre}"]`).first();
  await expect(hit).toHaveCount(1);
  await hit.dispatchEvent("pointerdown", { pointerId: 7, isPrimary: true, bubbles: true });
  await hit.dispatchEvent("pointerup", { pointerId: 7, isPrimary: true, bubbles: true });
}

async function download(page: Page, click: () => Promise<void>) {
  const [dl] = await Promise.all([page.waitForEvent("download"), click()]);
  const p = await dl.path();
  return { name: dl.suggestedFilename(), bytes: readFileSync(p!) };
}

interface ExplorerMeta { meta: { frozen_treefile: { path: string; sha256: string }; support_source: { path: string; sha256: string }; derived_newick: { sha256: string } } }

test.describe("Phylogeny explorer", () => {
  test("full 472-tip tree renders; layouts, branch lengths and colour modes update canvas, legend and URL", async ({ page, watch }) => {
    await page.goto("#/phylogeny");
    const c = canvas(page);
    await expect(c).toHaveAttribute("data-visible-leaves", "472");
    await expect(c).toHaveAttribute("data-layout", "rect");
    await expect(page.getByTestId("info-empty")).toContainText("472 tips, 471 internal nodes");
    await expect(page.getByTestId("legend-outgroup-title")).toHaveText("Heliorhodopsin outgroup (15 tips)");
    await expect(page.getByTestId("clade-strip")).toBeAttached();

    await page.getByTestId("layout-radial").click();
    await expect(page).toHaveURL(/#\/phylogeny\?layout=radial$/);
    await expect(c).toHaveAttribute("data-layout", "radial");
    await page.getByTestId("bl-uniform").click();
    await expect(page).toHaveURL(/layout=radial&bl=uniform/);
    await expect(c).toHaveAttribute("data-branch", "uniform");

    for (const mode of ["subclade", "domain", "phylum", "function", "evidence", "motif", "role", "clade"]) {
      await page.getByTestId("tree-color").selectOption(mode);
      await expect(c).toHaveAttribute("data-color", mode);
      await expect(page.getByTestId("tree-legend")).toHaveAttribute("data-mode", mode);
      // the outgroup is always listed separately from the ingroup categories
      await expect(page.getByTestId("legend-outgroup-title")).toContainText("(15 tips)");
      const ingroup = await page.getByTestId("legend-ingroup").locator("li span.tabular-nums").allInnerTexts();
      expect(ingroup.reduce((a, x) => a + Number(x), 0), mode).toBe(457);
    }
    await page.goBack();
    await expect(c).toHaveAttribute("data-color", "role");
    expect(watch.dataFiles()).toEqual(expect.arrayContaining(["phylogeny/explorer.json", "phylogeny/MR_RT_003.rooted.treefile", "clades.json"]));
    expect(watch.dataFiles().filter((f) => f.startsWith("records/"))).toEqual([]);
  });

  test("support toggle: 469 run1 values, thresholds re-evaluate, MR_CLD3_017 shows 50.3/72 and fails", async ({ page, watch }) => {
    await page.goto("#/phylogeny");
    await expect(page.getByTestId("tree-support")).toHaveCount(0);
    await page.getByTestId("support-toggle").check();
    await expect(page).toHaveURL(/support=1/);
    const marks = page.locator("[data-testid=tree-support] > g");
    await expect(marks).toHaveCount(469);
    const meets80 = await page.locator('[data-testid=tree-support] > g[data-meets="1"]').count();
    await expect(page.locator('[data-testid=tree-support] > g[data-pre="744"]')).toHaveAttribute("data-support", "50.3/72");
    await expect(page.locator('[data-testid=tree-support] > g[data-pre="744"]')).toHaveAttribute("data-meets", "0");
    // the ingroup root child carries no mark: the root split is shown once, on the outgroup branch
    await expect(page.locator('[data-testid=tree-support] > g[data-pre="30"]')).toHaveCount(0);
    await expect(page.locator('[data-testid=tree-support] > g[data-pre="1"]')).toHaveAttribute("data-support", "98.8/100");
    await page.getByTestId("support-sh").fill("50");
    await page.getByTestId("support-uf").fill("70");
    await expect(page.locator('[data-testid=tree-support] > g[data-pre="744"]')).toHaveAttribute("data-meets", "1");
    expect(await page.locator('[data-testid=tree-support] > g[data-meets="1"]').count()).toBeGreaterThan(meets80);
    await expect(page).toHaveURL(/sh=50&uf=70/);
    expect(watch.errors).toEqual([]);
  });

  test("node panel: corrected support, rerooting discrepancy audit, root split, legacy MRCA", async ({ page, watch }) => {
    await page.goto("#/phylogeny");
    await selectPre(page, 744);
    const info = page.getByTestId("info-node");
    await expect(info).toHaveAttribute("data-pre", "744");
    await expect(info.getByTestId("info-support")).toContainText("SH-aLRT 50.3 / UFBoot 72");
    await expect(info.getByTestId("info-support")).toContainText("below 80/95");
    await expect(info.getByTestId("info-rooted-label")).toContainText("100/100");
    await expect(info.getByTestId("info-label-discrepancy")).toContainText("17 rerooting discrepancies");
    await expect(info).toContainText("MR_CLD3_017");
    await expect(info).toContainText("legacy assignment");

    // the 17 discrepant nodes always show the run1 value, never the rooted-file label
    const disc: [number, string, string | null][] = [[40, "92.1/96", "82.2/82"], [662, "98.7/81", "18.9/64"], [848, "100/100", "87.1/98"], [894, "40/51", null]];
    for (const [pre, run1, rooted] of disc) {
      await selectPre(page, pre);
      const [sh, uf] = run1.split("/");
      await expect(page.getByTestId("info-support")).toContainText(`SH-aLRT ${sh} / UFBoot ${uf}`);
      await expect(page.getByTestId("info-rooted-label")).toContainText(rooted ?? "None");
      await expect(page.getByTestId("info-label-discrepancy")).toBeVisible();
    }

    await selectPre(page, 30);
    await expect(page.getByTestId("info-root-split")).toContainText("98.8/100 is shown on the outgroup branch (pre 1)");
    await selectPre(page, 1);
    await expect(page.getByTestId("info-support")).toContainText("SH-aLRT 98.8 / UFBoot 100");
    await expect(page.getByTestId("info-support")).toContainText("Root split");
    await selectPre(page, 0);
    await expect(page.getByTestId("info-support")).toContainText("the root has no branch above it");
    expect(watch.errors).toEqual([]);
  });

  test("tip deep links: Protein Entry link, absent-from-corpus tips, non-tips are refused", async ({ page, watch }) => {
    await page.goto("#/phylogeny?tip=Q9UW81");
    const tip = page.getByTestId("info-tip");
    await expect(tip).toHaveAttribute("data-acc", "Q9UW81");
    await expect(page.getByTestId("tree-highlight-tip")).toHaveCount(1);
    await expect(page.getByTestId("tree-selected")).toHaveCount(1);
    await expect(canvas(page)).toHaveAttribute("data-labels", "on");
    await expect(page.getByTestId("tree-tip-label").filter({ hasText: "Q9UW81" })).toHaveCount(1);
    await expect(tip.getByTestId("info-entry-link")).toHaveText("MRDB000012");
    await tip.getByTestId("info-entry-link").click();
    await expect(page).toHaveURL(/#\/record\/MRDB000012$/);
    await page.goBack();
    await expect(page.getByTestId("info-tip")).toHaveAttribute("data-acc", "Q9UW81");

    for (const acc of ["QBQ84355", "QBQ84358"]) {
      await page.goto(`#/phylogeny?tip=${acc}`);
      await expect(page.getByTestId("info-tip")).toHaveAttribute("data-acc", acc);
      await expect(page.getByTestId("info-tip")).toContainText("not in the v1.6.1 corpus");
      await expect(page.getByTestId("info-entry-link")).toHaveCount(0);
    }
    // A0A0D1ZKH7 is a placed record (MRDB000101), not a tip
    await page.goto("#/phylogeny?tip=A0A0D1ZKH7");
    await expect(page.getByTestId("tip-missing")).toContainText("A0A0D1ZKH7");
    await expect(page.getByTestId("tree-highlight-tip")).toHaveCount(0);
    expect(watch.errors).toEqual([]);
  });

  test("placement deep link highlights only the best_edge branch and shows stored fields verbatim", async ({ page, watch }) => {
    await page.goto("#/phylogeny?placement=MRDB000101");
    const pp = page.getByTestId("placement-panel");
    await expect(pp).toContainText("not a tip");
    await expect(pp.getByTestId("pl-best_edge")).toContainText("E0832");
    await expect(pp.getByTestId("pl-clade_call_qc")).toContainText("assigned");
    await expect(pp.getByTestId("placement-targets")).toContainText("pre 802");
    await expect(pp).toContainText("position along the branch is not stored");
    await expect(page.getByTestId("tree-placement-edge")).toHaveCount(1);
    await expect(page.getByTestId("tree-placement-edge")).toHaveAttribute("data-pre", "802");
    await expect(page.getByTestId("tree-highlight-tip")).toHaveCount(0);
    expect(watch.dataFiles()).toContain("records/MRDB000101.json");

    // a reference-tip record has no placement; an unknown record is reported, nothing is drawn
    await page.goto("#/phylogeny?placement=MRDB000012");
    await expect(page.getByTestId("placement-is-tip")).toContainText("Q9UW81");
    await expect(page.getByTestId("tree-placement-edge")).toHaveCount(0);
    expect(watch.errors).toEqual([]);
  });

  test("record page links open the explorer at the tip or at the placement", async ({ page, watch }) => {
    await page.goto("#/record/MRDB000101?section=phylogeny");
    await page.getByTestId("mini-tree-explorer").click();
    await expect(page).toHaveURL(/#\/phylogeny\?placement=MRDB000101/);
    await expect(page.getByTestId("tree-placement-edge")).toHaveCount(1);
    await page.goto("#/record/MRDB000012?section=phylogeny");
    await page.getByTestId("record-explorer-link").click();
    await expect(page).toHaveURL(/#\/phylogeny\?tip=Q9UW81$/);
    await expect(page.getByTestId("info-tip")).toHaveAttribute("data-acc", "Q9UW81");
    expect(watch.errors).toEqual([]);
  });

  test("search finds tips by accession, MRDB accession and organism; placed records are not offered", async ({ page, watch }) => {
    await page.goto("#/phylogeny");
    const s = page.getByTestId("tree-search");
    await s.fill("MRDB000012");
    await expect(page.getByTestId("tree-search-results")).toContainText("Q9UW81");
    await s.press("Enter");
    await expect(page).toHaveURL(/tip=Q9UW81/);
    await expect(page.getByTestId("info-tip")).toHaveAttribute("data-acc", "Q9UW81");
    await s.fill("Neurospora");
    await expect(page.getByTestId("tree-search-results").locator("button").first()).toBeVisible();
    await s.fill("A0A0D1ZKH7");
    await expect(page.getByTestId("tree-search-results")).toContainText("No reference tip matches");
    expect(watch.errors).toEqual([]);
  });

  test("subtree view, collapse / expand and the clade table", async ({ page, watch }) => {
    await page.goto("#/phylogeny");
    await selectPre(page, 744);
    await page.getByTestId("info-subtree").click();
    await expect(page).toHaveURL(/node=744/);
    const c = canvas(page);
    await expect(c).toHaveAttribute("data-root", "744");
    await expect(c).toHaveAttribute("data-visible-leaves", "100");
    // legend counts follow the subtree: no outgroup block, 100 tips in total
    await expect(page.getByTestId("legend-outgroup-title")).toHaveCount(0);
    const n = await page.getByTestId("legend-ingroup").locator("li span.tabular-nums").allInnerTexts();
    expect(n.reduce((a, x) => a + Number(x), 0)).toBe(100);
    await page.getByRole("link", { name: "Whole tree" }).click();
    await expect(c).toHaveAttribute("data-visible-leaves", "472");

    await page.getByTestId("collapse-all").click();
    await expect(page).toHaveURL(/collapsed=/);
    const collapsedLeaves = Number(await c.getAttribute("data-visible-leaves"));
    expect(collapsedLeaves).toBeLessThan(472);
    // 17 level-1 clades + 2 backbone groups, each collapsed at its MRCA
    await expect(page.getByTestId("tree-collapsed")).toHaveCount(19);
    await page.getByTestId("expand-all").click();
    await expect(c).toHaveAttribute("data-visible-leaves", "472");

    const rows = page.getByTestId("clade-explorer").locator("tbody tr");
    await expect(rows).toHaveCount(19);
    await expect(page.getByTestId("ce-row-MR_CLD3_017")).toContainText("50.3 / 72");
    await expect(page.getByTestId("ce-row-MR_CLD3_017")).toContainText("legacy; fails");
    await page.getByTestId("ce-row-MR_CLD3_009").getByRole("link", { name: "Subtree" }).click();
    await expect(page).toHaveURL(/clade=MR_CLD3_009/);
    await expect(c).not.toHaveAttribute("data-root", "0");
    await expect(page.getByTestId("ce-row-MR_CLD3_009")).toBeVisible();
    await page.getByTestId("clade-explorer").getByRole("link", { name: "MR_CLD3_B01" }).click();
    await expect(page).toHaveURL(/#\/clade\/MR_CLD3_B01$/);
    expect(watch.errors).toEqual([]);
  });

  test("keyboard: focusable canvas zooms, pans, resets; Escape clears the selection", async ({ page, watch }) => {
    await page.goto("#/phylogeny?tip=Q9UW81");
    await expect(page.getByTestId("info-tip")).toBeVisible();
    await page.getByTestId("zoom-reset").click();
    const c = canvas(page);
    await expect(c).toHaveAttribute("data-zoom", "1.000");
    await c.focus();
    await page.keyboard.press("+");
    await expect(c).not.toHaveAttribute("data-zoom", "1.000");
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("0");
    await expect(c).toHaveAttribute("data-zoom", "1.000");
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("info-empty")).toBeVisible();
    await page.getByTestId("zoom-in").click();
    await expect(c).toHaveAttribute("data-zoom", "1.500");
    expect(watch.errors).toEqual([]);
  });

  test("downloads: frozen files byte-identical, DERIVED Newick + README, SVG and PNG figures", async ({ page, watch }) => {
    const ex = await (async () => { await page.goto("#/phylogeny"); return dataJson<ExplorerMeta>(page, "phylogeny/explorer.json"); })();
    const dl = page.getByTestId("tree-downloads");

    const orig = await download(page, () => dl.getByTestId("dl-original-link").click());
    expect(orig.name).toBe("MR_RT_003.rooted.treefile");
    expect(sha256(orig.bytes)).toBe(ex.meta.frozen_treefile.sha256);
    expect(orig.bytes.equals(readFileSync(resolve(REPO, ex.meta.frozen_treefile.path)))).toBe(true);

    const run1 = await download(page, () => dl.getByTestId("dl-run1-link").click());
    expect(sha256(run1.bytes)).toBe(ex.meta.support_source.sha256);
    expect(run1.bytes.equals(readFileSync(resolve(REPO, ex.meta.support_source.path)))).toBe(true);

    const der = await download(page, () => dl.getByTestId("dl-derived-link").click());
    expect(der.name).toMatch(/DERIVED\.nwk$/);
    expect(sha256(der.bytes)).toBe(ex.meta.derived_newick.sha256);
    const derTxt = der.bytes.toString("utf8");
    expect(derTxt).toContain(")50.3/72:");
    expect(derTxt).not.toBe(orig.bytes.toString("utf8"));
    const readmeHref = await dl.getByTestId("dl-derived-readme").getAttribute("href");
    const readme = await page.request.get(new URL(readmeHref!, page.url()).toString());
    expect(readme.ok()).toBe(true);
    expect(await readme.text()).toMatch(/DERIVED/);

    const svg = await download(page, () => dl.getByTestId("dl-svg").click());
    expect(svg.name).toBe("MR_RT_003_rect_clade.svg");
    const svgTxt = svg.bytes.toString("utf8");
    expect(svgTxt.startsWith("<?xml") || svgTxt.startsWith("<svg")).toBe(true);
    expect(svgTxt).not.toContain("NaN");
    expect(svgTxt).toContain("Q9UW81");
    expect(svgTxt).toContain("MR_CLD3_017");
    // PR-4a: export size is tens to hundreds of kB, not MB. Default view (support marks off) ~89 kB;
    // with support marks (PR-4 audit export, ?support=1) 158,004 B. Never 4.6 MB as an earlier draft said.
    console.log(`[pr4a] rect clade SVG export size (support off): ${svg.bytes.length} bytes`);
    expect(svg.bytes.length).toBeGreaterThan(50_000);
    expect(svg.bytes.length).toBeLessThan(150_000);
    expect((svgTxt.match(/<text/g) ?? []).length).toBeGreaterThanOrEqual(472);
    await page.goto("#/phylogeny?support=1");
    await expect(canvas(page)).toHaveAttribute("data-visible-leaves", "472");
    const svgS = await download(page, () => page.getByTestId("tree-downloads").getByTestId("dl-svg").click());
    console.log(`[pr4a] rect clade SVG export size (support on): ${svgS.bytes.length} bytes`);
    expect(svgS.bytes.length).toBeGreaterThan(svg.bytes.length);
    expect(svgS.bytes.length).toBeGreaterThan(100_000);
    expect(svgS.bytes.length).toBeLessThan(300_000);
    await page.goto("#/phylogeny");
    await expect(canvas(page)).toHaveAttribute("data-visible-leaves", "472");
    const png = await download(page, () => dl.getByTestId("dl-png").click());
    expect(png.name).toBe("MR_RT_003_rect_clade.png");
    expect(png.bytes.subarray(0, 8).toString("hex")).toBe("89504e470d0a1a0a");
    expect(png.bytes.length).toBeGreaterThan(20_000);
    expect(watch.errors).toEqual([]);
  });

  for (const vp of [{ w: 375, h: 812, canvasH: 440 }, { w: 768, h: 1024, canvasH: 560 }, { w: 1280, h: 800, canvasH: 660 }]) {
    test(`responsive ${vp.w}px: no page overflow, canvas fits, controls reachable`, async ({ page, watch }) => {
      await page.setViewportSize({ width: vp.w, height: vp.h });
      await page.goto("#/phylogeny?clade=MR_CLD3_017&support=1");
      const c = canvas(page);
      await expect(c).toHaveAttribute("data-visible-leaves", "472");
      await page.evaluate(() => document.fonts.ready);
      await expectNoHorizontalOverflow(page);
      const box = await c.boundingBox();
      expect(box!.width).toBeLessThanOrEqual(vp.w);
      expect(Math.round(box!.height)).toBe(vp.canvasH);
      await expect(page.getByTestId("layout-radial")).toBeVisible();
      await page.getByTestId("layout-radial").click();
      await expect(c).toHaveAttribute("data-layout", "radial");
      await expectNoHorizontalOverflow(page);
      mkdirSync(OUT, { recursive: true });
      await c.scrollIntoViewIfNeeded();
      await page.screenshot({ path: resolve(OUT, `pr4_phylogeny_radial_017_${vp.w}.png`) });
      expect(watch.errors).toEqual([]);
    });
  }
});
