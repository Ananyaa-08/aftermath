"use client";
import { useEffect, useState } from "react";
import { exampleWorkspace } from "../fixtures/example-workspace";
import { workspaceForMode, type View, type WorkspaceMode } from "../lib/workspace";
import LiveCorpus from "./live-corpus";
import LiveChanges from "./live-changes";
import Connection from "./connection";
import Sculpture from "./sculpture";
import SourceChange from "./source-change";
import AnswerInspector from "./answer-inspector";

export default function Workspace() {
  const [mode, setMode] = useState<WorkspaceMode>("live");
  const [view, setView] = useState<View>("overview");
  const data = workspaceForMode(mode, exampleWorkspace);
  useEffect(() => {
    const requested = new URLSearchParams(window.location.search).get("view");
    if (requested === "inspect" || requested === "experiments") setView(requested);
  }, []);
  const openExample = () => { setMode("example"); setView("inspect"); };
  return <main className={`workspace ${view !== "overview" ? "workspace-compact" : ""} ${!data && view === "overview" ? "live-demo" : ""}`}>
    <a href="#workspace-content" className="skip-link">Skip to workspace content</a>
    <header className="masthead"><div className="brand-small"><a href="/" aria-label="AFTERMATH homepage">←</a><span aria-hidden="true">✳</span> <span className="brand-wordmark">aftermath</span> <span className="brand-description">/ A RESEARCH INSTRUMENT</span></div><div className="mode-switch" role="group" aria-label="Workspace data mode"><button aria-pressed={mode === "live"} onClick={() => setMode("live")}>Live workspace</button><button aria-pressed={mode === "example"} onClick={() => setMode("example")}>Example workspace <span aria-hidden="true">↗</span></button></div></header>
    <div className="title-composition"><div className="title-kicker"><span className="mono">SOURCE → ANSWER → EVIDENCE</span><span className="mono">FIELD NOTES / 001</span></div><h1 className="workspace-wordmark">aftermath</h1><Sculpture/><p className="composition-caption">What changes<br/><b>when sources change?</b></p></div>
    <nav className="workspace-nav" aria-label="Workspace views">{([{id:"overview", label:"Overview", number:"01"}, {id:"inspect", label:"Inspect changes", number:"02"}, {id:"experiments", label:"Experiments", number:"03"}] as const).map(item => <button key={item.id} aria-current={view === item.id ? "page" : undefined} onClick={() => setView(item.id)}><span className="mono">{item.number}</span>{item.label}<span className="nav-arrow" aria-hidden="true">↗</span></button>)}<span className="nav-edition mono">FOUNDATION EDITION</span></nav>
    <div className={`mode-banner ${data ? "example-banner" : "live-banner"}`} role="status"><div><span className="mode-marker" aria-hidden="true">{data ? "◇" : "●"}</span><strong>{data ? "Example workspace" : "Live workspace"}</strong><span>{data ? "Deterministic illustrations. No live corpus, model calls, or research results." : "Real corpus storage, grounded answers, and snapshot-scoped reassessment. A candidate is not a confirmed impact."}</span></div>{data && <button className="text-button" onClick={() => setMode("live")}>Return to live ↗</button>}</div>
    <Connection/>
    <div id="workspace-content" tabIndex={-1}>
      {!data && view === "overview" && <LiveCorpus/>}
      {data && view === "overview" && <section className="overview">
        <div className="overview-main"><span className="eyebrow">01 / {data ? "Example corpus" : "Corpus overview"}</span><h2>{data ? <>One source changes.<br/>Several questions follow.</> : <>Ready to look.<br/>Nothing to assume.</>}</h2><p className="overview-description">{data ? "Explore a fictional export-policy revision. Follow the change through archived answers, individual claims, and the evidence behind each recorded assessment." : "Connect the evidence before drawing a conclusion. Your services can report readiness; a live corpus and semantic assessments are not available yet."}</p><button className="solid-button" onClick={openExample}>{data ? "Inspect this example" : "Explore the example workspace"}<span aria-hidden="true"> ↗</span></button><p className="action-note">{data ? "All records in this workspace are authored examples." : "An isolated, labeled illustration. No setup or model calls."}</p></div>
        <aside className="notebook"><span className="notebook-index mono">RESEARCH NOTE / 01</span><span className="notebook-star" aria-hidden="true">✳</span><h3>A changed source<br/>is a question.<br/><em>Not a verdict.</em></h3><p>Freshness tells us where to look. Evidence and temporal scope explain what still holds.</p><span className="mono">KEEP THESE TWO THINGS APART.</span></aside>
        <div className="context-register"><div><span className="eyebrow">Corpus / snapshot</span><h3>{data.name}</h3><p className="mono">{data.snapshot} · EXAMPLE</p></div><div><span className="eyebrow">Latest source update</span><h3>Export policy · r1 → r2</h3><p>Example effective time: 01 Nov 2026, 00:00 UTC</p></div><div><span className="eyebrow">Assessment activity</span><h3>8 authored answer records</h3><p>Illustrative workflow states; no measured performance.</p></div></div>
      </section>}
      {view === "inspect" && (data ? <><SourceChange/><AnswerInspector workspace={data}/></> : <LiveChanges/>)}
      {view === "experiments" && <section className="unavailable-surface"><span className="eyebrow">03 / Experiments</span><div className="unavailable-content"><span className="empty-symbol" aria-hidden="true">∅</span><div><h2>Evidence before performance.</h2><p>Experiment execution and comparison reports are not available. The current Python CLI can validate configuration and database readiness; it does not run research experiments.</p><p className="experiment-note">No runs, scores, cost estimates, or model comparisons are shown. {data && "Example workspace mode does not simulate experimental results."}</p><button className="text-button" onClick={() => setView("overview")}>Back to overview ↗</button></div></div></section>}
    </div>
    <footer><span className="footer-brand">aftermath<span aria-hidden="true">✳</span></span><p>Cited answers can be reassessed when a source passage changes. No research performance result is claimed.</p><span className="mono">OBSERVE CAREFULLY.<br/>KEEP THE EVIDENCE.</span></footer>
  </main>;
}
