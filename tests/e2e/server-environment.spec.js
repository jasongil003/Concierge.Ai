import { expect, test } from "@playwright/test";
import { createTestServerEnvironment } from "./server_environment.js";

test("the isolated Playwright server excludes host credentials", () => {
  const environment = createTestServerEnvironment({
    path: "/synthetic/bin",
    temporaryDirectory: "/tmp",
    stateDirectory: "/tmp/concierge-e2e-synthetic",
    databasePath: "/tmp/concierge-e2e-synthetic/concierge.db",
  });
  const keys = Object.keys(environment).sort();

  expect(keys).toEqual([
    "ADMIN_BOOTSTRAP_PASSWORD",
    "ADMIN_BOOTSTRAP_USERNAME",
    "ALLOW_BODY_PROPERTY_SELECTION",
    "APP_ENVIRONMENT",
    "CONCIERGE_TESTING",
    "CREDENTIAL_ENCRYPTION_SECRET",
    "DATABASE_URL",
    "DB_PATH",
    "ENABLE_BACKGROUND_WORKERS",
    "HOME",
    "INTELLIGENT_GUEST_UI_GLOBAL_ENABLED",
    "PATH",
    "PROPERTY_ID",
    "REDIS_URL",
    "STATE_DIRECTORY",
    "TEMP",
    "TMP",
    "TMPDIR",
    "UPLOAD_ROOT",
  ]);
  expect(environment).not.toHaveProperty("BROWSER_USE_ACCESS_VERIFYING_IDENTITY");
  expect(environment).not.toHaveProperty("GITHUB_TOKEN");
  expect(environment).not.toHaveProperty("OPENAI_API_KEY");
});
