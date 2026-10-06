import { defineConfig, devices } from "@playwright/test";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { mkdtempSync } from "node:fs";

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
    env: {
      ...process.env,
      APP_ENVIRONMENT: "test",
      CONCIERGE_TESTING: "1",
      STATE_DIRECTORY: e2eStateDirectory,
      UPLOAD_ROOT: join(e2eStateDirectory, "uploads"),
      DATABASE_URL: "",
      REDIS_URL: "",
      ENABLE_BACKGROUND_WORKERS: "false",
      ADMIN_BOOTSTRAP_USERNAME: "admin",
      ADMIN_BOOTSTRAP_PASSWORD: "PlaywrightOnly-Admin-123!",
      CREDENTIAL_ENCRYPTION_SECRET: "PlaywrightOnly-Encryption-Secret-1234567890",
      DB_PATH: e2eDatabase,
      PROPERTY_ID: "",
      ALLOW_BODY_PROPERTY_SELECTION: "true",
    },
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
