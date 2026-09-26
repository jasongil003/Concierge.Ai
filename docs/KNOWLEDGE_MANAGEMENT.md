# Hotel Knowledge Management

## Implemented architecture

The existing FastAPI app, SQLite database, admin session/CSRF middleware, property RBAC, provider router, and Admin UI remain in use. `app/knowledge_management.py` owns the new document lifecycle. `app/main.py` exposes property-scoped admin routes and adds published retrieval to Guest AI. Uploaded content never becomes a tool instruction or authorization source.

```text
Admin upload → extension/MIME/magic and archive checks → original file in UPLOAD_ROOT
             → persisted source (uploaded) → background processing → source-located items
             → lexical chunks → review/edit → approve → publish → Guest AI retrieval
```

The queue is represented by persisted `km_sources.status` rows. FastAPI background tasks start processing after upload. A startup worker resumes `uploaded` rows and reclaims `processing` rows older than five minutes. The claim is atomic so concurrent workers do not process the same source. `processing_failed` rows are retried only on request. A retry replaces previously derived rows inside a transaction. API and Admin UI expose errors and retry.

New SQLite tables are `km_sources`, `km_items`, `km_chunks`, and `km_conflicts`, all scoped to `property_id`. The existing `knowledge_items` table remains intact. New tables and indexes are created idempotently when `KnowledgeStore` initializes; `structured_json` and `risk_flags_json` are added to early versions of `km_items` if missing. Take a database and upload-volume backup before deployment. On rollback, restore that backup to remove new data; the additive tables do not alter existing rows.

Original files live under `UPLOAD_ROOT/knowledge/<hashed-property-id>/<server-generated-source-id>`. The original filename is stored as sanitized metadata and is never used as a filesystem path. Deleting a source cascades its items and chunks, removes conflicts involving them, clears remaining conflict flags, and unlinks the original file. The existing admin audit log retains action metadata and IDs without document bodies.

## Supported formats and limits

PDF, DOCX, XLSX, CSV, TXT, Markdown, JSON, PPTX, PNG, JPEG, and WEBP are accepted. PDF text is extracted with pypdf. Office files are parsed as data; macros and embedded executables are never run. Excel formulas are read as cached values. Text files require UTF-8. Image OCR uses Pillow and Tesseract with a 30-second OCR timeout and a 30-megapixel pixel limit. Scanned PDFs currently fail with a clear OCR-not-configured message; machine-readable PDFs are not OCRed.

| Variable | Default | Purpose |
| --- | ---: | --- |
| `UPLOAD_ROOT` | `DB_PATH` parent `/uploads` | Persistent original storage |
| `KNOWLEDGE_MAX_FILE_BYTES` | 25 MiB | Per file upload ceiling |
| `KNOWLEDGE_MAX_FILES_PER_UPLOAD` | 5 | Admin UI selection ceiling |
| `KNOWLEDGE_MAX_FILES_PER_PROPERTY` | 500 | Source count ceiling |
| `KNOWLEDGE_STORAGE_QUOTA_BYTES` | 2 GiB | Per property original storage ceiling |
| `KNOWLEDGE_MAX_EXTRACTED_CHARS` | 500,000 | Parser text ceiling and archive expansion basis |

The Docker image installs `tesseract-ocr`. Non-Docker deployments must install the Tesseract executable on the server PATH for image OCR. Upload storage should be on an encrypted volume if encryption at rest is required. Backups already include `UPLOAD_ROOT`.

## Lifecycle, scope, and citations

New sources move through `uploaded`, `processing`, `processing_failed`, `ready_review`, `conflict_detected`, and `archived`. Extracted items begin at `ready_review`; authorized users can edit them, approve, publish, unpublish, or archive. Guest AI queries only `published` items with `visibility=guest`, no unresolved conflict, an effective date at or before now, an expiration after now, and the current property ID. Those checks happen in SQL before context reaches the AI provider. The existing manually managed entry/FAQ UI remains a legacy approved-content path when enabled. Legacy text document rows are excluded from Guest AI retrieval; their data is preserved for admin review or migration. Guest answers use only the selected property's published profile and property-scoped knowledge records.

Extracted items keep source ID, filename, category, normalized text, simple observed key/value data, section and page/paragraph/sheet/row/slide/line location. Tables retain rows and column labels in plain text. Admin AI returns citations, and users with edit permission can download the original. Guests currently receive source-grounded content in the provider context, but the guest response does not render explicit citations.

Visibility options are guest, admin, manager, engineering, staff, and an API-level custom role slug. `knowledge.view`, `knowledge.edit`, `knowledge.publish`, and `knowledge.delete` are enforced by the existing RBAC middleware and additional item checks. Publishing and source deletion are server-authorized; the UI asks for confirmation. New uploads default to Admin Only. There is no automatic publication switch enabled. The current model service remains provider-independent; extraction and search do not call any provider-specific embedding API.

The search index is a property-scoped SQLite chunk table with term-frequency metadata. It is a conservative keyword index, **not a dense vector or semantic embedding index**. Relevant chunks are assembled before a provider call. The provider policy marks retrieved content as untrusted. Specific prompt-injection and secret phrases are flagged and cannot be set to guest visibility until edited out. This pattern check is a guardrail, not a malware scanner or comprehensive DLP system.

Conflicts are detected only for explicit `key: value` facts sharing the same key with different values. Both records are withheld from Guest AI while the conflict is open. Resolution records the chosen item, archives the other, and requires `knowledge.publish`. Replacements link source versions. A new version does not remove the old one until an authorized user explicitly supersedes it. Source version history is available from the API and Documents UI.

Knowledge Health is computed from the presence of eight required categories and six core facts in published, currently effective items. Each criterion has equal weight; the result is a measurable coverage proxy, not a quality assessment. Missing categories and facts, pending review, conflicts, and expired item counts are shown. It never invents hotel facts. Admin AI uses deterministic read-only results for health, conflicts, and pending-review questions, and routes other questions through the existing provider abstraction with property-scoped citations. Declarative hotel statements can be proposed as drafts; they are saved only after an explicit Admin UI action.

## API additions

All routes below start with `/api/admin/properties/{property_id}/knowledge` and inherit admin session, CSRF, property isolation, and rate limiting.

| Route | Action |
| --- | --- |
| `GET /managed`, `GET /health`, `GET /conflicts` | List reviewable data, measured coverage, conflicts |
| `POST /conflicts/{id}/resolve` | Resolve with winner and note |
| `POST /sources`, `GET /sources/{id}` | Upload and inspect source |
| `GET /sources/{id}/download`, `GET /sources/{id}/versions` | Original and lineage |
| `POST /sources/{id}/retry`, `POST /sources/{id}/replace`, `POST /sources/{id}/supersede` | Processing and version actions |
| `DELETE /sources/{id}` | Delete original and derived content |
| `POST /items`, `GET /items/{id}`, `PATCH /items/{id}` | Create draft and review/edit item |
| `POST /items/{id}/approve`, `/publish`, `/unpublish`, `/archive` | Lifecycle actions |

The old document-upload route is an alias of the review-first upload flow. Existing manual entry and FAQ routes remain in place.

## Deployment and migration

1. Back up the current SQLite database and upload volume together.
2. Install updated Python requirements. Install Tesseract for image OCR, or leave image uploads to fail with a clear processing error until it is installed.
3. Set `UPLOAD_ROOT` to persistent writable storage and tune the limits above. Encrypt the host volume if required by hotel policy.
4. Deploy one app instance initially; the atomic SQLite processing claim supports multiple workers, but high-throughput ingestion should move to a dedicated queue.
5. Start the app. `KnowledgeStore` creates additive tables and indexes automatically; no production manual SQL is needed.
6. Review existing legacy document rows before retiring or migrating them. They are preserved but excluded from Guest AI retrieval. Existing enabled manual entries and FAQs remain available.
7. Verify the [manual QA checklist](KNOWLEDGE_MANAGEMENT_QA.md) with at least two property accounts and one read-only role.

## Known limitations and next work

- Dense embeddings, semantic reranking, and a dedicated vector database are not implemented. Keyword search can miss paraphrases.
- Extraction is conservative and deterministic. It does not run an LLM to infer every hotel entity or understand complex tables. Admin review is essential.
- OCR confidence and scanned-PDF OCR are not implemented. Tesseract image OCR language support depends on installed language packs.
- Secret and prompt-injection detection uses patterns. A malware scanning adapter, antivirus service, and stronger DLP are needed before accepting arbitrary external files at scale.
- The file selection count is enforced in the Admin UI; each API request currently carries one file. For large deployments, use streaming multipart uploads and a dedicated worker queue.
- Fine-grained role visibility is available in the API; the current Admin UI offers the standard five scopes.
- Guest answer preview, retrieval usage analytics, and automated unanswered-question mining are future work. Guest responses do not yet include visible citations.
