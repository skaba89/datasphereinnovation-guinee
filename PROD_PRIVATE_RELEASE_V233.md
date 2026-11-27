# Private production release — staged gate

Phase 1: verify a distinct Ed25519 private release signature with an independently pinned authority, exact commit/image/config/evidence digests, unique nonce, scope and at most one hour of validity. A PASS authenticates the claim only. It does not authorize startup. Existing server and Compose stops stay unchanged.

Remaining mandatory before first private startup: independent host measurements and trust provisioning, durable nonce consumption (including rejection of reissued nonce), runtime binding to immutable image and actual configuration, private volume initialization, named-account activation workflow, scanner roundtrip, authenticated backup and rollback rehearsal. No public route or DNS change. No REC data or key reuse. The first private instance must not ingest customer data until backup/restore and security gates are satisfied.

Rollback for this preparatory code: revert the PR, never remove any volume or alter REC. For eventual private runtime rollback: stop only dsig-prod app after preserving evidence and backup; restore only to an isolated target first. No deployment command is authorized by this change.