import { NextResponse } from "next/server";
import { backendReady } from "../../../lib/connectivity";

export const dynamic = "force-dynamic";
export async function GET() {
  const base = process.env.BACKEND_URL;
  if (!base) return NextResponse.json({ status: "unconfigured" }, { status: 503 });
  try {
    const url = new URL("/health/ready", base);
    if (!["http:", "https:"].includes(url.protocol)) throw new Error("Invalid protocol");
    const result = await fetch(url, { cache: "no-store", signal: AbortSignal.timeout(5000) });
    const data: unknown = await result.json();
    if (backendReady(result.ok, data)) {
      return NextResponse.json({ status: "ready" });
    }
    return NextResponse.json({ status: "unavailable" }, { status: 503 });
  } catch {
    return NextResponse.json({ status: "unreachable" }, { status: 503 });
  }
}
