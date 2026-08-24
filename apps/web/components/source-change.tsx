import { exampleSource } from "../fixtures/example-workspace";

export default function SourceChange() {
  return <section className="source-change" aria-labelledby="source-heading">
    <div className="section-heading"><div><span className="eyebrow">01 / Source change · example</span><h2 id="source-heading">A narrower permission.</h2></div><span className="outline-label">REPLACEMENT + INSERTION</span></div>
    <div className="source-meta mono"><span>export-guide / r1 → r2</span><span>Observed: 01 Nov 2026, 09:00 UTC</span><span>Effective: 01 Nov 2026, 00:00 UTC</span></div>
    <div className="diff-grid">
      <article className="passage before-passage"><div className="passage-top"><span className="mono">− BEFORE / r1</span><span>Historical passage</span></div>
        <p>Bulk export is available to <del>all paid plans</del>. Exports are delivered as CSV files. Workspace owners can export the entire archive from Settings → Data.</p><span className="passage-note">− Removed: “all paid plans”</span>
      </article>
      <article className="passage after-passage"><div className="passage-top"><span className="mono">+ AFTER / r2</span><span>Current example revision</span></div>
        <p>Bulk export is available to <ins>Pro and Enterprise plans</ins>. Exports are delivered as CSV files. Workspace owners can export the entire archive from Settings → Data.</p>
        <p className="insertion"><span className="mono">+ INSERTED</span> Starter workspaces can still download individual records; this does not include an archive-wide export.</p>
      </article>
    </div>
    <p className="source-footnote">Source: {exampleSource.id} · Authority tier 2 · A changed passage is a reason to inspect an answer, not a verdict.</p>
  </section>;
}
