# Streaming and reverse-proxy acceptance

## Implementation and local evidence

The guest Intelligent UI has a bounded SSE route, provider delta adapters, schema/event checks, cancellation, and a client disconnect path. Existing backend and browser tests exercise event ordering, cancellation/provider-slot release, isolation, and guest UI handling. These tests run through the local ASGI test client and do not reproduce deployment buffering.

## Target proxy result

**BLOCKED.** No reverse proxy or target deployment was available on this host. Docker daemon, nginx, and Caddy were unavailable. Real provider delta timing and buffering, client disconnect over TCP, proxy idle timeout, and streaming behavior across target workers remain unverified.

## Disposable proxy acceptance

1. Run the candidate behind the same proxy version and buffering/timeout settings intended for the pilot, on an isolated network with synthetic fixtures.
2. Use an authorized provider test credential or the existing deterministic provider fixture. Do not report fixture output as live-provider evidence.
3. Capture server and browser timestamps for request start, first SSE event, ordered deltas, terminal event, and completion; report p50/p95/p99 only with sufficient samples.
4. Exercise guest cancellation, abrupt disconnect, network interruption, proxy idle timeout, concurrent sessions, session expiry during stream, cross-property attempts, provider failure, and duplicate action prevention.
5. Inspect response headers and proxy config for buffering/compression/idle-timeout behavior. Confirm all failure paths release provider slots and do not create duplicate state-changing requests.
6. Verify guest legacy UI fallback and admin/property feature flags through the same proxy; preserve explicit confirmation for guest actions.

Do not claim proxy acceptance based on the local test server. Record actual proxy version, relevant non-secret settings, test SHA, sanitized event timings, and failures.
