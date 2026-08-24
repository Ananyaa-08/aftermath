import type { Evidence, ExampleAnswer, ExampleWorkspace } from "../lib/workspace";

// Authored display fixtures, not model outputs, evaluation gold, or live API responses.
const original: Evidence = {
  reference: "dv:export-guide@r1 · §2 · tier 2",
  text: "Bulk export is available to all paid plans. Exports are delivered as CSV files. Workspace owners can export the entire archive from Settings → Data.",
  authority: "Product documentation · authority tier 2",
};
const revised: Evidence = {
  reference: "dv:export-guide@r2 · §2 · tier 2",
  text: "Bulk export is available to Pro and Enterprise plans. Exports are delivered as CSV files. Workspace owners can export the entire archive from Settings → Data. Starter workspaces can still download individual records; this does not include an archive-wide export.",
  authority: "Product documentation · authority tier 2",
};
const verdict = (status: NonNullable<ExampleAnswer["verdict"]>["status"]) => ({
  status, snapshot: "snap:000002", evaluationTime: "2026-11-01T09:00:00.000Z", policy: "example-policy-v1",
});
const pendingClaim = (id: string, text: string, explanation: string) => ({
  id, text, status: null, explanation, before: original, after: null,
});
export const exampleWorkspace: ExampleWorkspace = {
  kind: "example", name: "Fieldnotes / Export policy", snapshot: "snap:000002",
  answers: [
    {
      id: "av:starter-export@1", question: "Can I export our entire archive on the Starter plan?",
      answer: "Yes. Your Starter plan supports bulk export, and the archive is delivered as a CSV file.",
      scope: "ROLLING_CURRENT", scopeDetail: "Current use · evaluated at 01 Nov 2026, 09:00 UTC",
      workflow: "COMPLETED", verdict: verdict("CONTRADICTED"),
      selectionReason: "PROVENANCE_CITATION · cites the replaced export-policy passage. Selection identifies a candidate; it does not establish impact.",
      claims: [
        { id: "clm:starter-export@1#c01", text: "The Starter plan supports bulk export.", status: "CONTRADICTED", before: original, after: revised,
          explanation: "Illustrative policy-resolved verdict: the applicable r2 passage restricts bulk export to Pro and Enterprise. Under the declared example policy, r2 supersedes r1. The current-use Starter claim is contradicted." },
        { id: "clm:starter-export@1#c02", text: "The archive is delivered as a CSV file.", status: "SUPPORTED", before: original, after: revised,
          explanation: "Illustrative policy-resolved verdict: CSV remains explicitly stated in the applicable r2 evidence. This claim was separately assessed; an unchanged sentence alone would not establish continued support." },
      ],
      history: [
        { snapshot: "snap:000001", label: "SUPPORTED · historical", detail: "Example initial assessment against r1. This verdict remains bound to the old snapshot." },
        { snapshot: "snap:000002", label: "CONTRADICTED · current example", detail: "One material claim is contradicted; the CSV claim remains supported. These are authored fixtures, not computed results." },
      ],
    },
    {
      id: "av:october-export@1", question: "Was bulk export included in Starter on 15 October 2026?",
      answer: "Yes. On 15 October 2026, all paid plans included bulk export.",
      scope: "FIXED_TIME", scopeDetail: "Historical question · 2026-10-15T00:00:00.000Z",
      workflow: "COMPLETED", verdict: { ...verdict("SUPPORTED"), evaluationTime: "2026-10-15T00:00:00.000Z" },
      selectionReason: "EXHAUSTIVE · included in the example check set. New source text does not silently change a historical question.",
      claims: [{ id: "clm:october-export@1#c01", text: "Starter included bulk export on 15 October.", status: "SUPPORTED", before: original, after: original,
        explanation: "The question remains fixed to 15 October. In this fixture, r1 was effective then; r2 takes effect on 1 November. The historical claim is assessed using r1 with knowledge at snap:000002." }],
      history: [],
    },
    {
      id: "av:delivery-time@1", question: "Will a large archive export be ready within 24 hours, including workspaces with more than a million records and attachments retained under a custom data policy?",
      answer: "Every archive export will be ready within 24 hours, regardless of archive size.",
      scope: "ROLLING_CURRENT", scopeDetail: "Current use · evaluated at 01 Nov 2026, 09:00 UTC",
      workflow: "COMPLETED", verdict: verdict("INSUFFICIENT_SUPPORT"),
      selectionReason: "SIMILARITY · shares the export topic. A topic match is not confirmed impact.",
      claims: [{ id: "clm:delivery-time@1#c01", text: "Every archive export is ready within 24 hours.", status: "INSUFFICIENT_SUPPORT", before: null, after: revised,
        explanation: "Neither support nor contradiction for a 24-hour guarantee was found in the example evidence bundle. This is a retrieval-bounded conclusion, not proof that the claim is false or that no supporting passage exists elsewhere." }],
      history: [],
    },
    {
      id: "av:trial-export@1", question: "Does a Pro trial include bulk export?",
      answer: "All Pro trials include bulk export.", scope: "ROLLING_CURRENT", scopeDetail: "Current use · evaluated at 01 Nov 2026, 09:00 UTC",
      workflow: "COMPLETED", verdict: verdict("UNRESOLVED_CONFLICT"),
      selectionReason: "DISCOVERY · new trial guidance conflicts with an unchanged citation. Freshness alone does not settle support.",
      claims: [{ id: "clm:trial-export@1#c01", text: "All Pro trials include bulk export.", status: "UNRESOLVED_CONFLICT",
        before: { reference: "dv:trial-guide@r1 · tier 2", text: "Pro trials include bulk export for the duration of the trial.", authority: "Product documentation · authority tier 2 · still applicable" },
        after: { reference: "dv:trial-faq@r1 · tier 2", text: "Bulk export is excluded from all Pro trials.", authority: "Product FAQ · authority tier 2 · also applicable" },
        explanation: "Two applicable sources at the same authority tier disagree. The example source policy does not break this tie. The unchanged citation is not a reason to ignore the new contradiction." }],
      history: [],
    },
    {
      id: "av:scheduled-export@1", question: "Can Starter schedule a weekly archive export?",
      answer: "Starter can schedule a weekly export.", scope: "ROLLING_CURRENT", scopeDetail: "Current use · target snap:000002",
      workflow: "FAILED", verdict: null,
      selectionReason: "PROVENANCE_CITATION · associated source changed; assessment could not complete.",
      claims: [pendingClaim("clm:scheduled-export@1#c01", "Starter can schedule a weekly export.", "Example operational failure: PROVIDER_ERROR after retries. No policy-resolved verdict exists. The provider error does not establish whether this claim is supported, contradicted, or missing evidence.")],
      history: [],
    },
    {
      id: "av:enterprise-export@1", question: "Can Enterprise export the full archive?",
      answer: "Enterprise includes full-archive export.", scope: "ROLLING_CURRENT", scopeDetail: "Current use · target snap:000002",
      workflow: "QUEUED", verdict: null,
      selectionReason: "PROVENANCE_CITATION · queued because its citation changed; no new assessment yet.",
      claims: [pendingClaim("clm:enterprise-export@1#c01", "Enterprise includes full-archive export.", "Example queued assessment. No new semantic conclusion can be drawn while the work is pending.")],
      history: [{ snapshot: "snap:000001", label: "SUPPORTED · historical only", detail: "A prior example verdict exists at r1. It is not a new verification at snap:000002." }],
    },
    {
      id: "av:retention-export@1", question: "Are archived records kept after an export?",
      answer: "Records remain in the workspace after export.", scope: "ROLLING_CURRENT", scopeDetail: "Current use · target snap:000002",
      workflow: "WITHHELD", verdict: null, selectionReason: "SIMILARITY · selected but the example policy withheld assessment.",
      claims: [pendingClaim("clm:retention-export@1#c01", "Records remain after export.", "The example assessment was withheld by policy. Withholding is a workflow disposition, not a claim that the answer is false.")],
      history: [],
    },
    {
      id: "av:version-one@1", question: "What does revision r1 say about export formats?",
      answer: "Revision r1 says exports are delivered as CSV files.", scope: "FIXED_VERSION", scopeDetail: "Version-bound · dv:export-guide@r1",
      workflow: "UNASSESSED", verdict: null,
      selectionReason: "TEMPORALLY_EXCLUDED · fixed-version question; r1 is immutable. Not selected, and no new verdict is created.",
      claims: [pendingClaim("clm:version-one@1#c01", "Revision r1 specifies CSV files.", "Not assessed in this example run. A fixed-version question retains its original scope; temporal exclusion is not a new semantic verification.")],
      history: [],
    },
  ],
};
export const exampleSource = {
  id: "export-guide", title: "Export policy", before: original, after: revised,
  observedAt: "2026-11-01T09:00:00.000Z", effectiveAt: "2026-11-01T00:00:00.000Z",
};
