import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../scripts/ai_flow/web_static",
    emptyOutDir: true
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8765"
    }
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    globals: true
  }
});
