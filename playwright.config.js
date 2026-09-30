import { defineConfig, devices } from "@playwright/test";
import { tmpdir } from "node:os";
import { join } from "node:path";

const e2eDatabase = join(tmpdir(), `concierge-ai-e2e-${process.pid}.db`);
const serverCommand = process.env.PLAYWRIGHT_SERVER_COMMAND
  || ".venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8092 --no-proxy-headers";

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
    env: {
      ...process.env,
      ADMIN_BOOTSTRAP_PASSWORD: process.env.ADMIN_BOOTSTRAP_PASSWORD || "PlaywrightOnly-Admin-123!",
      CREDENTIAL_ENCRYPTION_SECRET: process.env.CREDENTIAL_ENCRYPTION_SECRET || "PlaywrightOnly-Encryption-Secret-1234567890",
      DB_PATH: e2eDatabase,
      PROPERTY_ID: "",
      ALLOW_BODY_PROPERTY_SELECTION: "true",
    },
    url: "http://127.0.0.1:8092/health",
    reuseExistingServer: !process.env.CI,
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
