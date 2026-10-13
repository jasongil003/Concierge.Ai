import { defineConfig, devices } from "@playwright/test";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { mkdtempSync } from "node:fs";
import { createTestServerEnvironment } from "./tests/e2e/server_environment.js";

const e2eStateDirectory = mkdtempSync(join(tmpdir(), "concierge-ai-e2e-"));
const e2eDatabase = join(e2eStateDirectory, "concierge.db");
const serverCommand = process.env.PLAYWRIGHT_SERVER_COMMAND
  || ".venv/bin/python tests/e2e/run_server.py";

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 30_000,
  expect: {
    timeout: 5_000,
  },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: "http://127.0.0.1:8092",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  webServer: {
    command: serverCommand,
    gracefulShutdown: { signal: "SIGTERM", timeout: 10_000 },
    env: createTestServerEnvironment({
      path: process.env.PATH,
      temporaryDirectory: tmpdir(),
      stateDirectory: e2eStateDirectory,
      databasePath: e2eDatabase,
    }),
    url: "http://127.0.0.1:8092/health",
      // Never reuse an unrelated developer server that may use persistent state.
      reuseExistingServer: false,
    timeout: 60_000,
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "mobile-chrome",
      use: { ...devices["Pixel 7"] },
    },
  ],
});
