# On-Prem Prototype Deployment

## Minimum prototype

You need:

- ANTlabs lab gateway or guest network
- one computer for Concierge.Ai
- Ollama installed on the AI host
- Python 3.12+ or Docker
- a local 4B-class model

A domain and SSL certificate are not required for the first LAN test.

## Option A: run with Python

```bash
git clone https://github.com/jasongil003/Concierge.Ai.git
cd Concierge.Ai
git checkout feature/onprem-mvp

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
ollama pull qwen3:4b
ollama serve

uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Open:

```text
http://<server-ip>:8080
```

Health check:

```text
http://<server-ip>:8080/health
```

## Option B: application in Docker, Ollama on host

```bash
cp .env.example .env
docker compose up --build
```

Ollama must already be running on the host.

The compose configuration points the container at `host.docker.internal:11434`.

## First ANTlabs lab test

Keep:

```env
ANTLABS_MODE=mock
```

Then verify:

1. a phone on the guest VLAN can reach the Concierge server before authentication
2. normal Internet access is still blocked
3. Concierge UI loads
4. hotel FAQ fast paths work
5. local model responses work
6. the temporary session expires after inactivity

Only after those steps should the gateway authentication handoff be enabled.

## Production-like pilot

Recommended next step:

```text
concierge.example.com
        |
        | internal DNS
        v
10.x.x.x local Concierge server
```

Add:

- valid HTTPS certificate
- internal DNS
- ANTlabs HTTPS walled-garden rule
- dedicated service VLAN
- firewall policy
- reverse proxy
- persistent database
- monitoring
- log retention policy
- backup/restore procedure

## HTTPS

For the lab, HTTP is acceptable.

For a guest pilot, use a trusted HTTPS certificate. Do not rely on a self-signed certificate on guest devices.

## Model sizing

Start small:

```env
OLLAMA_MODEL=qwen3:4b
MAX_OUTPUT_TOKENS=160
OLLAMA_THINK=false
```

Then benchmark:

- time to first token
- tokens per second
- 5 concurrent requests
- 10 concurrent requests
- 20 concurrent requests
- CPU/GPU utilization
- memory pressure
- queue time

Do not select a larger model until measured answer quality requires it.

## Security note

The prototype is intentionally not production hardened yet.

Do not expose it directly to the public Internet or connect it to production PMS data until the security milestones in the roadmap are complete.
