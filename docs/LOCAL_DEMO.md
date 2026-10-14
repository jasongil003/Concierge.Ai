# Isolated Concierge.AI Local Demo

This runbook starts the existing FastAPI application with SQLite, the guest interface, and the Admin portal in an isolated local workspace. The current Hotel De Luna V2 demo is running on loopback port 8083.

## Local safety and storage

- The local demo binds to `127.0.0.1`; it is not exposed to the LAN.
- State is stored only under `.local-demo/`: SQLite at `.local-demo/state/concierge.db`, uploaded media at `.local-demo/uploads/`, and logs, credentials, and screenshots alongside them. Git ignores this directory.
- The launcher sets `DEMO_MODE=true`, clears external database and AI-provider credentials, disables Redis and background workers, and uses mock ANTlabs mode. Guest Wi-Fi/PMS authentication is disabled by the property's default policy.
- Seed, import, and reset verify the checkout-owned `.local-demo/DEMO_STATE` marker, dedicated SQLite path, blank `DATABASE_URL`, and exact upload directory. Reset clears only the demo database and uploads.
- Administrator and staff passwords are generated for this checkout and stored in ignored `.local-demo/credentials.json` with file mode `0600`.
- The existing `state/concierge.db`, other services, and production configuration are not used.

## Open the demo

| Purpose | URL |
| --- | --- |
| Guest experience | <http://127.0.0.1:8083/> |
| Admin portal | <http://127.0.0.1:8083/admin> |
| API documentation | <http://127.0.0.1:8083/docs> |
| Readiness check | <http://127.0.0.1:8083/health/ready> |

The launcher defaults to port `8082`. If that port is occupied, select port 8083 for every command:

```bash
CONCIERGE_LOCAL_DEMO_PORT=8083 ./scripts/local-demo.sh start
```

For a foreground server, use `CONCIERGE_LOCAL_DEMO_PORT=8083 ./scripts/local-demo.sh foreground` and stop it with Ctrl+C. The launcher refuses to stop a process unless its recorded PID also owns the selected port.

## Import Hotel De Luna V2

```bash
CONCIERGE_LOCAL_DEMO_PORT=8083 ./scripts/local-demo.sh import /path/to/Hotel_De_Luna_V2_Complete_Demo.zip
```

The importer reads the package guide, fixture JSON, and asset manifest. It validates archive paths, foreign references, prices, image signatures, and image decoding before writing. It uses the existing property-scoped Admin APIs and adapts package data to the current property, restaurant, menu, facility, room, map, recommendation, and service schemas. Repeating the import updates matching records without duplicating them.

The archive is retained at `.local-demo/hotel_de_luna_v2.zip`. Later `start` and `seed` commands reapply it. Imported media is stored under `.local-demo/uploads/hotel-de-luna-demo/hotel_media/` using content-addressed filenames and served through a property-scoped route.

Imported package content:

- 6 room types
- 4 restaurants and 40 published menu items
- 11 hotel facilities
- 19 conceptual floor maps
- 12 guest services and 6 nearby attraction records
- 2 synthetic service requests with backend-generated IDs
- 111 validated bundled images

Images are actual bundled assets, but they are stylized placeholders, not photographs of a real hotel. Menu prices and room rates are fictional PHP demo references. Maps show conceptual markers; the package has no indoor route graph, live booking engine, or POS integration. Nearby places do not include verified live hours, travel distances, or traffic.

## Demo accounts

| Account | Login | Scope |
| --- | --- | --- |
| Administrator | `demo-admin` / generated password | Local demo property administration |
| Housekeeping lead | `demo-housekeeping` / generated password | Housekeeping department manager |
| Restaurant manager | `demo-sora-manager` / generated password | Sora Japanese Restaurant |
| Guest | Room `1208`, last name `Rivera` | Mock PMS login |

To display a generated password locally:

```bash
.venv/bin/python scripts/local_demo_credentials.py --ensure --field admin_password
.venv/bin/python scripts/local_demo_credentials.py --ensure --field housekeeping_password
.venv/bin/python scripts/local_demo_credentials.py --ensure --field restaurant_manager_password
```

Credentials and guest data are synthetic. Staff accounts use the existing RBAC roles and restaurant/department assignments.

## AI and service boundaries

The demo clears Gemini, OpenAI, compatible-provider, and Places credentials. It permits a local Ollama endpoint at `127.0.0.1:11434`; if Ollama is unavailable, verified property retrieval, local rich cards, service requests, and transparent fallback responses still work. No external AI or Places provider is contacted by the launcher.

The property keeps guest Wi-Fi/PMS sign-in disabled by default. The mock gateway mode does not contact a real gateway or grant network access.

Service requests require guest confirmation, then use the local backend and return a request ID. They do not dispatch to hotel staff or an external fulfillment service.

## Commands

```bash
CONCIERGE_LOCAL_DEMO_PORT=8083 ./scripts/local-demo.sh health
CONCIERGE_LOCAL_DEMO_PORT=8083 ./scripts/local-demo.sh logs
CONCIERGE_LOCAL_DEMO_PORT=8083 ./scripts/local-demo.sh restart
CONCIERGE_LOCAL_DEMO_PORT=8083 ./scripts/local-demo.sh seed
CONCIERGE_LOCAL_DEMO_PORT=8083 ./scripts/local-demo.sh import /path/to/Hotel_De_Luna_V2_Complete_Demo.zip
CONCIERGE_LOCAL_DEMO_PORT=8083 ./scripts/local-demo.sh reset --yes
CONCIERGE_LOCAL_DEMO_PORT=8083 ./scripts/local-demo.sh screenshots
./scripts/local-demo.sh backend-tests
./scripts/local-demo.sh e2e-tests
```

The Python test command and Playwright config use their own temporary test state. Neither suite uses the local demo database.

## Browser coverage

The V2 Playwright runner verifies greeting, dining cards, all 40 menu descriptions/prices/images, a named menu-item answer with its image, room rates and galleries, checkout policy, facility and conceptual map, nearby recommendations, confirmation and status of service requests, Admin content panels and policy editing, authentication boundaries, and 390px/412px mobile layouts. Screenshots and a JSON report are written to ignored `.local-demo/screenshots/`.
