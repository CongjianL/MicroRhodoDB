/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import type { Plugin } from "vite";
import { CSP } from "./csp.config";

/** PR-6: inject the Content-Security-Policy meta tag into the production build only. */
const cspMeta = (): Plugin => ({
  name: "mrdb-csp-meta",
  apply: "build",
  transformIndexHtml: (html) => html.replace("<meta charset=\"UTF-8\" />", `<meta charset="UTF-8" />\n    <meta http-equiv="Content-Security-Policy" content="${CSP}" />`),
});

/**
 * PR-7: build provenance. web/scripts/build_site_artifact.py sets MRDB_BUILD_COMMIT (40-hex) and MRDB_BUILD_DATE
 * (YYYY-MM-DD, the commit date). Without them (npm run dev / plain npm run build) the stamp is undefined and the
 * footer reads "Development build; not the deployed site".
 */
const buildCommit = process.env.MRDB_BUILD_COMMIT ?? "";
const buildDate = process.env.MRDB_BUILD_DATE ?? "";
const buildStamp = /^[0-9a-f]{40}$/.test(buildCommit) ? { commit: buildCommit, date: /^\d{4}-\d{2}-\d{2}$/.test(buildDate) ? buildDate : "" } : undefined;

// GitHub Pages project site: https://<owner>.github.io/MicroRhodoDB/site/
// Hash routing (#/...) means no SPA fallback is needed for refreshes or deep links.
export default defineConfig({
  base: "/MicroRhodoDB/site/",
  plugins: [react(), tailwindcss(), cspMeta()],
  define: { __MRDB_BUILD__: buildStamp === undefined ? "undefined" : JSON.stringify(buildStamp) },
  build: {
    outDir: "dist/site",
    emptyOutDir: true,
    target: "es2020",
    sourcemap: false,
    reportCompressedSize: true,
  },
  server: { port: 5173, strictPort: true },
  test: {
    include: ["tests/unit/**/*.test.ts"],
    environment: "node",
    testTimeout: 60000,
  },
});
