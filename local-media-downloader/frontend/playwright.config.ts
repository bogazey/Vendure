import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  outputDir: "./node_modules/.cache/playwright-results",
  use: {
    baseURL: "http://127.0.0.1:4175",
    channel: "chrome",
    reducedMotion: "reduce",
  },
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 4175",
    url: "http://127.0.0.1:4175",
    reuseExistingServer: true,
  },
});
