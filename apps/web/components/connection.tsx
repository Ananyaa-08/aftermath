"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { connectivityText, parseConnectivity, type ConnectivityStatus } from "../lib/connectivity";

export default function Connection() {
  const [status, setStatus] = useState<ConnectivityStatus>("checking");
  const [checkedAt, setCheckedAt] = useState<string | null>(null);
  const request = useRef<AbortController | null>(null);
  const check = useCallback(async () => {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setStatus("checking");
    try {
      const response = await fetch("/api/connectivity", { cache: "no-store", signal: controller.signal });
      const data: unknown = await response.json();
      if (!controller.signal.aborted) setStatus(parseConnectivity(response.ok, data));
    } catch {
      if (!controller.signal.aborted) setStatus("unreachable");
    } finally {
      if (!controller.signal.aborted) setCheckedAt(new Date().toISOString().slice(11, 19) + " UTC");
    }
  }, []);
  useEffect(() => { void check(); return () => request.current?.abort(); }, [check]);
  return <section className="connection-bar" aria-label="Actual backend readiness">
    <div className="connection-label"><span className="mini-cross" aria-hidden="true">✳</span><span className="mono">LIVE SYSTEM</span></div>
    <div className="connection-message"><p role="status" aria-live="polite"><span className={`signal ${status === "ready" ? "signal-ready" : ""}`} aria-hidden="true"/>{connectivityText[status]}</p><span className="connection-time">{checkedAt ? `Last checked ${checkedAt}` : "Reading the configured backend"} · health only</span></div>
    <button className="text-button" onClick={() => void check()} disabled={status === "checking"}>{status === "checking" ? "Checking…" : "Check again"}<span aria-hidden="true"> ↗</span></button>
  </section>;
}
