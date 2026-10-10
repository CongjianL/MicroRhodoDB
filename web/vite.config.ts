/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// GitHub Pages project site: https://<owner>.github.io/MicroRhodoDB/site/
// Hash routing (#/...) means no SPA fallback is needed for refreshes or deep links.
export default defineConfig({
  base: "/MicroRhodoDB/site/",
  plugins: [react(), tailwindcss()],
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
