// PR-2 performance + contrast capture (browser side). Driven by scripts/pr2_perf_audit.py, which
// starts the static server, runs this script, and post-processes the JSON (file sizes, gzip, tables).
//
// For each route and run: fresh browser context (cold HTTP cache), record every request URL and the
// time at which the route's "ready" element is present. On the first run per route at 1440 px, also
// run a WCAG text-contrast scan over visible HTML text (computed colour vs. first opaque ancestor
// background; SVG/canvas text is not scanned).
//
// Usage: node scripts/perf_capture.mjs <baseURL> <runs> <out.json>
import { chromium } from "@playwright/test";
import { writeFileSync } from "node:fs";

const [baseURL = "http://127.0.0.1:4173/MicroRhodoDB/site/", runsArg = "5", out = "perf_capture.json"] = process.argv.slice(2);
const RUNS = Number(runsArg);

const ROUTES = [
  { id: "home", hash: "#/", ready: '[data-testid="stat-cards"]', also: 'svg[data-testid="tree-preview"] path' },
  { id: "about", hash: "#/about", ready: '[data-testid="clade-support-notice"]' },
  { id: "browse", hash: "#/browse", ready: '[data-testid="results-table"] tbody tr' },
  { id: "browse_clade017_tent", hash: "#/browse?group=all&eng=1&clade=MR_CLD3_017&tent=1", ready: '[data-testid="results-table"] tbody tr' },
  { id: "record_source", hash: "#/record/P02945", ready: '[data-testid="sequence"]' },
  { id: "record_mrdb", hash: "#/record/MRDB000001", ready: '[data-testid="sequence"]' },
  { id: "planned_phylogeny", hash: "#/phylogeny", ready: '[data-testid="planned-notice"]' },
];

function contrastScan() {
  const lum = ([r, g, b]) => {
    const f = (c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
  };
  const parse = (s) => { const m = s.match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(/[ ,/]+/).filter(Boolean).map(Number); return { rgb: p.slice(0, 3), a: p.length > 3 ? p[3] : 1 }; };
  const bgOf = (el) => {
    let layers = [];
    for (let e = el; e; e = e.parentElement) {
      const c = parse(getComputedStyle(e).backgroundColor);
      if (c && c.a > 0) { layers.push(c); if (c.a >= 1) break; }
    }
    let rgb = [255, 255, 255];
    for (const l of layers.reverse()) rgb = rgb.map((v, i) => Math.round(l.rgb[i] * l.a + v * (1 - l.a)));
    return rgb;
  };
  const results = new Map();
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const text = n.textContent.trim();
    const el = n.parentElement;
    if (!text || !el || el.closest("svg, canvas, script, style, noscript")) continue;
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    if (r.width === 0 || r.height === 0 || cs.visibility === "hidden" || Number(cs.opacity) === 0) continue;
    if (el.closest('[aria-hidden="true"]') || el.closest(".sr-only, .sr-only-focusable")) continue;
    const fg = parse(cs.color); if (!fg) continue;
    const bg = bgOf(el);
    const fgRgb = fg.rgb.map((v, i) => Math.round(v * fg.a + bg[i] * (1 - fg.a)));
    const L1 = lum(fgRgb), L2 = lum(bg);
    const ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
    const px = parseFloat(cs.fontSize), bold = Number(cs.fontWeight) >= 700;
    const large = px >= 24 || (bold && px >= 18.66);
    const need = large ? 3 : 4.5;
    const key = `${fgRgb.join(",")}|${bg.join(",")}|${large}`;
    const cur = results.get(key) ?? { fg: `rgb(${fgRgb})`, bg: `rgb(${bg})`, ratio: Math.round(ratio * 100) / 100, large, need, count: 0, sample: text.slice(0, 40) };
    cur.count++;
    results.set(key, cur);
  }
  return [...results.values()].sort((a, b) => a.ratio - b.ratio);
}

const browser = await chromium.launch();
const env = { userAgent: "", chromium: browser.version(), runs: RUNS, baseURL };
const routes = [];
for (const r of ROUTES) {
  const runs = [];
  let contrast = null;
  for (let i = 0; i < RUNS; i++) {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await ctx.newPage();
    if (!env.userAgent) env.userAgent = await page.evaluate(() => navigator.userAgent);
    const requests = [];
    const errors = [];
    page.on("request", (q) => requests.push(q.url()));
    page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
    page.on("pageerror", (e) => errors.push(e.message));
    await page.goto(baseURL + r.hash, { waitUntil: "commit" });
    await page.waitForSelector(r.ready, { state: "attached", timeout: 30000 });
    const readyMs = await page.evaluate(() => performance.now());
    if (r.also) await page.waitForSelector(r.also, { state: "attached", timeout: 30000 });
    const alsoMs = r.also ? await page.evaluate(() => performance.now()) : null;
    await page.waitForLoadState("networkidle");
    const nav = await page.evaluate(() => {
      const n = performance.getEntriesByType("navigation")[0];
      const fcp = performance.getEntriesByName("first-contentful-paint")[0];
      return { dcl: n.domContentLoadedEventEnd, load: n.loadEventEnd, fcp: fcp ? fcp.startTime : null };
    });
    if (i === 0) contrast = await page.evaluate(contrastScan);
    runs.push({ readyMs, alsoMs, ...nav, requests: [...new Set(requests)], errors });
    await ctx.close();
  }
  routes.push({ id: r.id, hash: r.hash, ready: r.ready, also: r.also ?? null, runs, contrast });
}
await browser.close();
writeFileSync(out, JSON.stringify({ env, routes }, null, 1));
console.log(`wrote ${out}`);
