/**
 * PR-3a regression tests for the Protein Entry page:
 *   1. source position in multi-accession entries ("i of N", not a hardcoded "1 of N");
 *   2. Mol* async races (rapid switching, Retry, change during initialisation, unmount while loading);
 *   4. release-model provenance warning (stored "ESMCFold2 (full)" vs historical ESMFold note/file name);
 *   5. MR_CLD3_017 mini-tree label clearance and Copy link keeping section + structure.
 * (Correction 3, Browse export file names, is covered in browse.spec.ts and tests/unit/exporters.test.ts.)
 *
 * Race tests read `window.__MRDB_VIEWER_STATS`, an opt-in diagnostics object filled by the Mol*
 * wrapper only when the page defines it: plugins created/disposed, labels committed to the Mol*
 * state (`rendered`, in order) and the label currently committed (`current`).
 */
import { mkdirSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import type { Page, Route } from "@playwright/test";
import { expect, test } from "./fixtures";
import { dropExpected, mockStructures, molstarChunk } from "./structureMocks";

const OUT = resolve(process.env.SCREENSHOT_DIR ?? "test-results/screenshots");
const FIX = resolve(dirname(fileURLToPath(import.meta.url)), "../fixtures/structures");
const CORS = { "access-control-allow-origin": "*" };
const SHOT = { style: "header, [data-testid=section-nav] { visibility: hidden !important; }" };
const viewer = (p: Page) => p.getByTestId("structure-viewer");
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

interface Stats { created: number; disposed: number; rendered: string[]; current: string | null }
const stats = (p: Page) => p.evaluate(() => (window as unknown as { __MRDB_VIEWER_STATS: Stats }).__MRDB_VIEWER_STATS);
const withStats = (p: Page) => p.addInitScript(() => { (window as unknown as { __MRDB_VIEWER_STATS: object }).__MRDB_VIEWER_STATS = {}; });

async function waitReady(p: Page) {
  await expect(viewer(p)).toHaveAttribute("data-phase", "ready", { timeout: 45_000 });
}

/** Answer matching structure requests from the fixtures after a delay (the page may abort meanwhile). */
function delayed(delays: { re: RegExp; ms: number; file: string; type: string }[]) {
  return async (route: Route, url: URL) => {
    const d = delays.find((x) => x.re.test(url.toString()));
    if (!d) return false;
    await sleep(d.ms);
    try {
      await route.fulfill({ status: 200, headers: { ...CORS, "content-type": d.type }, body: readFileSync(resolve(FIX, d.file)) });
    } catch {
      // request already aborted by the page: expected for superseded loads
    }
    return true;
  };
}
const PDB_5ZIM = (ms: number) => ({ re: /models\.rcsb\.org\/v1\/5zim\//, ms, file: "5zim.bcif", type: "application/octet-stream" });
const PDB_4Y9H = (ms: number) => ({ re: /models\.rcsb\.org\/v1\/4y9h\//, ms, file: "4y9h.bcif", type: "application/octet-stream" });
const AF_P02945 = (ms: number) => ({ re: /AF-P02945-F1-model_v\d+\.pdb$/, ms, file: "AF-P02945-F1-model_v6.pdb", type: "chemical/x-pdb" });
const ABORTED = [/requestfailed: https:\/\/(models\.rcsb\.org|files\.rcsb\.org|alphafold\.ebi\.ac\.uk)/, /Failed to load resource/];

test.describe("1. source position in multi-accession entries", () => {
  test("MRDB000001: P02945 is (1 of 2), B0R5N9 is (2 of 2); switching updates the label", async ({ page, watch }) => {
    await page.goto("#/record/B0R5N9");
    const pos = page.getByTestId("source-position");
    await expect(page.getByTestId("record-eyebrow")).toContainText("MRDB000001 · source record B0R5N9 (2 of 2)");
    await expect(pos).toHaveAttribute("data-index", "2");
    await expect(pos).toHaveAttribute("data-total", "2");
    mkdirSync(OUT, { recursive: true });
    await page.screenshot({ path: resolve(OUT, "pr3a_eyebrow_B0R5N9_2of2_1440.png"), clip: { x: 0, y: 0, width: 1440, height: 360 } });
    await page.getByTestId("sources-table").locator('[data-source="P02945"]').getByTestId("source-switch").click();
    await expect(page.getByTestId("record-eyebrow")).toContainText("source record P02945 (1 of 2)");
    await page.goto("#/record/MRDB000001");
    await expect(page.getByTestId("record-eyebrow")).toContainText("source record P02945 (1 of 2)");
    expect(watch.errors).toEqual([]);
  });

  test("MRDB000249: each of the 7 sources shows its own position, in source-table order", async ({ page, watch }) => {
    await page.goto("#/record/MRDB000249");
    const rows = page.getByTestId("sources-table").locator("tbody tr[data-source]");
    await expect(rows).toHaveCount(7);
    const accs = await rows.evaluateAll((els) => els.map((e) => e.getAttribute("data-source")!));
    const seen: string[] = [];
    for (const [i, acc] of accs.entries()) {
      await page.goto(`#/record/${acc}`);
      await expect(page.getByTestId("record-page")).toHaveAttribute("data-focus", acc);
      await expect(page.getByTestId("source-position")).toHaveText(` (${i + 1} of 7)`);
      seen.push(await page.getByTestId("source-position").getAttribute("data-index") as string);
    }
    expect(seen).toEqual(["1", "2", "3", "4", "5", "6", "7"]);
    expect(watch.errors).toEqual([]);
  });

  test("single-source entry shows no position", async ({ page, watch }) => {
    await page.goto("#/record/MRDB000009");
    await expect(page.getByTestId("record-eyebrow")).toContainText("source record Q5V4H7");
    await expect(page.getByTestId("source-position")).toHaveCount(0);
    expect(watch.errors).toEqual([]);
  });
});

test.describe("2. Mol* async races", () => {
  test("slow PDB load superseded by AlphaFold DB: the stale structure is never shown", async ({ page, watch }) => {
    await withStats(page);
    await mockStructures(page, delayed([PDB_5ZIM(3000)]));
    await page.goto("#/record/MRDB000001");
    await page.getByTestId("viewer-load").click();
    await expect(viewer(page)).toHaveAttribute("data-phase", "loading", { timeout: 30_000 });
    await page.getByTestId("structure-picker").selectOption("afdb");
    await waitReady(page);
    await expect(viewer(page)).toHaveAttribute("data-selected", "afdb");
    await sleep(3500); // past the delayed 5ZIM response
    await expect(viewer(page)).toHaveAttribute("data-phase", "ready");
    await expect(page.getByTestId("viewer-status")).toContainText("AF-P02945-F1");
    const s = await stats(page);
    expect(s.created).toBe(1);
    expect(s.current).toMatch(/^AlphaFold DB AF-P02945-F1/);
    expect(s.rendered.some((l) => l.startsWith("5ZIM"))).toBe(false);
    expect(molstarChunk(watch).length).toBe(1);
    dropExpected(watch, ...ABORTED);
  });

  test("rapid switching through several structures: the last selection wins", async ({ page, watch }) => {
    await withStats(page);
    const log = await mockStructures(page, delayed([PDB_5ZIM(2500), AF_P02945(1200), PDB_4Y9H(400)]));
    await page.goto("#/record/MRDB000001");
    await page.getByTestId("viewer-load").click();
    await expect(viewer(page)).toHaveAttribute("data-phase", "loading", { timeout: 30_000 });
    const pick = page.getByTestId("structure-picker");
    for (const k of ["afdb", "pdb:4Y9H", "afdb", "pdb:5ZIM", "pdb:4Y9H"]) await pick.selectOption(k);
    await waitReady(page);
    await sleep(3000); // let every delayed response arrive
    await expect(viewer(page)).toHaveAttribute("data-selected", "pdb:4Y9H");
    await expect(viewer(page)).toHaveAttribute("data-phase", "ready");
    await expect(page.getByTestId("viewer-status")).toContainText("4Y9H");
    const s = await stats(page);
    expect(s.created).toBe(1);
    expect(s.current).toMatch(/^4Y9H/);
    expect(s.rendered.at(-1)).toMatch(/^4Y9H/);
    expect(s.rendered.filter((l) => !l.startsWith("4Y9H"))).toEqual([]);
    expect(log.hits.length).toBeGreaterThanOrEqual(3);
    dropExpected(watch, ...ABORTED);
  });

  test("double Retry after an error loads the structure once", async ({ page, watch }) => {
    await withStats(page);
    let fail = true;
    const slow = delayed([PDB_5ZIM(800)]);
    await mockStructures(page, async (route, url) => {
      if (fail) {
        await route.fulfill({ status: 404, headers: CORS, body: "x" });
        return true;
      }
      return slow(route, url);
    });
    await page.goto("#/record/MRDB000001");
    await page.getByTestId("viewer-load").click();
    await expect(viewer(page)).toHaveAttribute("data-phase", "error", { timeout: 30_000 });
    fail = false;
    // Two clicks in the same task, before React re-renders: two concurrent load requests.
    await page.getByTestId("viewer-retry").evaluate((b: HTMLButtonElement) => { b.click(); b.click(); });
    await waitReady(page);
    await sleep(1500);
    await expect(viewer(page)).toHaveAttribute("data-phase", "ready");
    const s = await stats(page);
    expect(s.created).toBe(1);
    expect(s.rendered).toHaveLength(1);
    expect(s.current).toMatch(/^5ZIM/);
    dropExpected(watch, /HTTP 404: https:\/\/(models|files)\.rcsb\.org/, ...ABORTED);
  });

  test("selection changed while Mol* is still initialising: one plugin, only the final selection is fetched", async ({ page, watch }) => {
    await withStats(page);
    const log = await mockStructures(page);
    await page.route(/\/assets\/molstarViewer-[^/]+\.js$/, async (r) => {
      await sleep(2000);
      await r.continue();
    });
    await page.goto("#/record/MRDB000001");
    await page.getByTestId("viewer-load").click();
    await expect(viewer(page)).toHaveAttribute("data-phase", "starting");
    await page.getByTestId("structure-picker").selectOption("pdb:4Y9H");
    await page.getByTestId("structure-picker").selectOption("afdb");
    await waitReady(page);
    await expect(viewer(page)).toHaveAttribute("data-selected", "afdb");
    const s = await stats(page);
    expect(s.created).toBe(1);
    expect(s.rendered).toHaveLength(1);
    expect(s.current).toMatch(/^AlphaFold DB/);
    expect(log.hits).toEqual(["https://alphafold.ebi.ac.uk/files/AF-P02945-F1-model_v6.pdb"]);
    expect(molstarChunk(watch).length).toBe(1);
  });

  test("leaving the page while a structure is loading disposes the plugin and commits nothing", async ({ page, watch }) => {
    await withStats(page);
    await mockStructures(page, delayed([PDB_5ZIM(2500)]));
    await page.goto("#/record/MRDB000001");
    await page.getByTestId("viewer-load").click();
    await expect(viewer(page)).toHaveAttribute("data-phase", "loading", { timeout: 30_000 });
    await page.goto("#/");
    await expect(page.getByTestId("record-page")).toHaveCount(0);
    await sleep(3000);
    const s = await stats(page);
    expect(s.created).toBe(1);
    expect(s.disposed).toBe(1);
    expect(s.rendered).toEqual([]);
    expect(s.current).toBeNull();
    dropExpected(watch, ...ABORTED);
  });

  test("leaving the page while Mol* is initialising never creates a plugin", async ({ page, watch }) => {
    await withStats(page);
    await mockStructures(page);
    await page.route(/\/assets\/molstarViewer-[^/]+\.js$/, async (r) => {
      await sleep(1500);
      await r.continue();
    });
    await page.goto("#/record/MRDB000001");
    await page.getByTestId("viewer-load").click();
    await expect(viewer(page)).toHaveAttribute("data-phase", "starting");
    await page.goto("#/");
    await sleep(3000);
    // The stats object is only filled by a constructed plugin; it stays empty here.
    const s = await stats(page);
    expect(s.created ?? 0).toBe(0);
    expect(s.disposed ?? 0).toBe(0);
    expect(s.rendered ?? []).toEqual([]);
    expect(molstarChunk(watch).length).toBe(1);
    expect(watch.errors).toEqual([]);
  });

  test("switching source while loading: the old viewer is disposed, the new one starts idle", async ({ page, watch }) => {
    await withStats(page);
    await mockStructures(page, delayed([PDB_5ZIM(2500)]));
    await page.goto("#/record/MRDB000001");
    await page.getByTestId("viewer-load").click();
    await expect(viewer(page)).toHaveAttribute("data-phase", "loading", { timeout: 30_000 });
    await page.getByTestId("sources-table").locator('[data-source="B0R5N9"]').getByTestId("source-switch").click();
    await expect(page.getByTestId("record-page")).toHaveAttribute("data-focus", "B0R5N9");
    await sleep(3000);
    await expect(viewer(page)).toHaveAttribute("data-phase", "idle");
    await expect(viewer(page)).toHaveAttribute("data-selected", "pdb:4Y9H");
    const s = await stats(page);
    expect(s.created).toBe(1);
    expect(s.disposed).toBe(1);
    expect(s.rendered).toEqual([]);
    dropExpected(watch, ...ABORTED);
  });
});

test.describe("4. release-model provenance warning", () => {
  for (const [mrdb, acc] of [["MRDB000030", "B0R633"], ["MRDB003319", "A0A9X2L7U0"]] as const) {
    test(`${mrdb} / ${acc}: warning in the Predicted section and the viewer; stored values unchanged`, async ({ page, watch }) => {
      await page.goto(`#/record/${acc}?section=predicted&structure=pred`);
      await expect(page.getByTestId("record-page")).toHaveAttribute("data-mrdb", mrdb);
      const rm = page.getByTestId("release-model");
      await expect(rm).toContainText("ESMCFold2 (full)");
      await expect(rm).toContainText("ESMFold prediction for clade rep");
      const w = page.getByTestId("release-provenance-warning");
      await expect(w).toBeVisible();
      await expect(w).toContainText('Method label discrepancy: the stored method is "ESMCFold2 (full)"');
      await expect(w).toContainText("note and file name refer to ESMFold");
      await expect(w).toContainText("not been corrected");
      await expect(page.getByTestId("viewer-provenance-warning")).toContainText("Method label discrepancy");
      if (acc === "B0R633") {
        mkdirSync(OUT, { recursive: true });
        await page.getByTestId("section-predicted").screenshot({ path: resolve(OUT, "pr3a_provenance_B0R633_1440.png"), ...SHOT });
      }
      // Experimental structures carry no such warning.
      await page.goto("#/record/MRDB000001");
      await expect(viewer(page)).toHaveAttribute("data-selected", "pdb:5ZIM");
      await expect(page.getByTestId("viewer-provenance-warning")).toHaveCount(0);
      expect(watch.errors).toEqual([]);
    });
  }
});

test.describe("5. minor UI corrections", () => {
  test("MR_CLD3_017 mini-tree label lies entirely outside the highlight outline and inside the drawing", async ({ page, watch }) => {
    await page.goto("#/record/A0A135LS53?section=phylogeny");
    await page.getByTestId("mini-tree-show").click();
    await expect(page.getByTestId("tree-highlight-arc").first()).toBeVisible({ timeout: 20_000 });
    const label = page.getByTestId("mini-tree").locator('[data-testid="tree-label"][data-highlighted="true"]');
    await expect(label).toHaveCount(1);
    await expect(label).toHaveAttribute("data-group", "MR_CLD3_017");
    await expect(label).toHaveText("017!");
    const g = await label.evaluate((t: SVGTextElement) => {
      const b = t.getBBox();
      const vb = t.ownerSVGElement!.viewBox.baseVal;
      const dx = Math.max(0, b.x, -(b.x + b.width));
      const dy = Math.max(0, b.y, -(b.y + b.height));
      return { minDist: Math.hypot(dx, dy), clearR: Number(t.dataset.clearR), b: { x: b.x, y: b.y, w: b.width, h: b.height }, vb: { x: vb.x, y: vb.y, w: vb.width, h: vb.height } };
    });
    expect(g.clearR).toBeGreaterThan(0);
    expect(g.minDist, JSON.stringify(g)).toBeGreaterThanOrEqual(g.clearR);
    expect(g.b.x).toBeGreaterThanOrEqual(g.vb.x);
    expect(g.b.y).toBeGreaterThanOrEqual(g.vb.y);
    expect(g.b.x + g.b.w).toBeLessThanOrEqual(g.vb.x + g.vb.w);
    expect(g.b.y + g.b.h).toBeLessThanOrEqual(g.vb.y + g.vb.h);
    // The label is the topmost element at its own centre (not covered by the outline).
    const top = await label.evaluate((t: SVGTextElement) => {
      const r = t.getBoundingClientRect();
      const el = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
      return el === t || t.contains(el);
    });
    expect(top).toBe(true);
    mkdirSync(OUT, { recursive: true });
    await page.getByTestId("mini-tree").screenshot({ path: resolve(OUT, "pr3a_minitree_A0A135LS53_017_1440.png"), ...SHOT });
    expect(watch.errors).toEqual([]);
  });

  test("Copy link keeps the selected section and structure (and drops invalid parameters)", async ({ page, watch }) => {
    await page.addInitScript(() => {
      const w = window as unknown as { __copied: string[] };
      w.__copied = [];
      Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: async (t: string) => { w.__copied.push(t); } } });
    });
    const copied = async () => {
      await page.getByTestId("copy-link").click();
      await expect(page.getByText("Link copied (includes the selected section and structure).")).toBeVisible();
      const all = await page.evaluate(() => (window as unknown as { __copied: string[] }).__copied);
      return new URL(all.at(-1)!);
    };
    await page.goto("#/record/B0R5N9");
    await page.getByTestId("structure-picker").selectOption("afdb");
    await expect(page).toHaveURL(/structure=afdb/);
    await page.locator('[data-testid="section-nav"] [data-section="predicted"]').click();
    await expect(page).toHaveURL(/section=predicted/);
    let u = await copied();
    expect(u.hash).toBe("#/record/B0R5N9?section=predicted&structure=afdb");
    expect(new URL(page.url()).pathname).toBe(u.pathname);

    await page.goto("#/record/MRDB000001?section=bogus&structure=pdb:4Y9H");
    await expect(viewer(page)).toHaveAttribute("data-selected", "pdb:4Y9H");
    u = await copied();
    expect(u.hash).toBe("#/record/MRDB000001?structure=pdb:4Y9H");

    // The copied link reopens the same view.
    await page.goto("#/record/B0R5N9?section=predicted&structure=afdb");
    await expect(viewer(page)).toHaveAttribute("data-selected", "afdb");
    await expect(page.getByTestId("section-predicted")).toBeInViewport();
    expect(watch.errors).toEqual([]);
  });
});
