export function sameOriginWrite(request: Request): boolean {
  const target = new URL(request.url);
  const expected = request.headers.get("host")
    ? `${target.protocol}//${request.headers.get("host")}`
    : target.origin;
  const origin = request.headers.get("origin");
  if (origin) return origin === expected;
  if (request.headers.get("x-aftermath-request") === "same-origin-browser") return true;
  const referer = request.headers.get("referer");
  if (request.headers.get("sec-fetch-site") !== "same-origin" || !referer) return false;
  try {
    return new URL(referer).origin === expected;
  } catch {
    return false;
  }
}
