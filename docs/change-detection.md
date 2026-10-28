# Deterministic source-change detection

Step 2B describes source state only. **A detected source change is not a confirmed affected answer and is not a semantic verdict.**

## Text and passage identity

`seg-v1` scans canonical text line-by-line. Markdown headings update a six-level section path and are not passages. Blank lines end paragraphs; consecutive content lines remain one exact canonical slice. Paragraphs over 1,200 code points are greedily chunked at `sentences-v1` punctuation boundaries where possible; one oversized sentence remains whole. Empty documents have no passages.

Passage versions use `pv:<document>@<revision>#p<ordinal>` and retain document-version ownership, code-point offsets, exact text, section path, exact hash, `norm-v1` hash, and segmentation version. Lineage uses `lin:<document>:<first-revision>:p<ordinal>` and represents conceptual continuity rather than immutable passage identity.

`norm-v1` is a derived matching view: whole-string Unicode NFKC, whole-result case-fold, whitespace collapse, and outer trim. It is never canonical storage. Its text is exactly `unicodedata.normalize("NFKC", source).casefold()` before whitespace handling. Matching helpers preserve canonical-source provenance through composition, expansion, compatibility collapse, and whitespace collapse, then map complete normalized units back to canonical code-point ranges. This is not a character-for-character inverse: a normalized character may deliberately map to the complete source range that produced its normalization unit, and a partial expanded unit is not a valid recoverable span.

## `diff-v1`

The deterministic alignment order is exact content, normalized content, Dice-modified pairs, two/three-passage merges and splits, then leftovers. Exact matches prefer the same ordinal and become `IDENTICAL` or `MOVED`. Normalized matches become `REFORMATTED`. `dice-v1` tokenizes normalized text with Unicode `\w+` and compares token multisets.

Defaults are modification `0.50`, high confidence `0.70`, ambiguity margin `0.05`, and merge/split containment `0.80`. Candidate order is descending score, old ordinal, new ordinal, then stable identity. Every old and new passage must occur in exactly one primary edge; an inconsistency raises `AlignmentError` and rolls back the delivery.

`MODIFIED` edges use `difflib.SequenceMatcher` over `\S+` tokens and persist non-equal canonical slices. Merge/split spans cover complete passage ranges. Added, deleted, moved, and reformatted edges retain audit spans. Whole-document creation/deletion uses `DOCUMENT_ADDED`/`DOCUMENT_DELETED`.

`features-v1` evaluates each exact local slice in its smallest containing sentence within the passage. Boundaries follow specification `sentences-v1`: `.`, `!`, or `?` followed by whitespace and an ASCII uppercase letter, digit, opening quote, or bracket. Passage endpoints are fallback boundaries; separator whitespace is excluded. A span crossing a boundary receives the union of touched sentences. Unicode punctuation that does not satisfy this rule does not introduce an inferred boundary. All offsets count canonical Python code points.

An empty opcode inside two existing passages is distinct from an absent passage. Its exact local text and offsets remain null, but its feature context comes from the opcode boundary: use the following unchanged token when it belongs to the nonempty side's sentence, otherwise the preceding sentence, clamped at passage endpoints. This compares the corresponding sentences without treating unchanged negators, numbers, dates, or qualifiers as newly added/deleted. True passage/document addition or deletion retains an absent context on the missing side. `metadata.feature_evidence` records local and contextual results, context offsets/text, the zero-length opcode boundary and affinity, and the context passage identity separately from the local span.

Features record numeric multisets, dates, token/phrase-boundary negator-count changes, and token/phrase-boundary qualifier sets. Multi-token phrases remain atomic features and `n't` suffix contractions (including normalized curly apostrophes) are intentional negators. Features never decide answer impact or truth.

### Feature version and existing local data

Specification v1.1.1 section 8.3 defines slices plus containing-sentence features; section 8.2 C2 defines `sentences-v1`. It does not define a persisted `feature_version` field or a feature-version increment policy. `features-v1` was introduced by the pre-acceptance repair, and Step 2B has not yet passed independent re-review. This correction therefore retains that label and stamps new contextual evidence with `implementation: features-v1-symmetric-context-2026-11-04`. This is an explicit pre-acceptance implementation decision, not a specification-defined algorithm-version exemption.

Old immutable feature records remain exactly as stored and are returned without recomputation. `features-v1` alone must not be interpreted as proof of corrected context: contextual records lacking the new implementation marker are superseded pre-acceptance outputs and must be excluded from acceptance/research comparisons. Migration `0006` changes referential constraints only and cannot repair those historical feature values. Verification uses new, uniquely named disposable corpora; replaying an old delivery preserves its original output. No old workspace is deleted, no row is relabeled, and no in-place feature backfill is authorized. If historical recomputation becomes necessary, it requires a separately specified append-only algorithm-run identity and repair workflow.

Low-confidence sections and sections with unmatched material on both sides receive additional `EXPANDED_UNCERTAIN` coverage. If more than half of passage sides are low-confidence or unmatched, expansion covers the document. Precise spans remain intact.

## Latest observed versus effective time

The latest-observed comparison uses the newest version known to the parent snapshot. Re-addition uses the last non-tombstone observed source for text comparison. This is distinct from the version effective at any time and from exact fixed-version selection.

`timeline-v1` splits both parent and result knowledge at every known `effective_from`, uses the Step 2A greatest-effective-date/greatest-source-sequence resolver, and compares effective-evidence fingerprints. Fingerprints include content, source type, and authority metadata; revision ID alone does not create a change. Adjacent equivalent changed intervals merge.

If an interval compares the same pair as the latest-observed diff, applicability attaches to those spans and records reuse. A different pair runs the same deterministic comparison with `TIMELINE` origin and persists its alignment in `timeline_alignment_edges`, never as passage lineage. AS-24 therefore has only the identical r2→r3 latest-observed lineage edge, one changed interval from 1 April to 1 December, and a separately typed r1→r3 timeline alignment with a numeric span from `12` to `15`.

Same-date higher-sequence revisions supersede earlier observations. A revision effective earlier than a scheduled revision does not cancel the later schedule. Withdrawal without replacement remains explicitly unsupported.

## Persistence, transaction, and bounds

Migration `0003` adds `passage_versions`, `passage_lineage_edges`, `passage_lineage_edge_members`, `snapshot_changes`, `change_spans`, and `applicability_changes`. Migration `0004_step2b_repair` adds fully scoped document/version foreign keys for applicability records and copies legacy timeline-only alignments into append-only `timeline_alignment_edges` and `timeline_alignment_edge_members`; immutable legacy rows remain stored but read APIs exclude copied temporal edges from lineage. Migration `0005_timeline_event_integrity` adds the update event to the change-span → timeline-alignment foreign key and enforces native-versus-reclassified recording shape. Its downgrade refuses before schema changes when native `timeline-v1` rows exist; databases with no timeline rows or only reconstructible `0004` legacy copies can downgrade. Rows are workspace/corpus/document scoped and append-only. Versions, passages, lineage, timeline alignments, spans, applicability, snapshot membership, head compare-and-swap, and successful event status commit in one transaction.

Defaults: 32 documents/delivery, 256 KiB/source, 1 MiB request, 500 passages/document, 100,000 code points/passage, 20,000 alignment pairs, 1,000 timeline breakpoints, 2,000 corpus versions, and 100 returned spans/page. Exceeding a persistence bound rejects the complete delivery; it never silently truncates a stored change set.

Migration `0006_span_passage_integrity` is the new head. It audits old and new span passage/version mismatches before schema changes and fails with bounded category/count diagnostics. Composite FKs `change_span_old_passage_version_fk` and `change_span_new_passage_version_fk` reference `passage_document_version_uq` in exact `(workspace_id, corpus_id, document_id, document_version_id, passage_version_id)` order. Companion checks require a document version whenever a passage is present. Null passages remain valid for absent/local-empty sides and authority-only records. Upgrade never rewrites immutable spans; downgrade removes only the four `0006` constraints, preserving native timeline data and all pre-existing constraints. User-run PostgreSQL-backed verification passed the full suite with zero skips on 4 November 2026.

## Read APIs

Under `/api/v1/workspaces/{workspace}/corpora/{corpus}`:

- `GET /updates` and `/updates/{delivery}`
- `GET /updates/{delivery}/documents`
- `GET /updates/{delivery}/documents/{document}/comparison` (lineage in `edges`, timeline in `timeline_alignments`)
- `GET /updates/{delivery}/lineage`
- `GET /updates/{delivery}/spans`
- `GET /updates/{delivery}/applicability`
- `GET /documents/{document}/timeline?snapshot_id=...`
- `POST /documents/{document}/timeline/compare`

Responses expose alignment confidence only; they contain no model confidence, affected-answer claim, or verdict.

There is no standalone public timeline-alignment endpoint. The document comparison already returns the interval-bound alignments needed by the current live inspector, with their spans and applicability records in one bounded response. Adding an independently paginated route has no current specification or workflow justification.
