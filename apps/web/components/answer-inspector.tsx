"use client";
import { useId, useMemo, useState } from "react";
import type { ExampleAnswer, ExampleWorkspace, SemanticStatus } from "../lib/workspace";
import { currentVerdict, filterAnswers, verdictLabel, workflowStates } from "../lib/workspace";

export function Status({ status }: { status: SemanticStatus | null }) {
  return <span className={`semantic-label ${status ? `semantic-${status.toLowerCase()}` : "semantic-none"}`}><span aria-hidden="true">{status === "SUPPORTED" ? "+" : status === "CONTRADICTED" ? "×" : status === "UNRESOLVED_CONFLICT" ? "↔" : "—"}</span> {status ?? "NO SEMANTIC VERDICT"}</span>;
}

function AnswerDetail({ answer, snapshot }: { answer: ExampleAnswer; snapshot: string }) {
  const [claimIndex, setClaimIndex] = useState(0);
  const claim = answer.claims[claimIndex];
  const status = currentVerdict(answer, snapshot);
  return <article className="answer-detail" aria-label="Selected answer inspection">
    <div className="detail-top"><span className="mono">{answer.id}</span><span className="example-stamp">EXAMPLE RECORD</span></div>
    <h3>{answer.question}</h3>
    <div className="scope-line"><span className="outline-label">{answer.scope}</span><span>{answer.scopeDetail}</span></div>
    <div className="archived-answer"><span className="eyebrow">Archived answer / original text</span><p>“{answer.answer}”</p></div>
    <div className="assessment-summary"><div><span className="eyebrow">Workflow state</span><strong className="workflow-value">{answer.workflow}</strong></div><div><span className="eyebrow">Policy-resolved assessment</span><Status status={status}/></div></div>
    <p className="snapshot-note">{status && answer.verdict ? <>Valid for <b>{answer.verdict.snapshot}</b> · {answer.verdict.evaluationTime} · {answer.verdict.policy}</> : <>Target <b>{snapshot}</b> · {verdictLabel(answer, snapshot)}. No new verification is implied.</>}</p>
    <details className="selection-reason"><summary>Why this answer is in the inspection set</summary><p>{answer.selectionReason}</p></details>
    <section className="claims-section" aria-label="Claim inspection">
      <div className="claim-heading"><span className="eyebrow">Claim-by-claim / {answer.claims.length} example {answer.claims.length === 1 ? "claim" : "claims"}</span><span className="mono">02 → 03</span></div>
      <div className="claim-selector" role="group" aria-label="Select a claim">{answer.claims.map((item, index) => <button key={item.id} aria-pressed={index === claimIndex} onClick={() => setClaimIndex(index)} className={index === claimIndex ? "selected" : ""}><span className="mono">C{String(index + 1).padStart(2, "0")}</span>{item.text}</button>)}</div>
      {claim && <div className="claim-content" aria-live="polite">
        <div className="claim-result"><span className="mono">{claim.id}</span><Status status={status ? claim.status : null}/></div>
        <p className="explanation">{claim.explanation}</p>
        <div className="evidence-pair">{([['Recorded / earlier evidence', claim.before], ['Applicable / inspected evidence', claim.after]] as const).map(([label, evidence]) => <section key={label} className="evidence-block"><h4>{label}</h4>{evidence ? <><p className="evidence-ref mono">{evidence.reference}</p><blockquote>{evidence.text}</blockquote><p className="evidence-authority">{evidence.authority}</p></> : <p className="empty-evidence">No evidence recorded in this example. Absence is not contradiction.</p>}</section>)}</div>
      </div>}
    </section>
    <details className="history"><summary>Assessment history <span className="mono">({answer.history.length} example records)</span></summary>{answer.history.length ? <ol>{answer.history.map((record, index) => <li key={index}><span className="mono">{record.snapshot}</span><strong>{record.label}</strong><p>{record.detail}</p></li>)}</ol> : <p>No assessment history is provided for this example.</p>}</details>
    <p className="detail-disclaimer">Authored illustration. No provider was called; these are not research results.</p>
  </article>;
}

export default function AnswerInspector({ workspace }: { workspace: ExampleWorkspace }) {
  const [search, setSearch] = useState("");
  const [workflow, setWorkflow] = useState("ALL");
  const [sort, setSort] = useState("id");
  const [selectedId, setSelectedId] = useState("av:starter-export@1");
  const controlId = useId();
  const answers = useMemo(() => filterAnswers(workspace.answers, search, workflow, sort), [workspace, search, workflow, sort]);
  const selected = answers.find(answer => answer.id === selectedId) ?? answers[0];
  return <section className="answer-section" aria-labelledby="answers-heading">
    <div className="section-heading"><div><span className="eyebrow">02 / Archived answers · example</span><h2 id="answers-heading">Follow the consequences.</h2></div><p>Candidates, not confirmed impact.</p></div>
    <div className="answer-toolbar"><label htmlFor={`${controlId}-search`}>Search questions<input id={`${controlId}-search`} type="search" placeholder="Question, answer, or ID…" value={search} onChange={event => setSearch(event.target.value)}/></label><label htmlFor={`${controlId}-workflow`}>Workflow<select id={`${controlId}-workflow`} value={workflow} onChange={event => setWorkflow(event.target.value)}><option value="ALL">All workflow states</option>{workflowStates.map(state => <option key={state}>{state}</option>)}</select></label><label htmlFor={`${controlId}-sort`}>Sort by<select id={`${controlId}-sort`} value={sort} onChange={event => setSort(event.target.value)}><option value="id">Answer ID</option><option value="question">Question A–Z</option></select></label></div>
    <p className="result-count mono" role="status">{answers.length} of {workspace.answers.length} example answers · target {workspace.snapshot}</p>
    {answers.length === 0 ? <div className="empty-filter"><span className="empty-symbol" aria-hidden="true">∅</span><h3>No example answers match.</h3><p>Try a different question or workflow state. Nothing has been removed.</p><button className="solid-button" onClick={() => {setSearch(""); setWorkflow("ALL");}}>Clear filters</button></div> : <div className="inspection-grid"><nav className="answer-list" aria-label="Example answers">{answers.map((answer, index) => <button key={answer.id} aria-current={selected?.id === answer.id ? "true" : undefined} onClick={() => setSelectedId(answer.id)}><span className="answer-row-number mono">{String(index + 1).padStart(2, "0")} <span aria-hidden="true">↗</span></span><strong>{answer.question}</strong><span className="row-workflow">Workflow / {answer.workflow}</span><span className="row-verdict">{verdictLabel(answer, workspace.snapshot)}</span></button>)}</nav>{selected && <AnswerDetail key={selected.id} answer={selected} snapshot={workspace.snapshot}/>}</div>}
  </section>;
}
