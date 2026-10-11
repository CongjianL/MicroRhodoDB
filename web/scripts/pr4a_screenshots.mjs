// PR-4a review screenshots: formal assignments vs placements on clade pages (B02, B01, 017, 017.02)
// and the MR_CLD3_009 E1 note, at 375 / 768 / 1440 px. Needs a build and a running static server
// (scripts/serve_e2e.py <port>). Fails on console errors or horizontal overflow.
//
// Usage: node scripts/pr4a_screenshots.mjs <baseURL> <outDir>
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";

const [base = "http://127.0.0.1:4173/MicroRhodoDB/site/", outArg = "../docs/website/pr4a/screenshots"] = process.argv.slice(2);
const OUT = resolve(outArg);
mkdirSync(OUT, { recursive: true });

const SHOTS = [];
for (const w of [375, 768, 1440]) {
  SHOTS.push({ n: "clade_B02_assignments", h: "#/clade/MR_CLD3_B02", w, sel: '[data-testid="clade-assignments"]' });
  SHOTS.push({ n: "clade_017_assignments", h: "#/clade/MR_CLD3_017", w, sel: '[data-testid="clade-assignments"]' });
  SHOTS.push({ n: "clade_009_e1_note", h: "#/clade/MR_CLD3_009", w, sel: '[data-testid="clade-function"]' });
}
SHOTS.push({ n: "clade_017_subclade_table", h: "#/clade/MR_CLD3_017", w: 1440, sel: '[data-testid="clade-subclades"]' });
SHOTS.push({ n: "clade_017.02_assignments", h: "#/clade/MR_CLD3_017.02", w: 1440, sel: '[data-testid="clade-assignments"]' });
SHOTS.push({ n: "clade_B01_assignments", h: "#/clade/MR_CLD3_B01", w: 1440, sel: '[data-testid="clade-assignments"]' });

const b = await chromium.launch();
let errors = 0;
for (const s of SHOTS) {
  const ctx = await b.newContext({ viewport: { width: s.w, height: 900 } });
  const p = await ctx.newPage();
  p.on("console", (m) => { if (m.type() === "error") { errors++; console.error(s.n, m.text()); } });
  p.on("pageerror", (e) => { errors++; console.error(s.n, String(e)); });
  await p.goto(base + s.h);
  await p.waitForSelector(s.sel, { state: "visible", timeout: 30000 });
  await p.evaluate(() => document.fonts.ready);
  const ow = await p.evaluate(() => document.documentElement.scrollWidth);
  if (ow > s.w) { errors++; console.error(`${s.n} ${s.w}: horizontal overflow ${ow}`); }
  await p.locator(s.sel).first().evaluate((e) => e.scrollIntoView({ block: "start" }));
  await p.evaluate(() => window.scrollBy(0, -72));
  await p.waitForTimeout(300);
  await p.screenshot({ path: resolve(OUT, `pr4a_${s.n}_${s.w}.png`) });
  await ctx.close();
}
await b.close();
console.log(`wrote ${SHOTS.length} screenshots to ${OUT}; errors: ${errors}`);
if (errors) process.exit(1);
