# Concierge.AI Local Demo Results

Run date: 2026-10-14. Hotel De Luna is fictional; all records, accounts, requests, prices, and images are synthetic demo data.

## Environment

- Application: existing FastAPI/Uvicorn service, guest UI, and Admin portal.
- Local demo property: `hotel-de-luna-demo`.
- Storage: isolated SQLite and upload directories under `.local-demo/`.
- Active URLs: Guest <http://127.0.0.1:8083/>; Admin <http://127.0.0.1:8083/admin>; readiness <http://127.0.0.1:8083/health/ready>.
- The demo uses port 8083 because port 8082 was occupied; that existing listener was left untouched.
- Production, the existing persistent database, and GitHub were not changed.

## Imported content

| Content | Imported |
| --- | ---: |
| Room types | 6 |
| Restaurants | 4 |
| Published menu items | 40 |
| Hotel facilities | 11 |
| Conceptual floor maps | 19 |
| Guest services | 12 |
| Nearby attraction samples | 6 |
| Synthetic sample service requests | 2 |
| Validated bundled images | 111 |

The importer validates the ZIP paths, foreign references, prices, image signatures, and image decoding, then stores images in the existing local upload store. Images are stylized placeholders, not real hotel photographs.

## Verification

| Area | Result | Evidence |
| --- | --- | --- |
| V2 guest and Admin browser flow | PASS | 28 checks; 18 screenshots in `.local-demo/screenshots/`. |
| Image rendering | PASS | 77 rendered images decoded successfully; all requests stayed on the local origin. This includes the 40 published menu images and a single-item menu answer. |
| Specific menu-item question | PASS | “Breakfast Buffet” returned its published description, PHP 1,450 (DEMO) price, and stored image. |
| Admin edit reflected in guest UI | PASS | Checkout was temporarily changed from 12:00 to 12:30, retrieved in guest chat, then restored to 12:00. |
| Service request flow | PASS | Guest confirmation created a backend request ID; the request appeared in guest status and the Admin queue. The clean reseeded environment contains the package's two sample requests. |
| Admin data coverage | PASS | Admin displays 4 restaurants, 40 published menu items, 11 facilities, and all 19 V2 conceptual floors. |
| Access boundaries | PASS | Generated Admin credentials worked; unauthenticated Admin property access and unknown property scope were denied. Guest Wi-Fi/PMS authentication remains disabled by property policy. |
| Browser runtime | PASS | No page errors, console errors, failed local requests, or external browser requests. |
| Responsive guest UI | PASS | iPhone 390px and Pixel 412px layouts had no horizontal overflow. |
| Repository Playwright suite | PASS | 314 passed, 38 skipped, 352 total, across Chromium and Mobile Chrome. The skips are existing project/device scope exclusions. |
| Python syntax | PASS | `py_compile` completed for the importer and changed Python modules. |
| Repository pytest suite | NOT RUN | The requested browser checks were run; pytest was not run after these changes. |

The local demo was reset and reimported after browser testing, leaving the two fixture service requests and removing test-generated requests. The 8083 app is running in a foreground local session.

## Known limits

- All hotel facts, names, prices, recommendations, and images are synthetic demo content.
- Floor images are conceptual and markers do not form a route graph; indoor directions are unavailable.
- There is no live booking, reservation, POS, payment, request fulfillment, or hotel-operations integration.
- Attraction hours, distances, traffic, and current availability are not verified live.
- Guest Wi-Fi/PMS authentication is disabled by default; there is no live gateway connection.
- Free-form model generation requires a local Ollama service and model. Verified property retrieval and deterministic flows work without it.

## Artifacts

- V2 browser report: `.local-demo/screenshots/hotel-de-luna-v2-results.json`
- Screenshots: `.local-demo/screenshots/v2-01-guest-welcome.png` through the Admin and mobile screenshots listed in the report.

No production deployment, GitHub push, or merge was performed.
