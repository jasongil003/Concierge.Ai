# Concierge.AI

[![CI](https://github.com/jasongil003/Concierge.Ai/actions/workflows/ci.yml/badge.svg)](https://github.com/jasongil003/Concierge.Ai/actions/workflows/ci.yml)

**On-prem, AI-powered hotel concierge and operations platform designed for guest Wi-Fi environments, property teams, and ANTlabs integrations.**

Concierge.AI turns the hotel Wi-Fi entry point into a temporary digital concierge experience. Guests get a mobile-first personal assistant for hotel information, dining, service requests, recommendations, directions, and stay support, while hotel teams manage property content, operations, AI providers, access, reporting, and diagnostics from one property-scoped admin platform.

> **Release stage:** v1.0-RC1 production hardening. The repository has extensive automated security, backend, integration, container, and browser coverage, but a real hotel deployment still requires property-specific network, TLS, ANTlabs/PMS, physical-device, recovery, and capacity validation.

## What Concierge.AI is

Concierge.AI is designed to sit alongside the hotel network and existing systems rather than replace them.

- **ANTlabs / captive portal** remains the authority for guest Internet authentication and network admission.
- **PMS** remains the authority for hotel stay data when a PMS integration is enabled.
- **Concierge.AI** provides the guest experience, property knowledge, AI orchestration, service workflows, admin operations, analytics, and controlled integrations.
- **Hotel data stays property-scoped** so one property's guests, restaurants, configuration, reports, and staff access do not mix with another property.

## Core capabilities

| Area | Current capability |
| --- | --- |
| Guest experience | Mobile-first personal stay dashboard, Explore, Requests, My Stay, Concierge, Wi-Fi authentication flow, recommendations, dining, service requests, accessibility and error states |
| Admin platform | Property management, operational dashboard, guest requests/sessions, reports, health, network access, users/roles, restaurant workflows, design/branding and AI administration |
| AI | Provider abstraction for OpenAI, Gemini, Groq, Claude, OpenRouter and local OpenAI-compatible/Ollama services; routing, fallback, health, latency and usage controls |
| Property isolation | Backend-enforced property scope, restaurant assignments, host/domain collision protection and cross-property regression tests |
| RBAC | Server-side authorization, role ceilings, department/restaurant scope, session controls and audit-sensitive operations |
| Knowledge | Property-managed FAQs/documents, ingestion, review/publish flow, source metadata and bounded file processing |
| Hospitality | Facilities, restaurants, menus, promotions, recommendations, service catalog, SLAs, request lifecycle and guest-facing structured data |
| Operations | Health/readiness, metrics, alerts, reporting, XLSX/PDF exports, backup/restore and operational diagnostics |
| Network | Separate management and guest access concepts, management CIDRs, trusted proxy controls, canonical guest host/domain validation and secure production defaults |
| Data layer | SQLite for simple single-node on-prem deployments; PostgreSQL/Redis integration paths are covered by CI |
| Deployment | Docker production image, non-root runtime, persistent storage, migration tooling, security scanning and SBOM generation |
| ANTlabs / PMS | Adapters and validation paths exist; the exact live SG5/PMS contract must still be proven against the target hotel environment |

## High-level architecture

```text
Guest device
    |
    | Hotel Wi-Fi / QR / NFC
    v
ANTlabs / captive network
    |
    | pre-auth access to approved Concierge host
    v
+-----------------------------+
|        Concierge.AI         |
|                             |
|  Guest Experience           |
|  Personal Assistant         |
|  Property Knowledge         |
|  Service Requests           |
|  Dining / Recommendations   |
|  Stay Context               |
+-------------+---------------+
              |
      +-------+--------+
      |                |
      v                v
 Admin Platform     AI Router
      |                |
      |         +------+-----------------------------+
      |         |      |      |      |      |        |
      |       Local  OpenAI Gemini  Groq  Claude OpenRouter
      |
      +--> Property / RBAC / Restaurants / Reports / Diagnostics
      |
      +--> SQLite or PostgreSQL / Redis
      |
      +--> PMS / ANTlabs / approved external integrations
```

## Guest journey

```text
Join hotel Wi-Fi
      |
      v
ANTlabs pre-auth session
      |
      v
Concierge.AI guest experience
      |
      +--> hotel information
      +--> dining and recommendations
      +--> service requests
      +--> directions and stay assistance
      +--> Wi-Fi authentication
      |
      v
ANTlabs / PMS validates the guest when configured
      |
      v
Internet access opens
      |
      v
Concierge remains available during the stay
      |
      v
Checkout / expiry / retention boundary
      |
      v
Temporary guest context is expired, cleared or retained
according to the configured policy
```

## Important integration boundary

Concierge.AI does **not** directly grant Internet access.

ANTlabs remains responsible for moving a downstream device from unauthenticated to authenticated. Concierge.AI can participate in the guest login journey, but the exact SG5 external-portal fields, redirects, session binding, walled-garden rules, and logout/checkout behavior must be validated against the actual gateway before a hotel pilot.

Likewise, simulated PMS tests do not replace validation against the hotel's real PMS implementation. Message formats, timing, resynchronization, missing-guest behavior, checkout events, and recovery paths must be verified in the target environment.

See [ANTlabs integration](docs/ANTLABS_INTEGRATION.md).

## Quick start

### Requirements

- Python 3.12 recommended
- Node.js for Playwright/browser QA
- Ollama only if using a local AI model

### 1. Clone and create the Python environment

```bash
git clone https://github.com/jasongil003/Concierge.Ai.git
cd Concierge.Ai

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure the application

```bash
cp .env.example .env
```

Review the environment values before using any production profile. Development and mock integration settings are not production defaults.

### 3. Optional: start local AI

```bash
ollama serve
```

Configure the selected local model and endpoint in the admin AI settings. When Concierge.AI runs in Docker, the Ollama endpoint must be reachable from the container.

### 4. Start the development server

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8080 --no-proxy-headers
```

Open:

```text
Guest: http://localhost:8080
Admin: http://localhost:8080/admin
```

For a phone in a controlled hotel/lab network, use the server address allowed by the lab firewall and walled-garden policy.

## Testing

### Backend

```bash
python -m pytest -q
```

### Browser / E2E

```bash
npm ci
npx playwright install chromium
npm run test:e2e
```

The CI workflow also includes:

- backend tests
- PostgreSQL and Redis integration tests
- Python and npm dependency audits
- static security analysis
- repository secret scanning
- Docker production-image build
- non-root runtime and persistence smoke tests
- container vulnerability scanning
- SBOM generation
- Chromium/mobile browser workflows
- responsive and accessibility-oriented UI checks

A release should not be treated as green while any required CI gate is failing.

## Security model

Concierge.AI is designed around several boundaries:

- authentication and authorization are enforced server-side
- privileged actions require backend permission checks
- property and restaurant scope are validated by the backend
- guest session credentials are expiring and server-controlled
- production settings fail closed for unsafe secrets, hosts, origins, cookies, proxies, and broad management access
- AI-generated actions still pass normal authorization and confirmation rules
- provider secrets remain server-side and are masked from browser responses/logs
- uploaded content is validated and resource-bounded
- management access and guest access are treated as separate trust zones

See [Security boundaries](SECURITY.md) and [Vulnerability findings](audit/VULNERABILITY_FINDINGS.md).

## Production readiness

The application is in **RC1 production-hardening**, not general-production certification.

Before a real hotel rollout, validate at minimum:

1. green release CI on the exact release revision
2. hotel DNS, trusted HTTPS and canonical guest hostname
3. management CIDRs, trusted proxy configuration and guest/admin network separation
4. real ANTlabs SG5 captive-portal and authentication contract
5. real PMS behavior if PMS integration is enabled
6. physical iPhone and Android captive/browser flows
7. backup and restore from the intended off-host location
8. representative load, soak and failure/recovery tests on target hardware
9. hotel-specific monitoring, alerts and operating ownership

The repository's latest evidence and remaining gates are tracked in [Production Readiness Report](audit/PRODUCTION_READINESS_REPORT.md).

## Repository structure

```text
app/          FastAPI application, domain services and web assets
audit/        QA, security and production-readiness evidence
deploy/       Deployment and operational support files
docs/         Architecture, deployment, integrations and product documentation
loadtest/     Load/performance tooling
migrations/   Database migrations
tests/        Backend and integration tests
tests/e2e/    Playwright browser tests
```

## Key documentation

- [Architecture](docs/ARCHITECTURE.md)
- [On-prem deployment](docs/DEPLOYMENT.md)
- [ANTlabs integration](docs/ANTLABS_INTEGRATION.md)
- [AI providers and routing](docs/AI_PROVIDERS.md)
- [Hotel Knowledge Management](docs/KNOWLEDGE_MANAGEMENT.md)
- [Product roadmap](docs/ROADMAP.md)
- [Master product expansion plan](docs/MASTER_PRODUCT_PLAN.md)
- [Security boundaries](SECURITY.md)
- [Production readiness](audit/PRODUCTION_READINESS_REPORT.md)
- [Real-device acceptance](audit/REAL_DEVICE_ACCEPTANCE.md)

## Product direction

The priority is to prove a dependable hotel operating path:

```text
Guest joins Wi-Fi
      ->
Concierge is reachable before authentication
      ->
Guest receives a premium property-scoped assistant experience
      ->
Configured guest authentication succeeds
      ->
Internet access is granted by ANTlabs
      ->
Concierge remains available during the stay
      ->
Operational state, requests and temporary context are safely managed
```

The commercial architecture remains **on-prem first**, with cloud/hybrid capability evolving without weakening property isolation or requiring the guest experience to be rebuilt.

Native lightweight experiences such as App Clip / Android Instant App are not required for the core v1.0 release path; HTTPS guest access through Wi-Fi, QR or NFC remains the primary baseline.

## License

No project license has been selected yet. Do not assume redistribution or commercial-use rights until a license is explicitly added.
