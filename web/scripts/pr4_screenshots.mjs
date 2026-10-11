// PR-4 review screenshots of the Phylogeny explorer and Clade Explorer pages, plus one exported
// SVG figure. Needs a build and a running static server (scripts/serve_e2e.py <port>).
//
// Usage: node scripts/pr4_screenshots.mjs <baseURL> <outDir>
import { chromium } from "@playwright/test";
import { copyFileSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";

const [base = "http://127.0.0.1:4173/MicroRhodoDB/site/", outArg = "../docs/website/pr4/screenshots"] = process.argv.slice(2);
const OUT = resolve(outArg);
mkdirSync(OUT, { recursive: true });
const CANVAS = '[data-testid="tree-canvas"],[data-testid="clade-tree-canvas"]';

const select = async (p, pre) => {
  const hit = p.locator(`[data-testid="tree-hits"] [data-pre="${pre}"]`).first();
  await hit.dispatchEvent("pointerdown", { pointerId: 7, isPrimary: true, bubbles: true });
  await hit.dispatchEvent("pointerup", { pointerId: 7, isPrimary: true, bubbles: true });
};

const SHOTS = [
  { n: "phylogeny_top", h: "#/phylogeny", w: 1440 },
  { n: "phylogeny_rect", h: "#/phylogeny", w: 1440, canvas: true },
  { n: "phylogeny_radial", h: "#/phylogeny?layout=radial", w: 1440, canvas: true },
  { n: "phylogeny_radial_uniform_function", h: "#/phylogeny?layout=radial&bl=uniform&color=function", w: 1440, canvas: true },
  { n: "phylogeny_support_clade017", h: "#/phylogeny?clade=MR_CLD3_017&support=1", w: 1440, canvas: true },
  { n: "phylogeny_node744_panel", h: "#/phylogeny?support=1", w: 1440, canvas: true, act: (p) => select(p, 744) },
  { n: "phylogeny_rootsplit_panel", h: "#/phylogeny?support=1", w: 1440, canvas: true, act: (p) => select(p, 30) },
  { n: "phylogeny_discrepancy894_panel", h: "#/phylogeny?support=1", w: 1440, canvas: true, act: (p) => select(p, 894) },
  { n: "phylogeny_tip_Q9UW81", h: "#/phylogeny?tip=Q9UW81&color=evidence", w: 1440, canvas: true },
  { n: "phylogeny_tip_absent_QBQ84355", h: "#/phylogeny?tip=QBQ84355", w: 1440, canvas: true },
  { n: "phylogeny_placement_MRDB000101", h: "#/phylogeny?placement=MRDB000101", w: 1440, canvas: true },
  { n: "phylogeny_subtree744_support", h: "#/phylogeny?node=744&support=1&color=subclade", w: 1440, canvas: true },
  { n: "phylogeny_collapsed", h: "#/phylogeny", w: 1440, canvas: true, act: (p) => p.click('[data-testid="collapse-all"]') },
  { n: "phylogeny_clade_table", h: "#/phylogeny", w: 1440, scrollTo: '[data-testid="clade-explorer"]' },
  { n: "phylogeny_downloads", h: "#/phylogeny", w: 1440, scrollTo: '[data-testid="tree-downloads"]' },
  { n: "phylogeny_rect", h: "#/phylogeny", w: 768, canvas: true },
  { n: "phylogeny_rect", h: "#/phylogeny", w: 375, canvas: true },
  { n: "phylogeny_toolbar", h: "#/phylogeny", w: 375, scrollTo: '[data-testid="tree-toolbar"]' },
  { n: "clade_017_top", h: "#/clade/MR_CLD3_017", w: 1440 },
  { n: "clade_017_tree", h: "#/clade/MR_CLD3_017", w: 1440, canvas: true },
  { n: "clade_017_top", h: "#/clade/MR_CLD3_017", w: 375 },
  { n: "clade_017.01_subclade", h: "#/clade/MR_CLD3_017.01", w: 1440 },
  { n: "clade_B01_backbone", h: "#/clade/MR_CLD3_B01", w: 1440 },
  { n: "clade_001_members_absent", h: "#/clade/MR_CLD3_001", w: 1440, scrollTo: '[data-testid="clade-members"]' },
  { n: "home_phylogeny_nav", h: "#/", w: 1440 },
];

const b = await chromium.launch();
let errors = 0;
for (const s of SHOTS) {
  const p = await b.newPage({ viewport: { width: s.w, height: s.w < 800 ? (s.w < 500 ? 812 : 1024) : 900 } });
  p.on("console", (m) => { if (m.type() === "error") { errors++; console.error(s.n, m.text()); } });
  p.on("pageerror", (e) => { errors++; console.error(s.n, String(e)); });
  await p.goto(base + s.h);
  await p.waitForSelector(s.h.startsWith("#/clade") || s.h.startsWith("#/phylogeny") ? CANVAS : '[data-testid="stat-cards"]', { state: "visible", timeout: 30000 });
  await p.evaluate(() => document.fonts.ready);
  if (s.act) await s.act(p);
  const sel = s.canvas ? CANVAS : s.scrollTo;
  if (sel) await p.locator(sel).first().evaluate((e) => e.scrollIntoView({ block: "start" }));
  await p.evaluate(() => window.scrollBy(0, -72));
  await p.waitForTimeout(500);
  await p.screenshot({ path: resolve(OUT, `pr4_${s.n}_${s.w}.png`) });
  await p.close();
}

// one exported figure (SVG) of the full tree with support and the legacy clade hatched
const ctx = await b.newContext({ viewport: { width: 1440, height: 900 }, acceptDownloads: true });
const p = await ctx.newPage();
await p.goto(base + "#/phylogeny?support=1");
await p.waitForSelector('[data-testid="tree-canvas"]');
const [dl] = await Promise.all([p.waitForEvent("download"), p.click('[data-testid="dl-svg"]')]);
copyFileSync(await dl.path(), resolve(OUT, "pr4_export_" + dl.suggestedFilename()));
await b.close();
console.log(`wrote ${SHOTS.length} screenshots + 1 SVG export to ${OUT}; console errors: ${errors}`);
if (errors) process.exit(1);
