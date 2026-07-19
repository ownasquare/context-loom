import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 4173,
    strictPort: true,
    proxy: {
      "/api": "http://127.0.0.1:8768",
      "/healthz": "http://127.0.0.1:8768",
      "/readyz": "http://127.0.0.1:8768",
    },
  },
  preview: {
    host: "127.0.0.1",
    port: 4173,
    strictPort: true,
  },
  build: {
    outDir: "../src/context_loom/static",
    emptyOutDir: true,
    sourcemap: false,
    target: "es2022",
  },
});
