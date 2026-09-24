# 26 — AI provider verification

Status: **FIXED AND VERIFIED** with deterministic provider adapters.

The existing modes are enforced rather than replaced: `fixed`, `automatic`, `privacy_first`, and `cloud_first`. `fallback_chain` ordering is honored, disabled/unavailable entries are excluded, local-only mode filters cloud providers, and the loop is finite and de-duplicated. Each attempted provider records a success/failure row; tokens are charged only on a successful response, and the returned provider is the adapter that actually succeeded.

Property-scoped limits now support requests per minute/day/month, per-response token budget, and monthly token budget. Request reservation is atomic and recorded once per guest request, not once per fallback attempt. Tests verify fallback order, actual-provider usage, no double token charge after failure, limit rejection, and property A/B independence.

Prompt construction now has explicit `SYSTEM POLICY`, `PROPERTY CONTEXT`, `UNTRUSTED HOTEL KNOWLEDGE`, `UNTRUSTED INTERNET RESULTS`, and `CONVERSATION` sections. Retrieved text cannot grant roles, switch properties, authorize tools, disclose secrets, or direct access to local/private/metadata destinations. Server RBAC and tool permission checks remain authoritative.

Residual risk: monetary budgets are not enforced because no audited price/version table exists. Live paid-provider credentials were intentionally not used; live timeout/429/5xx behavior remains a deployment integration check.
