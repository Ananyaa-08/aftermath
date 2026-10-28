import type {
  ChangedDocumentRecord,
  CorpusRecord,
  DocumentComparison,
  UpdateEventRecord,
  WorkspaceRecord,
} from "./storage";

export type Stage = "workspaces" | "corpora" | "events" | "documents" | "comparison";
type Request = {id: number; key: string};
type Failure = {key: string; message: string};

export type InspectionState = {
  workspaces: WorkspaceRecord[];
  workspace: string;
  corpora: CorpusRecord[];
  corpus: string;
  events: UpdateEventRecord[];
  delivery: string;
  documents: ChangedDocumentRecord[];
  document: string;
  comparison: DocumentComparison | null;
  requests: Partial<Record<Stage, Request>>;
  errors: Partial<Record<Stage, Failure>>;
};

export const initialInspectionState: InspectionState = {
  workspaces: [],
  workspace: "",
  corpora: [],
  corpus: "",
  events: [],
  delivery: "",
  documents: [],
  document: "",
  comparison: null,
  requests: {},
  errors: {},
};

export type InspectionAction =
  | {type: "select"; stage: "workspace" | "corpus" | "delivery" | "document"; value: string}
  | {type: "request"; stage: Stage; id: number; key: string}
  | {type: "success"; stage: Stage; id: number; key: string; value: unknown}
  | {type: "failure"; stage: Stage; id: number; key: string; message: string};

const currentKey = (state: InspectionState, stage: Stage) => {
  if (stage === "workspaces") return "root";
  if (stage === "corpora") return state.workspace;
  if (stage === "events") return `${state.workspace}/${state.corpus}`;
  if (stage === "documents") return `${state.workspace}/${state.corpus}/${state.delivery}`;
  return `${state.workspace}/${state.corpus}/${state.delivery}/${state.document}`;
};

const valid = (state: InspectionState, stage: Stage, id: number, key: string) =>
  state.requests[stage]?.id === id &&
  state.requests[stage]?.key === key &&
  currentKey(state, stage) === key;

function without<T extends Record<string, unknown>>(value: T, keys: string[]): T {
  return Object.fromEntries(Object.entries(value).filter(([key]) => !keys.includes(key))) as T;
}

export function inspectionReducer(
  state: InspectionState,
  action: InspectionAction,
): InspectionState {
  if (action.type === "select") {
    if (state[action.stage] === action.value) return state;
    if (action.stage === "workspace") {
      return {
        ...state,
        workspace: action.value,
        corpora: [],
        corpus: "",
        events: [],
        delivery: "",
        documents: [],
        document: "",
        comparison: null,
        requests: without(state.requests, ["corpora", "events", "documents", "comparison"]),
        errors: without(state.errors, ["corpora", "events", "documents", "comparison"]),
      };
    }
    if (action.stage === "corpus") {
      return {
        ...state,
        corpus: action.value,
        events: [],
        delivery: "",
        documents: [],
        document: "",
        comparison: null,
        requests: without(state.requests, ["events", "documents", "comparison"]),
        errors: without(state.errors, ["events", "documents", "comparison"]),
      };
    }
    if (action.stage === "delivery") {
      return {
        ...state,
        delivery: action.value,
        documents: [],
        document: "",
        comparison: null,
        requests: without(state.requests, ["documents", "comparison"]),
        errors: without(state.errors, ["documents", "comparison"]),
      };
    }
    return {
      ...state,
      document: action.value,
      comparison: null,
      requests: without(state.requests, ["comparison"]),
      errors: without(state.errors, ["comparison"]),
    };
  }

  if (action.type === "request") {
    return {
      ...state,
      requests: {...state.requests, [action.stage]: {id: action.id, key: action.key}},
      errors: without(state.errors, [action.stage]),
    };
  }
  if (!valid(state, action.stage, action.id, action.key)) return state;

  const requests = without(state.requests, [action.stage]);
  if (action.type === "failure") {
    let errors = {
      ...without(state.errors, [action.stage]),
      [action.stage]: {key: action.key, message: action.message},
    };
    if (action.stage === "workspaces") {
      return {...initialInspectionState, errors: {workspaces: errors.workspaces}};
    }
    if (action.stage === "corpora") {
      errors = without(errors, ["events", "documents", "comparison"]);
      return {
        ...state,
        corpora: [],
        corpus: "",
        events: [],
        delivery: "",
        documents: [],
        document: "",
        comparison: null,
        requests: without(requests, ["events", "documents", "comparison"]),
        errors,
      };
    }
    if (action.stage === "events") {
      errors = without(errors, ["documents", "comparison"]);
      return {
        ...state,
        events: [],
        delivery: "",
        documents: [],
        document: "",
        comparison: null,
        requests: without(requests, ["documents", "comparison"]),
        errors,
      };
    }
    if (action.stage === "documents") {
      return {
        ...state,
        documents: [],
        document: "",
        comparison: null,
        requests: without(requests, ["comparison"]),
        errors: without(errors, ["comparison"]),
      };
    }
    return {...state, comparison: null, requests, errors};
  }

  const errors = without(state.errors, [action.stage]);
  if (action.stage === "workspaces") {
    return {...state, workspaces: action.value as WorkspaceRecord[], requests, errors};
  }
  if (action.stage === "corpora") {
    return {...state, corpora: action.value as CorpusRecord[], requests, errors};
  }
  if (action.stage === "events") {
    return {...state, events: action.value as UpdateEventRecord[], requests, errors};
  }
  if (action.stage === "documents") {
    return {...state, documents: action.value as ChangedDocumentRecord[], requests, errors};
  }
  return {...state, comparison: action.value as DocumentComparison, requests, errors};
}

const errorPriority: Stage[] = ["comparison", "documents", "events", "corpora", "workspaces"];

export const visibleInspectionError = (state: InspectionState) =>
  errorPriority.map((stage) => state.errors[stage]?.message).find(Boolean) ?? "";

export const isInspectionLoading = (state: InspectionState) =>
  Object.keys(state.requests).length > 0;

export function availablePreset(value: string, options: string[]): string {
  return value && options.includes(value) ? value : "";
}
