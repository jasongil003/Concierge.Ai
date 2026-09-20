# Concierge.Ai

**On-prem, AI-powered hotel concierge designed to integrate with guest Wi-Fi and ANTlabs gateways.**

Concierge.Ai is intended to turn the hotel Wi-Fi login journey into a temporary digital concierge experience. The gateway remains responsible for guest authentication and Internet access; Concierge.Ai provides the guest interface, local AI, hotel knowledge, and service workflows.

## Current prototype

The `feature/onprem-mvp` branch now includes:

- mobile-first guest concierge UI
- temporary guest session lifecycle
- hotel-specific configuration
- zero-LLM fast paths for common questions
- local AI through Ollama
- Qwen3 8B default local model configuration
- admin-managed AI provider selection: Gemini / Groq / OpenAI / Claude / Copilot placeholder / Local AI
- property-level AI settings with Local-Only Mode and encrypted server-side credentials
- Fast / Auto / Advanced guest AI mode switcher
- live nearby-place recommendation adapter
- ANTlabs integration adapter
- mock gateway authentication
- browser-based ANTlabs authentication handoff scaffold
- admin zone/facility/floor-map foundation with AP-to-zone mapping and deterministic route graph
- privacy-first guest stay memory with property-scoped pseudonymous device identity
- location analytics foundation for live zone occupancy, dwell time, movement, and aggregate reports
- configurable intro experience with logo-generated presets and validated web animation uploads
- SQLite prototype state
- Docker deployment
- phased architecture/security documentation

## Guest journey

```text
Join Hotel Wi-Fi
      |
      v
ANTlabs pre-auth session
      |
      v
Concierge.Ai
      |
      +--> hotel questions
      +--> Wi-Fi help
      +--> guest authentication
      |
      v
ANTlabs / PMS validates guest
      |
      v
Internet access opens
      |
      v
Concierge remains available
      |
      v
Session expires / checkout
      |
      v
Temporary guest context removed
```

## Important integration rule

Concierge.Ai does **not** open Internet access itself.

ANTlabs remains the authority that changes a downstream guest from unauthenticated to authenticated. The repository contains a configurable browser-handoff scaffold, but the exact SG5 login endpoint and field names must be captured and validated on a real gateway before enabling it.

See [ANTlabs integration plan](docs/ANTLABS_INTEGRATION.md).

## Quick start

### 1. Install and start Ollama

```bash
ollama pull qwen3:8b
ollama serve
```

### 2. Run Concierge.Ai

```bash
git clone https://github.com/jasongil003/Concierge.Ai.git
cd Concierge.Ai
git checkout feature/onprem-mvp

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Open:

```text
http://localhost:8080
```

Admin AI configuration is available at:

```text
http://localhost:8080/admin
Settings -> AI Models
```

New roadmap administration sections are available in the same admin platform:

```text
Zones
Sessions
Location Analytics
Branding -> Intro Experience
```

The V1 location model is intentionally aggregate: `Device -> Associated AP -> Zone -> Facility`. Concierge.Ai does not infer exact indoor X/Y guest position from a single AP and guest-facing APIs never expose AP identifiers or WLAN infrastructure.

For Docker-based local AI, use an endpoint reachable from the container, commonly `http://host.docker.internal:11434`.

### 3. Run browser tests

The repository includes Playwright end-to-end tests for the guest chat and admin platform.

```bash
npm install
npx playwright install chromium
npm run test:e2e
```

Playwright starts its own FastAPI server on `http://127.0.0.1:8092` during the test run, so it can run alongside a local dev server on another port.

For a phone on the hotel/lab network:

```text
http://<concierge-server-ip>:8080
```

The prototype starts in:

```env
ANTLABS_MODE=mock
```

so the UI can be built and tested before connecting it to a real SG5 authentication flow.

## Why local first?

The first prototype does not require:

- a public domain
- a cloud AI account
- AI token billing
- a GPU server
- public Internet exposure

A real hotel pilot should add a proper hostname, internal DNS, trusted HTTPS, network isolation, monitoring, and the validated ANTlabs authentication contract.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [ANTlabs integration](docs/ANTLABS_INTEGRATION.md)
- [AI providers and routing](docs/AI_PROVIDERS.md)
- [On-prem deployment](docs/DEPLOYMENT.md)
- [Product roadmap](docs/ROADMAP.md)
- [Security boundaries](SECURITY.md)

## Prototype priorities

The next technical milestone is deliberately narrow:

> **Unauthenticated guest -> local Concierge.Ai -> valid hotel credentials -> ANTlabs authenticates the same device -> Internet opens -> Concierge remains available.**

The commercial roadmap is **on-prem first, cloud/hybrid later**. The immediate order is ANTlabs authentication proof, production HTTPS/re-entry, the self-service property/landing-page platform, hotel knowledge/RAG, and one real hotel pilot. Voice and advanced indoor positioning come after the core flow is proven.

## License

No license has been selected yet. Do not assume commercial redistribution rights until a project license is added.
