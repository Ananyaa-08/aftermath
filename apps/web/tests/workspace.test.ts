import assert from "node:assert/strict";
import { test } from "node:test";
import { exampleWorkspace } from "../fixtures/example-workspace";
import { currentVerdict, filterAnswers, semanticStatuses, verdictLabel, workflowStates, workspaceForMode } from "../lib/workspace";
import { backendReady, parseConnectivity } from "../lib/connectivity";

test("live mode never receives example records, including after mode changes", () => {
  assert.equal(workspaceForMode("live", exampleWorkspace), null);
  assert.equal(workspaceForMode("example", exampleWorkspace)?.kind, "example");
  assert.equal(workspaceForMode("live", exampleWorkspace), null);
});

test("provider failure, queued, withheld and unassessed work never become semantic verdicts", () => {
  const completed = exampleWorkspace.answers[0];
  for (const workflow of ["FAILED", "QUEUED", "IN_PROGRESS", "WITHHELD", "UNASSESSED"] as const) {
    // Even a stale/erroneous verdict field must not be shown as a new result.
    const answer = { ...completed, workflow };
    assert.equal(currentVerdict(answer, exampleWorkspace.snapshot), null);
    assert.doesNotMatch(verdictLabel(answer, exampleWorkspace.snapshot), /^INSUFFICIENT_SUPPORT$/);
  }
  assert.equal(verdictLabel({ ...completed, workflow: "FAILED" }, exampleWorkspace.snapshot), "No verdict · assessment failed");
});

test("a completed verdict is bound to its own snapshot", () => {
  assert.equal(currentVerdict(exampleWorkspace.answers[0], "snap:000002"), "CONTRADICTED");
  assert.equal(currentVerdict(exampleWorkspace.answers[0], "snap:000003"), null);
  assert.equal(verdictLabel(exampleWorkspace.answers[0], "snap:000003"), "Historical verdict only");
});

test("fixtures use literal contract enums and separate pending state from final verdict", () => {
  for (const answer of exampleWorkspace.answers) {
    assert.ok(workflowStates.includes(answer.workflow));
    if (answer.verdict) {
      assert.equal(answer.workflow, "COMPLETED");
      assert.ok(semanticStatuses.includes(answer.verdict.status));
      assert.ok(answer.verdict.snapshot && answer.verdict.evaluationTime && answer.verdict.policy);
    } else {
      assert.ok(answer.claims.every(claim => claim.status === null));
    }
  }
  const historical = exampleWorkspace.answers.find(answer => answer.scope === "FIXED_TIME")!;
  assert.match(historical.scopeDetail, /2026-10-15/);
  assert.equal(historical.verdict?.evaluationTime, "2026-10-15T00:00:00.000Z");
});

test("filters preserve original records and represent empty results honestly", () => {
  assert.equal(filterAnswers(exampleWorkspace.answers, "no-such-question", "ALL", "id").length, 0);
  assert.equal(filterAnswers(exampleWorkspace.answers, "", "FAILED", "id")[0].workflow, "FAILED");
  assert.equal(filterAnswers(exampleWorkspace.answers, "", "IN_PROGRESS", "id").length, 0);
  assert.equal(exampleWorkspace.answers[0].id, "av:starter-export@1");
});

test("healthy state requires HTTP success AND a healthy PostgreSQL dependency", () => {
  const ready = { status: "ready", dependencies: { postgresql: "ready" } };
  assert.equal(backendReady(true, ready), true);
  assert.equal(backendReady(false, ready), false);
  assert.equal(backendReady(true, { status: "ready" }), false);
  assert.equal(backendReady(true, { status: "ready", dependencies: { postgresql: "unavailable" } }), false);
  assert.equal(backendReady(true, null), false);
  assert.equal(parseConnectivity(false, { status: "ready" }), "unavailable");
  assert.equal(parseConnectivity(true, { status: "invented" }), "unreachable");
  assert.equal(parseConnectivity(false, { status: "unconfigured" }), "unconfigured");
});
