/**
 * Responsive audit at 375 / 768 / 1440 px: no horizontal page overflow, no console errors, key
 * content visible, wide tables scroll inside their own container. Screenshots are written to
 * $SCREENSHOT_DIR (default test-results/screenshots) for manual review.
 */
import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import type { Page } from "@playwright/test";
import { expect, expectNoHorizontalOverflow, test } from "./fixtures";

const OUT = resolve(process.env.SCREENSHOT_DIR ?? "test-results/screenshots");
const VIEWPORTS = [
  { w: 375, h: 812 },
  { w: 768, h: 1024 },
  { w: 1440, h: 900 },
] as const;

const PAGES: { name: string; hash: string; ready: (p: Page) => Promise<void> }[] = [
  { name: "home", hash: "#/", ready: async (p) => {
    await expect(p.getByTestId("tree-preview")).toBeVisible();
    await expect(p.getByTestId("chart-evidence").locator("svg").first()).toBeVisible();
  } },
  { name: "browse", hash: "#/browse", ready: async (p) => { await expect(p.getByTestId("results-table")).toBeVisible(); } },
  { name: "browse_clade017_tent", hash: "#/browse?group=all&eng=1&clade=MR_CLD3_017&tent=1", ready: async (p) => {
    await expect(p.getByTestId("caveat-count")).toBeVisible();
  } },
  { name: "record_P02945", hash: "#/record/P02945", ready: async (p) => { await expect(p.getByTestId("sequence")).toBeVisible(); } },
  { name: "about", hash: "#/about", ready: async (p) => { await expect(p.getByTestId("clade-support-notice")).toBeVisible(); } },
  // PR-4: Phylogeny is a real page now (was planned_phylogeny)
  { name: "phylogeny", hash: "#/phylogeny", ready: async (p) => { await expect(p.getByTestId("tree-canvas")).toBeVisible(); } },
  { name: "clade_017", hash: "#/clade/MR_CLD3_017", ready: async (p) => { await expect(p.getByTestId("clade-tree-canvas")).toBeVisible(); } },
];

const audit: Record<string, unknown>[] = [];

for (const vp of VIEWPORTS) {
  test.describe(`viewport ${vp.w}px`, () => {
    test.use({ viewport: { width: vp.w, height: vp.h } });
    for (const pg of PAGES) {
      test(`${pg.name}: no horizontal overflow, screenshot`, async ({ page, watch }) => {
        await page.goto(pg.hash);
        await pg.ready(page);
        await page.waitForLoadState("networkidle");
        await page.evaluate(() => document.fonts.ready);
        await expectNoHorizontalOverflow(page);
        const m = await page.evaluate(() => {
          const sc = document.querySelector('[data-testid="results-scroll"]') as HTMLElement | null;
          const header = document.querySelector("header") as HTMLElement | null;
          return {
            scrollWidth: document.documentElement.scrollWidth,
            innerWidth: window.innerWidth,
            scrollHeight: document.documentElement.scrollHeight,
            headerHeight: header ? Math.round(header.getBoundingClientRect().height) : null,
            tableScroll: sc ? { client: sc.clientWidth, scroll: sc.scrollWidth } : null,
          };
        });
        if (m.tableScroll) {
          // the table may be wider than the viewport, but only inside its own scroll container
          expect(m.tableScroll.client).toBeLessThanOrEqual(vp.w);
        }
        if (vp.w < 1024) {
          // mobile/tablet: primary navigation collapses into the Menu button
          await expect(page.getByRole("button", { name: /menu/i })).toBeVisible();
        } else {
          await expect(page.getByRole("navigation", { name: "Primary", exact: true })).toBeVisible();
        }
        mkdirSync(OUT, { recursive: true });
        await page.screenshot({ path: resolve(OUT, `pr2_${pg.name}_${vp.w}.png`), fullPage: false });
        await page.screenshot({ path: resolve(OUT, `pr2_${pg.name}_${vp.w}_full.png`), fullPage: true });
        audit.push({ page: pg.name, hash: pg.hash, viewport: vp.w, ...m, console_errors: watch.errors.length });
        writeFileSync(resolve(OUT, `audit_${vp.w}_${pg.name}.json`), JSON.stringify(audit.at(-1), null, 1));
      });
    }

    test("mobile menu opens with keyboard and closes on Escape", async ({ page, watch }) => {
      test.skip(vp.w >= 1024, "desktop shows the full navigation");
      await page.goto("#/");
      const btn = page.getByRole("button", { name: /menu/i });
      await btn.focus();
      await page.keyboard.press("Enter");
      await expect(btn).toHaveAttribute("aria-expanded", "true");
      const nav = page.getByRole("navigation", { name: "Primary (mobile)" });
      await expect(nav.getByRole("link", { name: "Browse" })).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(btn).toHaveAttribute("aria-expanded", "false");
      await btn.click();
      await nav.getByRole("link", { name: "Browse" }).click();
      await expect(page).toHaveURL(/#\/browse$/);
      await expect(btn).toHaveAttribute("aria-expanded", "false");
      await expectNoHorizontalOverflow(page);
      expect(watch.errors).toEqual([]);
    });

    test("browse filters are reachable (sidebar on desktop, collapsible on mobile)", async ({ page, watch }) => {
      await page.goto("#/browse");
      await expect(page.getByTestId("results-table")).toBeVisible();
      if (vp.w < 1024) {
        const d = page.getByTestId("mobile-filters");
        await d.locator("summary").click();
      }
      const ev = page.locator('[data-testid="filter-evidence"]:visible');
      await ev.selectOption("E3");
      await expect(page).toHaveURL(/evidence=E3/);
      await expectNoHorizontalOverflow(page);
      expect(watch.errors).toEqual([]);
    });
  });
}
