import { defineConfig, devices } from "@playwright/test";

/**
 * E2E tests run against the production build (web/dist/site) served under /MicroRhodoDB/site/
 * by a plain static server (scripts/serve_e2e.py). Prerequisites: exporter output in
 * web/public/data and `npm run build`. Set PLAYWRIGHT_BROWSERS_PATH if browsers live elsewhere.
 */
const PORT = Number(process.env.E2E_PORT ?? 4173);
const PY = process.env.E2E_PYTHON ?? "python3";

export default defineConfig({
  testDir: "tests/e2e",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: true,
  workers: process.env.CI ? 2 : 4,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${PORT}/MicroRhodoDB/site/`,
    ...devices["Desktop Chrome"],
    viewport: { width: 1440, height: 900 },
    acceptDownloads: true,
    trace: "off",
    // Software WebGL (SwiftShader) so the Mol* viewer renders in headless CI without a GPU.
    launchOptions: { args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] },
  },
  // @live tests hit RCSB PDB / AlphaFold DB over the network; excluded unless E2E_LIVE=1.
  grepInvert: process.env.E2E_LIVE ? undefined : /@live/,
  webServer: {
    command: `${PY} scripts/serve_e2e.py ${PORT}`,
    url: `http://127.0.0.1:${PORT}/MicroRhodoDB/site/index.html`,
    reuseExistingServer: false,
    timeout: 30_000,
    stdout: "ignore",
  },
});
