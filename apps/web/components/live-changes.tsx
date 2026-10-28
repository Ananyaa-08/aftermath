"use client";

import {useEffect,useReducer,useRef,useState,type ReactNode} from "react";
import {availablePreset,initialInspectionState,inspectionReducer,isInspectionLoading,visibleInspectionError,type Stage} from "../lib/change-inspection";
import {storageRequest,StorageError,type ChangedDocumentRecord,type CorpusRecord,type DocumentComparison,type UpdateEventRecord,type WorkspaceRecord} from "../lib/storage";

const errorMessage=(error:unknown)=>error instanceof StorageError?`${error.code} · ${error.message}`:"UNREACHABLE · Source-change records could not be loaded.";
const featureLabels=(span:DocumentComparison["spans"][number])=>[
  span.features.numeric_change&&`NUMERIC ${span.features.numbers_old.join(", ")} → ${span.features.numbers_new.join(", ")}`,
  span.features.date_change&&"DATE CHANGED",span.features.negation_change&&"NEGATION CHANGED",
  span.features.qualifier_change&&`QUALIFIER ${span.features.qualifiers_old.join(", ")||"none"} → ${span.features.qualifiers_new.join(", ")||"none"}`,
].filter(Boolean) as string[];

export function LiveChangeOutcome({error,comparison,children}:{error:string;comparison:DocumentComparison|null;children?:ReactNode}){
  return <>{error&&<div role="alert" className="storage-error"><strong>CHANGE RECORDS UNAVAILABLE</strong><p>{error}</p><p>No example changes were substituted.</p></div>}{comparison&&children}</>;
}

export default function LiveChanges(){
  const [state,dispatch]=useReducer(inspectionReducer,initialInspectionState);
  const [retry,setRetry]=useState(0); const sequence=useRef(0);
  const latestState=useRef(state); latestState.current=state;
  const active=useRef<Partial<Record<Stage,{id:number;key:string}>>>({});
  const preset=useRef({
    values:{workspace:"",corpus:"",delivery:"",document:""},
    pending:{workspace:true,corpus:true,delivery:true,document:true},
  });
  const base=`/${encodeURIComponent(state.workspace)}/corpora/${encodeURIComponent(state.corpus)}`;
  const loading=isInspectionLoading(state); const error=visibleInspectionError(state);

  const isActive=(stage:Stage,id:number,key:string)=>active.current[stage]?.id===id&&active.current[stage]?.key===key;
  const invalidate=(stages:Stage[])=>{for(const stage of stages)delete active.current[stage];};
  const takePreset=(stage:"workspace"|"corpus"|"delivery"|"document",options:string[],parentsMatch=true)=>{
    if(!preset.current.pending[stage])return "";
    preset.current.pending[stage]=false;
    return parentsMatch?availablePreset(preset.current.values[stage],options):"";
  };
  const select=(stage:"workspace"|"corpus"|"delivery"|"document",value:string,user=true)=>{
    if(latestState.current[stage]===value)return;
    const order=["workspace","corpus","delivery","document"] as const;
    const index=order.indexOf(stage);
    invalidate((stage==="workspace"?["corpora","events","documents","comparison"]:stage==="corpus"?["events","documents","comparison"]:stage==="delivery"?["documents","comparison"]:["comparison"]) as Stage[]);
    if(user)for(const item of order.slice(index))preset.current.pending[item]=false;
    dispatch({type:"select",stage,value});
  };
  const begin=(stage:Stage,key:string)=>{const id=++sequence.current;active.current[stage]={id,key};dispatch({type:"request",stage,id,key});return id;};
  const finish=(stage:Stage,id:number,key:string)=>{if(!isActive(stage,id,key))return false;delete active.current[stage];return true;};
  const cleanup=(stage:Stage,id:number,key:string,controller:AbortController)=>{if(isActive(stage,id,key))delete active.current[stage];controller.abort();};

  useEffect(()=>{const query=new URLSearchParams(window.location.search);preset.current.values={workspace:query.get("workspace")??"",corpus:query.get("corpus")??"",delivery:query.get("delivery")??"",document:query.get("document")??""};},[]);
  useEffect(()=>{const stage="workspaces";const key="root";const controller=new AbortController();const id=begin(stage,key);storageRequest<WorkspaceRecord[]>("?limit=100",undefined,controller.signal).then(values=>{if(!finish(stage,id,key))return;dispatch({type:"success",stage,id,key,value:values});const selected=takePreset("workspace",values.map(item=>item.id));if(selected)select("workspace",selected,false);}).catch(reason=>{if(finish(stage,id,key)&&!controller.signal.aborted)dispatch({type:"failure",stage,id,key,message:errorMessage(reason)});});return()=>cleanup(stage,id,key,controller);},[retry]);
  useEffect(()=>{if(!state.workspace)return;const stage="corpora";const key=state.workspace;const controller=new AbortController();const id=begin(stage,key);storageRequest<CorpusRecord[]>(`/${encodeURIComponent(state.workspace)}/corpora?limit=100`,undefined,controller.signal).then(values=>{if(!finish(stage,id,key))return;dispatch({type:"success",stage,id,key,value:values});const selected=takePreset("corpus",values.map(item=>item.corpus_id),preset.current.values.workspace===state.workspace);if(selected)select("corpus",selected,false);}).catch(reason=>{if(finish(stage,id,key)&&!controller.signal.aborted)dispatch({type:"failure",stage,id,key,message:errorMessage(reason)});});return()=>cleanup(stage,id,key,controller);},[state.workspace,retry]);
  useEffect(()=>{if(!state.workspace||!state.corpus)return;const stage="events";const key=`${state.workspace}/${state.corpus}`;const controller=new AbortController();const id=begin(stage,key);storageRequest<UpdateEventRecord[]>(`${base}/updates?limit=100`,undefined,controller.signal).then(values=>{if(!finish(stage,id,key))return;const applied=values.filter(item=>item.status==="APPLIED");dispatch({type:"success",stage,id,key,value:applied});const selected=takePreset("delivery",applied.map(item=>item.delivery_id),preset.current.values.workspace===state.workspace&&preset.current.values.corpus===state.corpus);if(selected)select("delivery",selected,false);}).catch(reason=>{if(finish(stage,id,key)&&!controller.signal.aborted)dispatch({type:"failure",stage,id,key,message:errorMessage(reason)});});return()=>cleanup(stage,id,key,controller);},[state.workspace,state.corpus,base,retry]);
  useEffect(()=>{if(!state.delivery)return;const stage="documents";const key=`${state.workspace}/${state.corpus}/${state.delivery}`;const controller=new AbortController();const id=begin(stage,key);storageRequest<ChangedDocumentRecord[]>(`${base}/updates/${encodeURIComponent(state.delivery)}/documents`,undefined,controller.signal).then(values=>{if(!finish(stage,id,key))return;dispatch({type:"success",stage,id,key,value:values});const options=values.map(item=>item.document_id);const requested=takePreset("document",options,preset.current.values.workspace===state.workspace&&preset.current.values.corpus===state.corpus&&preset.current.values.delivery===state.delivery);const current=availablePreset(latestState.current.document,options);const selected=requested||current||values[0]?.document_id||"";if(selected)select("document",selected,false);}).catch(reason=>{if(finish(stage,id,key)&&!controller.signal.aborted)dispatch({type:"failure",stage,id,key,message:errorMessage(reason)});});return()=>cleanup(stage,id,key,controller);},[state.workspace,state.corpus,state.delivery,base,retry]);
  useEffect(()=>{if(!state.delivery||!state.document)return;const stage="comparison";const key=`${state.workspace}/${state.corpus}/${state.delivery}/${state.document}`;const controller=new AbortController();const id=begin(stage,key);storageRequest<DocumentComparison>(`${base}/updates/${encodeURIComponent(state.delivery)}/documents/${encodeURIComponent(state.document)}/comparison`,undefined,controller.signal).then(value=>{if(finish(stage,id,key))dispatch({type:"success",stage,id,key,value});}).catch(reason=>{if(finish(stage,id,key)&&!controller.signal.aborted)dispatch({type:"failure",stage,id,key,message:errorMessage(reason)});});return()=>cleanup(stage,id,key,controller);},[state.workspace,state.corpus,state.delivery,state.document,base,retry]);

  return <section className="live-changes" aria-labelledby="changes-title">
    <div className="storage-heading"><div><span className="eyebrow">02 / Real source changes</span><h2 id="changes-title">Inspect what moved.</h2><p>A source change is not a confirmed affected answer and is not a semantic verdict.</p></div><button className="text-button" disabled={loading} onClick={()=>setRetry(value=>value+1)}>Retry / refresh ↻</button></div>
    {loading&&<p role="status" className="mono">LOADING SOURCE CHANGES…</p>}
    <div className="change-selectors">
      <label>Workspace<select value={state.workspace} onChange={event=>select("workspace",event.target.value)}><option value="">Select a workspace</option>{state.workspaces.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      <label>Corpus<select value={state.corpus} disabled={!state.workspace} onChange={event=>select("corpus",event.target.value)}><option value="">Select a corpus</option>{state.corpora.map(item=><option key={item.corpus_id} value={item.corpus_id}>{item.name} / {item.corpus_id}</option>)}</select></label>
      <label>Applied update<select value={state.delivery} disabled={!state.corpus} onChange={event=>select("delivery",event.target.value)}><option value="">Select an update</option>{state.events.map(item=><option key={item.delivery_id} value={item.delivery_id}>{item.delivery_id} / {item.snapshot_id}</option>)}</select></label>
      <label>Changed document<select value={state.document} disabled={!state.delivery} onChange={event=>select("document",event.target.value)}><option value="">Select a document</option>{state.documents.map(item=><option key={item.document_id} value={item.document_id}>{item.document_id} / {item.span_count} span(s)</option>)}</select></label>
    </div>
    {state.corpus&&!state.events.length&&!loading&&<div className="storage-empty"><span aria-hidden="true">∅</span><h3>No applied update history.</h3><p>Ingest a revision in Overview, then return here to inspect its passage lineage and effective timeline.</p></div>}
    {state.delivery&&!state.documents.length&&!loading&&<div className="storage-empty"><h3>No persisted change documents.</h3><p>This event did not produce a Step 2B change set.</p></div>}
    <LiveChangeOutcome error={error} comparison={state.comparison}>{state.comparison&&<Comparison comparison={state.comparison}/>}</LiveChangeOutcome>
  </section>;
}

function Comparison({comparison}:{comparison:DocumentComparison}){return <article className="change-inspection">
  <header className="change-boundary"><div><span className="eyebrow">Update → document</span><h3>{comparison.delivery_id} / {comparison.document_id}</h3></div><dl><div><dt>Parent knowledge</dt><dd>{comparison.parent_snapshot_id??"First snapshot"}</dd></div><div><dt>Result knowledge</dt><dd>{comparison.result_snapshot_id}</dd></div></dl></header>
  <div className="revision-pair"><div><span className="outline-label">BEFORE</span><strong>{comparison.old_version?.document_version_id??"No earlier version"}</strong><span>{comparison.old_version?.source_type??"Absent"} / {JSON.stringify(comparison.old_version?.authority??{})}</span></div><div><span className="outline-label">AFTER</span><strong>{comparison.new_version.document_version_id}</strong><span>{comparison.new_version.source_type} / {JSON.stringify(comparison.new_version.authority)}</span></div></div>
  <section aria-labelledby="lineage-title"><div className="section-heading"><div><span className="eyebrow">Passage lineage</span><h3 id="lineage-title">Latest-observed alignment</h3></div><p>{comparison.edges.length} complete lineage edge(s)</p></div><ol className="lineage-list">{comparison.edges.map(edge=><li key={edge.lineage_edge_id}><span className="mono">{edge.lineage_edge_id}</span><strong>{edge.relation}</strong><span>{edge.alignment_confidence} alignment confidence{edge.alignment_score===null?"":` / ${edge.alignment_score.toFixed(2)}`}</span><small>{edge.from_passage_version_ids.join(", ")||"∅"} → {edge.to_passage_version_ids.join(", ")||"∅"}</small></li>)}</ol></section>
  {!!comparison.timeline_alignments.length&&<section aria-labelledby="timeline-alignment-title"><div className="section-heading"><div><span className="eyebrow">Effective timeline</span><h3 id="timeline-alignment-title">Timeline comparison · not lineage</h3></div><p>{comparison.timeline_alignments.length} interval-bound comparison(s)</p></div><ol className="lineage-list">{comparison.timeline_alignments.map(item=><li key={item.timeline_alignment_edge_id}><span className="mono">{item.timeline_alignment_edge_id}</span><strong>{item.relation}</strong><span>{item.alignment_confidence} comparison confidence{item.alignment_score===null?"":` / ${item.alignment_score.toFixed(2)}`}</span><small>{item.from_passage_version_ids.join(", ")||"∅"} → {item.to_passage_version_ids.join(", ")||"∅"} / {item.applicability_change_id}{item.legacy_lineage_edge_id?` / reclassified ${item.legacy_lineage_edge_id}`:""}</small></li>)}</ol></section>}
  <section aria-labelledby="spans-title"><div className="section-heading"><div><span className="eyebrow">Exact canonical spans</span><h3 id="spans-title">Before / after</h3></div><p>Python code-point offsets</p></div>{!comparison.spans.length&&<p className="storage-help">The latest observed text is identical. Check applicability intervals below for an effective-date-only change.</p>}<div className="live-span-list">{comparison.spans.map(span=><article key={span.change_span_id} className="live-span"><header><span className="outline-label">{span.kind}</span><span className="mono">{span.origin} / {span.alignment_confidence} ALIGNMENT</span></header><div className="diff-grid"><div className="passage before-passage"><div className="passage-top"><strong>Before</strong><span className="mono">{span.old_start??"∅"}–{span.old_end??"∅"}</span></div>{span.old_text===null?<p>∅ No textual side</p>:<p><del>{span.old_text}</del></p>}</div><div className="passage after-passage"><div className="passage-top"><strong>After</strong><span className="mono">{span.new_start??"∅"}–{span.new_end??"∅"}</span></div>{span.new_text===null?<p>∅ No textual side</p>:<p><ins>{span.new_text}</ins></p>}</div></div><div className="span-notes">{featureLabels(span).map(label=><span key={label}>{label}</span>)}{span.kind==="AUTHORITY_CHANGED"&&<span>AUTHORITY METADATA / {JSON.stringify(span.metadata)}</span>}<span>{span.effective_from} → {span.effective_to??"open"}</span>{span.text_diff_reused&&<span>TEXT DIFF REUSED BY TIMELINE</span>}{span.reclassified_lineage_edge_id&&<span>LEGACY TIMELINE EDGE / {span.reclassified_lineage_edge_id}</span>}</div></article>)}</div></section>
  <section className="applicability-panel" aria-labelledby="applicability-title"><span className="eyebrow">Effective timeline</span><h3 id="applicability-title">Applicability changes</h3>{!comparison.applicability_changes.length?<p>No effective-evidence interval changed.</p>:<ol>{comparison.applicability_changes.map(item=><li key={item.applicability_change_id}><strong>{item.reason}</strong><span>{item.interval_from} → {item.interval_to??"open"}</span><span>{item.old_effective_version_id??"Absent"} → {item.new_effective_version_id??"Absent"}</span><small>{item.text_diff_reused?"Reuses latest-observed text span":"Timeline-specific comparison"} / {item.parent_snapshot_id??"∅"} → {item.result_snapshot_id}</small></li>)}</ol>}</section>
  <p className="source-footnote">Hierarchy: update → document → latest-observed lineage or timeline comparison → exact span → effective interval. These records describe source state only; affected-answer discovery is unavailable.</p>
</article>}
