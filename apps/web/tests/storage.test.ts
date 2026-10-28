import assert from "node:assert/strict";
import {test} from "node:test";
import {readFileSync} from "node:fs";
import {renderToStaticMarkup} from "react-dom/server";
import {createElement} from "react";
import Home from "../app/page";
import LiveCorpus from "../components/live-corpus";
import LiveChanges, {LiveChangeOutcome} from "../components/live-changes";
import {deliveryLabel, sourceBase64, storageRequest, StorageError} from "../lib/storage";
import {initialInspectionState, inspectionReducer, visibleInspectionError, type InspectionState} from "../lib/change-inspection";
import type {DocumentComparison} from "../lib/storage";
import {sameOriginWrite} from "../lib/same-origin";
test("homepage routes and honest capability labels",()=>{
 const html=renderToStaticMarkup(createElement(Home));
 assert.match(html,/href="\/workspace"/); assert.match(html,/id="how-it-works"/);
 assert.match(html,/aftermath/); assert.match(html,/When sources change/);
 assert.doesNotMatch(html,/SEMANTIC REASSESSMENT: NOT YET|AVAILABLE NOW|Existing models first|01 — IMPLEMENTED|02 — PLANNED|03 — PLANNED|LIVING KNOWLEDGE|VOL\. 01|FIG\. 01|01 \/ THE QUESTION/);
 assert.match(readFileSync("app/workspace/page.tsx","utf8"),/Workspace/);
});
test("real storage cannot render example assessments",()=>{
 const html=renderToStaticMarkup(createElement(LiveCorpus));
 assert.match(html,/Storage results are not semantic assessments/);
 assert.match(readFileSync("components/live-answer.tsx","utf8"),/Ask a grounded question/);
 assert.doesNotMatch(html,/CONTRADICTED|SUPPORTED|av:starter/);
 assert.doesNotMatch(readFileSync("components/live-corpus.tsx","utf8"),/fixtures|exampleWorkspace|AnswerInspector/);
 assert.doesNotMatch(readFileSync("components/live-answer.tsx","utf8"),/fixtures|exampleWorkspace|AnswerInspector/);
});
test("live change inspection is source-state only and keeps failures isolated",()=>{
 const html=renderToStaticMarkup(createElement(LiveChanges));
 assert.match(html,/Real source changes/);
 assert.match(html,/not a confirmed affected answer/);
 assert.doesNotMatch(html,/CONTRADICTED|SUPPORTED|INSUFFICIENT_SUPPORT/);
 const source=readFileSync("components/live-changes.tsx","utf8");
 assert.match(source,/No example changes were substituted/);
 assert.doesNotMatch(source,/fixtures|exampleWorkspace|AnswerInspector/);
 assert.match(source,/NUMERIC/); assert.match(source,/AUTHORITY_CHANGED/); assert.match(source,/Applicability changes/);
 assert.match(source,/Timeline comparison · not lineage/);
 assert.doesNotMatch(source,/timeline_alignments\.length} complete lineage edge/);
});
test("a successful comparison clears an earlier NOT_FOUND alert",()=>{
 let state:InspectionState={...initialInspectionState,workspace:"w",corpus:"c",delivery:"d",document:"doc"};
 state=inspectionReducer(state,{type:"request",stage:"comparison",id:1,key:"w/c/d/doc"});
 state=inspectionReducer(state,{type:"failure",stage:"comparison",id:1,key:"w/c/d/doc",message:"NOT_FOUND · Changed document not found"});
 assert.match(visibleInspectionError(state),/NOT_FOUND/);
 state=inspectionReducer(state,{type:"request",stage:"comparison",id:2,key:"w/c/d/doc"});
 state=inspectionReducer(state,{type:"success",stage:"comparison",id:2,key:"w/c/d/doc",value:{} as DocumentComparison});
 const html=renderToStaticMarkup(createElement(
   LiveChangeOutcome,
   {error:visibleInspectionError(state),comparison:state.comparison},
   createElement("div",null,"SUCCESSFUL COMPARISON"),
 ));
 assert.match(html,/SUCCESSFUL COMPARISON/);
 assert.doesNotMatch(html,/role="alert"|NOT_FOUND/);
});
test("a slower stale comparison cannot overwrite newer successful state",()=>{
 let state:InspectionState={...initialInspectionState,workspace:"w",corpus:"c",delivery:"d",document:"old"};
 state=inspectionReducer(state,{type:"request",stage:"comparison",id:1,key:"w/c/d/old"});
 state=inspectionReducer(state,{type:"select",stage:"document",value:"new"});
 state=inspectionReducer(state,{type:"request",stage:"comparison",id:2,key:"w/c/d/new"});
 const current={delivery_id:"d",document_id:"new"} as DocumentComparison;
 state=inspectionReducer(state,{type:"success",stage:"comparison",id:2,key:"w/c/d/new",value:current});
 state=inspectionReducer(state,{type:"failure",stage:"comparison",id:1,key:"w/c/d/old",message:"NOT_FOUND"});
 assert.equal(state.comparison,current);
 assert.equal(visibleInspectionError(state),"");
});
test("changing workspace clears downstream selection, comparison, and errors",()=>{
 let state:InspectionState={
  ...initialInspectionState,workspace:"w1",corpus:"c",delivery:"d",document:"doc",
  comparison:{delivery_id:"d",document_id:"doc"} as DocumentComparison,
 };
 state=inspectionReducer(state,{type:"request",stage:"comparison",id:1,key:"w1/c/d/doc"});
 state=inspectionReducer(state,{type:"failure",stage:"comparison",id:1,key:"w1/c/d/doc",message:"NOT_FOUND"});
 assert.match(visibleInspectionError(state),/NOT_FOUND/);
 state=inspectionReducer(state,{type:"select",stage:"workspace",value:"w2"});
 assert.equal(state.workspace,"w2");
 assert.equal(state.corpus,"");
 assert.equal(state.delivery,"");
 assert.equal(state.document,"");
 assert.equal(state.comparison,null);
 assert.equal(visibleInspectionError(state),"");
});
test("storage errors remain typed failures",async()=>{
 const previous=globalThis.fetch;
 globalThis.fetch=async()=>new Response(JSON.stringify({error:{code:"STALE_HEAD",message:"Reload"}}),{status:409});
 try {await assert.rejects(storageRequest("/id"),(e:unknown)=>e instanceof StorageError&&e.code==="STALE_HEAD");} finally {globalThis.fetch=previous;}
 assert.equal(deliveryLabel({status:"PARKED_OUT_OF_ORDER",duplicate:false,snapshot_id:null,error_code:null,delivery_id:"d"}),"PARKED_OUT_OF_ORDER · No new snapshot");
});
test("storage writes accept browser same-origin evidence and reject ambiguous or cross-origin writes",()=>{
 const url="http://localhost:3000/api/storage/workspaces";
 assert.equal(sameOriginWrite(new Request(url,{method:"POST",headers:{origin:"http://localhost:3000"}})),true);
 assert.equal(sameOriginWrite(new Request(url,{method:"POST",headers:{origin:"https://attacker.example"}})),false);
 assert.equal(sameOriginWrite(new Request(url,{method:"POST",headers:{host:"127.0.0.1:3000",origin:"http://127.0.0.1:3000"}})),true);
 assert.equal(sameOriginWrite(new Request(url,{method:"POST",headers:{"x-aftermath-request":"same-origin-browser"}})),true);
 assert.equal(sameOriginWrite(new Request(url,{method:"POST",headers:{origin:"https://attacker.example","x-aftermath-request":"same-origin-browser"}})),false);
 assert.equal(sameOriginWrite(new Request(url,{method:"POST",headers:{"x-aftermath-request":"wrong"}})),false);
 assert.equal(sameOriginWrite(new Request(url,{method:"POST",headers:{"sec-fetch-site":"same-origin",referer:"http://localhost:3000/workspace"}})),true);
 assert.equal(sameOriginWrite(new Request(url,{method:"POST",headers:{"sec-fetch-site":"same-origin",referer:"https://attacker.example/workspace"}})),false);
 assert.equal(sameOriginWrite(new Request(url,{method:"POST",headers:{referer:"http://localhost:3000/workspace"}})),false);
});
test("browser preserves Unicode bytes and limits source size",()=>{
 const source="\uFEFFe\u0301\r\n😀";
 assert.equal(Buffer.from(sourceBase64(source),"base64").toString("utf8"),source);
 assert.throws(()=>sourceBase64("x".repeat(262145)),StorageError);
});
test("only the three centralized pigments occur in active CSS and SVG",()=>{
 const css=readFileSync("app/globals.css","utf8");
 const colors=[...css.matchAll(/#[\da-f]{3,8}\b/gi)].map(m=>m[0].toUpperCase());
 assert.ok(colors.every(c=>["#B8E7F2","#FFF9E8","#382414"].includes(c)));
 assert.doesNotMatch(css,/--(?:blue|butter|danger|success|color-deep-blue)\b|rgba?\(/);
 assert.doesNotMatch(readFileSync("components/sculpture.tsx","utf8"),/#[\da-f]{6}\b/i);
});
