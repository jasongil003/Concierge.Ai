# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: guest-privacy.spec.js >> guest privacy explains staff access and retained conversations truthfully
- Location: tests/e2e/guest-privacy.spec.js:3:1

# Error details

```
Error: expect(locator).toContainText(expected) failed

Locator: locator('#message-list')
Expected substring: "Authorized hotel staff can review conversation history"
Received string:    "ConciergeYour messages are processed by this property's configured AI service and aren't shown to hotel staff. Chat context stays in this open session and expires after inactivity. Confirmed service requests are shared with the hotel team. Personalization is optional; you can review or clear saved preferences in Personalization / Memory."
Timeout: 5000ms

Call log:
  - Expect "toContainText" locator('#message-list') with timeout 5000ms
  - waiting for locator('#message-list')
    14 × locator resolved to <section id="message-list" aria-live="polite" class="message-list" aria-label="Messages">…</section>
       - unexpected value "ConciergeYour messages are processed by this property's configured AI service and aren't shown to hotel staff. Chat context stays in this open session and expires after inactivity. Confirmed service requests are shared with the hotel team. Personalization is optional; you can review or clear saved preferences in Personalization / Memory."

```

```yaml
- region "Messages":
  - article:
    - text: Concierge
    - paragraph: Your messages are processed by this property's configured AI service and aren't shown to hotel staff. Chat context stays in this open session and expires after inactivity. Confirmed service requests are shared with the hotel team. Personalization is optional; you can review or clear saved preferences in Personalization / Memory.
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
  8  |   await expect(page.locator("#home-view")).toBeVisible();
  9  |   await page.locator(".experience-configured-header .experience-configured-menu").click();
  10 |   await page.locator('[data-menu-action="privacy"]').click();
  11 |   const messages = page.locator("#message-list");
> 12 |   await expect(messages).toContainText("Authorized hotel staff can review conversation history");
     |                          ^ Error: expect(locator).toContainText(expected) failed
  13 |   await expect(messages).toContainText("closing this page does not delete them");
  14 |   await expect(messages).not.toContainText("aren't shown to hotel staff");
  15 |   await expect(messages).not.toContainText("Chat context stays in this open session");
  16 | });
  17 | 
```