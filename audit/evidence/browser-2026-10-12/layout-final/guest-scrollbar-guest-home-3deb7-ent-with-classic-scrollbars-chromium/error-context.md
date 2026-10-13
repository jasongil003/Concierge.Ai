# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: guest-scrollbar.spec.js >> guest home and concierge retain aligned content with classic scrollbars
- Location: tests/e2e/guest-scrollbar.spec.js:6:1

# Error details

```
Error: home/chat left edge at 1440px

expect(received).toBeCloseTo(expected, precision)

Expected: 221
Received: 206

Expected precision:    0
Expected difference: < 0.5
Received difference:   15
```

# Page snapshot

```yaml
- generic [ref=e1]:
  - main [ref=e2]:
    - region "Concierge conversation" [ref=e3]:
      - generic [ref=e4]:
        - generic [ref=e5]:
          - heading "Your concierge" [level=2] [ref=e6]
          - generic [ref=e7]: Private conversation
        - generic [ref=e8]:
          - generic [ref=e9]:
            - generic [ref=e10]:
              - paragraph [ref=e12]: Good evening.
              - heading "How can I help?" [level=1] [ref=e13]
              - paragraph [ref=e14]: Ask anything about your stay. You can return to your stay home whenever you like.
            - generic "Suggested prompts"
            - generic [ref=e15]: Your concierge chat stays private. Confirmed service and restaurant staff requests share only the details you submit.
            - button "Personalize my stay" [ref=e20] [cursor=pointer]
          - region "Messages" [ref=e21]
        - generic [ref=e22]:
          - generic [ref=e24]:
            - button "Open concierge shortcuts" [ref=e25] [cursor=pointer]
            - textbox "Ask your concierge" [active] [ref=e28]:
              - /placeholder: Ask your concierge...
            - button "Send message" [disabled] [ref=e29]
          - paragraph [ref=e33]: Enter to send · Shift+Enter for a new line
    - navigation "Guest navigation" [ref=e35]:
      - button "Home" [ref=e36] [cursor=pointer]:
        - generic [aria-hidden] [ref=e37]: ⌂
      - button "Explore" [ref=e39] [cursor=pointer]:
        - generic [aria-hidden] [ref=e40]: ◇
      - button "Requests" [ref=e42] [cursor=pointer]:
        - generic [aria-hidden] [ref=e43]: ✓
      - button "My Stay" [ref=e45] [cursor=pointer]:
        - generic [aria-hidden] [ref=e46]: ▤
      - button "Concierge" [ref=e48] [cursor=pointer]:
        - generic [aria-hidden] [ref=e49]: ○
    - status
  - complementary [aria-hidden]:
    - generic:
      - generic:
        - generic:
          - generic: Guest services
          - strong: How can we help?
        - button: ×
      - paragraph: Concierge
      - button:
        - generic:
          - strong: New conversation
          - generic: Start fresh with your concierge
      - button:
        - generic:
          - strong: Hotel information
          - generic: Address, amenities, and hours
      - button:
        - generic:
          - strong: Language
          - generic: Switch reply language
      - button:
        - generic:
          - strong: Personalization & memory
          - generic: Review or clear saved preferences
      - button:
        - generic:
          - strong: Accessibility
          - generic: Adjust reading and display
      - button:
        - generic:
          - strong: Privacy
          - generic: How your chat is handled
      - button:
        - generic:
          - strong: Help
          - generic: Tips for a smooth stay
```

# Test source

```ts
  1  | import { expect, test } from "@playwright/test";
  2  | import { prepareGuestFixture } from "./support.js";
  3  | 
  4  | test.beforeEach(async ({ request }) => prepareGuestFixture(request));
  5  | 
  6  | test("guest home and concierge retain aligned content with classic scrollbars", async ({ page }) => {
  7  |   await page.route("**/api/guest/intro**", (route) => route.fulfill({ json: { mode: "none" } }));
  8  |   // Keep the application's CSP intact; extend its same-origin stylesheet.
  9  |   await page.route("**/static/styles.css*", async (route) => {
  10 |     const response = await route.fetch();
  11 |     await route.fulfill({ response, body: `${await response.text()}\n.guest-view::-webkit-scrollbar { width: 15px; }` });
  12 |   });
  13 |   await page.goto("/");
  14 |   await expect(page.locator(".experience-configured-navigation")).toBeVisible();
  15 |   // Explicit widths reproduce non-overlay Linux/Windows scrollbars on macOS too.
  16 |   for (const width of [320, 375, 768, 1024, 1440, 1920]) {
  17 |     await page.setViewportSize({ width, height: 900 });
  18 |     await page.locator(".experience-configured-navigation").getByRole("button", { name: "Home", exact: true }).click();
  19 |     await expect(page.locator(".experience-hero")).toBeVisible();
  20 |     const hero = await page.locator(".experience-hero").boundingBox();
  21 |     await page.locator(".experience-configured-navigation").getByRole("button", { name: "Concierge", exact: true }).click();
  22 |     await expect(page.locator("#concierge-card")).toBeVisible();
  23 |     const card = await page.locator("#concierge-card").boundingBox();
> 24 |     expect(hero.x, `home/chat left edge at ${width}px`).toBeCloseTo(card.x, 0);
     |                                                         ^ Error: home/chat left edge at 1440px
  25 |     expect(hero.width, `home/chat content width at ${width}px`).toBeCloseTo(card.width, 0);
  26 |   }
  27 | });
  28 | 
```