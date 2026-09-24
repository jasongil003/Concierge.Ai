# Guardrails and Security Policy

`app/guardrails.py` is the central policy layer for guest access. Guest requests are evaluated against the property selected by an authorized host/property binding, the direct or trusted-forwarded source IP, the guest session’s property, and the action level before protected work occurs.

## Request path

1. Resolve the property from the configured guest hostname. A caller-supplied property ID cannot override a hostname assigned to another property.
2. Resolve the client address. `X-Forwarded-For` is ignored unless the direct peer belongs to a configured trusted proxy range.
3. Match the resolved address against the property’s approved CIDRs.
4. For existing sessions, confirm the session belongs to that property and re-run network validation. Failed validation suspends or expires the session according to policy.
5. Classify the action. Read actions may proceed; requests and transactions require explicit confirmation; restricted actions are denied.
6. Apply privacy, prompt-injection, input-minimization, output-validation, rate-limit, and audit policy before the protected operation.

Guardrail denial responses contain a safe structured decision with `allowed`, `reason`, `policy`, `propertyId`, `actionLevel`, `confirmationRequired`, `escalationRequired`, and `requestId`. Client IPs, matched internal ranges, secrets, and internal policy details are not returned to guests.

## Safe defaults

Guest network enforcement is enabled. A new development property permits loopback only (`127.0.0.0/8` and `::1/128`) so local setup remains usable; production properties must replace those ranges with approved hotel guest subnets. Reservations and financial actions are disabled until a backend integration supplies authoritative confirmation.

## ANTlabs boundary

ANTlabs context is trusted only when the direct source belongs to an approved gateway range and the request carries a fresh HMAC-SHA256 signature over `timestamp + "." + raw_body`. The exact headers and gateway-side signing support must be confirmed against the deployed ANTlabs model and firmware. Browser-supplied `gateway_context` is deliberately discarded at session creation.

## Outbound access

Guest place search uses fixed provider code rather than guest-supplied URLs. Webhook destinations pass centralized URL/DNS validation, block credentials and nonstandard ports, block loopback/private/link-local/reserved destinations, and disable redirects. Revalidation immediately before connection limits DNS-rebinding exposure.

See [GUARDRAILS_CHECKLIST.md](GUARDRAILS_CHECKLIST.md) for the staging release gate.
