"use client";
import {useEffect, useRef, useState, type FormEvent, type KeyboardEvent} from "react";
import {
  storageRequest,
  StorageError,
  type ActivityDetail,
  type ActivityIndex,
  type ArchivedAnswer,
  type ChangedDocumentRecord,
  type DocumentRecord,
  type GroundedAnswer,
  type UpdateEventRecord,
  type UploadedSource,
} from "../lib/storage";
import ChangedAnswers, {type ChangedCard} from "./live-activity";

type Citation = {document_id: string; document_version_id: string; quote: string};
type Turn = {
  id: string;
  at: string;
  kind: "system" | "user" | "assistant";
  text: string;
  answerId?: string;
  answerType?: "grounded" | "not_found";
  source?: "LIVE" | "DEMO_FALLBACK";
  citations?: Citation[];
  model?: string;
  prompt?: string;
  snapshot?: string;
  tokens?: string;
  changedIn?: string;
  updated?: boolean;
  previousId?: string | null;
};
type Failure = {id: string; question: string; note: string};
type Attachment = {name: string; text: string; documentId: string; editable: boolean};

const plain = (error: unknown) => {
  if (!(error instanceof StorageError)) return "That didn't go through. Try again.";
  if (error.code === "PROVIDER_NOT_CONFIGURED") return "The answering model is not configured.";
  if (error.code === "PROVIDER_ERROR") return "The model could not answer just now. Try again.";
  if (error.code === "INVALID_SOURCE_TYPE") return "Upload a .txt or .md file.";
  if (error.code === "EMPTY_SOURCE") return "That file is empty.";
  if (error.code === "NO_SNAPSHOT") return "Add a document before asking.";
  return "That didn't go through. Try again.";
};

function revisionOf(versionId: string) {
  const at = versionId.lastIndexOf("@");
  return at >= 0 ? versionId.slice(at + 1) : "";
}

function chip(citation: Citation) {
  const revision = revisionOf(citation.document_version_id);
  const where = revision ? `${citation.document_id} ${revision}` : citation.document_id;
  return `${where} · ${citation.quote}`;
}

function notFoundCopy(text: string) {
  const body = text.trim() || "Your documents don't mention that, so I can't confirm it.";
  const hint = "If you have an updated document, attach it with the paperclip and ask again.";
  return body.includes("paperclip") ? body : `${body} ${hint}`;
}

function verdictLine(status: string | null | undefined, documentId: string, revision: string) {
  const where = [documentId, revision].filter(Boolean).join(" ");
  if (status === "CONTRADICTED") return `Contradicted by ${where}`;
  if (status === "SUPPORTED") return `Still supported by ${where}`;
  if (status === "INSUFFICIENT_SUPPORT") return `Not enough evidence in ${where}`;
  if (status === "UNRESOLVED_CONFLICT") return `Conflicting evidence in ${where}`;
  if (status === "PROVIDER_ERROR") return "The model failed. This is not a verdict.";
  return "Not yet assessed";
}

function documentStem(filename: string) {
  const stem = filename.replace(/\.[^.]+$/, "").toLowerCase().replace(/[^a-z0-9_.-]+/g, "-");
  const cleaned = stem.replace(/^-+|-+$/g, "").slice(0, 64);
  return /^[a-z0-9]/.test(cleaned) ? cleaned : "upload";
}

function citationsOf(answer: ArchivedAnswer): Citation[] {
  const seen = new Set<string>();
  const rows: Citation[] = [];
  for (const claim of answer.claims ?? []) {
    for (const citation of claim.citations ?? []) {
      const key = `${citation.passage_version_id}:${citation.quote}`;
      if (seen.has(key)) continue;
      seen.add(key);
      rows.push(citation);
    }
  }
  return rows;
}

export default function LiveAnswer({
  workspace,
  corpus,
  documents,
  head,
  disabled,
  refreshKey,
  onStored,
}: {
  workspace: string;
  corpus: string;
  documents: DocumentRecord[];
  head: string | null;
  disabled: boolean;
  refreshKey: number;
  onStored: () => void;
}) {
  const base = `/${encodeURIComponent(workspace)}/corpora/${encodeURIComponent(corpus)}`;
  const [turns, setTurns] = useState<Turn[]>([]);
  const [cards, setCards] = useState<ChangedCard[]>([]);
  const [failures, setFailures] = useState<Failure[]>([]);
  const [loadError, setLoadError] = useState("");
  const [composerError, setComposerError] = useState("");
  const [draft, setDraft] = useState("");
  const [attachment, setAttachment] = useState<Attachment | null>(null);
  const [menu, setMenu] = useState(false);
  const [panelOpen, setPanelOpen] = useState(false);
  const [highlight, setHighlight] = useState("");
  const [busy, setBusy] = useState(false);
  const [busyId, setBusyId] = useState("");
  const [pending, setPending] = useState("");
  const generation = useRef(0);
  const requestId = useRef(0);
  const fileRef = useRef<HTMLInputElement>(null);
  const paperclipRef = useRef<HTMLButtonElement>(null);
  const firstMenuItem = useRef<HTMLButtonElement>(null);
  const pick = useRef<"new" | string>("new");

  useEffect(() => {
    setDraft("");
    setAttachment(null);
    setFailures([]);
    setComposerError("");
    setHighlight("");
    setMenu(false);
    setPanelOpen(false);
  }, [workspace, corpus]);

  useEffect(() => {
    const gen = ++generation.current;
    if (!workspace || !corpus) {
      setTurns([]);
      setCards([]);
      return;
    }
    let active = true;
    (async () => {
      try {
        const [answers, events, activities] = await Promise.all([
          storageRequest<ArchivedAnswer[]>(`${base}/answers`),
          storageRequest<UpdateEventRecord[]>(`${base}/updates?limit=100`),
          storageRequest<ActivityIndex[]>(`${base}/activity`),
        ]);
        if (!active || gen !== generation.current) return;
        const applied = events.filter(event => event.status === "APPLIED");
        const changed = await Promise.all(applied.map(async event => {
          try {
            const rows = await storageRequest<ChangedDocumentRecord[]>(
              `${base}/updates/${encodeURIComponent(event.delivery_id)}/documents`,
            );
            return {event, rows};
          } catch {
            return {event, rows: [] as ChangedDocumentRecord[]};
          }
        }));
        const details = await Promise.all(
          activities.filter(item => item.selected > 0).map(item =>
            storageRequest<ActivityDetail>(`${base}/activity/${encodeURIComponent(item.delivery_id)}`),
          ),
        );
        if (!active || gen !== generation.current) return;
        const selectedByDelivery = new Map(activities.map(item => [item.delivery_id, item.selected]));
        const revisionByDelivery = new Map<string, string>();
        const notes: Turn[] = [];
        for (const {event, rows} of changed) {
          for (const row of rows) {
            const revision = revisionOf(row.new_version_id);
            revisionByDelivery.set(event.delivery_id, revision);
            const count = selectedByDelivery.get(event.delivery_id) ?? 0;
            const text = row.old_version_id
              ? count > 0
                ? `Updated ${row.document_id} to ${revision} · ${count} answers changed`
                : `Updated ${row.document_id} to ${revision}`
              : `Uploaded ${row.document_id} (${revision || "r1"})`;
            notes.push({id: `sys-${event.delivery_id}-${row.document_id}`, at: event.as_of, kind: "system", text});
          }
        }
        const followup = new Map<string, ArchivedAnswer>();
        for (const answer of answers) {
          if (answer.previous_answer_id) followup.set(answer.previous_answer_id, answer);
        }
        const changedIn = new Map<string, string>();
        const nextCards: ChangedCard[] = [];
        for (const detail of details) {
          const revision = revisionByDelivery.get(detail.delivery_id) ?? "";
          for (const item of detail.answers) {
            if (item.state !== "SELECTED" || !item.assessment) continue;
            changedIn.set(item.answer_id, revision);
            const updated = followup.get(item.answer_id);
            nextCards.push({
              answerId: item.answer_id,
              question: item.question,
              oldAnswer: item.answer_text,
              verdict: verdictLine(item.assessment.semantic_status, detail.document_id, revision),
              diffs: (item.changes ?? []).map(change => ({oldText: change.old_text, newText: change.new_text})),
              snapshotId: item.assessment.snapshot_id,
              updatedText: updated?.answer_text ?? null,
            });
          }
        }
        const messages: Turn[] = [...notes];
        for (const answer of answers) {
          const at = answer.created_at;
          if (!answer.previous_answer_id) {
            messages.push({id: `q-${answer.answer_id}`, at, kind: "user", text: answer.question, answerId: answer.answer_id});
          }
          messages.push({
            id: `a-${answer.answer_id}`,
            at,
            kind: "assistant",
            text: answer.answer_text,
            answerId: answer.answer_id,
            answerType: answer.answer_type ?? "grounded",
            source: answer.answer_source,
            citations: citationsOf(answer),
            model: answer.model_id,
            prompt: answer.prompt_version,
            snapshot: answer.snapshot_id,
            changedIn: changedIn.get(answer.answer_id),
            updated: Boolean(answer.previous_answer_id),
            previousId: answer.previous_answer_id,
          });
        }
        const rank = (turn: Turn) => turn.kind === "system" ? 0 : turn.kind === "user" ? 1 : 2;
        messages.sort((left, right) => left.at.localeCompare(right.at) || rank(left) - rank(right) || left.id.localeCompare(right.id));
        setTurns(messages);
        setCards(nextCards);
        setLoadError("");
      } catch (error) {
        if (!active || gen !== generation.current) return;
        setLoadError(plain(error));
        setTurns([]);
        setCards([]);
      }
    })();
    return () => { active = false; };
  }, [workspace, corpus, base, refreshKey]);

  useEffect(() => {
    if (menu) firstMenuItem.current?.focus();
  }, [menu]);

  function focusTurn(answerId: string) {
    setHighlight(answerId);
    setPanelOpen(false);
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    document.getElementById(`turn-${answerId}`)?.scrollIntoView({behavior: reduced ? "auto" : "smooth", block: "center"});
  }

  async function storeAttachment(current: Attachment) {
    if (!/\.(txt|md)$/i.test(current.name)) throw new StorageError("INVALID_SOURCE_TYPE", "Upload a .txt or .md file.");
    if (!current.text.trim()) throw new StorageError("EMPTY_SOURCE", "That file is empty.");
    return storageRequest<UploadedSource>(`${base}/uploads`, {
      filename: current.name,
      document_id: current.documentId,
      text: current.text,
    });
  }

  async function ask(question: string, snapshot: string | null, gen: number) {
    const result = await storageRequest<GroundedAnswer>(`${base}/answers`, {
      question,
      ...(snapshot ? {snapshot_id: snapshot} : {}),
    });
    if (gen !== generation.current) return "stale" as const;
    if (result.status !== "ANSWERED") {
      setFailures(current => [...current, {
        id: `fail-${crypto.randomUUID()}`,
        question,
        note: "I couldn't verify this answer against your documents. Try rephrasing.",
      }]);
      return "failed" as const;
    }
    setFailures([]);
    return "ok" as const;
  }

  async function submit(question = draft, withAttachment: Attachment | null = attachment) {
    const text = question.trim();
    if (busy || disabled || (!text && !withAttachment)) return;
    const gen = generation.current;
    const request = ++requestId.current;
    const currentAttachment = withAttachment;
    setBusy(true);
    setComposerError("");
    setPending(text || currentAttachment?.name || "");
    try {
      let snapshot = head;
      if (currentAttachment) {
        const uploaded = await storeAttachment(currentAttachment);
        if (gen !== generation.current) return;
        snapshot = uploaded.snapshot_id ?? snapshot;
        setAttachment(null);
      }
      if (text) {
        const outcome = await ask(text, snapshot, gen);
        if (outcome === "stale") return;
      }
      if (gen === generation.current) {
        setDraft("");
        onStored();
      }
    } catch (error) {
      if (gen !== generation.current) return;
      if (text) {
        setFailures(current => [...current, {id: `fail-${crypto.randomUUID()}`, question: text, note: plain(error)}]);
      } else setComposerError(plain(error));
    } finally {
      if (requestId.current === request) {
        setBusy(false);
        setPending("");
      }
    }
  }

  async function generate(answerId: string) {
    const gen = generation.current;
    const request = ++requestId.current;
    setBusyId(answerId);
    setComposerError("");
    try {
      const result = await storageRequest<GroundedAnswer>(
        `${base}/answers/${encodeURIComponent(answerId)}/updates`,
        {},
      );
      if (gen !== generation.current) return;
      if (result.status !== "ANSWERED") {
        setComposerError("I couldn't verify this answer against your documents. Try rephrasing.");
        return;
      }
      onStored();
    } catch (error) {
      if (gen === generation.current) setComposerError(plain(error));
    } finally {
      if (requestId.current === request) setBusyId("");
    }
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void submit();
    }
  }

  function chooseFile(mode: "new" | string) {
    pick.current = mode;
    setMenu(false);
    fileRef.current?.click();
  }

  async function onFile(file: File) {
    const mode = pick.current;
    const text = await file.text();
    setAttachment({
      name: file.name,
      text,
      documentId: mode === "new" ? documentStem(file.name) : mode,
      editable: mode === "new",
    });
    paperclipRef.current?.focus();
  }

  return <div className="chat-shell">
    <div className="chat-main">
      <button type="button" className="changed-drawer-toggle text-button" aria-expanded={panelOpen} onClick={() => setPanelOpen(open => !open)}>
        Changed answers
      </button>
      <div className="chat-thread" role="log" aria-live="polite" aria-relevant="additions">
        {loadError && <div className="chat-failure" role="alert"><p>{loadError}</p><button type="button" className="text-button" onClick={onStored}>Retry</button></div>}
        {turns.map(turn => {
          if (turn.kind === "system") return <p key={turn.id} className="chat-system">{turn.text}</p>;
          if (turn.kind === "user") {
            return <div key={turn.id} id={turn.answerId ? `turn-${turn.answerId}` : undefined} className={highlight === turn.answerId ? "chat-row is-user is-highlight" : "chat-row is-user"}>
              <p className="chat-bubble is-user">{turn.text}</p>
            </div>;
          }
          const copy = turn.answerType === "not_found" ? notFoundCopy(turn.text) : turn.text;
          return <div key={turn.id} className="chat-row is-assistant">
            <div className="chat-bubble is-assistant">
              {turn.updated && <p className="updated-label">Updated answer{turn.previousId && <> · <a href={`#turn-${turn.previousId}`}>Original question</a></>}</p>}
              <p>{copy}</p>
              {!!turn.citations?.length && <ul className="cite-list">{turn.citations.map((citation, index) => <li key={`${citation.document_version_id}-${index}`} className="cite-chip">{chip(citation)}</li>)}</ul>}
              <p className="source-tag">{turn.source === "DEMO_FALLBACK" ? "DEMO FALLBACK" : "LIVE"}{turn.changedIn ? <span className="changed-badge">changed in {turn.changedIn}</span> : null}</p>
              <details className="chat-details">
                <summary>details</summary>
                <p>{[turn.model, turn.prompt, turn.snapshot, turn.tokens].filter(Boolean).join(" · ")}</p>
              </details>
            </div>
          </div>;
        })}
        {failures.map(failure => <div key={failure.id} className="chat-failure" role="alert">
          <p className="chat-bubble is-user">{failure.question}</p>
          <p>{failure.note}</p>
          <button type="button" className="text-button" onClick={() => { setFailures(current => current.filter(item => item.id !== failure.id)); void submit(failure.question, null); }}>Retry</button>
        </div>)}
        {pending && <p className="chat-system">{pending}</p>}
      </div>
      <form className="chat-composer" aria-label="Ask a grounded question" onSubmit={(event: FormEvent) => { event.preventDefault(); void submit(); }}>
        {composerError && <p className="chat-failure" role="alert">{composerError}</p>}
        {attachment && <div className={busy ? "attach-chip is-pending" : "attach-chip"}>
          <span>{attachment.name}</span>
          {attachment.editable && <input aria-label="Document id" value={attachment.documentId} onChange={event => setAttachment({...attachment, documentId: event.target.value})} pattern="[a-z0-9][a-z0-9_.-]*" maxLength={64}/>}
          {busy && <span>Uploading…</span>}
          <button type="button" aria-label={`Remove ${attachment.name}`} onClick={() => setAttachment(null)}>×</button>
        </div>}
        <div className="composer-row">
          <button ref={paperclipRef} type="button" className="paperclip" aria-expanded={menu} aria-haspopup="true" aria-label="Add a document" onClick={() => setMenu(open => !open)}>+</button>
          {menu && <div className="attach-menu" role="menu" onKeyDown={event => {
            if (event.key === "Escape") { setMenu(false); paperclipRef.current?.focus(); }
          }}>
            {documents.length === 0 ? (
              <button ref={firstMenuItem} type="button" role="menuitem" onClick={() => chooseFile("new")}>Upload document</button>
            ) : <>
              {documents.map((document, index) => (
                <button key={document.document_id} ref={index === 0 ? firstMenuItem : undefined} type="button" role="menuitem" onClick={() => chooseFile(document.document_id)}>
                  Update {document.document_id}
                </button>
              ))}
              <button type="button" role="menuitem" onClick={() => chooseFile("new")}>Upload new document</button>
            </>}
          </div>}
          <input ref={fileRef} className="file-hidden" tabIndex={-1} type="file" accept=".txt,.md,text/plain,text/markdown" aria-hidden="true" onChange={event => {
            const file = event.currentTarget.files?.[0];
            event.currentTarget.value = "";
            if (file) void onFile(file);
          }}/>
          <textarea value={draft} onChange={event => setDraft(event.target.value)} onKeyDown={onKeyDown} rows={1} maxLength={4000} placeholder="Ask about your documents" disabled={disabled}/>
          <button type="submit" className="solid-button" disabled={busy || disabled || (!draft.trim() && !attachment)}>Send</button>
        </div>
      </form>
    </div>
    <ChangedAnswers cards={cards} open={panelOpen} busyId={busyId} onClose={() => setPanelOpen(false)} onSelect={focusTurn} onGenerate={answerId => void generate(answerId)}/>
  </div>;
}
