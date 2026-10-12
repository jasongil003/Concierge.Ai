# Transcript encryption key rotation design

## Scope and compatibility

Transcript encryption continues to use the existing Fernet implementation in `app/ai_providers.py`; provider credential encryption and its `CREDENTIAL_ENCRYPTION_SECRET` are unchanged. Before a key ring is configured, new conversation messages keep the existing `fernet:v1:<token>` format and guest UI turn fields keep their historical untagged Fernet format. Historical plaintext conversation rows remain readable for compatibility.

When `CONVERSATION_ENCRYPTION_KEYS` and `CONVERSATION_ENCRYPTION_ACTIVE_KEY_ID` are configured, new transcript cells use `fernet:v2:<key-id>:<token>`. The key ring always includes the existing credential secret as the implicit `legacy` read key for v1 and untagged turn ciphertext. Additional configured IDs support current and previous keys. Unknown versions and missing IDs fail closed; conversation rendering returns the established unavailable-message placeholder rather than plaintext fallback.

The credential secret is deliberately not rotated by this transcript tool. It also protects provider credentials and request hashes; changing it without separately migrating those values would strand them.

## Rotation and rollback

`python -m app.transcript_rotation` is read-only and emits aggregate counts, unreadable count, active/target key IDs, and a keyed stable fingerprint over ordered record identities and stored cells. The fingerprint uses an HMAC keyed by the legacy secret so it does not expose low-entropy legacy text to offline guessing. It never prints transcript content or key material. `--apply --target-key-id <id>` is required to re-encrypt. Each batch is bounded (default 100, maximum 5,000), transactional, compare-and-update guarded, and decrypted again before commit. A failed batch rolls back as a unit; earlier committed batches remain safe to resume because records already at the target format are skipped.

Migration includes conversation message content, guest UI turn messages, and guest UI turn responses. It preserves property/session/turn identifiers and does not alter sessions, expiry, retention, or authorization state. Historical plaintext conversation cells are encrypted during a rotation. Empty turn responses are not rewritten.

Rollback before key retirement is another explicit rotation. To return to a previous key, target its retained key ID. To return to a pre-key-ring application release, target `legacy`; this restores v1 conversation rows and untagged guest-turn ciphertext before rolling back the application binary. Verify the inventory and a synthetic conversation before the binary rollback. Never remove an old key while any stored record still needs it or before the approved rollback window closes.

## Staged rollout

1. Place the old credential secret and all required key-ring values in the installation's approved secret manager. Distribute IDs and values to every application worker without logging them.
2. Deploy this dual-read application everywhere with the new key in the ring and the intended active key ID. Keep the old credential secret unchanged. New writes now use the active v2 key; old and mixed-key rows remain readable.
3. Take and verify a database backup, record its checksum, and keep the source read-only during rehearsal. Run the inventory command and save only its sanitized JSON result.
4. Rehearse `--apply` against a disposable copy. Review updated counts, rerun inventory, verify zero unreadable records, and read synthetic records across property/session boundaries.
5. For an approved environment, use the same inventory/apply/verify sequence with a bounded batch size and an operator-approved change window. No automatic rotation runs at application startup.
6. Retain the old key in the key ring and off-host escrow through the recovery window. Retire a key only after inventory proves no ciphertext depends on it, backup restore proves key retrieval, and the change owner approves retirement.

If workers are not all on a dual-read release, do not begin re-encryption. The previous application cannot read v2 ciphertext; rollback requires converting records back to legacy formats first.

## Failure behavior and audit trail

The tool refuses to create a missing SQLite database. Production apply requires both `--apply` and the additional `--allow-production` confirmation. Logs contain batch number, row count, and key ID only. A decryption failure stops before the first write; a database write/verification failure rolls back the active batch. Do not suppress either error. Re-run the read-only inventory, restore access to the missing key if needed, then resume or roll back with an explicitly selected retained key.

The automated tests use disposable SQLite databases and synthetic text. They do not perform production key rotation or prove access to a real external secret manager.
