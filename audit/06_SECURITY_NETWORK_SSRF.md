# 06 — Security: Network, SSRF & Webhooks

## Verified network controls (proof script)

InternetGuard (webhook delivery + Places):
- Blocks: 127.0.0.1, localhost, 169.254.169.254 (metadata), 192.168.1.1, 10.0.0.1, ::1, ftp:// scheme, non-80/443 ports. PASS (script).
- Allows public https (domain + ip), strips fragment, requires http(s).

NetworkGuard (guest IP gate):
- allowed_cidrs default ["127.0.0.0/8","::1/128"], guest_network_only=True default → with a public-deployed settings.guest_network_only=True the app would block everyone not in the CIDR. Production must set allowed_cidrs to hotel Wi-Fi ranges (config, not code).

GatewayGuard: enabled when set; forces antlabs auth.

## Finding

- SEC-005 (MED): DNS-rebinding TOCTOU in webhook test + delivery paths (main.py ~1525, ~2775): `validate_url()` resolves & checks the host, then `httpx.post(url)` resolves AGAIN; a rebinding domain could pass validation and land on 127.0.0.1/169.254.169.254. Also webhook URLs are admin-supplied (admin trusted, but a compromised/naive admin or a stored-XSS jump could pivot; worse, MITM rebinding is the realistic vector).
  Fix options:
  a) Resolve once, pin the IP address into the httpx request via explicit IP override (`URL("http://1.2.3.4/...")` + Host header) or `pin_verifier` that rejects if the resolved set != validated set.
  b) Route webhook egress through an egress proxy with allow-listed domains.
  c) Require HTTPS + cert pinning for webhook target (TLS still allows rebinding to attacker IP; combine with (a)).
- OBS-006 (INFO): webhook retries? Confirm `max_retries` handled; recommend exponential backoff + dead-letter log. Out of scope unless code run shows otherwise.

## Recommendations in priority order
1. Implement single-resolution + IP-lock webhook sender (smallest safe fix).
2. Disable `follow_redirects` already off. Keep ports restricted.
3. For LAN-only deployments (default), risk is theoretical; still fix before internet exposure.