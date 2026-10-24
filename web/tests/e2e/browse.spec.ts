import { readFileSync } from "node:fs";
import type { Download, Page } from "@playwright/test";
import { expect, HEAVY, test, visible } from "./fixtures";

const count = (page: Page) => page.getByTestId("browse-count");
const bodyRows = (page: Page) => page.getByTestId("results-table").locator("tbody tr");

async function readDownload(d: Download): Promise<string> {
  const p = await d.path();
  return readFileSync(p!, "utf8");
}

test.describe("Browse", () => {
  test("default view: 3,087 Type-I members (engineered hidden), 50 rows per page", async ({ page, watch }) => {
    await page.goto("#/browse");
    await expect(count(page)).toHaveText("3,087");
    await expect(page.getByTestId("browse-total")).toHaveText("5,466");
    await expect(bodyRows(page)).toHaveCount(50);
    await expect(page.getByTestId("group-tabs").locator('[aria-pressed="true"]')).toHaveAttribute("data-group", "member");
    await page.getByTestId("toggle-eng").check();
    await expect(count(page)).toHaveText("3,091");
    await expect(page).toHaveURL(/#\/browse\?eng=1$/);
    expect(watch.dataFiles()).toContain("records-index.json");
    expect(watch.dataFiles().some((f) => f.startsWith("sequences/"))).toBe(false);
  });

  test("filters update the URL, show chips, and Back/Forward restore them", async ({ page, watch }) => {
    await page.goto("#/browse");
    await expect(count(page)).toHaveText("3,087");
    await page.getByTestId("group-tabs").locator('[data-group="all"]').click();
    await expect(count(page)).toHaveText("5,460");
    await visible(page, "filter-evidence").selectOption("E1");
    await expect(count(page)).toHaveText("88");
    await expect(page).toHaveURL(/#\/browse\?group=all&evidence=E1$/);
    await expect(page.getByTestId("filter-chips")).toContainText("E1");
    await visible(page, "filter-q").fill("bacteriorhodopsin");
    await expect(page).toHaveURL(/q=bacteriorhodopsin/);
    const nq = await count(page).innerText();
    expect(Number(nq.replace(/,/g, ""))).toBeLessThan(88);
    await page.goBack();
    await expect(page).toHaveURL(/#\/browse\?group=all&evidence=E1$/);
    await expect(count(page)).toHaveText("88");
    await expect(visible(page, "filter-evidence")).toHaveValue("E1");
    await page.goForward();
    await expect(count(page)).toHaveText(nq);
    await page.getByTestId("clear-filters").click();
    await expect(count(page)).toHaveText("5,460");
    expect(watch.errors).toEqual([]);
  });

  test("clade filter with and without tentative placements; uncertainty banner for MR_CLD3_017", async ({ page, watch }) => {
    await page.goto("#/browse?group=all&eng=1&clade=MR_CLD3_017");
    await expect(count(page)).toHaveText("1,646");
    await expect(page.getByTestId("caveat-count")).toContainText("1,646 records in this selection");
    await expect(page.getByTestId("clade-support-notice")).toContainText("SH-aLRT 50.3 / UFBoot 72");
    await visible(page, "filter-tent").check();
    await expect(count(page)).toHaveText("2,243");
    await expect(page).toHaveURL(/clade=MR_CLD3_017&tent=1/);
    await expect(page.getByTestId("results-table")).toContainText("tentative");
    expect(watch.errors).toEqual([]);
  });

  test("sorting by length cycles ascending, descending, none and sets aria-sort", async ({ page, watch }) => {
    await page.goto("#/browse?group=all&eng=1");
    const th = page.getByTestId("results-table").locator("thead th", { hasText: "Length" });
    const btn = th.getByRole("button");
    await btn.click();
    await expect(page).toHaveURL(/sort=length/);
    await expect(th).toHaveAttribute("aria-sort", "ascending");
    const lengths = async () => (await page.getByTestId("results-table").locator("tbody td[data-col=length]").allInnerTexts()).map((x) => Number(x.replace(/[^\d]/g, "")));
    const asc = await lengths();
    expect(asc.length).toBe(50);
    expect([...asc].sort((a, b) => a - b)).toEqual(asc);
    await btn.click();
    await expect(th).toHaveAttribute("aria-sort", "descending");
    await expect(page).toHaveURL(/sort=length&dir=desc/);
    const desc = await lengths();
    expect([...desc].sort((a, b) => b - a)).toEqual(desc);
    expect(desc[0]).toBeGreaterThanOrEqual(asc[asc.length - 1]);
    await btn.click();
    await expect(th).toHaveAttribute("aria-sort", "none");
    await expect(page).not.toHaveURL(/sort=/);
    expect(watch.errors).toEqual([]);
  });

  test("pagination: next, last, page size, out-of-range page", async ({ page, watch }) => {
    await page.goto("#/browse?group=all&evidence=E1");
    await expect(count(page)).toHaveText("88");
    const pag = page.getByRole("navigation", { name: "Pagination" });
    await pag.getByRole("button", { name: "Next" }).click();
    await expect(page).toHaveURL(/page=2/);
    await expect(bodyRows(page)).toHaveCount(38);
    await page.getByTestId("page-size").selectOption("25");
    await expect(page).toHaveURL(/size=25/);
    await expect(page).not.toHaveURL(/page=/);
    await pag.getByRole("button", { name: "Last page" }).click();
    await expect(page).toHaveURL(/page=4/);
    await expect(bodyRows(page)).toHaveCount(13);
    await page.goto("#/browse?group=all&evidence=E1&page=99");
    await expect(bodyRows(page)).toHaveCount(38);
    expect(watch.errors).toEqual([]);
  });

  test("invalid URL parameters are reported, not silently applied", async ({ page, watch }) => {
    await page.goto("#/browse?evidence=E9&group=all");
    await expect(page.getByTestId("ignored-params")).toContainText("evidence");
    await expect(count(page)).toHaveText("5,460");
    expect(watch.errors).toEqual([]);
  });

  test("legacy alias status=member and record links", async ({ page, watch }) => {
    await page.goto("#/browse?status=member&q=P02945");
    await expect(count(page)).toHaveText("1");
    await page.getByTestId("results-table").getByRole("link", { name: "MRDB000001" }).first().click();
    await expect(page).toHaveURL(/#\/record\/MRDB000001/);
    await expect(page.getByTestId("record-page")).toBeVisible();
    await page.goBack();
    await expect(count(page)).toHaveText("1");
    expect(watch.errors).toEqual([]);
  });

  test("exports: TSV, source FASTA, unique MRDB FASTA and manifest contain exactly the selection", async ({ page, watch }) => {
    await page.goto("#/browse?group=all&evidence=E1&sort=length&dir=desc");
    await expect(count(page)).toHaveText("88");
    const open = async () => { if (!(await page.getByTestId("export-tsv").isVisible())) await page.getByRole("button", { name: "Download" }).click(); };

    await open();
    let [d] = await Promise.all([page.waitForEvent("download"), page.getByTestId("export-tsv").click()]);
    expect(d.suggestedFilename()).toMatch(/^microrhododb_v1\.6\.1_browse_[0-9a-f]{8}_[0-9a-f]{8}_88_source_records\.tsv$/);
    const tsvName = d.suggestedFilename();
    const tsv = (await readDownload(d)).split("\n");
    expect(tsv[0].split("\t").slice(0, 3)).toEqual(["mrdb_acc", "source_acc", "protein_name"]);
    expect(tsv[0].split("\t")).toHaveLength(47);
    expect(tsv.length).toBe(88 + 2);
    const evCol = tsv[0].split("\t").indexOf("evidence_level");
    const lenCol = tsv[0].split("\t").indexOf("length");
    expect(tsv.slice(1, -1).every((l) => l.split("\t")[evCol] === "E1")).toBe(true);
    const lens = tsv.slice(1, -1).map((l) => Number(l.split("\t")[lenCol]));
    expect([...lens].sort((a, b) => b - a)).toEqual(lens);

    await open();
    [d] = await Promise.all([page.waitForEvent("download"), page.getByTestId("export-fasta").click()]);
    expect(d.suggestedFilename()).toMatch(/_88_source_records\.fasta$/);
    const faName = d.suggestedFilename();
    const fa = await readDownload(d);
    expect((fa.match(/^>/gm) ?? []).length).toBe(88);
    expect(fa).toMatch(/^>MRDB\d{6} \S+ status=\S+ evidence=E1 func=\S+ clade=\S+ engineered=0\n[A-Z]+/);
    expect(fa.split("\n").every((l) => l.startsWith(">") || l.length <= 60)).toBe(true);

    await open();
    [d] = await Promise.all([page.waitForEvent("download"), page.getByTestId("export-mrdb").click()]);
    expect(d.suggestedFilename()).toMatch(/_mrdb_sequences\.fasta$/);
    const u = await readDownload(d);
    const nU = (u.match(/^>/gm) ?? []).length;
    expect(d.suggestedFilename()).toContain(`_${nU}_mrdb_sequences`);
    expect(nU).toBeLessThan(88);
    const mrdbName = d.suggestedFilename();

    await open();
    [d] = await Promise.all([page.waitForEvent("download"), page.getByTestId("export-manifest").click()]);
    const man = JSON.parse(await readDownload(d));
    expect(man).toMatchObject({ dataset_release: "1.6.1", n_source_records: 88, n_mrdb_accessions: nU, filter_query: "group=all&evidence=E1", sort: { key: "length", dir: "desc" }, sort_token: "length:desc" });
    // PR-3a: the manifest lists exactly the names of the files that were downloaded.
    expect(man.files).toEqual({ records_tsv: tsvName, records_fasta: faName, mrdb_fasta: mrdbName, manifest: d.suggestedFilename() });
    expect(tsvName).toContain(`_browse_${man.selection_id}_${man.export_id}_88_`);
    expect(watch.dataFiles()).toContain("sequences/corpus.fasta");
    expect(watch.errors).toEqual([]);
  });

  // PR-3a regression (PR-2 issue): different sort orders gave different file contents under one name.
  test("exports of the same selection in different sort orders get distinct names; selection_id is shared", async ({ page, watch }) => {
    const grab = async (hash: string) => {
      await page.goto(hash);
      await expect(count(page)).toHaveText("88");
      if (!(await page.getByTestId("export-tsv").isVisible())) await page.getByRole("button", { name: "Download" }).click();
      const [d] = await Promise.all([page.waitForEvent("download"), page.getByTestId("export-tsv").click()]);
      const name = d.suggestedFilename();
      const m = /^microrhododb_v1\.6\.1_browse_([0-9a-f]{8})_([0-9a-f]{8})_88_source_records\.tsv$/.exec(name);
      expect(m, name).not.toBeNull();
      const lines = (await readDownload(d)).split("\n").slice(1, -1);
      return { name, selection: m![1], exportId: m![2], body: lines.join("\n"), set: [...lines].sort().join("\n") };
    };
    const desc = await grab("#/browse?group=all&evidence=E1&sort=length&dir=desc");
    const asc = await grab("#/browse?group=all&evidence=E1&sort=length&dir=asc");
    const idx = await grab("#/browse?group=all&evidence=E1");
    expect(desc.body).not.toBe(asc.body);
    expect(desc.set).toBe(asc.set);
    expect(idx.set).toBe(asc.set);
    expect(new Set([desc.selection, asc.selection, idx.selection]).size).toBe(1);
    expect(new Set([desc.exportId, asc.exportId, idx.exportId]).size).toBe(3);
    expect(new Set([desc.name, asc.name, idx.name]).size).toBe(3);
    // Same sort again: same name (names are deterministic).
    expect((await grab("#/browse?group=all&evidence=E1&sort=length&dir=desc")).name).toBe(desc.name);
    expect(watch.errors).toEqual([]);
  });

  test("only the lightweight files plus records-index are loaded on Browse", async ({ page, watch }) => {
    await page.goto("#/browse");
    await expect(count(page)).toHaveText("3,087");
    await page.waitForLoadState("networkidle");
    const heavy = watch.dataFiles().filter((f) => HEAVY.some((re) => re.test(f)));
    expect(heavy).toEqual(["records-index.json"]);
  });
});
