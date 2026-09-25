# 17 — Compliance Recommendations

No contractual obligation was provided; this file cites good-practice mappings (GDPR, PCI-DSS Annex A, ISO 27001 control families) as advisory.

## Personal data
- Guest chats, memories, uploads, service requests contain PII; sessions auto-expire (30m TTL) — good. Add explicit `DELETE /api/guest/memory` (per-property "forget me") and document controller/processor split (property operator = controller; you = processor).
- Retention: sessions 30d, transcripts 90d, uploads 180d, analytics 12mo (configurable); purge job (DEP-003 pipeline).
- Privacy banner present; add one line: data leaves property only to the AI providers you configure.

## Security operations
- Admin audit log with outcome codes (built-in). Map to ISO 27001 A.8/A.12 record retention.
- Supplier risk: Google (Gemini/Places), OpenAI, Ollama etc → maintain a registry + DPAs if controllers.
- Breach response playbook: rotate CREDENTIAL_ENCRYPTION_SECRET, reset admin creds, revoke sessions (admin cookie invalidation exists), restore from nightly DB backup (DEP-003).

## Payment / PCI scope
- No card data stored; chat references room storage only. If guest chat ever captures PAN, add redaction (AIInputSanitizer secret-redaction pattern extension) and never store. Keep POST /api/guest/* route under TLS.

## Regional notes
- Add processing bases at first consent (hotel at check-in) — keep the privacy banner timestamped.
- Provide right-to-access: extend admin to export a guest mind of data (ids) to JSON/PDF (reuse reporting engines).
- Right-to-erasure: same API as "forget me" + cascade of transcripts/services/uploads.