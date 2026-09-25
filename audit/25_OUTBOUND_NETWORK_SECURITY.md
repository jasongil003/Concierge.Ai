# 25 — Outbound network security

Status: **FIXED AND VERIFIED** for webhook delivery.

`OutboundRequestBroker` is the controlled outbound transport. It permits only credential-free HTTP/HTTPS on ports 80/443, resolves a hostname once per hop, rejects any private/loopback/link-local/multicast/reserved/unspecified address (including IPv4-mapped IPv6), connects the socket directly to the validated address, and preserves TLS certificate/SNI validation against the original hostname. Every redirect is independently resolved and validated. Redirect count, response bytes, headers, time, user agent, and connection close behavior are bounded.

Automated coverage includes localhost, `127.0.0.1`, `::1`, RFC1918 ranges, `169.254.169.254`, `metadata.google.internal`, integer IPv4 notation, nonstandard ports, `ftp`, `file`, `gopher`, public-to-private redirects, and DNS answers changing after the single approved resolution.

Both test-webhook and event-webhook delivery use the broker and emit security audit events. URL validation during webhook configuration remains an early UX check, but the actual transport independently enforces policy.

Residual risk: administrator DNS/SSL diagnostic utilities are not yet routed through this broker. Known AI provider adapters use their configured provider endpoints and were not migrated to the HTTP/1.1 broker because local Ollama/LM Studio deliberately requires private-network connectivity; those endpoints need a separate provider-endpoint trust policy.
