# 09 — AI Providers, Fallback Chain & Spend Governance

## Verified architecture
- AIProviderStore: providers/credentials (Fernet-encrypted), default_provider, provider→property binding.
- AIModelService: `resolve_connection` and `concierge_chat` across providers; local Ollama preferred when `ai_provider_mode=auto`.
- Legacy AIOrchestrator (ai.py) remains as the exception-time fallback (complete provider cycle) when the primary path fails; fallback chain in llm.py includes OpenAI, Ollama, Groq, Gemini.
- LLM-only decisions: `llm.py` builds the deterministic system prompt (property data + knowledge), used by primary path. ai.py handles its own prompt.
- No "effective model plan" persisted; providers are tried in fixed order on failure.

## Findings
- SEC-009 (MED — governance dead-letter): ai_providers settings schema stores `routing_mode` ("single"/"content_moderation"/"provider_chain"), `fallback_chain_json`, `limits_json` (monthly/request/rate) — **but the runtime path (`concierge_chat`, `resolve_connection`, ordering) never reads them.** Limits are therefore advisory/DBA-level only; spend caps and chain order are not enforced in code. Recommend: enforce `limits_json` (deny when exceeded, using `record_usage` row) and make routing_mode select the fallback order; at minimum add a startup validation that rejects unknown routing mode and caps.
- OBS-OPS (LOW): local Ollama default `host.docker.internal:11434` — on LAN deployment make it a real URL with set ollama_base_url. (Ops concern, not vuln.)

## Recommendations
1. Wire limits_json into the chat path (cheap: check before generation; deny w/ 429-style response).
2. Enforce fallback_chain_json order in resolve_connection; remove hard-coded provider list in llm.py fallback builder.
3. Log and alert on "primary provider failed, fell back to X" — today only via observability raw logs.
4. Redact secrets everywhere in ai_providers logs (verified no plaintext in API responses; audit redaction covers).