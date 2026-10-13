# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: guest-scrollbar.spec.js >> guest home and concierge retain aligned content with classic scrollbars
- Location: tests/e2e/guest-scrollbar.spec.js:3:1

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: locator('.experience-configured-navigation')
Expected: visible
Timeout: 5000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" locator('.experience-configured-navigation') with timeout 5000ms
  - waiting for locator('.experience-configured-navigation')

```

```yaml
- text: "{\"detail\":\"Property not found.\"}"
```

# Test source

```ts
  1  | import { expect, test } from "@playwright/test";
  2  | 
  3  | test("guest home and concierge retain aligned content with classic scrollbars", async ({ page }) => {
  4  |   await page.route("**/api/guest/intro**", (route) => route.fulfill({ json: { mode: "none" } }));
  5  |   // Keep the application's CSP intact; extend its same-origin stylesheet.
  6  |   await page.route("**/static/styles.css*", async (route) => {
  7  |     const response = await route.fetch();
  8  |     await route.fulfill({ response, body: `${await response.text()}\n.guest-view::-webkit-scrollbar { width: 15px; }` });
  9  |   });
  10 |   await page.goto("/");
> 11 |   await expect(page.locator(".experience-configured-navigation")).toBeVisible();
     |                                                                   ^ Error: expect(locator).toBeVisible() failed
  12 |   // Explicit widths reproduce non-overlay Linux/Windows scrollbars on macOS too.
  13 |   for (const width of [320, 375, 768, 1024, 1440, 1920]) {
  14 |     await page.setViewportSize({ width, height: 900 });
  15 |     await page.locator(".experience-configured-navigation").getByRole("button", { name: "Home", exact: true }).click();
  16 |     await expect(page.locator(".experience-hero")).toBeVisible();
  17 |     const hero = await page.locator(".experience-hero").boundingBox();
  18 |     await page.locator(".experience-configured-navigation").getByRole("button", { name: "Concierge", exact: true }).click();
  19 |     await expect(page.locator("#concierge-card")).toBeVisible();
  20 |     const card = await page.locator("#concierge-card").boundingBox();
  21 |     expect(hero.x, `home/chat left edge at ${width}px`).toBeCloseTo(card.x, 0);
  22 |     expect(hero.width, `home/chat content width at ${width}px`).toBeCloseTo(card.width, 0);
  23 |   }
  24 | });
  25 | 
```