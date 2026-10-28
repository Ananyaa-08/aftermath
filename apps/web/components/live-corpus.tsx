"use client";
import {useEffect, useState, useRef, type FormEvent} from "react";
import {storageRequest, sourceBase64, deliveryLabel, StorageError, type WorkspaceRecord, type CorpusRecord, type DocumentRecord, type VersionRecord, type SnapshotRecord, type EffectiveResult, type DeliveryResult} from "../lib/storage";
import LiveAnswer from "./live-answer";
const value = (form:FormData,key:string) => String(form.get(key) ?? "");
const now = () => new Date().toISOString();
const message = (error:unknown) => error instanceof StorageError ? "That didn't go through. Try again." : "Storage could not be reached. Try again.";
const CORPUS_ID = /^[a-z0-9][a-z0-9_-]{0,63}$/;
export default function LiveCorpus() {
  const [workspaces,setWorkspaces] = useState<WorkspaceRecord[]>([]);
  const [workspace,setWorkspace] = useState(""); const [corpora,setCorpora] = useState<CorpusRecord[]>([]);
  const [corpus,setCorpus] = useState(""); const [documents,setDocuments] = useState<DocumentRecord[]>([]);
  const [snapshots,setSnapshots] = useState<SnapshotRecord[]>([]); const [document,setDocument] = useState("");
  const [versions,setVersions] = useState<VersionRecord[]>([]); const [result,setResult] = useState<EffectiveResult|null>(null);
  const [error,setError] = useState(""); const [notice,setNotice] = useState(""); const [busy,setBusy] = useState(false);
  const [loading,setLoading] = useState(false); const [refresh,setRefresh] = useState(0); const [scope,setScope] = useState("ROLLING_CURRENT");
  const [createOpen,setCreateOpen] = useState(false);
  const [createStep,setCreateStep] = useState<"menu"|"workspace"|"corpus">("menu");
  const [firstCorpus,setFirstCorpus] = useState(false);
  const [workspaceDraft,setWorkspaceDraft] = useState("");
  const [corpusName,setCorpusName] = useState("");
  const [corpusId,setCorpusId] = useState("");
  const deliveryClock = useRef<{id:string;at:string}|null>(null);
  const [deliveryId,setDeliveryId] = useState("");
  const base = `/${encodeURIComponent(workspace)}/corpora/${encodeURIComponent(corpus)}`;
  const selected = corpora.find(c => c.corpus_id === corpus);
  useEffect(() => { let active=true; setLoading(true); setError("");
    (async() => {
      const ws = await storageRequest<WorkspaceRecord[]>("?limit=100");
      if(!active)return; setWorkspaces(ws);
      if(!workspace){setCorpora([]);setDocuments([]);setSnapshots([]);return;}
      const cs = await storageRequest<CorpusRecord[]>(`/${encodeURIComponent(workspace)}/corpora?limit=100`);
      if(!active)return; setCorpora(cs);
      if(!corpus){setDocuments([]);setSnapshots([]);return;}
      const [ds,ss] = await Promise.all([storageRequest<DocumentRecord[]>(`${base}/documents?limit=100`),storageRequest<SnapshotRecord[]>(`${base}/snapshots?limit=100`)]);
      if(active){setDocuments(ds);setSnapshots(ss);}
    })().catch(e => {if(active){setError(message(e));setCorpora([]);setDocuments([]);setSnapshots([]);}}).finally(()=>{if(active)setLoading(false);});
    return ()=>{active=false;};
  },[workspace,corpus,base,refresh]);
  useEffect(()=>{let active=true;setVersions([]);setResult(null);if(document && workspace && corpus) storageRequest<VersionRecord[]>(`${base}/documents/${encodeURIComponent(document)}/versions?limit=100`).then(v=>{if(active)setVersions(v);}).catch(e=>{if(active)setError(message(e));});return()=>{active=false;};},[base,document,workspace,corpus,refresh]);
  async function act(event:FormEvent<HTMLFormElement>, operation:(form:FormData)=>Promise<void>) {event.preventDefault();if(busy)return;const form=new FormData(event.currentTarget);setBusy(true);setError("");setNotice("");try{await operation(form);}catch(e){setError(message(e));}finally{setBusy(false);}}
  function resetCreate(){setCreateStep("menu");setFirstCorpus(false);setWorkspaceDraft("");setCorpusName("");setCorpusId("");}
  function toggleCreate(){if(createOpen){setCreateOpen(false);resetCreate();return;}resetCreate();setCreateOpen(true);}
  const corpusReady = corpusName.trim().length>0 && CORPUS_ID.test(corpusId);
  return <section className="live-storage chat-app" aria-labelledby="storage-title">
    <p className="sr-only" id="storage-title">Storage results are not semantic assessments.</p>
    <header className="chat-top">
      <span className="brand-wordmark">aftermath</span>
      <label>Workspace<select value={workspace} onChange={e=>{setWorkspace(e.target.value);setCorpus("");setDocument("");setResult(null);setNotice("");}}><option value="">Select a workspace</option>{workspaces.map(w=><option key={w.id} value={w.id}>{w.name}</option>)}</select></label>
      <label>Corpus<select value={corpus} disabled={!workspace} onChange={e=>{setCorpus(e.target.value);setDocument("");setResult(null);setNotice("");}}><option value="">Select a corpus</option>{corpora.map(c=><option key={c.corpus_id} value={c.corpus_id}>{c.name}</option>)}</select></label>
      <div className="new-menu">
        <button type="button" className="text-button" aria-expanded={createOpen} onClick={toggleCreate}>New</button>
        {createOpen && <div className="new-popover" role="dialog" aria-label={createStep==="corpus" ? "New corpus" : "New workspace or corpus"}>
          {createStep==="menu" && <>
            <button type="button" className="solid-button" onClick={()=>{setWorkspaceDraft("");setCreateStep("workspace");}}>New workspace</button>
            <button type="button" className="solid-button" disabled={!workspace} onClick={()=>{setFirstCorpus(false);setCorpusName("");setCorpusId("");setCreateStep("corpus");}}>New corpus</button>
          </>}
          {createStep==="workspace" && <form onSubmit={e=>act(e,async()=>{
            const w=await storageRequest<WorkspaceRecord>("",{name:workspaceDraft.trim()});
            setWorkspaces(current=>current.some(item=>item.id===w.id)?current:[w,...current]);
            setWorkspace(w.id);setCorpus("");setDocument("");setResult(null);
            setWorkspaceDraft("");setCorpusName("");setCorpusId("");setFirstCorpus(true);setCreateStep("corpus");
            setNotice("Workspace created");setRefresh(n=>n+1);
          })}>
            <label>Workspace name<input value={workspaceDraft} onChange={e=>setWorkspaceDraft(e.target.value)} maxLength={120} autoFocus/></label>
            <button className="solid-button" disabled={busy||!workspaceDraft.trim()}>Continue</button>
          </form>}
          {createStep==="corpus" && <form onSubmit={e=>act(e,async()=>{
            const c=await storageRequest<CorpusRecord>(`/${workspace}/corpora`,{name:corpusName.trim(),corpus_id:corpusId});
            setCorpora(current=>current.some(item=>item.corpus_id===c.corpus_id)?current:[c,...current]);
            setCorpus(c.corpus_id);setDocument("");setResult(null);setCreateOpen(false);resetCreate();
            setNotice("Corpus created");setRefresh(n=>n+1);
          })}>
            <p className="storage-subtitle">{firstCorpus?"Name this workspace's first corpus":"New corpus"}</p>
            <label>Corpus name<input value={corpusName} onChange={e=>setCorpusName(e.target.value)} maxLength={120} autoFocus/></label>
            <label>Corpus ID<input value={corpusId} onChange={e=>setCorpusId(e.target.value.toLowerCase())} pattern="[a-z0-9][a-z0-9_-]*" placeholder="research-notes" maxLength={64} spellCheck={false}/></label>
            <button className="solid-button" disabled={busy||!workspace||!corpusReady}>Create corpus</button>
          </form>}
        </div>}
      </div>
    </header>
    {error && <div role="alert" className="chat-failure"><p>{error}</p><button type="button" className="text-button" onClick={()=>setRefresh(n=>n+1)}>Retry</button></div>}
    {notice && <p role="status" className="chat-system">{notice}</p>}
    {selected && <LiveAnswer workspace={workspace} corpus={corpus} documents={documents} head={selected.head_snapshot_id} disabled={busy} refreshKey={refresh} onStored={()=>setRefresh(n=>n+1)}/>}
    <fieldset disabled={busy||loading} className="storage-fieldset">
      {selected && <details className="corpus-register"><summary>Corpus register</summary><div className="storage-columns"><div><details className="ingestion-panel"><summary>Ingest a text / Markdown revision</summary><p className="storage-help">One document per delivery in this form. The API also accepts atomic batches. All timestamps use UTC (Z). Keep the delivery ID when retrying an uncertain request.</p><form onSubmit={e=>act(e,async f=>{const id=deliveryId||`delivery-${crypto.randomUUID()}`;setDeliveryId(id);if(deliveryClock.current?.id !== id) deliveryClock.current={id,at:now()};const result=await storageRequest<DeliveryResult>(`${base}/deliveries`,{delivery_id:id,expected_head:selected.head_snapshot_id,as_of:deliveryClock.current.at,documents:[{document_id:value(f,"document_id"),source_revision_id:value(f,"revision"),source_seq:Number(value(f,"sequence")),source_timestamp:value(f,"timestamp"),declared_effective_from:value(f,"effective")||null,source_type:value(f,"source_type"),source_base64:sourceBase64(value(f,"text")),authority:{}}]});setNotice(deliveryLabel(result));setRefresh(n=>n+1);if(result.status==="APPLIED"||result.status==="NO_OP_UNCHANGED")setDeliveryId("");})}>
      <div className="form-pair"><label>Document ID<input name="document_id" required pattern="[a-z0-9][a-z0-9_-]*" placeholder="guide" maxLength={64}/></label><label>Source revision ID<input name="revision" required pattern="[a-z0-9][a-z0-9_-]*" placeholder="r1" maxLength={64}/></label></div><div className="form-pair"><label>Source sequence<input type="number" name="sequence" required min={0} max={2147483647} step={1} defaultValue={1}/></label><label>Source type<input name="source_type" required defaultValue="markdown" pattern="[a-z0-9][a-z0-9_-]*" maxLength={64}/></label></div><label>Source timestamp (UTC)<input name="timestamp" required placeholder="2026-11-01T00:00:00Z"/></label><label>Declared effective date (UTC, optional)<input name="effective" placeholder="2026-12-01T00:00:00Z"/></label><label>Source text<textarea name="text" required rows={6} placeholder="Paste the source text to preserve…"/></label><label>Delivery ID (blank generates one)<input value={deliveryId} onChange={e=>setDeliveryId(e.target.value)} pattern="[a-z0-9][a-z0-9_-]*" maxLength={64}/></label><p className="mono">Expected parent: {selected.head_snapshot_id ?? "null (first snapshot)"}</p><button className="solid-button">{busy ? "Submitting…" : "Store immutable revision ↗"}</button></form></details>
      <h3 className="storage-subtitle">Document register</h3>{!documents.length && <p className="storage-help">No stored documents in this corpus.</p>}<div className="document-register">{documents.map(d=><button key={d.document_id} aria-pressed={document===d.document_id} onClick={()=>setDocument(d.document_id)}><strong>{d.document_id}</strong><span className="mono">{d.latest_version_id} · {d.version_count} revision(s){d.is_deletion ? " · TOMBSTONE" : ""}</span><span aria-hidden="true">↗</span></button>)}</div></div>
      <div>{document ? <><h3 className="storage-subtitle">Revision history / {document}</h3>{versions.map(v=><details className="version-entry" key={v.document_version_id}><summary>{v.document_version_id}{v.is_deletion ? " / TOMBSTONE" : ""}</summary><dl><dt>Source sequence</dt><dd>{v.source_seq}</dd><dt>Source timestamp</dt><dd>{v.source_timestamp}</dd><dt>Effective from</dt><dd>{v.effective_from} / {v.effective_from_source}</dd><dt>Source type</dt><dd>{v.source_type}</dd><dt>Canonical hash</dt><dd>{v.content_hash}</dd><dt>Original bytes hash</dt><dd>{v.source_bytes_hash}</dd><dt>Normalization</dt><dd>{v.normalization_version}</dd><dt>Authority metadata</dt><dd>{JSON.stringify(v.authority)}</dd></dl><pre>{v.text || "[empty source / tombstone]"}</pre></details>)}
      <h3 className="storage-subtitle">Resolve at a snapshot & time</h3><form className="resolve-form" onSubmit={e=>act(e,async f=>{setResult(null);const request={snapshot_id:value(f,"snapshot"),scope,...(scope==="FIXED_VERSION"?{version_id:value(f,"version")} : scope==="FIXED_TIME"?{fixed_time:value(f,"at")}:{evaluation_time:value(f,"at")||null})};setResult(await storageRequest<EffectiveResult>(`${base}/documents/${encodeURIComponent(document)}/resolve`,request));})}><label>Knowledge snapshot<select name="snapshot" required>{snapshots.map(s=><option key={s.snapshot_id} value={s.snapshot_id}>{s.snapshot_id} / {s.as_of}</option>)}</select></label><label>Temporal scope<select value={scope} onChange={e=>{setScope(e.target.value);setResult(null);}}><option>ROLLING_CURRENT</option><option>FIXED_TIME</option><option>FIXED_VERSION</option></select></label>{scope==="FIXED_VERSION"?<label>Immutable version<select name="version" required>{versions.map(v=><option key={v.document_version_id}>{v.document_version_id}</option>)}</select></label>:<label>Evaluation time (UTC){scope==="ROLLING_CURRENT" && " — blank uses snapshot time"}<input name="at" required={scope==="FIXED_TIME"} placeholder="2026-11-15T00:00:00Z"/></label>}<button className="solid-button">Resolve effective version ↗</button></form>
      {result && <div className="resolution-result" role="status"><span className="eyebrow">Storage resolution / {result.scope}</span><h4>{result.active ? "ACTIVE VERSION" : "NO ACTIVE EVIDENCE"}</h4><dl><dt>Selected revision</dt><dd>{result.selected_version_id ?? "None effective at this time"}</dd><dt>Bound snapshot</dt><dd>{result.snapshot_id}</dd><dt>Evaluated at</dt><dd>{result.evaluation_time ?? "Exact version scope"}</dd><dt>Derived effective end</dt><dd>{result.effective_to ?? "Open / not applicable"}</dd><dt>Evidence fingerprint</dt><dd>{result.fingerprint}</dd></dl>{result.version && <pre>{result.version.text}</pre>}<p className="storage-help">This selects stored source evidence. It does not assess an answer or generate a verdict.</p></div>}</>:<div className="storage-empty"><span aria-hidden="true">↳</span><h3>Select a document.</h3><p>Inspect stored revisions and resolve their effective time. A future-effective revision does not hide the version currently in force.</p></div>}</div></div></details>}
    </fieldset><p className="storage-limit mono">Lists show up to 100 records each. The API supports limit / offset pagination. Development identity only; production authentication is unavailable.</p>
  </section>;
}
