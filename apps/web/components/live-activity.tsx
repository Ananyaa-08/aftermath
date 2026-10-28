"use client";

export type ChangedCard = {
  answerId: string;
  question: string;
  oldAnswer: string;
  verdict: string;
  diffs: {oldText: string | null; newText: string | null}[];
  snapshotId: string;
  updatedText: string | null;
};

export default function ChangedAnswers({
  cards,
  open,
  busyId,
  onClose,
  onSelect,
  onGenerate,
}: {
  cards: ChangedCard[];
  open: boolean;
  busyId: string;
  onClose: () => void;
  onSelect: (answerId: string) => void;
  onGenerate: (answerId: string) => void;
}) {
  return (
    <aside className={open ? "changed-panel is-open" : "changed-panel"} aria-label="Changed answers">
      <div className="changed-panel-head">
        <h2>Changed answers</h2>
        <button type="button" className="changed-close text-button" onClick={onClose}>Close</button>
      </div>
      {!cards.length && (
        <p className="chat-muted">
          Answers you asked will appear here if a later document update changes their evidence.
        </p>
      )}
      <div className="changed-list">
        {cards.map(card => (
          <article key={card.answerId} className="changed-card">
            <button type="button" className="card-jump" onClick={() => onSelect(card.answerId)}>
              {card.question}
            </button>
            <p className="struck">{card.oldAnswer}</p>
            <p className="verdict-line">{card.verdict}</p>
            {card.diffs.map((diff, index) => (
              <div key={`${card.answerId}-${index}`} className="evidence-diff">
                <p><span className="diff-label">Was</span> <span className="struck">{diff.oldText}</span></p>
                <p><span className="diff-label">Now</span> {diff.newText}</p>
              </div>
            ))}
            {card.updatedText ? (
              <p className="updated-inline"><span className="diff-label">Updated answer</span> {card.updatedText}</p>
            ) : (
              <button
                type="button"
                className="text-button"
                disabled={busyId === card.answerId}
                onClick={() => onGenerate(card.answerId)}
              >
                {busyId === card.answerId ? "Generating…" : "Generate updated answer"}
              </button>
            )}
            <details className="chat-details">
              <summary>details</summary>
              <p>{card.snapshotId}</p>
            </details>
          </article>
        ))}
      </div>
    </aside>
  );
}
