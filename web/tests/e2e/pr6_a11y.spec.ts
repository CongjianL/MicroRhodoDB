/**
 * PR-6 accessibility audit: axe-core (WCAG 2.0/2.1/2.2 A + AA rules) on every mandatory route at
 * 375 / 768 / 1440 px, plus per-page semantic checks (one <h1>, <main> landmark, <html lang>,
 * document title, named form controls). Fails on any axe violation of impact "serious" or "critical";
 * page-level horizontal overflow (responsive layout) is checked and, with SCREENSHOT_DIR set, a viewport
 * screenshot is saved per route and width. All violations of any impact are written to $AUDIT_DIR/axe_<route>_<width>.json for the report.
 *
 * Charts are rendered as SVG by ECharts and are aria-hidden with a data table alternative; the
 * tree canvases expose a text alternative (tested in pr6_reliability.spec.ts). axe still scans them.
 */
import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "./fixtures";
import { ROUTES } from "./pr6Routes";

const OUT = resolve(process.env.AUDIT_DIR ?? "test-results/pr6-audit");
const VIEWPORTS = [
  { w: 375, h: 812 },
  { w: 768, h: 1024 },
  { w: 1440, h: 900 },
] as const;



const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

for (const vp of VIEWPORTS) {
  test.describe(`axe ${vp.w}px`, () => {
    test.use({ viewport: { width: vp.w, height: vp.h } });
    for (const r of ROUTES) {
      test(`${r.name}: no serious/critical WCAG A/AA violations; semantics`, async ({ page, watch }) => {
        await page.goto(r.hash);
        await r.ready(page);
        await page.waitForLoadState("networkidle");
        const res = await new AxeBuilder({ page }).withTags(TAGS).analyze();
        const viol = res.violations.map((v) => ({
          id: v.id, impact: v.impact, help: v.help, tags: v.tags.filter((t) => t.startsWith("wcag")),
          nodes: v.nodes.length, targets: v.nodes.slice(0, 8).map((n) => n.target.join(" ")),
          summary: v.nodes[0]?.failureSummary ?? "",
        }));
        const sem = await page.evaluate(() => ({
          h1: document.querySelectorAll("h1").length,
          main: document.querySelectorAll("main").length,
          lang: document.documentElement.lang,
          title: document.title,
          pageOverflowPx: document.documentElement.scrollWidth - window.innerWidth,
          unnamedControls: [...document.querySelectorAll("input:not([type=hidden]),select,textarea,button")]
            .filter((el) => {
              const e = el as HTMLElement;
              if (e.offsetParent === null && getComputedStyle(e).position !== "fixed") return false;
              const lbl = (el as HTMLInputElement).labels?.length ?? 0;
              return !lbl && !e.getAttribute("aria-label") && !e.getAttribute("aria-labelledby") && !(e.textContent ?? "").trim() && !e.getAttribute("title");
            }).map((el) => el.outerHTML.slice(0, 120)),
        }));
        mkdirSync(OUT, { recursive: true });
        writeFileSync(resolve(OUT, `axe_${r.name}_${vp.w}.json`), JSON.stringify({
          route: r.hash, width: vp.w, passes: res.passes.length, incomplete: res.incomplete.map((v) => ({
            id: v.id, nodes: v.nodes.length,
            // Why axe could not decide (e.g. bgOverlap, bgGradient, pseudoContent) with one example target each.
            reasons: Object.entries(v.nodes.reduce<Record<string, { n: number; example: string; fg?: string; bg?: string }>>((acc, n) => {
              const d = (n.any[0]?.data ?? {}) as { messageKey?: string; fgColor?: string; bgColor?: string };
              const k = d.messageKey ?? n.any[0]?.id ?? "unknown";
              acc[k] ??= { n: 0, example: n.target.join(" "), fg: d.fgColor, bg: d.bgColor };
              acc[k].n++;
              return acc;
            }, {})).map(([key, x]) => ({ key, ...x })),
          })),
          violations: viol, semantics: sem,
        }, null, 1));
        if (process.env.SCREENSHOT_DIR) {
          mkdirSync(resolve(process.env.SCREENSHOT_DIR), { recursive: true });
          await page.screenshot({ path: resolve(process.env.SCREENSHOT_DIR, `${r.name}_${vp.w}.png`) });
        }
        expect(sem.pageOverflowPx, "no page-level horizontal scrolling (wide tables scroll inside their own region)").toBeLessThanOrEqual(1);
        expect(sem.h1, "exactly one h1").toBe(1);
        expect(sem.main, "one main landmark").toBe(1);
        expect(sem.lang).toBe("en");
        expect(sem.title).toMatch(/MicroRhodoDB/);
        expect(sem.unnamedControls, "form controls without an accessible name").toEqual([]);
        expect(viol.filter((v) => v.impact === "serious" || v.impact === "critical"), "serious/critical axe violations").toEqual([]);
        expect(watch.errors).toEqual([]);
      });
    }
  });
}
