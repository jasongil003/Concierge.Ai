# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: guest-scrollbar.spec.js >> guest home and concierge retain aligned content with classic scrollbars
- Location: tests/e2e/guest-scrollbar.spec.js:3:1

# Error details

```
Error: page.addStyleTag: Applying inline style violates the following Content Security Policy directive 'style-src 'self''. Either the 'unsafe-inline' keyword, a hash ('sha256-d1KtQjI57tiQB/Tmt24XwhFYWdOQ90tvmjBfPOtM1pM='), or a nonce ('nonce-...') is required to enable inline execution. The action has been blocked.
```

# Page snapshot

```yaml
- generic [active] [ref=e1]:
  - main [ref=e2]:
    - region "Home" [ref=e3]:
      - generic [ref=e5]:
        - region "Header" [ref=e6]:
          - button "Open hotel menu" [ref=e7] [cursor=pointer]: Menu
          - generic [ref=e9]:
            - strong [ref=e10]: E2E Property
            - generic [ref=e11]: Concierge
        - region "Welcome" [ref=e12]:
          - paragraph [ref=e13]: Good evening.
          - heading "How can I help?" [level=1] [ref=e14]
          - paragraph [ref=e15]: Your personal concierge is here to make your stay more comfortable.
        - region "Quick actions" [ref=e16]:
          - heading "Quick actions" [level=2] [ref=e17]
          - generic [ref=e18]:
            - button [ref=e19] [cursor=pointer]:
              - strong [ref=e21]: Dining
            - button [ref=e22] [cursor=pointer]:
              - strong [ref=e24]: Request something
            - button [ref=e25] [cursor=pointer]:
              - strong [ref=e27]: Explore
            - button [ref=e28] [cursor=pointer]:
              - strong [ref=e30]: My Stay
        - region "Suggested for you" [ref=e31]:
          - article [ref=e33]:
            - strong [ref=e34]: Fixture Bistro
            - generic [ref=e35]: Dining
            - paragraph [ref=e36]: Synthetic test recommendation.
            - button "Directions" [ref=e38] [cursor=pointer]
    - generic [ref=e39]:
      - generic [ref=e41]:
        - button "Open concierge shortcuts" [ref=e42] [cursor=pointer]
        - textbox "Ask your concierge" [ref=e45]:
          - /placeholder: Ask your concierge...
        - button "Send message" [disabled] [ref=e46]
      - paragraph [ref=e50]: Enter to send · Shift+Enter for a new line
    - navigation "Guest navigation" [ref=e52]:
      - button "Home" [ref=e53] [cursor=pointer]:
        - generic [aria-hidden] [ref=e54]: ⌂
      - button "Explore" [ref=e56] [cursor=pointer]:
        - generic [aria-hidden] [ref=e57]: ◇
      - button "Requests" [ref=e59] [cursor=pointer]:
        - generic [aria-hidden] [ref=e60]: ✓
      - button "My Stay" [ref=e62] [cursor=pointer]:
        - generic [aria-hidden] [ref=e63]: ▤
      - button "Concierge" [ref=e65] [cursor=pointer]:
        - generic [aria-hidden] [ref=e66]: ○
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
          - strong: Talk to Restaurant Staff
          - generic: Send a private request to a dining team
      - button:
        - generic:
          - strong: Property map
          - generic: Find your way around
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
  2  | 
  3  | test("guest home and concierge retain aligned content with classic scrollbars", async ({ page }) => {
  4  |   await page.route("**/api/guest/intro**", (route) => route.fulfill({ json: { mode: "none" } }));
  5  |   await page.goto("/");
  6  |   await expect(page.locator(".experience-configured-navigation")).toBeVisible();
  7  |   // Explicit widths reproduce non-overlay Linux/Windows scrollbars on macOS too.
> 8  |   await page.addStyleTag({ content: ".guest-view::-webkit-scrollbar { width: 15px; }" });
     |              ^ Error: page.addStyleTag: Applying inline style violates the following Content Security Policy directive 'style-src 'self''. Either the 'unsafe-inline' keyword, a hash ('sha256-d1KtQjI57tiQB/Tmt24XwhFYWdOQ90tvmjBfPOtM1pM='), or a nonce ('nonce-...') is required to enable inline execution. The action has been blocked.
  9  |   for (const width of [320, 375, 768, 1024, 1440, 1920]) {
  10 |     await page.setViewportSize({ width, height: 900 });
  11 |     await page.locator(".experience-configured-navigation").getByRole("button", { name: "Home", exact: true }).click();
  12 |     await expect(page.locator(".experience-hero")).toBeVisible();
  13 |     const hero = await page.locator(".experience-hero").boundingBox();
  14 |     await page.locator(".experience-configured-navigation").getByRole("button", { name: "Concierge", exact: true }).click();
  15 |     await expect(page.locator("#concierge-card")).toBeVisible();
  16 |     const card = await page.locator("#concierge-card").boundingBox();
  17 |     expect(hero.x, `home/chat left edge at ${width}px`).toBeCloseTo(card.x, 0);
  18 |     expect(hero.width, `home/chat content width at ${width}px`).toBeCloseTo(card.width, 0);
  19 |   }
  20 | });
  21 | 
```