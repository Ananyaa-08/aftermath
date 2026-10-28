# Immutable corpus and temporal storage

Step 2B implements storage, deterministic source comparison, and temporal applicability comparison. It does not discover affected answers, retrieve evidence, judge claims, or produce semantic verdicts.

## Canonical text and objects

`canon-v1` strictly decodes UTF-8, removes one leading U+FEFF, converts CRLF and CR to LF, and normalizes to NFC. Canonical spans are half-open Python Unicode code-point offsets. Browser UTF-16 conversion is confined to `api.offsets`; splitting a surrogate pair is rejected. Canonical and original-byte hashes use `sha256:<64 lowercase hex>`.

The development `LocalObjectStore` keeps original bytes below a configured directory using the byte hash as the key. Keys are validated, paths cannot escape the root, symlinks are rejected, complete bytes are atomically linked into place, repeated identical writes are idempotent, and reads recheck the hash. The default directory is outside source packages. A failed database transaction may leave an unreferenced content-addressed blob; this is safe and may be garbage-collected later.

This adapter is not production durable storage and is unsuitable for Vercel's ephemeral filesystem. Supabase Storage remains a future `ObjectStore` adapter. API responses expose hashes and object identities, never local paths.

## Migration chain and records

`0001` creates pgvector, workspaces, and foundational job envelopes. `0002` adds:

- `workspace_members` and `corpora` for server-resolved development membership and scoped corpus heads.
- `documents`, immutable `document_versions`, and `source_objects`.
- immutable `snapshots` and `snapshot_documents` membership.
- `update_events`, append-only `update_event_status_log`, and `delivery_attempts`.

`0003` adds immutable `passage_versions`, `passage_lineage_edges`, edge members, `snapshot_changes`, `change_spans`, and `applicability_changes`. `0004_step2b_repair` adds scoped applicability document/version references and distinct immutable `timeline_alignment_edges`, copying legacy temporal comparisons so read models can exclude them from lineage without rewriting immutable rows. `0005_timeline_event_integrity` scopes timeline span references by update event and guards downgrade when native timeline rows exist. New head `0006_span_passage_integrity` audits and binds each old/new passage reference to its stated document version; its downgrade removes only its own constraints. User-run execution verification passed at `0006`, including disposable upgrade, audit-refusal, downgrade/re-upgrade, and readiness paths. See `change-detection.md` for algorithms, IDs, and handling of superseded pre-acceptance feature outputs.

Composite foreign keys carry workspace, corpus, and document identity where applicable so references cannot cross those boundaries. Deterministic IDs are `snap:<six-or-more digits>`, `upd:<delivery-id>`, and `dv:<document-id>@<source-revision-id>`. Revision identity, source sequence, hashes, effective-date provenance, tombstone text, and source-object identity have database checks. Append-only tables reject update and delete. Deferred constraints require an applied delivery for every committed snapshot and forbid adding knowledge or membership to a snapshot after its creation transaction. Corpus heads use a deferred composite foreign key and are advanced with compare-and-swap.

RLS is enabled with no public policies. The local database owner bypasses RLS, so deployment still requires a restricted runtime role, JWT validation, workspace-aware policies, and real membership authorization.

## Atomic deliveries

The application locks the corpus, validates the complete delivery, and plans segmentation, alignment, spans, and timeline changes before persistent database mutation. Original blobs are written immediately before one PostgreSQL transaction; versions, passages, lineage, changes, snapshot membership, head advance, and `APPLIED` commit together. Algorithm or database failure leaves no partial Step 2B rows and records `FAILED_APPLY` separately when safe.

Outcomes remain distinct:

- identical applied delivery ID and payload: duplicate response, no snapshot;
- reused delivery ID with different payload: `IDEMPOTENCY_CONFLICT`;
- identical known revision identity: no duplicate version;
- known revision identity with changed immutable data: `REVISION_CONFLICT`;
- new revision ID with unchanged text: a new immutable version and snapshot;
- unknown sequence at or below the latest observed sequence: whole delivery `PARKED_OUT_OF_ORDER`;
- stale expected head: compare-and-swap failure and no partial apply;
- mixed-effective input: `MIXED_EFFECTIVE`;
- unsupported withdrawal: `CANCELLATION_UNSUPPORTED`.

## Temporal resolver

The resolver first excludes versions whose `known_at_seq` is later than the named snapshot. For time scopes, it selects the greatest `effective_from` not after evaluation time and breaks ties by greatest `source_seq`. A future-effective revision therefore does not hide the current one. A selected tombstone returns no active evidence. Derived `effective_to` comes from the versions known at that snapshot and is never stored as permanent truth.

`ROLLING_CURRENT` uses the supplied evaluation time or snapshot logical time. `FIXED_TIME` requires an explicit UTC time. `FIXED_VERSION` selects one named immutable version and refuses a version unknown to the snapshot. The evidence fingerprint includes snapshot, scope, version/content identity, source type, authority metadata, provenance, applicability identity and derived end; authority-only changes can therefore change the fingerprint even when text does not.

## Real API

Implemented routes under `/api/v1` are workspace list/create/read; corpus list/create/read; delivery ingestion; snapshot and document lists; document read; version history; and `POST .../documents/{document_id}/resolve`. Lists require bounded `limit` and `offset`. Requests have a 1 MiB ASGI limit, individual source bytes default to 256 KiB, deliveries allow 1–32 documents, and a corpus defaults to 2,000 versions.

The development identity is configured server-side with `AFTERMATH_DEV_IDENTITY`; request headers cannot choose it. Every operation resolves membership before scoped access. Production rejects the development identity and data routes return `AUTH_UNAVAILABLE` until production authentication exists.

Step 3 remains responsible for affected-answer discovery, retrieval, semantic verification, policy verdicts, queues, and models.
