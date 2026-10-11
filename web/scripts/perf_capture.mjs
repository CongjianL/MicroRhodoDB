// PR-2 performance + contrast capture (browser side). Driven by scripts/pr2_perf_audit.py, which
// starts the static server, runs this script, and post-processes the JSON (file sizes, gzip, tables).
//
// For each route and run: fresh browser context (cold HTTP cache), record every request URL and the
// time at which the route's "ready" element is present. On the first run per route at 1440 px, also
// run a WCAG text-contrast scan over visible HTML text (computed colour vs. first opaque ancestor
// background; SVG/canvas text is not scanned).
//
// PR-3 adds a route set ("pr3") with Protein Entry record types and structure-viewer timings: the
// viewer is started by clicking "Load 3D viewer" after the page is ready; RCSB / AlphaFold DB are
// either answered from tests/fixtures/structures ("mocked") or fetched over the network ("live",
// only when PERF_LIVE=1). Bytes of external responses are recorded from the response bodies.
//
// PR-4 adds a route set ("pr4") for the phylogeny explorer and Clade Explorer pages, with timed
// interactions (layout / colour / support / collapse / zoom): each step is clicked or selected
// after the page is ready and timed until its "done" selector is attached (two animation frames
// later, so the paint is included).
//
// Usage: node scripts/perf_capture.mjs <baseURL> <runs> <out.json> [pr2|pr3|pr4|pr5]
import { chromium } from "@playwright/test";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const [baseURL = "http://127.0.0.1:4173/MicroRhodoDB/site/", runsArg = "5", out = "perf_capture.json", SET = "pr2"] = process.argv.slice(2);
const RUNS = Number(runsArg);
const FIX = resolve(dirname(fileURLToPath(import.meta.url)), "../tests/fixtures/structures");
const EXTERNAL = /^https:\/\/(models\.rcsb\.org|files\.rcsb\.org|alphafold\.ebi\.ac\.uk)\//;

const PR2_ROUTES = [
  { id: "home", hash: "#/", ready: '[data-testid="stat-cards"]', also: 'svg[data-testid="tree-preview"] path' },
  { id: "about", hash: "#/about", ready: '[data-testid="clade-support-notice"]' },
  { id: "browse", hash: "#/browse", ready: '[data-testid="results-table"] tbody tr' },
  { id: "browse_clade017_tent", hash: "#/browse?group=all&eng=1&clade=MR_CLD3_017&tent=1", ready: '[data-testid="results-table"] tbody tr' },
  { id: "record_source", hash: "#/record/P02945", ready: '[data-testid="sequence"]' },
  { id: "record_mrdb", hash: "#/record/MRDB000001", ready: '[data-testid="sequence"]' },
  // PR-4: #/phylogeny is no longer a planned page
  { id: "phylogeny", hash: "#/phylogeny", ready: '[data-testid="tree-canvas"] path' },
];

const SEQ = '[data-testid="sequence"]';
const PR3_ROUTES = [
  ...PR2_ROUTES,
  { id: "record_no_structure", hash: "#/record/MRDB000003", ready: SEQ },
  { id: "record_afdb_only", hash: "#/record/MRDB000009", ready: SEQ },
  { id: "record_multi_source", hash: "#/record/MRDB000249", ready: SEQ },
  { id: "record_tentative", hash: "#/record/A0A135LS53", ready: SEQ },
  { id: "viewer_mocked_pdb_5ZIM", hash: "#/record/MRDB000001", ready: SEQ, viewer: "mocked" },
  { id: "viewer_mocked_afdb_Q5V4H7", hash: "#/record/MRDB000009", ready: SEQ, viewer: "mocked" },
  { id: "viewer_release_B0R633", hash: "#/record/B0R633?structure=pred", ready: SEQ, viewer: "mocked" },
  ...(process.env.PERF_LIVE ? [
    { id: "viewer_live_pdb_5ZIM", hash: "#/record/MRDB000001", ready: SEQ, viewer: "live" },
    { id: "viewer_live_afdb_P02945", hash: "#/record/MRDB000001?structure=afdb", ready: SEQ, viewer: "live" },
  ] : []),
];
const CANVAS = '[data-testid="tree-canvas"]';
const PR4_ROUTES = [
  PR2_ROUTES[0],
  { id: "phylogeny", hash: "#/phylogeny", ready: `${CANVAS}[data-visible-leaves="472"] path`, interact: [
    { name: "layout_radial", click: '[data-testid="layout-radial"]', done: `${CANVAS}[data-layout="radial"]` },
    { name: "layout_rect", click: '[data-testid="layout-rect"]', done: `${CANVAS}[data-layout="rect"]` },
    { name: "branch_uniform", click: '[data-testid="bl-uniform"]', done: `${CANVAS}[data-branch="uniform"]` },
    { name: "color_function", select: ['[data-testid="tree-color"]', "function"], done: `${CANVAS}[data-color="function"]` },
    { name: "color_phylum", select: ['[data-testid="tree-color"]', "phylum"], done: `${CANVAS}[data-color="phylum"]` },
    { name: "support_on_469", click: '[data-testid="support-toggle"]', done: '[data-testid="tree-support"] > g:nth-child(469)' },
    { name: "collapse_all", click: '[data-testid="collapse-all"]', done: `${CANVAS}:not([data-visible-leaves="472"])` },
    { name: "expand_all", click: '[data-testid="expand-all"]', done: `${CANVAS}[data-visible-leaves="472"]` },
    { name: "zoom_in", click: '[data-testid="zoom-in"]', done: `${CANVAS}[data-zoom="1.500"]` },
  ] },
  { id: "phylogeny_radial", hash: "#/phylogeny?layout=radial&support=1", ready: '[data-testid="tree-support"] > g:nth-child(469)' },
  { id: "phylogeny_tip", hash: "#/phylogeny?tip=Q9UW81", ready: '[data-testid="info-tip"]' },
  { id: "phylogeny_placement", hash: "#/phylogeny?placement=MRDB000101", ready: '[data-testid="tree-placement-edge"]' },
  { id: "clade_017", hash: "#/clade/MR_CLD3_017", ready: '[data-testid="clade-tree-canvas"] path' },
  { id: "clade_007", hash: "#/clade/MR_CLD3_007", ready: '[data-testid="clade-tree-canvas"] path' },
  { id: "record_mrdb", hash: "#/record/MRDB000001", ready: SEQ },
];
// PR-5 section pages. Interactions record long tasks (>50 ms main-thread blocks) between click and done,
// so the sequence search can be shown to run off the main thread (Web Worker).
const PR5_ROUTES = [
  PR2_ROUTES[0],
  { id: "statistics", hash: "#/statistics", ready: '[data-testid="chart-evidence-level"] svg', interact: [
    { name: "stats_runtime_recount", click: '[data-testid="load-recount"]', done: '[data-testid="recon-status"]' },
  ] },
  { id: "evidence", hash: "#/evidence", ready: '[data-testid="e1-table"] tbody tr' },
  { id: "structures", hash: "#/structures", ready: '[data-testid="pdb-table"] tbody tr' },
  { id: "watchlist", hash: "#/watchlist", ready: '[data-testid="wl-table"] tbody tr' },
  { id: "search_text", hash: "#/search?q=bacteriorhodopsin", ready: '[data-testid="text-results"] tbody tr' },
  { id: "search_sequence", hash: "#/search?mode=sequence", ready: '[data-testid="seq-example"]', interact: [
    { name: "seq_load_example", click: '[data-testid="seq-example"]', done: '[data-testid="seq-input"]:not([data-length="0"])' },
    { name: "seq_search_P02945", click: '[data-testid="seq-run"]', done: '[data-testid="seq-hit-1"][data-acc="P02945"]' },
  ] },
  { id: "downloads", hash: "#/downloads", ready: '[data-testid="dl-release-files"] tbody tr' },
  { id: "methods", hash: "#/methods", ready: '[data-testid="methods-denominators"]' },
  { id: "citation", hash: "#/citation", ready: '[data-testid="cite-bibtex"]' },
  { id: "help", hash: "#/help", ready: '[data-testid="help-faq"]' },
];
const ROUTES = SET === "pr5" ? PR5_ROUTES : SET === "pr4" ? PR4_ROUTES : SET === "pr3" ? PR3_ROUTES : PR2_ROUTES;

async function interact(page, steps) {
  const out = [];
  for (const st of steps) {
    const t0 = await page.evaluate(() => performance.now());
    if (st.click) await page.click(st.click);
    else await page.selectOption(st.select[0], st.select[1]);
    await page.waitForSelector(st.done, { state: "attached", timeout: 30000 });
    const t1 = await page.evaluate(() => new Promise((res) => requestAnimationFrame(() => requestAnimationFrame(() => res(performance.now())))));
    const lt = await page.evaluate(([a, b]) => (window.__lt || []).filter((e) => e[0] + e[1] >= a && e[0] <= b).map((e) => e[1]), [t0, t1]);
    out.push({ name: st.name, ms: Math.round(t1 - t0), longTasks: lt.length, maxLongTaskMs: lt.length ? Math.round(Math.max(...lt)) : 0 });
  }
  return out;
}

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
    if (r.interact) await page.addInitScript(() => {
      window.__lt = [];
      try { new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__lt.push([e.startTime, e.duration]); }).observe({ type: "longtask", buffered: true }); } catch { /* unsupported */ }
    });
    const external = [];
    if (r.viewer) {
      if (r.viewer === "mocked") await mock(page);
      page.on("response", async (res) => {
        if (!EXTERNAL.test(res.url())) return;
        try { external.push({ url: res.url(), status: res.status(), bytes: (await res.body()).length }); } catch { external.push({ url: res.url(), status: res.status(), bytes: null }); }
      });
    }
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
    let viewer = null;
    if (r.viewer) {
      const before = [...new Set(requests)];
      const t0 = await page.evaluate(() => {
        // record every data-phase transition (starting = Mol* chunk + plugin init; loading = coordinates fetch/parse/build)
        const el = document.querySelector('[data-testid="structure-viewer"]');
        window.__phases = [];
        new MutationObserver(() => window.__phases.push([el.getAttribute("data-phase"), performance.now()])).observe(el, { attributes: true, attributeFilter: ["data-phase"] });
        return performance.now();
      });
      await page.click('[data-testid="viewer-load"]');
      await page.waitForSelector('[data-testid="structure-viewer"][data-phase="ready"], [data-testid="structure-viewer"][data-phase="error"]', { timeout: 90000 });
      const t1 = await page.evaluate(() => performance.now());
      const phase = await page.getAttribute('[data-testid="structure-viewer"]', "data-phase");
      const status = await page.textContent('[data-testid="viewer-status"]');
      await page.waitForLoadState("networkidle");
      const phases = (await page.evaluate(() => window.__phases)).map(([ph, t]) => [ph, Math.round(t - t0)]);
      viewer = { mode: r.viewer, clickToReadyMs: Math.round(t1 - t0), phase, status, phases, requestsBeforeClick: before, external: [...external] };
    }
    if (i === 0 && !r.viewer) contrast = await page.evaluate(contrastScan);
    const interactions = r.interact ? await interact(page, r.interact) : null;
    runs.push({ readyMs, alsoMs, ...nav, requests: [...new Set(requests)], errors, viewer, interactions });
    await ctx.close();
  }
  routes.push({ id: r.id, hash: r.hash, ready: r.ready, also: r.also ?? null, viewer: r.viewer ?? null, runs, contrast });
}
await browser.close();
writeFileSync(out, JSON.stringify({ env, routes }, null, 1));
console.log(`wrote ${out}`);
