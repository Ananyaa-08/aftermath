export type ConnectivityStatus = "checking" | "ready" | "unavailable" | "unreachable" | "unconfigured";
export const connectivityText: Record<ConnectivityStatus, string> = {
  checking: "Checking backend readiness…",
  ready: "API connected · PostgreSQL ready",
  unavailable: "API responded · readiness unavailable",
  unreachable: "Backend could not be reached",
  unconfigured: "Backend URL not configured",
};

/** Both HTTP success and the dependency payload are required; no optimistic green state. */
export function backendReady(ok: boolean, data: unknown): boolean {
  if (!ok || typeof data !== "object" || data === null || !("status" in data) || data.status !== "ready"
    || !("dependencies" in data) || typeof data.dependencies !== "object" || data.dependencies === null) return false;
  return "postgresql" in data.dependencies && data.dependencies.postgresql === "ready";
}

export function parseConnectivity(ok: boolean, data: unknown): Exclude<ConnectivityStatus, "checking"> {
  if (typeof data !== "object" || data === null || !("status" in data)) return "unreachable";
  if (data.status === "ready") return ok ? "ready" : "unavailable";
  if (["unavailable", "unreachable", "unconfigured"].includes(String(data.status))) {
    return data.status as "unavailable" | "unreachable" | "unconfigured";
  }
  return "unreachable";
}
