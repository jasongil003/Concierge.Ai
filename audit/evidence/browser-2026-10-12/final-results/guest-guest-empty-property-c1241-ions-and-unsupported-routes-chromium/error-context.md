# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: guest.spec.js >> guest: empty property home hides empty sections and unsupported routes
- Location: tests/e2e/guest.spec.js:174:1

# Error details

```
Error: apiResponse.json: Response has been disposed
```

# Page snapshot

```yaml
- generic [active] [ref=e1]:
  - main [ref=e2]:
    - generic [ref=e3]:
      - button "Open hotel menu" [ref=e4] [cursor=pointer]:
        - generic [ref=e7]: Menu
      - generic [ref=e8]:
        - generic [ref=e10]: C
        - generic [ref=e11]:
          - strong [ref=e12]: Concierge
          - generic [ref=e13]: AI concierge
    - region "Your stay" [ref=e16]:
      - generic [ref=e20]:
        - paragraph [ref=e21]: Welcome
        - heading "How can I help with your stay today?" [level=1] [ref=e22]
        - paragraph [ref=e23]: Your personal concierge is here to make your stay more comfortable.
    - generic [ref=e24]:
      - generic [ref=e26]:
        - button "Open concierge shortcuts" [ref=e27] [cursor=pointer]
        - textbox "Ask your concierge" [ref=e30]:
          - /placeholder: Ask Concierge anything...
        - button "Start voice input" [ref=e31] [cursor=pointer]
        - button "Send message" [disabled] [ref=e35]
      - paragraph [ref=e39]: Enter to send · Shift+Enter for a new line
    - navigation "Guest navigation" [ref=e40]:
      - button "Home" [ref=e41] [cursor=pointer]
      - button "Explore" [ref=e46] [cursor=pointer]
      - button "Requests" [ref=e52] [cursor=pointer]
      - button "My Stay" [ref=e60] [cursor=pointer]
      - button "Concierge" [ref=e66] [cursor=pointer]
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
  77  |     local: "Local",
  78  |     radius: "RADIUS",
  79  |     pms: "PMS / Room Login",
  80  |     credit_card: "Credit Card",
  81  |     access_code: "Access Code",
  82  |     global_account: "Global Account",
  83  |     global_code: "Global Code",
  84  |     user_form: "User Form",
  85  |     social_network: "Social Network",
  86  |   };
  87  |   prop.antlabs_config = {
  88  |     ...(prop.antlabs_config || {}),
  89  |     authentication_enabled: true,
  90  |     authentication_types: Object.fromEntries(
  91  |       Object.entries(labels).map(([id, label]) => [id, { label, enabled: enabledIds.includes(id) }])
  92  |     ),
  93  |   };
  94  |   const response = await request.put(`/api/admin/properties/${propertyId}`, {
  95  |     headers: { "X-CSRF-Token": csrf },
  96  |     data: prop,
  97  |   });
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
  175 |   await page.route("**/api/hotel", async (route) => {
  176 |     const response = await route.fetch();
> 177 |     const profile = await response.json();
      |                                    ^ Error: apiResponse.json: Response has been disposed
  178 |     profile.design = { ...(profile.design || {}), suggestions: [] };
  179 |     await route.fulfill({ response, json: profile });
  180 |   });
  181 |   await page.route("**/api/guest/home", (route) => route.fulfill({
  182 |     status: 200,
  183 |     contentType: "application/json",
  184 |     body: JSON.stringify({
  185 |       greeting: "Welcome", stay: { status: "unverified" }, cards: [], active_requests: [],
  186 |       quick_actions: [{ label: "Internal action", view: "internal" }], suggested_prompts: [],
  187 |       inventory: { restaurants: [], facilities: [], events: [], promotions: [], recommendations: [], menu_items: [] },
  188 |     }),
  189 |   }));
  190 |   await page.goto("/");
  191 | 
  192 |   await expect(page.locator(".experience-quick_actions")).toHaveCount(0);
  193 |   await expect(page.locator(".experience-card-grid")).toHaveCount(0);
  194 |   await expect(page.locator("#home-actions-section")).toBeHidden();
  195 |   await expect(page.locator("#home-cards-section")).toBeHidden();
  196 |   await expect(page.locator("#home-cards > article")).toHaveCount(0);
  197 |   await expect(page.locator("#quick-actions > button")).toHaveCount(0);
  198 | });
  199 | 
  200 | test("guest: optional catalog outages do not prevent a concierge session from starting", async ({ page }) => {
  201 |   await page.route("**/api/guest/service-catalog", (route) => route.fulfill({
  202 |     status: 503,
  203 |     contentType: "application/json",
  204 |     body: JSON.stringify({ detail: "Catalog temporarily unavailable" }),
  205 |   }));
  206 |   await page.route("**/api/guest/recommendations", (route) => route.fulfill({
  207 |     status: 503,
  208 |     contentType: "application/json",
  209 |     body: JSON.stringify({ detail: "Recommendations temporarily unavailable" }),
  210 |   }));
  211 |   const sessionStarted = page.waitForResponse((response) =>
  212 |     new URL(response.url()).pathname === "/api/session/start" && response.request().method() === "POST",
  213 |   );
  214 |   await page.goto("/");
  215 |   const response = await sessionStarted;
  216 | 
  217 |   expect(response.ok()).toBeTruthy();
  218 |   await expect(page.locator("#home-view")).toBeVisible();
  219 |   await expect(page.locator(".message-row.error")).toHaveCount(0);
  220 | });
  221 | 
  222 | test("guest: bottom navigation switches between stay, explore, requests, and concierge", async ({ page }) => {
  223 |   await page.goto("/");
  224 |   const navigation = await guestNavigation(page);
  225 |   await navigation.getByRole("button", { name: "Explore" }).click();
  226 |   await expect(page.locator("#explore-view")).toBeVisible();
  227 |   await navigation.getByRole("button", { name: "Requests" }).click();
  228 |   await expect(page.locator("#requests-view")).toBeVisible();
  229 |   await navigation.getByRole("button", { name: "My Stay" }).click();
  230 |   await expect(page.locator("#stay-view")).toBeVisible();
  231 |   await navigation.getByRole("button", { name: "Concierge", exact: true }).click();
  232 |   await expect(page.locator("#concierge-view")).toBeVisible();
  233 |   await navigation.getByRole("button", { name: "Home" }).click();
  234 |   await expect(page.locator("#home-view")).toBeVisible();
  235 | });
  236 | 
  237 | test("guest: Explore and My Stay use configured property content", async ({ page, request }) => {
  238 |   await ensureGuestData(request);
  239 |   await page.goto("/");
  240 |   const navigation = await guestNavigation(page);
  241 |   await navigation.getByRole("button", { name: "Explore" }).click();
  242 |   await expect(page.locator("#recommendation-list")).toContainText("Fixture Bistro");
  243 |   await navigation.getByRole("button", { name: "My Stay" }).click();
  244 |   await expect(page.locator("#stay-property-name")).toBeVisible();
  245 |   await expect(page.locator("#stay-summary-card")).toContainText("Active requests");
  246 | });
  247 | 
  248 | test("guest: hotel name and concierge name are displayed", async ({ page }) => {
  249 |   await page.goto("/");
  250 |   await expect(page.locator("#hotel-name")).toBeVisible();
  251 |   await expect(page.locator("#concierge-name")).toBeVisible();
  252 | });
  253 | 
  254 | test("guest: property branding and home prompts use the published property design", async ({ page }) => {
  255 |   await page.route("**/api/hotel", async (route) => {
  256 |     const response = await route.fetch();
  257 |     const profile = await response.json();
  258 |     profile.design = {
  259 |       ...(profile.design || {}),
  260 |       branding: { ...(profile.design?.branding || {}), hotelName: "The Linden House by the Quiet Sea" },
  261 |       welcome: {
  262 |         ...(profile.design?.welcome || {}),
  263 |         greeting: "Welcome back",
  264 |         headline: "A stay shaped around you",
  265 |         description: "Property-configured welcome copy.",
  266 |       },
  267 |       suggestions: [
  268 |         { label: "Explore dining", prompt: "Show dining options", enabled: true, order: 0 },
  269 |         { label: "My stay details", prompt: "Tell me about my stay", enabled: true, order: 1 },
  270 |         { label: "Disabled action", prompt: "Unavailable prompt", enabled: false, order: 2 },
  271 |       ],
  272 |       pages: (profile.design?.pages || []).map((page) => page.id !== "home" ? page : {
  273 |         ...page,
  274 |         sections: page.sections.map((section) => section.type !== "hero" ? section : {
  275 |           ...section,
  276 |           properties: {
  277 |             ...(section.properties || {}),
```