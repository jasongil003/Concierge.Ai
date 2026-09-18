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
- Qwen3 4B default model configuration
- ANTlabs integration adapter
- mock gateway authentication
- browser-based ANTlabs authentication handoff scaffold
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
ollama pull qwen3:4b
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
- [On-prem deployment](docs/DEPLOYMENT.md)
- [Roadmap](docs/ROADMAP.md)
- [Security boundaries](SECURITY.md)

## Prototype priorities

The next technical milestone is deliberately narrow:

> **Unauthenticated guest -> local Concierge.Ai -> valid hotel credentials -> ANTlabs authenticates the same device -> Internet opens -> Concierge remains available.**

Do not add voice, mobile apps, large models, or complex hotel integrations until this flow is proven reliably on a lab SG5.

## License

No license has been selected yet. Do not assume commercial redistribution rights until a project license is added.
