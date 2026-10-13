# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: guest.spec.js >> guest: empty property home hides empty sections and unsupported routes
- Location: tests/e2e/guest.spec.js:174:1

# Error details

```
Error: expect(locator).toHaveCount(expected) failed

Locator:  locator('.experience-quick_actions')
Expected: 0
Received: 1
Timeout:  5000ms

Call log:
  - Expect "toHaveCount" locator('.experience-quick_actions') with timeout 5000ms
  - waiting for locator('.experience-quick_actions')
    14 × locator resolved to 1 element
       - unexpected value "1"

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
      - generic [ref=e20]:
        - button "Open concierge shortcuts" [ref=e21] [cursor=pointer]
        - textbox "Ask your concierge" [ref=e24]:
          - /placeholder: Ask your concierge...
        - button "Send message" [disabled] [ref=e25]
      - paragraph [ref=e29]: Enter to send · Shift+Enter for a new line
    - navigation "Guest navigation" [ref=e31]:
      - button "Home" [ref=e32] [cursor=pointer]:
        - generic [aria-hidden] [ref=e33]: ⌂
      - button "Explore" [ref=e35] [cursor=pointer]:
        - generic [aria-hidden] [ref=e36]: ◇
      - button "Requests" [ref=e38] [cursor=pointer]:
        - generic [aria-hidden] [ref=e39]: ✓
      - button "My Stay" [ref=e41] [cursor=pointer]:
        - generic [aria-hidden] [ref=e42]: ▤
      - button "Concierge" [ref=e44] [cursor=pointer]:
        - generic [aria-hidden] [ref=e45]: ○
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
  98  |   expect(response.ok()).toBeTruthy();
  99  | }
  100 | 
  101 | async function setAuthenticationEnabled(request, enabled) {
  102 |   const csrf = await loginAdmin(request);
  103 |   const propertyId = (await (await request.get("/api/admin/properties")).json()).properties[0].property_id;
  104 |   const prop = await (await request.get(`/api/admin/properties/${propertyId}`)).json();
  105 |   prop.antlabs_config = { ...(prop.antlabs_config || {}), authentication_enabled: enabled };
  106 |   const response = await request.put(`/api/admin/properties/${propertyId}`, {
  107 |     headers: { "X-CSRF-Token": csrf },
  108 |     data: prop,
  109 |   });
  110 |   expect(response.ok()).toBeTruthy();
  111 | }
  112 | 
  113 | async function ensureGuestData(request) {
  114 |   const csrf = await loginAdmin(request);
  115 |   const propertyId = (await (await request.get("/api/admin/properties")).json()).properties[0].property_id;
  116 |   let catalog = await (await request.get(`/api/admin/properties/${propertyId}/service-catalog`)).json();
  117 |   let department = catalog.departments.find((item) => item.name === "Housekeeping");
  118 |   if (!department) {
  119 |     department = await (await request.put(`/api/admin/properties/${propertyId}/departments`, {
  120 |       headers: { "X-CSRF-Token": csrf }, data: { data: { name: "Housekeeping", default_sla_minutes: 15 } },
  121 |     })).json();
  122 |   }
  123 |   if (!catalog.services.some((item) => item.name === "Towels")) {
  124 |     await request.put(`/api/admin/properties/${propertyId}/service-catalog`, {
  125 |       headers: { "X-CSRF-Token": csrf },
  126 |       data: { data: { name: "Towels", department_id: department.department_id, keywords: ["towel", "towels"], sla_minutes: 15 } },
  127 |     });
  128 |   }
  129 |   const recommendations = await (await request.get(`/api/admin/properties/${propertyId}/recommendations`)).json();
  130 |   if (!recommendations.recommendations.some((item) => item.name === "Fixture Bistro")) {
  131 |     await request.put(`/api/admin/properties/${propertyId}/recommendations`, {
  132 |       headers: { "X-CSRF-Token": csrf },
  133 |       data: { data: { name: "Fixture Bistro", category: "Dining", address: "1 Example Road", map_url: "https://maps.example/fixture", description: "Synthetic test recommendation.", enabled: true } },
  134 |     });
  135 |   }
  136 | }
  137 | 
  138 | async function setIntelligentUi(request, enabled, { welcome = "", prompts = [], pool } = {}) {
  139 |   const csrf = await loginAdmin(request);
  140 |   const propertyId = "e2e-property";
  141 |   const propertyResponse = await request.get(`/api/admin/properties/${propertyId}`);
  142 |   expect(propertyResponse.ok()).toBeTruthy();
  143 |   const property = await propertyResponse.json();
  144 |   property.app_settings = {
  145 |     ...(property.app_settings || {}),
  146 |     guest_experience: {
  147 |       ...(property.app_settings?.guest_experience || {}),
  148 |       intelligent_ui: { enabled },
  149 |       welcome_message: welcome,
  150 |       suggested_prompts: prompts,
  151 |     },
  152 |   };
  153 |   if (pool) property.pool = pool;
  154 |   const saved = await request.put(`/api/admin/properties/${propertyId}`, {
  155 |     headers: { "X-CSRF-Token": csrf },
  156 |     data: property,
  157 |   });
  158 |   expect(saved.ok(), await saved.text()).toBeTruthy();
  159 | }
  160 | 
  161 | // --- 1. Guest initial load ---
  162 | 
  163 | test("guest: opens on the personal stay home, with chat available separately", async ({ page }) => {
  164 |   await page.goto("/");
  165 | 
  166 |   await expect(page.locator("#home-view")).toBeVisible();
  167 |   await expect(page.locator(".experience-hero h1")).toBeVisible();
  168 |   await expect(page.locator(".experience-hero h1")).not.toHaveText("");
  169 |   await expect(page.locator("#concierge-view")).toBeHidden();
  170 |   await expect(page.getByLabel("Ask your concierge")).toBeVisible();
  171 |   await expect(page.locator("#send-button")).toBeDisabled();
  172 | });
  173 | 
  174 | test("guest: empty property home hides empty sections and unsupported routes", async ({ page }) => {
  175 |   // Absence assertions can pass before the intercepted startup requests finish.
  176 |   // Wait for both fixtures so teardown cannot dispose an in-flight route.fetch().
  177 |   const homeLoaded = page.waitForResponse((response) => new URL(response.url()).pathname === "/api/guest/home" && response.status() === 200);
  178 |   const hotelLoaded = page.waitForResponse((response) => new URL(response.url()).pathname === "/api/hotel" && response.status() === 200);
  179 |   await page.route("**/api/hotel", async (route) => {
  180 |     const response = await route.fetch();
  181 |     const profile = await response.json();
  182 |     profile.design = { ...(profile.design || {}), suggestions: [] };
  183 |     await route.fulfill({ response, json: profile });
  184 |   });
  185 |   await page.route("**/api/guest/home", (route) => route.fulfill({
  186 |     status: 200,
  187 |     contentType: "application/json",
  188 |     body: JSON.stringify({
  189 |       greeting: "Welcome", stay: { status: "unverified" }, cards: [], active_requests: [],
  190 |       quick_actions: [{ label: "Internal action", view: "internal" }], suggested_prompts: [],
  191 |       inventory: { restaurants: [], facilities: [], events: [], promotions: [], recommendations: [], menu_items: [] },
  192 |     }),
  193 |   }));
  194 |   await page.goto("/");
  195 |   await Promise.all([homeLoaded, hotelLoaded]);
  196 |   await expect(page.locator(".experience-hero")).toBeVisible();
  197 | 
> 198 |   await expect(page.locator(".experience-quick_actions")).toHaveCount(0);
      |                                                           ^ Error: expect(locator).toHaveCount(expected) failed
  199 |   await expect(page.locator(".experience-card-grid")).toHaveCount(0);
  200 |   await expect(page.locator("#home-actions-section")).toBeHidden();
  201 |   await expect(page.locator("#home-cards-section")).toBeHidden();
  202 |   await expect(page.locator("#home-cards > article")).toHaveCount(0);
  203 |   await expect(page.locator("#quick-actions > button")).toHaveCount(0);
  204 | });
  205 | 
  206 | test("guest: optional catalog outages do not prevent a concierge session from starting", async ({ page }) => {
  207 |   await page.route("**/api/guest/service-catalog", (route) => route.fulfill({
  208 |     status: 503,
  209 |     contentType: "application/json",
  210 |     body: JSON.stringify({ detail: "Catalog temporarily unavailable" }),
  211 |   }));
  212 |   await page.route("**/api/guest/recommendations", (route) => route.fulfill({
  213 |     status: 503,
  214 |     contentType: "application/json",
  215 |     body: JSON.stringify({ detail: "Recommendations temporarily unavailable" }),
  216 |   }));
  217 |   const sessionStarted = page.waitForResponse((response) =>
  218 |     new URL(response.url()).pathname === "/api/session/start" && response.request().method() === "POST",
  219 |   );
  220 |   await page.goto("/");
  221 |   const response = await sessionStarted;
  222 | 
  223 |   expect(response.ok()).toBeTruthy();
  224 |   await expect(page.locator("#home-view")).toBeVisible();
  225 |   await expect(page.locator(".message-row.error")).toHaveCount(0);
  226 | });
  227 | 
  228 | test("guest: bottom navigation switches between stay, explore, requests, and concierge", async ({ page }) => {
  229 |   await page.goto("/");
  230 |   const navigation = await guestNavigation(page);
  231 |   await navigation.getByRole("button", { name: "Explore" }).click();
  232 |   await expect(page.locator("#explore-view")).toBeVisible();
  233 |   await navigation.getByRole("button", { name: "Requests" }).click();
  234 |   await expect(page.locator("#requests-view")).toBeVisible();
  235 |   await navigation.getByRole("button", { name: "My Stay" }).click();
  236 |   await expect(page.locator("#stay-view")).toBeVisible();
  237 |   await navigation.getByRole("button", { name: "Concierge", exact: true }).click();
  238 |   await expect(page.locator("#concierge-view")).toBeVisible();
  239 |   await navigation.getByRole("button", { name: "Home" }).click();
  240 |   await expect(page.locator("#home-view")).toBeVisible();
  241 | });
  242 | 
  243 | test("guest: Explore and My Stay use configured property content", async ({ page, request }) => {
  244 |   await ensureGuestData(request);
  245 |   await page.goto("/");
  246 |   const navigation = await guestNavigation(page);
  247 |   await navigation.getByRole("button", { name: "Explore" }).click();
  248 |   await expect(page.locator("#recommendation-list")).toContainText("Fixture Bistro");
  249 |   await navigation.getByRole("button", { name: "My Stay" }).click();
  250 |   await expect(page.locator("#stay-property-name")).toBeVisible();
  251 |   await expect(page.locator("#stay-summary-card")).toContainText("Active requests");
  252 | });
  253 | 
  254 | test("guest: hotel name and concierge name are displayed", async ({ page }) => {
  255 |   await page.goto("/");
  256 |   await expect(page.locator("#hotel-name")).toBeVisible();
  257 |   await expect(page.locator("#concierge-name")).toBeVisible();
  258 | });
  259 | 
  260 | test("guest: property branding and home prompts use the published property design", async ({ page }) => {
  261 |   await page.route("**/api/hotel", async (route) => {
  262 |     const response = await route.fetch();
  263 |     const profile = await response.json();
  264 |     profile.design = {
  265 |       ...(profile.design || {}),
  266 |       branding: { ...(profile.design?.branding || {}), hotelName: "The Linden House by the Quiet Sea" },
  267 |       welcome: {
  268 |         ...(profile.design?.welcome || {}),
  269 |         greeting: "Welcome back",
  270 |         headline: "A stay shaped around you",
  271 |         description: "Property-configured welcome copy.",
  272 |       },
  273 |       suggestions: [
  274 |         { label: "Explore dining", prompt: "Show dining options", enabled: true, order: 0 },
  275 |         { label: "My stay details", prompt: "Tell me about my stay", enabled: true, order: 1 },
  276 |         { label: "Disabled action", prompt: "Unavailable prompt", enabled: false, order: 2 },
  277 |       ],
  278 |       pages: (profile.design?.pages || []).map((page) => page.id !== "home" ? page : {
  279 |         ...page,
  280 |         sections: page.sections.map((section) => section.type !== "hero" ? section : {
  281 |           ...section,
  282 |           properties: {
  283 |             ...(section.properties || {}),
  284 |             eyebrow: "Welcome back",
  285 |             headline: "A stay shaped around you",
  286 |             description: "Property-configured welcome copy.",
  287 |           },
  288 |         }),
  289 |       }),
  290 |     };
  291 |     await route.fulfill({ response, json: profile });
  292 |   });
  293 |   await page.route("**/api/chat", (route) => route.fulfill({
  294 |     status: 200,
  295 |     contentType: "application/json",
  296 |     body: JSON.stringify({ answer: "Here are the configured dining options.", source: "knowledge" }),
  297 |   }));
  298 |   await page.route("**/api/guest/home", (route) => route.fulfill({
```