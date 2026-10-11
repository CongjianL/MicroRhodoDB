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

// GitHub Pages project site: https://<owner>.github.io/MicroRhodoDB/site/
// Hash routing (#/...) means no SPA fallback is needed for refreshes or deep links.
export default defineConfig({
  base: "/MicroRhodoDB/site/",
  plugins: [react(), tailwindcss(), cspMeta()],
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
