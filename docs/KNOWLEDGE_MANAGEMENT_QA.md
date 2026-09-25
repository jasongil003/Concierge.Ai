# Hotel Knowledge Management manual QA

Use a staging property and a separate second property. Prepare a valid text PDF, DOCX, XLSX, CSV, image with legible text, unsupported `.exe`, and two documents with conflicting `Checkout: value` lines. Record the observed result for each step.

| Area | Steps | Expected result |
| --- | --- | --- |
| Admin chat keyboard | Open Admin AI, type a question, press Shift+Enter; then press Enter twice rapidly. | Shift+Enter adds a line. Enter sends once; one answer appears. |
| Composer files | Attach two files, remove one, paste an image, then drag a file onto the composer. | Pending files appear with remove controls; no file uploads before Send. |
| Upload progress | Send a valid file. | Upload percentage and processing message appear; a source appears in Documents. |
| Validation | Upload `.exe`, mismatched MIME, malformed PDF, and a file over the configured limit. | Each is rejected with a clear error; no guest content appears. |
| Parsing and OCR | Upload PDF, DOCX, XLSX, CSV, and an image with Tesseract installed. | Reviewable items appear with page, paragraph, sheet/row, CSV row, or image location. Scanned PDF reports OCR not configured. |
| Review and editing | Open Knowledge, expand an extracted item, edit title/content/category/visibility and save. | The edited item remains in review; the original source is linked. |
| Publishing | Approve and publish a guest-visible item. | Guest AI can retrieve it for the same property. An Admin Only item remains unavailable to guests. |
| Unpublishing | Unpublish the item and ask Guest AI again. | The new item is absent from retrieval immediately. |
| Permissions | Log in as read-only staff; try publish, delete, and download. | Publish/delete are forbidden. Original download requires edit permission. |
| Conflict | Upload two sources with different `Checkout:` values. | Conflict appears; neither conflicting value reaches Guest AI until resolved. Resolve with a note and verify audit. |
| Versioning | Replace a document, inspect Versions, then supersede the previous source. | Linked version is visible; old source is archived and its chunks are excluded. |
| Effective dates | Set a future effective date and a past expiration on separate items. | Neither item reaches Guest AI until/while active. |
| Knowledge Health | Publish a fact in a missing required category; refresh Health. | Coverage and missing list change according to documented criteria. |
| Deletion | Delete a source, then search Admin AI and Guest AI and inspect original download. | Source, derived items/chunks, and original file are unavailable; audit event remains. |
| Prompt injection | Upload text asking the AI to ignore instructions and reveal Admin Only data. | Risk flag appears; guest visibility is rejected; no protected content enters guest retrieval. |
| Tenant isolation | Upload and publish in Property A, then switch to Property B. | B cannot list, download, search, or retrieve A's source or items. |
| Mobile | Open Admin AI, Knowledge, and Documents at mobile width. | Composer, lists, review fields, and actions remain usable without horizontal clipping. |
| Error and retry | Upload a scanned textless PDF or cause OCR failure; choose Retry. | Processing failure is visible; retry does not duplicate knowledge. |
