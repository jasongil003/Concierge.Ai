# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: guest-privacy.spec.js >> guest privacy explains staff access and retained conversations truthfully
- Location: tests/e2e/guest-privacy.spec.js:3:1

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: locator('#home-view')
Expected: visible
Timeout: 5000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" locator('#home-view') with timeout 5000ms
  - waiting for locator('#home-view')

```

```yaml
- text: "{\"detail\":\"Property not found.\"}"
```

# Test source

```ts
  1  | import { expect, test } from "@playwright/test";
  2  | 
  3  | test("guest privacy explains staff access and retained conversations truthfully", async ({ page }) => {
  4  |   await page.route("**/api/guest/intro**", (route) => route.fulfill({
  5  |     json: { mode: "none", first_visit_only: true, allow_skip: true },
  6  |   }));
  7  |   await page.goto("/");
> 8  |   await expect(page.locator("#home-view")).toBeVisible();
     |                                            ^ Error: expect(locator).toBeVisible() failed
  9  |   await page.locator(".experience-configured-header .experience-configured-menu").click();
  10 |   await page.locator('[data-menu-action="privacy"]').click();
  11 |   const messages = page.locator("#message-list");
  12 |   await expect(messages).toContainText("Authorized hotel staff can review conversation history");
  13 |   await expect(messages).toContainText("closing this page does not delete them");
  14 |   await expect(messages).not.toContainText("aren't shown to hotel staff");
  15 |   await expect(messages).not.toContainText("Chat context stays in this open session");
  16 | });
  17 | 
```