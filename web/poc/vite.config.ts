import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({ base: "/MicroRhodoDB/site/", plugins: [react()], build: { outDir: "dist/site", chunkSizeWarningLimit: 6000 } });
