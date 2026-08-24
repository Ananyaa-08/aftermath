/** Presentation contracts mirror Python enum names; no inference or policy resolution. */
export const workflowStates = ["UNASSESSED", "QUEUED", "IN_PROGRESS", "COMPLETED", "FAILED", "WITHHELD"] as const;
export type WorkflowState = (typeof workflowStates)[number];
export const semanticStatuses = ["SUPPORTED", "CONTRADICTED", "INSUFFICIENT_SUPPORT", "UNRESOLVED_CONFLICT"] as const;
export type SemanticStatus = (typeof semanticStatuses)[number];
export type Scope = "ROLLING_CURRENT" | "FIXED_TIME" | "FIXED_VERSION";
export type WorkspaceMode = "live" | "example";
export type View = "overview" | "inspect" | "experiments";
export interface Evidence {
  reference: string;
  text: string;
  authority: string;
}
export interface Claim {
  id: string;
  text: string;
  status: SemanticStatus | null;
  explanation: string;
  before: Evidence | null;
  after: Evidence | null;
}
export interface ExampleAnswer {
  id: string;
  question: string;
  answer: string;
  scope: Scope;
  scopeDetail: string;
  workflow: WorkflowState;
  verdict: { status: SemanticStatus; snapshot: string; evaluationTime: string; policy: string } | null;
  selectionReason: string;
  claims: Claim[];
  history: { snapshot: string; label: string; detail: string }[];
}
export interface ExampleWorkspace {
  kind: "example";
  name: string;
  snapshot: string;
  answers: ExampleAnswer[];
}

/** No fallback from absent live data to fixtures. */
export function workspaceForMode(mode: WorkspaceMode, example: ExampleWorkspace): ExampleWorkspace | null {
  return mode === "example" ? example : null;
}

/** Display a recorded final verdict only when the assessment completed at this snapshot. */
export function currentVerdict(answer: ExampleAnswer, snapshot: string): SemanticStatus | null {
  return answer.workflow === "COMPLETED" && answer.verdict?.snapshot === snapshot
    ? answer.verdict.status : null;
}

export function verdictLabel(answer: ExampleAnswer, snapshot: string): string {
  const verdict = currentVerdict(answer, snapshot);
  if (verdict) return verdict;
  if (answer.workflow === "FAILED") return "No verdict · assessment failed";
  if (answer.workflow === "WITHHELD") return "No verdict · assessment withheld";
  if (answer.workflow === "QUEUED" || answer.workflow === "IN_PROGRESS") return "No current verdict · pending";
  if (answer.verdict) return "Historical verdict only";
  return "No verdict · not assessed";
}

export function filterAnswers(answers: ExampleAnswer[], search: string, workflow: string, sort: string): ExampleAnswer[] {
  const query = search.trim().toLowerCase();
  return answers.filter(answer => (workflow === "ALL" || answer.workflow === workflow)
    && `${answer.id} ${answer.question} ${answer.answer}`.toLowerCase().includes(query))
    .sort((a, b) => sort === "question" ? a.question.localeCompare(b.question) : a.id.localeCompare(b.id));
}
