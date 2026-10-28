"""Grounded answering, citation checks, and snapshot-scoped reassessment."""

from __future__ import annotations

import base64
import binascii
import re
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from aftermath.application.corpus import CorpusService
from aftermath.core.answers import (
    AnswerAsk,
    GroundedAnswer,
    ProviderAnswer,
    RetrievedPassage,
    SourceUpload,
    UploadedSource,
    ValidatedCitation,
)
from aftermath.core.changes import PassageVersion, norm_v1_text
from aftermath.core.citations import validate_citations
from aftermath.core.contracts import ScopeKind, Usage
from aftermath.core.corpus import (
    Delivery,
    ResolveRequest,
    RevisionInput,
    Snapshot,
    Version,
    resolve_effective,
)
from aftermath.core.demo_fallback import (
    DEMO_DOCUMENT_IDS,
    canned_answer,
    canned_verdict,
    is_demo_document,
    is_rate_limited,
)
from aftermath.core.errors import DomainError, InvalidEncodingError
from aftermath.core.retrieval import Bm25Index
from aftermath.core.review import (
    ALGORITHM_VERSION,
    EXPLANATION,
    POLICY_VERSION,
    ActivityDetail,
    ActivityIndex,
    AnswerPreview,
    ArchivedAnswer,
    ArchivedCitation,
    ArchivedClaim,
    AssessmentRecord,
    ClaimVerdict,
    PassageChange,
    SourceChangeView,
    changed_passage_ids,
    changes_for_answer,
    overall_status,
    select_candidates,
)
from aftermath.core.text import canonical_text
from aftermath.ports.archive import AnswerArchive
from aftermath.ports.corpus import CorpusStore
from aftermath.ports.interfaces import AnswerProvider

RETRIEVE_K = 8
NOT_FOUND_TEXT = "The documents don't cover that."
PREVIEW_CHARS = 800
NAME = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")
STEM = re.compile(r"[^a-z0-9_-]+")


def retrieve_passages(
    question: str, passages: list[RetrievedPassage], k: int = RETRIEVE_K
) -> list[RetrievedPassage]:
    index = Bm25Index([(item.passage_version_id, item.text) for item in passages])
    by_id = {item.passage_version_id: item for item in passages}
    hits = index.search(question, k)
    ranked: list[RetrievedPassage] = []
    for hit in hits:
        item = by_id[hit.item_id]
        ranked.append(item.model_copy(update={"score": hit.score}))
    return ranked


def _not_found_result(
    question: str,
    snapshot_id: str,
    retrieved: list[RetrievedPassage],
    model_id: str,
    prompt_version: str,
    usage: Usage,
    source: str,
    text: str,
) -> GroundedAnswer:
    recorded: Literal["LIVE", "DEMO_FALLBACK"] = (
        "DEMO_FALLBACK" if source == "DEMO_FALLBACK" else "LIVE"
    )
    return GroundedAnswer(
        status="ANSWERED",
        answer_type="not_found",
        question=question,
        snapshot_id=snapshot_id,
        answer_text=text,
        citations=(),
        retrieved=tuple(retrieved),
        model_id=model_id,
        prompt_version=prompt_version,
        usage=usage,
        answer_source=recorded,
    )


def ground_answer(
    question: str,
    snapshot_id: str,
    workspace_id: UUID,
    corpus_id: str,
    eligible: list[RetrievedPassage],
    provider: AnswerProvider | None,
    force_fallback: bool = False,
) -> GroundedAnswer:
    retrieved = retrieve_passages(question, eligible)
    eligible_map = {item.passage_version_id: item for item in eligible}
    if not retrieved and not force_fallback:
        if provider is None:
            raise DomainError(
                "PROVIDER_NOT_CONFIGURED",
                "Gemini is not configured; set AFTERMATH_GEMINI_API_KEY on the backend",
                503,
            )
        return _not_found_result(
            question,
            snapshot_id,
            retrieved,
            provider.model_id,
            provider.prompt_version,
            Usage(),
            "LIVE",
            NOT_FOUND_TEXT,
        )
    generated, source = _generate(question, retrieved, eligible, provider, force_fallback)
    if generated.answer_type == "not_found":
        text = generated.answer_text.strip() or NOT_FOUND_TEXT
        return _not_found_result(
            question,
            snapshot_id,
            retrieved,
            generated.model_id,
            generated.prompt_version,
            generated.usage,
            source,
            text,
        )
    validated = validate_citations(generated.citations, eligible_map, workspace_id, corpus_id)
    if validated is None:
        return GroundedAnswer(
            status="INSUFFICIENT_GROUNDING",
            question=question,
            snapshot_id=snapshot_id,
            answer_text=generated.answer_text or None,
            retrieved=tuple(retrieved),
            returned_citations=generated.citations,
            model_id=generated.model_id,
            prompt_version=generated.prompt_version,
            usage=generated.usage,
            answer_source=source,
            error={
                "code": "INSUFFICIENT_GROUNDING",
                "message": "Citations missed this snapshot or did not match source text",
            },
        )
    return GroundedAnswer(
        status="ANSWERED",
        answer_type="grounded",
        question=question,
        snapshot_id=snapshot_id,
        answer_text=generated.answer_text,
        citations=validated,
        retrieved=tuple(retrieved),
        returned_citations=generated.citations,
        model_id=generated.model_id,
        prompt_version=generated.prompt_version,
        usage=generated.usage,
        answer_source=source,
    )


def _demo_canned(
    question: str, retrieved: list[RetrievedPassage], eligible: list[RetrievedPassage]
) -> ProviderAnswer | None:
    if not is_demo_document(eligible):
        return None
    retrieved_demo = [item for item in retrieved if item.document_id in DEMO_DOCUMENT_IDS]
    eligible_demo = [item for item in eligible if item.document_id in DEMO_DOCUMENT_IDS]
    return canned_answer(question, retrieved_demo or eligible_demo)


def _generate(
    question: str,
    retrieved: list[RetrievedPassage],
    eligible: list[RetrievedPassage],
    provider: AnswerProvider | None,
    force_fallback: bool = False,
) -> tuple[ProviderAnswer, Literal["LIVE", "DEMO_FALLBACK"]]:
    if force_fallback:
        canned = _demo_canned(question, retrieved, eligible)
        if canned is None:
            raise DomainError(
                "PROVIDER_ERROR",
                "Forced demo fallback only applies to the plans document",
                503,
            )
        return canned, "DEMO_FALLBACK"
    if provider is None:
        raise DomainError(
            "PROVIDER_NOT_CONFIGURED",
            "Gemini is not configured; set AFTERMATH_GEMINI_API_KEY on the backend",
            503,
        )
    try:
        return provider.answer(question, retrieved), "LIVE"
    except DomainError as exc:
        limited = exc.code == "PROVIDER_ERROR" and is_rate_limited(exc.message)
        if limited:
            canned = _demo_canned(question, retrieved, eligible)
            if canned is not None:
                return canned, "DEMO_FALLBACK"
        raise


def document_id_from_filename(filename: str | None) -> str:
    if not filename:
        return "upload"
    stem = filename.rsplit("/", 1)[-1].rsplit(".", 1)[0].lower()
    cleaned = STEM.sub("-", stem).strip("-.")[:64]
    return cleaned if NAME.match(cleaned) else "upload"


def source_kind(filename: str | None) -> str:
    if filename is None:
        return "markdown"
    lower = filename.lower()
    if lower.endswith(".md"):
        return "markdown"
    if lower.endswith(".txt"):
        return "text"
    raise DomainError("INVALID_SOURCE_TYPE", "Upload a UTF-8 .txt or .md file, or paste text")


class AnswerService:
    def __init__(
        self,
        store: CorpusStore,
        corpus: CorpusService,
        provider: AnswerProvider | None,
        archive: AnswerArchive,
        max_source_bytes: int = 262144,
        force_fallback: bool = False,
    ) -> None:
        self.store, self.corpus, self.provider = store, corpus, provider
        self.archive = archive
        self.max_source_bytes = max_source_bytes
        self.force_fallback = force_fallback

    def upload(
        self, principal: str, workspace: UUID, corpus: str, body: SourceUpload
    ) -> UploadedSource:
        kind = source_kind(body.filename)
        raw = self._payload_bytes(body)
        if len(raw) > self.max_source_bytes:
            raise DomainError("SOURCE_TOO_LARGE", "Source exceeds configured byte limit", 413)
        try:
            canonical = canonical_text(raw)
        except InvalidEncodingError:
            raise DomainError("INVALID_UTF8", "Source must be strict UTF-8") from None
        if not canonical.strip():
            raise DomainError("EMPTY_SOURCE", "Source text is empty")
        document_id = body.document_id or document_id_from_filename(body.filename)
        current = self.corpus.corpus(principal, workspace, corpus)
        try:
            known = self.corpus.versions(principal, workspace, corpus, document_id, 10000, 0)
        except DomainError as error:
            if error.code != "NOT_FOUND":
                raise
            known = []
        next_seq = max((item.source_seq for item in known), default=0) + 1
        revision_id = f"r{next_seq}"
        stamp = datetime.now(UTC)
        delivery_id = f"upl-{uuid4().hex[:12]}"
        result = self.corpus.ingest(
            principal,
            workspace,
            corpus,
            Delivery(
                delivery_id=delivery_id,
                expected_head=current.head_snapshot_id,
                as_of=stamp,
                documents=(
                    RevisionInput(
                        document_id=document_id,
                        source_revision_id=revision_id,
                        source_seq=next_seq,
                        source_timestamp=stamp,
                        source_type=kind,
                        source_base64=base64.b64encode(raw).decode("ascii"),
                    ),
                ),
            ),
        )
        version: Version | None = None
        passages: tuple[PassageVersion, ...] = ()
        if result.status == "APPLIED":
            self.observe(principal, workspace, corpus, result.delivery_id)
        if result.snapshot_id:
            versions = self.corpus.versions(principal, workspace, corpus, document_id, 10000, 0)
            version = next(
                (item for item in versions if item.source_revision_id == revision_id),
                versions[-1] if versions else None,
            )
            if version is not None:
                with self.store.transaction() as repo:
                    repo.authorize(workspace, principal)
                    passages = tuple(repo.passages(workspace, corpus, version.document_version_id))
        preview = canonical[:PREVIEW_CHARS]
        return UploadedSource(
            document_id=document_id,
            document_version_id=version.document_version_id if version else None,
            source_revision_id=revision_id,
            snapshot_id=result.snapshot_id,
            preview=preview,
            text=canonical,
            passages=passages,
            delivery=result,
        )

    def answer(
        self,
        principal: str,
        workspace: UUID,
        corpus: str,
        body: AnswerAsk,
        previous_answer_id: str | None = None,
    ) -> GroundedAnswer:
        if self.provider is None and not self.force_fallback:
            raise DomainError(
                "PROVIDER_NOT_CONFIGURED",
                "Gemini is not configured; set AFTERMATH_GEMINI_API_KEY on the backend",
                503,
            )
        snapshot, eligible = self._eligible(principal, workspace, corpus, body.snapshot_id)
        result = ground_answer(
            body.question,
            snapshot.snapshot_id,
            workspace,
            corpus,
            eligible,
            self.provider,
            self.force_fallback,
        )
        if result.status != "ANSWERED" or not result.answer_text:
            return result
        saved = self._archive_answer(workspace, corpus, result, previous_answer_id)
        return result.model_copy(update={"answer_id": saved.answer_id})

    def revise(
        self, principal: str, workspace: UUID, corpus: str, answer_id: str
    ) -> GroundedAnswer:
        self.corpus.corpus(principal, workspace, corpus)
        original = next(
            (
                item
                for item in self.archive.answers(workspace, corpus)
                if item.answer_id == answer_id and item.workspace_id == workspace
            ),
            None,
        )
        if original is None:
            raise DomainError("NOT_FOUND", "Archived answer not found", 404)
        return self.answer(
            principal,
            workspace,
            corpus,
            AnswerAsk(question=original.question),
            previous_answer_id=original.answer_id,
        )

    def archived_answers(
        self, principal: str, workspace: UUID, corpus: str
    ) -> list[ArchivedAnswer]:
        self.corpus.corpus(principal, workspace, corpus)
        rows = [
            item
            for item in self.archive.answers(workspace, corpus)
            if item.workspace_id == workspace and item.corpus_id == corpus
        ]
        rows.sort(key=lambda item: item.created_at)
        return rows

    def activities(self, principal: str, workspace: UUID, corpus: str) -> list[ActivityIndex]:
        self.corpus.corpus(principal, workspace, corpus)
        return [
            item
            for item in self.archive.activities(workspace, corpus)
            if item.workspace_id == workspace and item.corpus_id == corpus
        ]

    def activity(
        self, principal: str, workspace: UUID, corpus: str, delivery_id: str
    ) -> ActivityDetail:
        index = next(
            (
                item
                for item in self.activities(principal, workspace, corpus)
                if item.delivery_id == delivery_id
            ),
            None,
        )
        if index is None:
            raise DomainError("NOT_FOUND", "Source update not found", 404)
        spans = self.corpus.change_spans(principal, workspace, corpus, delivery_id, None, 500, 0)
        changes = tuple(
            SourceChangeView(
                document_id=span.document_id,
                old_passage_version_id=span.old_passage_version_id,
                new_passage_version_id=span.new_passage_version_id,
                old_text=span.old_text,
                new_text=span.new_text,
            )
            for span in spans
            if span.old_text != span.new_text
        )
        assessments = {
            item.answer_id: item
            for item in self.archive.assessments(workspace, corpus)
            if item.delivery_id == delivery_id and item.workspace_id == workspace
        }
        previews: list[AnswerPreview] = []
        for answer in self.archive.answers(workspace, corpus):
            if answer.workspace_id != workspace or answer.snapshot_id == index.snapshot_id:
                continue
            assessment = assessments.get(answer.answer_id)
            if assessment is None:
                continue
            previews.append(
                AnswerPreview(
                    answer_id=answer.answer_id,
                    question=answer.question,
                    answer_text=answer.answer_text,
                    snapshot_id=answer.snapshot_id,
                    scope=answer.scope,
                    state="SELECTED" if assessment else "NOT_REASSESSED",
                    selection_reason=assessment.selection_reason if assessment else None,
                    algorithm_version=assessment.algorithm_version if assessment else None,
                    previous_answer_id=answer.previous_answer_id,
                    assessment=assessment,
                    changes=changes_for_answer(answer, changes),
                )
            )
        previews.sort(key=lambda item: (item.state != "SELECTED", item.answer_id))
        return ActivityDetail(
            delivery_id=index.delivery_id,
            document_id=index.document_id,
            parent_snapshot_id=index.parent_snapshot_id,
            snapshot_id=index.snapshot_id,
            selected=index.selected,
            queued=index.queued,
            completed=index.completed,
            changes=changes,
            answers=tuple(previews),
        )

    def observe(
        self, principal: str, workspace: UUID, corpus: str, delivery_id: str
    ) -> ActivityDetail | None:
        event = self.corpus.update_event(principal, workspace, corpus, delivery_id)
        if event.status != "APPLIED" or not event.snapshot_id:
            return None
        with self.store.transaction() as repo:
            repo.authorize(workspace, principal)
            snapshot = repo.snapshot(workspace, corpus, event.snapshot_id)
        if snapshot.parent_snapshot_id is None:
            return None
        if any(
            item.delivery_id == delivery_id for item in self.archive.activities(workspace, corpus)
        ):
            return self.activity(principal, workspace, corpus, delivery_id)
        done = {
            item.answer_id
            for item in self.archive.assessments(workspace, corpus)
            if item.delivery_id == delivery_id
        }
        spans = self.corpus.change_spans(principal, workspace, corpus, delivery_id, None, 500, 0)
        changed = changed_passage_ids(
            [
                PassageChange(span.old_passage_version_id, span.old_text, span.new_text)
                for span in spans
            ]
        )
        prior = [
            item
            for item in self.archive.answers(workspace, corpus)
            if item.workspace_id == workspace and item.snapshot_id != snapshot.snapshot_id
        ]
        picked = select_candidates(prior, changed)
        documents = self.corpus.changed_documents(principal, workspace, corpus, delivery_id)
        if not documents:
            return None
        by_id = {item.answer_id: item for item in prior}
        completed = 0
        for candidate in picked:
            if candidate.answer_id in done:
                completed += 1
                continue
            assessment = self._reassess(
                principal,
                workspace,
                corpus,
                by_id[candidate.answer_id],
                snapshot,
                candidate.reason,
                delivery_id,
            )
            self.archive.add_assessment(assessment)
            completed += 1
        self.archive.add_activity(
            ActivityIndex(
                workspace_id=workspace,
                corpus_id=corpus,
                delivery_id=delivery_id,
                document_id=documents[0].document_id,
                parent_snapshot_id=snapshot.parent_snapshot_id,
                snapshot_id=snapshot.snapshot_id,
                selected=len(picked),
                queued=len(picked) - completed,
                completed=completed,
            )
        )
        return self.activity(principal, workspace, corpus, delivery_id)

    def _archive_answer(
        self,
        workspace: UUID,
        corpus: str,
        result: GroundedAnswer,
        previous_answer_id: str | None,
    ) -> ArchivedAnswer:
        answer_id = f"ans-{uuid4().hex[:16]}"
        text = result.answer_text or ""
        record = ArchivedAnswer(
            answer_id=answer_id,
            workspace_id=workspace,
            corpus_id=corpus,
            question=result.question,
            answer_text=text,
            snapshot_id=result.snapshot_id,
            scope="ROLLING_CURRENT",
            claims=build_claims(answer_id, text, result.citations),
            model_id=result.model_id,
            prompt_version=result.prompt_version,
            answer_source=result.answer_source,
            answer_type=result.answer_type,
            previous_answer_id=previous_answer_id,
            created_at=datetime.now(UTC),
        )
        self.archive.add_answer(record)
        return record

    def _reassess(
        self,
        principal: str,
        workspace: UUID,
        corpus: str,
        answer: ArchivedAnswer,
        snapshot: Snapshot,
        reason: str,
        delivery_id: str,
    ) -> AssessmentRecord:
        _, passages = self._eligible(
            principal, workspace, corpus, snapshot.snapshot_id, answer.scope, answer.evaluation_time
        )
        verdicts: list[ClaimVerdict] = []
        sources: list[str] = []
        for claim in answer.claims:
            verdict, claim_source = self._judge(claim, passages, workspace, corpus)
            verdicts.append(verdict)
            sources.append(claim_source)
        answer_source: Literal["LIVE", "DEMO_FALLBACK", "NONE"] = "NONE"
        if "DEMO_FALLBACK" in sources:
            answer_source = "DEMO_FALLBACK"
        elif "LIVE" in sources:
            answer_source = "LIVE"
        model_id = "demo-fallback" if answer_source == "DEMO_FALLBACK" else "unknown"
        prompt = "demo-fallback-v1" if answer_source == "DEMO_FALLBACK" else "unknown"
        if answer_source == "LIVE" and self.provider is not None:
            model_id, prompt = self.provider.model_id, self.provider.prompt_version
        if answer_source == "DEMO_FALLBACK":
            recorded: Literal["LIVE", "DEMO_FALLBACK", "NONE"] = "DEMO_FALLBACK"
        elif answer_source == "LIVE":
            recorded = "LIVE"
        else:
            recorded = "NONE"
        return AssessmentRecord(
            assessment_id=f"asmt-{uuid4().hex[:12]}",
            answer_id=answer.answer_id,
            workspace_id=workspace,
            corpus_id=corpus,
            delivery_id=delivery_id,
            parent_snapshot_id=snapshot.parent_snapshot_id,
            snapshot_id=snapshot.snapshot_id,
            scope=answer.scope,
            policy_version=POLICY_VERSION,
            model_id=model_id,
            prompt_version=prompt,
            algorithm_version=ALGORITHM_VERSION,
            selection_reason=reason,
            semantic_status=overall_status(verdicts),
            answer_source=recorded,
            claims=tuple(verdicts),
        )

    def _judge(
        self,
        claim: ArchivedClaim,
        passages: list[RetrievedPassage],
        workspace: UUID,
        corpus: str,
    ) -> tuple[ClaimVerdict, str]:
        if self.force_fallback:
            return _canned_claim(claim, passages)
        if self.provider is None:
            return _claim_verdict(claim, "PROVIDER_ERROR", (), "NONE"), "NONE"
        question = (
            "Judge whether this archived claim still holds. "
            f"Claim: {claim.text} "
            "Begin the answer with exactly one of SUPPORTED, CONTRADICTED, "
            "INSUFFICIENT_SUPPORT, or UNRESOLVED_CONFLICT, and cite one exact quote."
        )
        try:
            generated = self.provider.answer(question, retrieve_passages(claim.text, passages))
        except DomainError as exc:
            limited = exc.code == "PROVIDER_ERROR" and is_rate_limited(exc.message)
            if limited:
                return _canned_claim(claim, passages)
            return _claim_verdict(claim, "PROVIDER_ERROR", (), "NONE"), "NONE"
        mapping = {item.passage_version_id: item for item in passages}
        validated = validate_citations(generated.citations, mapping, workspace, corpus)
        stance = _stance(generated.answer_text)
        fresh = tuple(_from_validated(item) for item in validated) if validated else ()
        if stance in {"SUPPORTED", "CONTRADICTED"} and fresh:
            return _claim_verdict(claim, stance, fresh, "LIVE"), "LIVE"
        if stance == "UNRESOLVED_CONFLICT":
            return _claim_verdict(claim, stance, fresh, "LIVE"), "LIVE"
        if stance == "INSUFFICIENT_SUPPORT":
            return _claim_verdict(claim, stance, (), "LIVE"), "LIVE"
        return _claim_verdict(claim, "INSUFFICIENT_SUPPORT", (), "LIVE"), "LIVE"

    def _eligible(
        self,
        principal: str,
        workspace: UUID,
        corpus: str,
        snapshot_id: str | None,
        scope: str = "ROLLING_CURRENT",
        evaluation_time: datetime | None = None,
    ) -> tuple[Snapshot, list[RetrievedPassage]]:
        with self.store.transaction() as repo:
            repo.authorize(workspace, principal)
            current = repo.corpus(workspace, corpus)
            target = snapshot_id or current.head_snapshot_id
            if not target:
                raise DomainError("NO_SNAPSHOT", "Ingest a source before asking a question", 404)
            snapshot = repo.snapshot(workspace, corpus, target)
            documents = repo.documents(workspace, corpus, 100, 0)
            if scope == "FIXED_TIME" and evaluation_time is not None:
                request = ResolveRequest(
                    snapshot_id=snapshot.snapshot_id,
                    scope=ScopeKind.FIXED_TIME,
                    fixed_time=evaluation_time,
                )
            else:
                request = ResolveRequest(snapshot_id=snapshot.snapshot_id)
            eligible: list[RetrievedPassage] = []
            for document in documents:
                versions = repo.versions(workspace, corpus, document.document_id)
                resolved = self._resolve(versions, snapshot, request)
                if not resolved:
                    continue
                for passage in repo.passages(workspace, corpus, resolved.document_version_id):
                    if (
                        passage.workspace_id != workspace
                        or passage.corpus_id != corpus
                        or not passage.text.strip()
                    ):
                        continue
                    eligible.append(
                        RetrievedPassage(
                            workspace_id=passage.workspace_id,
                            corpus_id=passage.corpus_id,
                            document_id=passage.document_id,
                            document_version_id=passage.document_version_id,
                            passage_version_id=passage.passage_version_id,
                            start=passage.start,
                            end=passage.end,
                            text=passage.text,
                        )
                    )
            return snapshot, eligible

    def _resolve(
        self, versions: list[Version], snapshot: Snapshot, request: ResolveRequest
    ) -> Version | None:
        result = resolve_effective(versions, snapshot, request)
        if not result.active or result.version is None:
            return None
        if (
            result.version.workspace_id != snapshot.workspace_id
            or result.version.corpus_id != snapshot.corpus_id
        ):
            return None
        return result.version

    def _payload_bytes(self, body: SourceUpload) -> bytes:
        if body.source_base64 is not None and body.text is not None:
            raise DomainError("INVALID_INPUT", "Provide either pasted text or encoded bytes")
        if body.source_base64 is not None:
            try:
                return base64.b64decode(body.source_base64, validate=True)
            except (ValueError, binascii.Error):
                raise DomainError("INVALID_BASE64", "Source bytes must be base64 encoded") from None
        if body.text is not None:
            return body.text.encode("utf-8")
        raise DomainError("EMPTY_SOURCE", "Paste text or upload a UTF-8 .txt or .md file")


def build_claims(
    answer_id: str, text: str, citations: tuple[ValidatedCitation, ...]
) -> tuple[ArchivedClaim, ...]:
    spans = [
        (match.start(), match.end())
        for match in re.finditer(r"\S.*?(?:[.!?](?=\s|$)|$)", text, flags=re.S)
    ]
    if not spans and text:
        spans = [(0, len(text))]
    buckets: list[list[ValidatedCitation]] = [[] for _ in spans]
    for citation in citations:
        if not spans:
            break
        best = max(
            range(len(spans)),
            key=lambda index: _overlap(text[spans[index][0] : spans[index][1]], citation.quote),
        )
        buckets[best].append(citation)
    claims: list[ArchivedClaim] = []
    for number, ((start, end), attached) in enumerate(zip(spans, buckets, strict=True), start=1):
        claims.append(
            ArchivedClaim(
                claim_id=f"{answer_id}-c{number:02d}",
                text=text[start:end],
                start=start,
                end=end,
                citations=tuple(_from_validated(item) for item in attached),
            )
        )
    return tuple(claims)


def _overlap(sentence: str, quote: str) -> int:
    return len(set(norm_v1_text(sentence).split()) & set(norm_v1_text(quote).split()))


def _from_validated(item: ValidatedCitation) -> ArchivedCitation:
    return ArchivedCitation(
        passage_version_id=item.passage_version_id,
        document_id=item.document_id,
        document_version_id=item.document_version_id,
        quote=item.quote,
        start=item.start,
        end=item.end,
    )


def _canned_claim(
    claim: ArchivedClaim, passages: list[RetrievedPassage]
) -> tuple[ClaimVerdict, str]:
    canned = canned_verdict(claim.text, passages)
    if canned is None:
        return _claim_verdict(claim, "PROVIDER_ERROR", (), "NONE"), "NONE"
    status, passage = canned
    evidence = (
        ArchivedCitation(
            passage_version_id=passage.passage_version_id,
            document_id=passage.document_id,
            document_version_id=passage.document_version_id,
            quote=passage.text,
            start=passage.start,
            end=passage.end,
        ),
    )
    return _claim_verdict(claim, status, evidence, "DEMO_FALLBACK"), "DEMO_FALLBACK"


def _claim_verdict(
    claim: ArchivedClaim,
    status: str,
    evidence: tuple[ArchivedCitation, ...],
    source: str,
) -> ClaimVerdict:
    if status == "SUPPORTED":
        recorded = "SUPPORTED"
    elif status == "CONTRADICTED":
        recorded = "CONTRADICTED"
    elif status == "INSUFFICIENT_SUPPORT":
        recorded = "INSUFFICIENT_SUPPORT"
    elif status == "UNRESOLVED_CONFLICT":
        recorded = "UNRESOLVED_CONFLICT"
    else:
        recorded = "PROVIDER_ERROR"
    if source == "DEMO_FALLBACK":
        origin = "DEMO_FALLBACK"
    elif source == "LIVE":
        origin = "LIVE"
    else:
        origin = "NONE"
    return ClaimVerdict(
        claim_id=claim.claim_id,
        claim_text=claim.text,
        status=recorded,
        explanation=EXPLANATION[recorded],
        old_evidence=claim.citations,
        new_evidence=evidence,
        answer_source=origin,
    )


def _stance(text: str) -> str | None:
    for item in re.findall(r"[A-Z_]+", text.upper()):
        if not isinstance(item, str):
            continue
        if item in {"SUPPORTED", "CONTRADICTED", "INSUFFICIENT_SUPPORT", "UNRESOLVED_CONFLICT"}:
            return item
        if item == "CONTRADICTS":
            return "CONTRADICTED"
        if item == "SUPPORTS":
            return "SUPPORTED"
    return None
