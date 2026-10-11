// PR-6 performance + contrast capture (browser side). Driven by scripts/pr6_perf_audit.py, which starts
// scripts/serve_perf.py (gzip, no-store), runs this script and post-processes the JSON.
//
// Mode "perf": for each profile (desktop / mobile) and route, RUNS cold loads in fresh browser contexts
// with Chrome DevTools Protocol throttling applied before navigation:
//   desktop  1440x900, DPR 1, RTT 40 ms, 10 Mbit/s down / 10 Mbit/s up, CPU 1x  (Lighthouse desktop)
//   mobile    375x812, DPR 2, touch, RTT 562.5 ms, 1.47 Mbit/s down / 0.675 Mbit/s up, CPU 4x
//            (Lighthouse "Slow 4G" values as applied by DevTools throttling)
// Recorded per run: web-vitals 6 (FCP, LCP, CLS, TTFB; INP after the scripted interactions, reported with
// durationThreshold 16 ms), the time at which the route's ready selector is attached, long tasks and a
// total-blocking-time proxy (sum of long-task time above 50 ms until ready+network idle), JS heap after
// garbage collection, encoded (transferred) and decoded bytes per request, and the timing of route
// interactions (tree layout toggle, Browse filter, text search, sequence search, Mol* viewer with
// RCSB/AlphaFold DB answered from tests/fixtures/structures).
//
// Mode "contrast": unthrottled, every route at 375/768/1440, WCAG 2.x contrast of every visible text node,
// including text inside horizontally scrolled regions (which axe reports as "incomplete") and SVG <text>
// (fill colour vs. the first opaque HTML ancestor background). Canvas pixels are not scanned.
//
// Usage: node scripts/pr6_perf.mjs <baseURL> <mode: perf|contrast> <runs> <out.json>
import { chromium } from "@playwright/test";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const [baseURL, MODE = "perf", runsArg = "3", out = "pr6_perf.json"] = process.argv.slice(2);
const RUNS = Number(runsArg);
const HERE = dirname(fileURLToPath(import.meta.url));
const FIX = resolve(HERE, "../tests/fixtures/structures");
// Playwright evaluates init-script content in its own scope, so the IIFE's `var webVitals` is exported explicitly.
const WV = readFileSync(resolve(HERE, "../node_modules/web-vitals/dist/web-vitals.iife.js"), "utf8")
  .replace(/\/\/# sourceMappingURL=.*$/m, "") + "\n;window.webVitals = webVitals;";
const EXTERNAL = /^https:\/\/(models\.rcsb\.org|files\.rcsb\.org|alphafold\.ebi\.ac\.uk)\//;
const CANVAS = '[data-testid="tree-canvas"]';

// PR6_ONLY=id1,id2 restricts the route set (pilot runs).
const ONLY = (process.env.PR6_ONLY ?? "").split(",").filter(Boolean);
const PROFILES = {
  desktop: { viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1, isMobile: false, hasTouch: false,
    net: { latency: 40, downloadThroughput: (10240 * 1024) / 8, uploadThroughput: (10240 * 1024) / 8 }, cpu: 1 },
  mobile: { viewport: { width: 375, height: 812 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true,
    net: { latency: 562.5, downloadThroughput: (1474.56 * 1024) / 8, uploadThroughput: (675 * 1024) / 8 }, cpu: 4 },
};

const typeQ = (sel, value, submit) => async (page) => {
  const mf = page.locator('[data-testid="mobile-filters"]');
  if (sel === '[data-testid="filter-q"]' && (await mf.isVisible().catch(() => false))) await mf.click();
  const input = page.locator(sel).filter({ visible: true }).first();
  await input.fill(value);
  if (submit) await page.locator(submit).filter({ visible: true }).first().click(); else await input.press("Enter");
};

const ROUTES = [
  { id: "home", hash: "#/", ready: '[data-testid="stat-cards"]' },
  { id: "browse", hash: "#/browse", ready: '[data-testid="results-table"] tbody tr', interact: [
    { name: "browse_filter_text", run: typeQ('[data-testid="filter-q"]', "halorhodopsin"), done: '[data-testid="filter-chips"]' },
  ] },
  { id: "browse_clade017_tent", hash: "#/browse?group=all&eng=1&clade=MR_CLD3_017&tent=1", ready: '[data-testid="results-table"] tbody tr' },
  { id: "record_P02945", hash: "#/record/P02945", ready: '[data-testid="sequence"]', interact: [
    { name: "molstar_mocked_load", run: async (p) => p.click('[data-testid="viewer-load"]'), done: '[data-testid="structure-viewer"][data-phase="ready"]', timeout: 120000 },
  ] },
  { id: "record_engineered", hash: "#/record/A0ABF7PQA2", ready: '[data-testid="sequence"]' },
  { id: "about", hash: "#/about", ready: '[data-testid="clade-support-notice"]' },
  { id: "phylogeny", hash: "#/phylogeny", ready: `${CANVAS}[data-visible-leaves="472"] path`, interact: [
    { name: "tree_layout_radial", run: async (p) => p.click('[data-testid="layout-radial"]'), done: `${CANVAS}[data-layout="radial"]` },
    { name: "tree_layout_rect", run: async (p) => p.click('[data-testid="layout-rect"]'), done: `${CANVAS}[data-layout="rect"]` },
    { name: "tree_support_on", run: async (p) => p.click('[data-testid="support-toggle"]'), done: '[data-testid="tree-support"] > g:nth-child(469)' },
  ] },
  { id: "clade_017", hash: "#/clade/MR_CLD3_017", ready: '[data-testid="clade-tree-canvas"] path' },
  { id: "statistics", hash: "#/statistics", ready: '[data-testid="chart-evidence-level"] svg' },
  { id: "evidence", hash: "#/evidence", ready: '[data-testid="e1-table"] tbody tr' },
  { id: "structures", hash: "#/structures", ready: '[data-testid="pdb-table"] tbody tr' },
  { id: "watchlist", hash: "#/watchlist", ready: '[data-testid="wl-table"] tbody tr' },
  { id: "search_text", hash: "#/search", ready: '[data-testid="text-q"]', interact: [
    { name: "text_search_MR_CLD3_017", run: typeQ('[data-testid="text-q"]', "MR_CLD3_017", '[data-testid="text-submit"]'), done: '[data-testid="text-results"] tbody tr', timeout: 120000 },
  ] },
  { id: "search_seq", hash: "#/search?mode=sequence", ready: '[data-testid="seq-example"]', interact: [
    { name: "seq_load_example", run: async (p) => p.click('[data-testid="seq-example"]'), done: '[data-testid="seq-input"]:not([data-length="0"])' },
    { name: "seq_search_P02945", run: async (p) => p.click('[data-testid="seq-run"]'), done: '[data-testid="seq-hit-1"][data-acc="P02945"]', timeout: 180000 },
  ] },
  { id: "downloads", hash: "#/downloads", ready: '[data-testid="dl-release-files"] tbody tr' },
  { id: "methods", hash: "#/methods", ready: '[data-testid="methods-denominators"]' },
  { id: "citation", hash: "#/citation", ready: '[data-testid="cite-bibtex"]' },
  { id: "help", hash: "#/help", ready: '[data-testid="help-faq"]' },
  { id: "record_not_found", hash: "#/record/ZZZ999", ready: '[data-testid="record-not-found"]' },
  { id: "not_found", hash: "#/does-not-exist", ready: '[data-testid="not-found"]' },
];

async function mock(page) {
  await page.route(EXTERNAL, async (route) => {
    const u = new URL(route.request().url());
    let m, file = null;
    if (u.hostname === "models.rcsb.org" && (m = /^\/v1\/([0-9a-z]{4})\/full$/.exec(u.pathname))) file = `${m[1]}.bcif`;
    else if (u.hostname === "files.rcsb.org" && (m = /^\/download\/([0-9A-Z]{4})\.cif$/.exec(u.pathname))) file = `${m[1]}.cif`;
    else if (u.hostname === "alphafold.ebi.ac.uk" && (m = /^\/files\/(AF-[A-Z0-9]+-F1-model_v\d+\.pdb)$/.exec(u.pathname))) file = m[1];
    const p = file && resolve(FIX, file);
    if (p && existsSync(p)) return route.fulfill({ status: 200, headers: { "access-control-allow-origin": "*" }, body: readFileSync(p) });
    return route.fulfill({ status: 404, headers: { "access-control-allow-origin": "*" }, body: "not mocked" });
  });
}

function initScript() {
  window.__wv = {};
  window.__lt = [];
  try {
    new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__lt.push([e.startTime, e.duration]); })
      .observe({ type: "longtask", buffered: true });
  } catch { /* unsupported */ }
  const reg = () => {
    const wv = window.webVitals;
    if (!wv) return;
    const put = (m) => { window.__wv[m.name] = { value: m.value, rating: m.rating, n: (window.__wv[m.name]?.n ?? 0) + 1 }; };
    wv.onFCP(put); wv.onTTFB(put);
    wv.onLCP(put, { reportAllChanges: true });
    wv.onCLS(put, { reportAllChanges: true });
    wv.onINP(put, { reportAllChanges: true, durationThreshold: 16 });
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", reg); else reg();
}

const settle = (page) => page.evaluate(() => new Promise((res) => requestAnimationFrame(() => requestAnimationFrame(() => res(performance.now())))));

async function perfRun(browser, prof, r) {
  const ctx = await browser.newContext({ viewport: prof.viewport, deviceScaleFactor: prof.deviceScaleFactor, isMobile: prof.isMobile, hasTouch: prof.hasTouch });
  const page = await ctx.newPage();
  const cdp = await ctx.newCDPSession(page);
  await cdp.send("Network.enable");
  await cdp.send("Network.emulateNetworkConditions", { offline: false, ...prof.net });
  await cdp.send("Emulation.setCPUThrottlingRate", { rate: prof.cpu });
  await cdp.send("Performance.enable");
  await page.addInitScript({ content: WV });
  await page.addInitScript(initScript);
  if (r.interact?.some((s) => s.name.startsWith("molstar"))) await mock(page);
  const reqs = [];
  const errors = [];
  page.on("requestfinished", async (q) => {
    try {
      const s = await q.sizes();
      const res = await q.response();
      reqs.push({ url: q.url(), type: q.resourceType(), encoded: s.responseBodySize + s.responseHeadersSize, body: s.responseBodySize,
        decoded: Number(res?.headers()["content-length"] ?? s.responseBodySize), enc: res?.headers()["content-encoding"] ?? null });
    } catch { /* page closed */ }
  });
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push(e.message));

  await page.goto(baseURL + r.hash, { waitUntil: "commit" });
  await page.waitForSelector(r.ready, { state: "attached", timeout: 120000 });
  const readyMs = await settle(page);
  await page.waitForLoadState("networkidle", { timeout: 180000 });
  const idleMs = await page.evaluate(() => performance.now());
  const loadReqs = reqs.length;
  const loadLt = await page.evaluate((t) => window.__lt.filter((e) => e[0] <= t).map((e) => e[1]), idleMs);
  const interactions = [];
  for (const st of r.interact ?? []) {
    const t0 = await page.evaluate(() => performance.now());
    await st.run(page);
    await page.waitForSelector(st.done, { state: "attached", timeout: st.timeout ?? 60000 });
    const t1 = await settle(page);
    const lt = await page.evaluate(([a, b]) => window.__lt.filter((e) => e[0] + e[1] >= a && e[0] <= b).map((e) => e[1]), [t0, t1]);
    interactions.push({ name: st.name, ms: Math.round(t1 - t0), longTasks: lt.length, maxLongTaskMs: lt.length ? Math.round(Math.max(...lt)) : 0 });
  }
  await page.waitForTimeout(300);
  // Hide the page so web-vitals finalises LCP / CLS / INP (as on a real tab switch).
  await page.evaluate(() => {
    Object.defineProperty(document, "visibilityState", { value: "hidden", configurable: true });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  const wv = await page.evaluate(() => window.__wv);
  await cdp.send("HeapProfiler.collectGarbage");
  const metrics = Object.fromEntries((await cdp.send("Performance.getMetrics")).metrics.map((m) => [m.name, m.value]));
  await ctx.close();
  return {
    readyMs: Math.round(readyMs), idleMs: Math.round(idleMs),
    fcp: wv.FCP?.value ?? null, lcp: wv.LCP?.value ?? null, cls: wv.CLS?.value ?? null, ttfb: wv.TTFB?.value ?? null,
    inp: wv.INP?.value ?? null, inpReported: !!wv.INP,
    longTasks: loadLt.length, tbtProxyMs: Math.round(loadLt.reduce((a, d) => a + Math.max(0, d - 50), 0)),
    maxLongTaskMs: loadLt.length ? Math.round(Math.max(...loadLt)) : 0,
    heapMB: Math.round((metrics.JSHeapUsedSize / 1048576) * 10) / 10, domNodes: metrics.Nodes,
    requests: reqs.slice(0, loadReqs), interactionRequests: reqs.slice(loadReqs).map((q) => ({ url: q.url, encoded: q.encoded })), errors, interactions,
  };
}

function contrastScan() {
  const lum = ([r, g, b]) => {
    const f = (c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
  };
  const parse = (s) => {
    if (!s) return null;
    const m = s.match(/rgba?\(([^)]+)\)/);
    if (m) { const p = m[1].split(/[ ,/]+/).filter(Boolean).map(Number); return { rgb: p.slice(0, 3), a: p.length > 3 ? p[3] : 1 }; }
    const h = s.trim().match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
    if (h) { const x = h[1].length === 3 ? h[1].split("").map((c) => c + c).join("") : h[1]; return { rgb: [0, 2, 4].map((i) => parseInt(x.slice(i, i + 2), 16)), a: 1 }; }
    return null;
  };
  const bgOf = (el) => {
    const layers = [];
    for (let e = el; e; e = e.parentElement) {
      if (e instanceof SVGElement && !(e instanceof SVGSVGElement)) continue;
      const c = parse(getComputedStyle(e).backgroundColor);
      if (c && c.a > 0) { layers.push(c); if (c.a >= 1) break; }
    }
    let rgb = [255, 255, 255];
    for (const l of layers.reverse()) rgb = rgb.map((v, i) => Math.round(l.rgb[i] * l.a + v * (1 - l.a)));
    return rgb;
  };
  const results = new Map();
  const add = (el, text, fgStr, svg, inactive) => {
    const cs = getComputedStyle(el);
    const fg = parse(fgStr); if (!fg) return;
    const bg = bgOf(el);
    const op = Number(cs.opacity ?? 1) * (svg ? Number(cs.fillOpacity ?? 1) : 1);
    const a = fg.a * op;
    const fgRgb = fg.rgb.map((v, i) => Math.round(v * a + bg[i] * (1 - a)));
    const L1 = lum(fgRgb), L2 = lum(bg);
    const ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
    const px = parseFloat(cs.fontSize), bold = Number(cs.fontWeight) >= 700;
    const large = px >= 24 || (bold && px >= 18.66);
    const need = large ? 3 : 4.5;
    const key = `${svg}|${inactive}|${fgRgb.join(",")}|${bg.join(",")}|${large}`;
    const cur = results.get(key) ?? { svg, inactive, fg: `rgb(${fgRgb})`, bg: `rgb(${bg})`, ratio: Math.round(ratio * 100) / 100, large, need, count: 0, sample: text.slice(0, 40) };
    cur.count++;
    results.set(key, cur);
  };
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const text = n.textContent.trim();
    const el = n.parentElement;
    if (!text || !el || el.closest("canvas, script, style, noscript, title, desc")) continue;
    if (el.closest('[aria-hidden="true"]') && !el.closest("svg")) continue;
    if (el.closest(".sr-only, .sr-only-focusable")) continue;
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    if (r.width === 0 || r.height === 0 || cs.visibility === "hidden" || Number(cs.opacity) === 0 || cs.display === "none") continue;
    const svg = !!el.closest("svg");
    // visible content inside closed <details> has zero size and is skipped above
    // WCAG 1.4.3 exempts inactive (disabled) user-interface components; they are reported but flagged.
    const inactive = !!el.closest("button:disabled, input:disabled, select:disabled, fieldset:disabled, [aria-disabled='true']");
    add(el, text, svg ? cs.fill : cs.color, svg, inactive);
  }
  return [...results.values()].sort((a, b) => a.ratio - b.ratio);
}

const browser = await chromium.launch();
const env = { chromium: browser.version(), runs: RUNS, baseURL, mode: MODE, profiles: PROFILES, node: process.version };
const result = { env, routes: [] };
if (MODE === "perf") {
  for (const [pname, prof] of Object.entries(PROFILES)) {
    for (const r of ROUTES.filter((x) => !ONLY.length || ONLY.includes(x.id))) {
      const runs = [];
      for (let i = 0; i < RUNS; i++) {
        try { runs.push(await perfRun(browser, prof, r)); } catch (e) { runs.push({ failed: String(e).slice(0, 400) }); }
      }
      result.routes.push({ profile: pname, id: r.id, hash: r.hash, ready: r.ready, runs });
      console.log(`${pname} ${r.id}: ready ${runs.map((x) => x.readyMs ?? "FAIL").join("/")} ms`);
    }
  }
} else {
  for (const w of [375, 768, 1440]) {
    const ctx = await browser.newContext({ viewport: { width: w, height: 900 } });
    for (const r of ROUTES) {
      const page = await ctx.newPage();
      await page.goto(baseURL + r.hash);
      await page.waitForSelector(r.ready, { state: "attached", timeout: 60000 });
      await page.waitForLoadState("networkidle");
      // Cells of horizontally scrolled tables keep a non-zero bounding box, so they are scanned too
      // (axe reports them as "incomplete: partially obscured").
      const c = await page.evaluate(contrastScan);
      result.routes.push({ width: w, id: r.id, hash: r.hash, contrast: c, failures: c.filter((x) => x.ratio < x.need && !x.inactive) });
      await page.close();
    }
    await ctx.close();
  }
}
await browser.close();
writeFileSync(out, JSON.stringify(result, null, 1));
console.log(`wrote ${out}`);
