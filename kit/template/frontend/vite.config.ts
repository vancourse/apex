import { defineConfig } from "vitest/config";

export default defineConfig({
  server: {
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}", "eslint-rules/**/*.test.js", "scripts/**/*.test.mjs"],
  },
});
