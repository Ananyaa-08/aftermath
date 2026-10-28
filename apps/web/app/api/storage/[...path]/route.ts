import { NextResponse } from "next/server";
import { sameOriginWrite } from "../../../../lib/same-origin";
export const dynamic = "force-dynamic";
const failure = (code: string, message: string, status: number) => NextResponse.json({error:{code,message}}, {status});
async function proxy(request: Request, context: {params: Promise<{path:string[]}>}) {
  const base = process.env.BACKEND_URL;
  if (!base) return failure("UNCONFIGURED", "Backend URL is not configured", 503);
  const {path} = await context.params;
  if (path[0] !== "workspaces" || path.some(p => !/^[a-zA-Z0-9:_@.-]+$/.test(p) || p === "." || p === "..")) return failure("INVALID_PATH", "Invalid storage path", 400);
  if (request.method === "POST" && !sameOriginWrite(request)) return failure("ORIGIN_REJECTED", "Same-origin request required", 403);
  try {
    const url = new URL(`/api/v1/${path.map(encodeURIComponent).join("/")}`, base);
    if (!["http:","https:"].includes(url.protocol)) throw new Error("Invalid backend");
    const query = new URL(request.url).searchParams;
    for (const key of ["limit","offset","document_id","snapshot_id"]) if (query.has(key)) url.searchParams.set(key,query.get(key)!);
    let body: Uint8Array | undefined;
    if (request.method === "POST") {
      if (!request.headers.get("content-type")?.startsWith("application/json")) return failure("INVALID_MEDIA_TYPE","JSON required",415);
      const reader = request.body?.getReader(); const chunks: Uint8Array[] = []; let total = 0;
      if (reader) { while (true) { const {done,value} = await reader.read(); if (done) break; total += value.length; if (total > 1048576) { await reader.cancel(); return failure("BODY_TOO_LARGE","Delivery exceeds 1 MiB",413); } chunks.push(value); } }
      body = new Uint8Array(total); let position = 0; for (const chunk of chunks) { body.set(chunk,position); position += chunk.length; }
    }
    const slow = path.includes("answers") || path.includes("uploads");
    const timeout = slow ? 120000 : 15000;
    const response = await fetch(url, {method:request.method, headers:{"Content-Type":"application/json"}, body:body as BodyInit | undefined, cache:"no-store", redirect:"error", signal:AbortSignal.timeout(timeout)});
    const data: unknown = await response.json();
    return NextResponse.json(data,{status:response.status});
  } catch { return failure("UNREACHABLE", "Storage request could not complete; refresh before retrying a delivery",503); }
}
export const GET = proxy;
export const POST = proxy;
