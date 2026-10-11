import { defineConfig, devices } from "@playwright/test";

/**
 * PR-7 deployment smoke tests (tests/smoke). Three targets, never the development server:
 *   SMOKE_ARTIFACT=<dir>   a built deployment artifact (build_site_artifact.py), served like GitHub Pages under
 *                          /MicroRhodoDB/ by scripts/serve_artifact.py (preview and pre-deploy checks)
 *   SMOKE_BASE_URL=<url>   an already served site root, e.g. https://congjianl.github.io/MicroRhodoDB/ (post-deploy,
 *                          with SMOKE_LIVE=1) - read-only page loads, no writes of any kind
 *   SMOKE_LEGACY=1         with SMOKE_ARTIFACT or SMOKE_BASE_URL: smoke-test the pre-redesign (rollback) site instead
 * Optional: SMOKE_EXPECT_COMMIT=<sha> (BUILD_INFO / footer must show this commit), SMOKE_REPORT_DIR (JSON + HTML report),
 * SMOKE_PORT (default 4350).
 * External structure services (RCSB PDB, AlphaFold DB) are answered from committed fixtures in every mode, so a
 * smoke failure always means a site defect, not a third-party outage; the outage behaviour is tested explicitly.
 */
const PORT = Number(process.env.SMOKE_PORT ?? 4350);
const PY = process.env.E2E_PYTHON ?? "python3";
const ART = process.env.SMOKE_ARTIFACT;
const BASE = process.env.SMOKE_BASE_URL;
if (!ART === !BASE) throw new Error("set exactly one of SMOKE_ARTIFACT or SMOKE_BASE_URL");
const root = BASE ? (BASE.endsWith("/") ? BASE : `${BASE}/`) : `http://127.0.0.1:${PORT}/MicroRhodoDB/`;
const REPORT = process.env.SMOKE_REPORT_DIR;

export default defineConfig({
  testDir: "tests/smoke",
  testMatch: process.env.SMOKE_LEGACY ? /legacy_smoke\.spec\.ts$/ : /site_smoke\.spec\.ts$/,
  timeout: 90_000,
  expect: { timeout: 20_000 },
  fullyParallel: true,
  workers: process.env.SMOKE_LIVE ? 2 : 4,
  retries: process.env.SMOKE_LIVE ? 1 : 0,
  reporter: REPORT
    ? [["list"], ["json", { outputFile: `${REPORT}/smoke-results.json` }], ["html", { outputFolder: `${REPORT}/html`, open: "never" }]]
    : [["list"]],
  outputDir: REPORT ? `${REPORT}/test-results` : "test-results/smoke",
  use: {
    baseURL: `${root}site/`,
    ...devices["Desktop Chrome"],
    viewport: { width: 1440, height: 900 },
    trace: "off",
    launchOptions: { args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] },
  },
  metadata: { target: ART ? `artifact ${ART}` : `served ${root}`, legacy: !!process.env.SMOKE_LEGACY },
  webServer: ART
    ? {
        command: `${PY} scripts/serve_artifact.py "${ART}" ${PORT}`,
        url: `http://127.0.0.1:${PORT}/MicroRhodoDB/site/index.html`,
        reuseExistingServer: false,
        timeout: 30_000,
        stdout: "ignore",
      }
    : undefined,
});
