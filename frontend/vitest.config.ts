import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
  test: { environment: "jsdom", setupFiles: ["./tests/setup.ts"] },
  esbuild: { jsx: "automatic" },
  resolve: { alias: { "@": path.resolve(__dirname) } },
});
