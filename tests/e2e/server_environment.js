export function createTestServerEnvironment({ path, temporaryDirectory, stateDirectory, databasePath }) {
  return {
    PATH: path || "/usr/bin:/bin",
    HOME: stateDirectory,
    TMPDIR: temporaryDirectory || stateDirectory,
    TEMP: temporaryDirectory || stateDirectory,
    TMP: temporaryDirectory || stateDirectory,
    APP_ENVIRONMENT: "test",
    CONCIERGE_TESTING: "1",
    CONCIERGE_E2E_CONTROL_TOKEN: "playwright-local-session-clock-control",
    STATE_DIRECTORY: stateDirectory,
    UPLOAD_ROOT: `${stateDirectory}/uploads`,
    DATABASE_URL: "",
    REDIS_URL: "",
    ENABLE_BACKGROUND_WORKERS: "false",
    INTELLIGENT_GUEST_UI_GLOBAL_ENABLED: "true",
    ADMIN_BOOTSTRAP_USERNAME: "admin",
    ADMIN_BOOTSTRAP_PASSWORD: "PlaywrightOnly-Admin-123!",
    CREDENTIAL_ENCRYPTION_SECRET: "PlaywrightOnly-Encryption-Secret-1234567890",
    DB_PATH: databasePath,
    PROPERTY_ID: "",
    ALLOW_BODY_PROPERTY_SELECTION: "true",
  };
}
