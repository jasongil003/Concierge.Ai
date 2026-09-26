import { defineConfig, devices } from "@playwright/test";
import { tmpdir } from "node:os";
import { join } from "node:path";

const e2eDatabase = join(tmpdir(), `concierge-ai-e2e-${process.pid}.db`);
const serverCommand = process.env.PLAYWRIGHT_SERVER_COMMAND
  || ".venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8092";

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
    env: { ...process.env, DB_PATH: e2eDatabase, PROPERTY_ID: "", ALLOW_BODY_PROPERTY_SELECTION: "true" },
    url: "http://127.0.0.1:8092/health",
    reuseExistingServer: !process.env.CI,
    timeout: 20_000,
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
