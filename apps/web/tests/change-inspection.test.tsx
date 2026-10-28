import assert from "node:assert/strict";
import {afterEach, test} from "node:test";
import {JSDOM} from "jsdom";
import {act} from "react";
import {createRoot, type Root} from "react-dom/client";
import LiveChanges from "../components/live-changes";
import type {DocumentComparison, VersionRecord} from "../lib/storage";

type Deferred<T> = {promise: Promise<T>; resolve: (value: T) => void};

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return {promise, resolve};
}

const response = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {status, headers: {"Content-Type": "application/json"}});

const version = (document: string): VersionRecord => ({
  document_version_id: `dv:${document}@r2`,
  source_seq: 2,
  source_timestamp: "2026-02-01T00:00:00Z",
  effective_from: "2026-02-01T00:00:00Z",
  effective_from_source: "DECLARED_METADATA",
  source_type: "product_doc",
  content_hash: "sha256:" + "1".repeat(64),
  source_bytes_hash: "sha256:" + "1".repeat(64),
  normalization_version: "canon-v1",
  is_deletion: false,
  text: "Current source text",
  authority: {},
});

const comparison = (document: string): DocumentComparison => ({
  delivery_id: "d1",
  document_id: document,
  parent_snapshot_id: "snap:000001",
  result_snapshot_id: "snap:000002",
  old_version: null,
  new_version: version(document),
  old_passages: [],
  new_passages: [],
  edges: [],
  timeline_alignments: [],
  spans: [],
  applicability_changes: [],
});

let mountedRoot: Root | null = null;
let dom: JSDOM | null = null;
const originalFetch = globalThis.fetch;

afterEach(async () => {
  if (mountedRoot) await act(async () => mountedRoot?.unmount());
  mountedRoot = null;
  dom?.window.close();
  dom = null;
  globalThis.fetch = originalFetch;
});

async function eventually(predicate: () => boolean, message: string): Promise<void> {
  for (let attempt = 0; attempt < 80; attempt += 1) {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    if (predicate()) return;
  }
  assert.fail(message);
}

test("mounted live inspection clears stale failures and isolates concurrent requests", async () => {
  dom = new JSDOM("<!doctype html><div id='root'></div>", {
    url: "http://localhost/workspace?workspace=w1&corpus=c1&delivery=d1&document=doc1",
  });
  Object.assign(globalThis, {
    window: dom.window,
    document: dom.window.document,
    Event: dom.window.Event,
    HTMLElement: dom.window.HTMLElement,
  });
  Object.defineProperty(globalThis, "navigator", {value: dom.window.navigator, configurable: true});
  (globalThis as typeof globalThis & {IS_REACT_ACT_ENVIRONMENT: boolean}).IS_REACT_ACT_ENVIRONMENT =
    true;

  const comparisonQueues = new Map<string, Array<Response | Promise<Response>>>();
  const requests: Array<{kind: string; signal?: AbortSignal}> = [];
  let refresh = new Map<string, Deferred<Response>>();
  let captureRefreshSignals = false;
  comparisonQueues.set("doc1", [
    response({error: {code: "NOT_FOUND", message: "Changed document not found"}}, 404),
  ]);

  globalThis.fetch = async (input, init) => {
    const url = String(input);
    let kind = "unknown";
    if (/\/comparison$/.test(url)) kind = "comparison";
    else if (/\/documents$/.test(url)) kind = "documents";
    else if (/\/updates\?/.test(url)) kind = "events";
    else if (/\/corpora\?/.test(url)) kind = "corpora";
    else if (/workspaces\?/.test(url)) kind = "workspaces";
    if (captureRefreshSignals) requests.push({kind, signal: init?.signal ?? undefined});
    const held = refresh.get(kind);
    if (held) return held.promise;
    if (kind === "workspaces") return response([{id: "w1", name: "Live workspace"}]);
    if (kind === "corpora") {
      return response([
        {corpus_id: "c1", name: "Live corpus", head_snapshot_id: "snap:000002", document_count: 2, version_count: 4},
      ]);
    }
    if (kind === "events") {
      return response([
        {delivery_id: "d1", update_event_id: "upd:d1", as_of: "2026-02-01T00:00:00Z", expected_head: "snap:000001", received_at: "2026-02-01T00:00:00Z", status: "APPLIED", snapshot_id: "snap:000002", error_code: null},
      ]);
    }
    if (kind === "documents") {
      return response([
        {document_id: "doc1", old_version_id: null, new_version_id: "dv:doc1@r2", span_count: 0, applicability_count: 0},
        {document_id: "doc2", old_version_id: null, new_version_id: "dv:doc2@r2", span_count: 0, applicability_count: 0},
      ]);
    }
    const document = decodeURIComponent(url.split("/").at(-2) ?? "");
    const queued = comparisonQueues.get(document)?.shift();
    return queued ? await queued : response(comparison(document));
  };

  const container = dom.window.document.querySelector("#root") as HTMLElement;
  mountedRoot = createRoot(container);
  await act(async () => mountedRoot?.render(<LiveChanges />));
  await eventually(() => container.textContent?.includes("NOT_FOUND") ?? false, "initial error missing");
  assert.ok(container.querySelector("[role='alert']"));

  const documentSelect = container.querySelectorAll("select")[3] as HTMLSelectElement;
  documentSelect.value = "doc2";
  await act(async () => documentSelect.dispatchEvent(new dom!.window.Event("change", {bubbles: true})));
  await eventually(
    () => container.textContent?.includes("d1 / doc2") ?? false,
    "successful comparison did not render",
  );
  assert.equal(container.querySelector("[role='alert']"), null);
  assert.doesNotMatch(container.textContent ?? "", /NOT_FOUND|No example changes were substituted/);

  for (const staleStatus of [200, 404]) {
    const slow = deferred<Response>();
    comparisonQueues.set("doc1", [slow.promise]);
    documentSelect.value = "doc1";
    await act(async () =>
      documentSelect.dispatchEvent(new dom!.window.Event("change", {bubbles: true})),
    );
    await eventually(
      () => (comparisonQueues.get("doc1")?.length ?? 1) === 0,
      "slow comparison did not start",
    );
    documentSelect.value = "doc2";
    await act(async () =>
      documentSelect.dispatchEvent(new dom!.window.Event("change", {bubbles: true})),
    );
    await eventually(
      () => container.textContent?.includes("d1 / doc2") ?? false,
      "newer comparison did not win",
    );
    slow.resolve(
      staleStatus === 200
        ? response(comparison("doc1"))
        : response({error: {code: "NOT_FOUND", message: "Stale failure"}}, 404),
    );
    await act(async () => Promise.resolve());
    assert.match(container.textContent ?? "", /d1 \/ doc2/);
    assert.equal(container.querySelector("[role='alert']"), null);
  }

  refresh = new Map(
    ["workspaces", "corpora", "events", "documents", "comparison"].map((kind) => [
      kind,
      deferred<Response>(),
    ]),
  );
  const retry = [...container.querySelectorAll("button")].find((item) =>
    item.textContent?.includes("Retry"),
  )!;
  await act(async () => retry.click());
  assert.ok(container.querySelector("[role='status']"));
  refresh.get("workspaces")!.resolve(response([{id: "w1", name: "Live workspace"}]));
  await act(async () => Promise.resolve());
  assert.ok(container.querySelector("[role='status']"), "one completion cleared concurrent loading");
  refresh.get("corpora")!.resolve(
    response([{corpus_id: "c1", name: "Live corpus", head_snapshot_id: "snap:000002", document_count: 2, version_count: 4}]),
  );
  refresh.get("events")!.resolve(response([{delivery_id: "d1", update_event_id: "upd:d1", as_of: "2026-02-01T00:00:00Z", expected_head: "snap:000001", received_at: "2026-02-01T00:00:00Z", status: "APPLIED", snapshot_id: "snap:000002", error_code: null}]));
  refresh.get("documents")!.resolve(response([{document_id: "doc1", old_version_id: null, new_version_id: "dv:doc1@r2", span_count: 0, applicability_count: 0}, {document_id: "doc2", old_version_id: null, new_version_id: "dv:doc2@r2", span_count: 0, applicability_count: 0}]));
  refresh.get("comparison")!.resolve(response(comparison("doc2")));
  await eventually(() => container.querySelector("[role='status']") === null, "loading did not settle");
  assert.equal(documentSelect.value, "doc2", "retry reapplied the one-shot doc1 preset");

  refresh = new Map(
    ["workspaces", "corpora", "events", "documents", "comparison"].map((kind) => [
      kind,
      deferred<Response>(),
    ]),
  );
  captureRefreshSignals = true;
  await act(async () => retry.click());
  await eventually(() => requests.length === 5, "concurrent refresh requests did not start");
  await act(async () => mountedRoot?.unmount());
  mountedRoot = null;
  assert.ok(requests.every((item) => item.signal?.aborted), "unmount left a request active");
  assert.doesNotMatch(container.textContent ?? "", /CONTRADICTED|SUPPORTED|exampleWorkspace/);
});
