# ANTlabs staging and production acceptance checklist

**Status: NOT TESTED.** Local mock mode and browser tests do not prove gateway integration. No physical ANTlabs gateway, live property DNS, or production certificate was available for this run. Do not mark a physical integration row as passed without dated evidence from the actual gateway and property network.

## Test record

- Property / site: ____________________________________________
- Gateway model, firmware, and configured mode: __________________
- Concierge.Ai build / commit: _________________________________
- Tester / date / approved maintenance window: __________________
- Staging or production VLANs (no passwords or secrets): ___________
- Guest hostname / DNS records / certificate expiry: _______________
- Gateway and Concierge.Ai log/evidence references: _______________
- Test guest identifiers (disposable): ____________________________

## Acceptance steps

| Check | Exact steps and expected result | Status |
|---|---|---|
| Actual gateway integration | Configure the deployed ANTlabs gateway to use the documented Concierge adapter and staging callback. Confirm the live adapter mode is selected and no mock response is involved. | NOT TESTED |
| Captive portal redirect | Associate a physical guest device to the staging SSID. Confirm the gateway redirects to the Concierge guest hostname with the required signed/session parameters and no open redirect. | NOT TESTED |
| Guest domain | Confirm the requested domain belongs to exactly one property, and that the gateway redirect, HTTP Host, Origin, and property mapping all select that property. | NOT TESTED |
| Real DNS resolution | Resolve the guest hostname from the guest VLAN and an independent external resolver as applicable. Confirm A/AAAA records point to the approved ingress only and do not expose management addresses. | NOT TESTED |
| TLS certificate | Connect from a physical iOS and Android guest device. Verify certificate name, chain, dates, SNI, and absence of interstitial warnings. Record expiry/fingerprint, never private key material. | NOT TESTED |
| HTTPS redirect | Request the configured HTTP guest URL and verify it redirects to the same assigned hostname over HTTPS without losing valid gateway parameters or session state. | NOT TESTED |
| Gateway allowlist | From the guest VLAN, verify only the approved portal, authentication, DNS, and required provider destinations are reachable. Confirm management, database, Redis, metrics, and Admin endpoints remain blocked. | NOT TESTED |
| Session start | Authenticate one disposable guest through the real gateway and confirm the gateway and Concierge.Ai agree on the same property, session, and authorization state. | NOT TESTED |
| Session resume | Reopen the portal with the same device/session and confirm documented continuation without creating an unrelated or cross-property session. | NOT TESTED |
| Logout | Log out through Concierge.Ai, then attempt to resume via the portal and gateway. Confirm the old app session is revoked and gateway behavior matches the agreed logout contract. | NOT TESTED |
| Session expiration | Use a short staging expiry; wait beyond it and confirm app actions fail closed and the gateway requires the documented reauthentication flow. | NOT TESTED |
| Multiple devices | Authenticate two disposable devices; verify sessions remain independent, logout/expiry affects only intended sessions, and each device is mapped to the correct property. | NOT TESTED |
| Property isolation | Exercise two properties with separate guest domains and gateway profiles. Attempt host/origin/property-ID substitution and confirm no cross-property data or session access. | NOT TESTED |
| Gateway unreachable | In staging, block or stop the gateway integration endpoint safely. Confirm the app reports a safe degraded state, does not falsely authenticate guests, and recovers after connectivity returns. | NOT TESTED |
| Concierge.Ai restart | Restart only the staging Concierge.Ai app container/process during an approved test. Verify persistent property, session, and network configuration behavior and successful gateway reconnection. | NOT TESTED |
| Gateway restart, when safe | Only during an approved staging maintenance window, restart the gateway using the site's runbook. Verify no duplicate sessions/requests, clean recovery, and correct handling of in-flight guests. Do not perform on production without explicit operational approval. | NOT TESTED |

## Evidence and sign-off

- Capture gateway configuration exports with credentials and secrets removed.
- Correlate timestamps and request IDs between gateway and Concierge.Ai logs.
- Record the exact observed redirect chain, status codes, hostnames, certificate chain, and session outcomes.
- Track every failure with steps, expected/actual result, affected property/device, log reference, and retest build.
- Overall result: **NOT TESTED** until the required staging gateway rows are completed and reviewed by the property's network operator.
- Network operator: __________________________ Date: _______________________
- Concierge.Ai operator: ______________________ Date: _______________________
