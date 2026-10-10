import type { Clades, Summary } from "../../src/data/types";
import { dataJson, expect, fmt, HEAVY, test } from "./fixtures";

const metric = (s: Summary, id: string) => s.metrics.find((m) => m.id === id)!.value;

test.describe("Home", () => {
  test("renders statistics equal to summary.json with explicit denominators", async ({ page, watch }) => {
    await page.goto("#/");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page).toHaveTitle(/MicroRhodoDB/);
    const S = await dataJson<Summary>(page, "summary.json");
    const cards: [string, string][] = [
      ["stat-records", "records_total"], ["stat-members", "typeI_members"], ["stat-e1", "e1_counted"],
      ["stat-tips", "tree_tips"], ["stat-pubs", "publications"], ["stat-watchlist", "watchlist"],
    ];
    for (const [tid, id] of cards) await expect(page.getByTestId(`${tid}-value`)).toHaveText(fmt(metric(S, id)));
    for (const id of ["records_counted", "mrdb_accessions", "typeI_candidates", "records_with_pdb", "records_with_afdb", "call_conflict"]) {
      await expect(page.getByTestId(`ctx-${id}`)).toHaveText(fmt(metric(S, id)));
    }
    // frozen v1.6.0 headline values
    await expect(page.getByTestId("stat-records-value")).toHaveText("5,466");
    await expect(page.getByTestId("ctx-records_counted")).toHaveText("5,460");
    await expect(page.getByTestId("ctx-mrdb_accessions")).toHaveText("5,299");
    await expect(page.getByTestId("stat-tips")).toContainText("17 level-1 clades + 2 backbone groups");
    await expect(page.getByTestId("stat-e1")).toContainText("of 5,460 counted records");
    await expect(page.getByTestId("stat-members")).toContainText("of 5,466 source records");
    await expect(page.getByTestId("release-line")).toContainText("v1.6.0");
    await expect(page.getByTestId("footer-release")).toContainText("1.6.0");
    expect(watch.errors).toEqual([]);
  });

  test("membership and evidence charts show real counts and denominators", async ({ page, watch }) => {
    await page.goto("#/");
    const S = await dataJson<Summary>(page, "summary.json");
    const mem = page.getByTestId("chart-membership");
    const ev = page.getByTestId("chart-evidence");
    await expect(mem.locator("svg").first()).toBeVisible();
    await expect(ev.locator("svg").first()).toBeVisible();
    await expect(mem).toContainText("5,466");
    await expect(ev).toContainText("5,460");
    // data tables (accessible alternative to the charts)
    await mem.locator("summary").first().click();
    await ev.locator("summary").first().click();
    for (const it of S.distributions.find((d) => d.id === "membership_group")!.items) {
      await expect(mem.locator("table")).toContainText(fmt(it.value));
    }
    for (const it of S.distributions.find((d) => d.id === "evidence_level_counted")!.items) {
      await expect(ev.locator("table").getByRole("row", { name: new RegExp(`^${it.key}\\b`) })).toContainText(fmt(it.value));
    }
    await expect(page.getByTestId("evidence-definitions")).toContainText("E1");
    expect(watch.errors).toEqual([]);
  });

  test("tree preview draws the real 472-tip MR_RT_003 tree and discloses MR_CLD3_017 uncertainty", async ({ page, watch }) => {
    await page.goto("#/");
    const C = await dataJson<Clades>(page, "clades.json");
    const tree = page.getByTestId("tree-preview");
    await expect(tree).toHaveAttribute("data-tips", "472");
    await expect(tree.locator("path").first()).toBeVisible();
    const legend = page.getByTestId("clade-legend");
    await expect(legend.locator("tbody tr")).toHaveCount(C.level1.length);
    await expect(page.getByTestId("legend-support-MR_CLD3_017")).toContainText("50.3");
    await expect(page.getByTestId("legend-support-MR_CLD3_017")).toContainText("72");
    await expect(legend).toContainText("fails thresholds");
    const notice = page.getByTestId("clade-support-notice");
    await expect(notice).toContainText("Phylogenetic uncertainty");
    await expect(notice).toContainText("MR_CLD3_017");
    await expect(page.getByTestId("support-MR_CLD3_017")).toHaveText(/SH-aLRT 50\.3 \/ UFBoot 72/);
    await expect(notice).toContainText(/SH-aLRT ≥ 80/);
    await expect(notice).toContainText(/UFBoot ≥ 95/);
    await expect(notice).toContainText(/legacy v1\.6\.0/i);
    // the rooted-file labels are never shown: MR_CLD3_017's DB/rooted-file label is 100/100
    await expect(page.getByTestId("legend-support-MR_CLD3_017")).not.toContainText("100");
    expect(watch.errors).toEqual([]);
  });

  test("does not download the full database (no index, accessions, records or sequences)", async ({ page, watch }) => {
    await page.goto("#/");
    await expect(page.getByTestId("tree-preview")).toBeVisible();
    await expect(page.getByTestId("chart-evidence").locator("svg").first()).toBeVisible();
    await page.waitForLoadState("networkidle");
    const files = watch.dataFiles();
    expect(files).toEqual(expect.arrayContaining(["manifest.json", "summary.json", "clades.json"]));
    for (const f of files) for (const re of HEAVY) expect(f, `Home requested ${f}`).not.toMatch(re);
    expect(watch.requests.some((u) => u.endsWith("/data.js"))).toBe(false);
  });

  test("search box and entry points navigate to the right routes", async ({ page, watch }) => {
    await page.goto("#/");
    const search = page.getByRole("search").first().getByRole("searchbox");
    await search.fill("P02945");
    await search.press("Enter");
    await expect(page).toHaveURL(/#\/record\/P02945$/);
    await expect(page.getByTestId("record-page")).toBeVisible();
    await page.goBack();
    await expect(page.getByTestId("stat-cards")).toBeVisible();
    for (const [name, url] of [["browse", /#\/browse$/], ["phylogeny", /#\/phylogeny$/], ["structures", /#\/structures$/],
      ["search", /#\/search$/], ["downloads", /#\/downloads$/], ["about", /#\/about$/]] as const) {
      await page.goto("#/");
      await page.getByTestId(`entry-${name}`).click();
      await expect(page).toHaveURL(url);
    }
    expect(watch.errors).toEqual([]);
  });

  test("function links open Browse selections of the displayed size", async ({ page, watch }) => {
    await page.goto("#/");
    const n = (await page.getByTestId("func-count-sensory").innerText()).trim();
    await page.locator('[data-func="sensory"]').click();
    await expect(page).toHaveURL(/#\/browse\?group=all&func=sensory$/);
    await expect(page.getByTestId("browse-count")).toHaveText(n);
    expect(watch.errors).toEqual([]);
  });
});

test("About does not download the full database and states provenance", async ({ page, watch }) => {
  await page.goto("#/about");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("About");
  await expect(page.locator("main")).toContainText("379a254356c6489a2b9e0600d501d76d22bc8e3ced4cfbdd5160fb00c3dce17f");
  await expect(page.getByTestId("clade-support-notice")).toContainText("SH-aLRT 50.3 / UFBoot 72");
  await page.waitForLoadState("networkidle");
  for (const f of watch.dataFiles()) for (const re of HEAVY) expect(f, `About requested ${f}`).not.toMatch(re);
});
