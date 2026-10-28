/** Only Chromium HTTP resource errors for the exact scenario URL/status qualify. */
export function classifyConsoleError(event, scope) {
  if (event.kind !== "console" || !scope) return {expected: false, scenario: null};
  const messages = {
    404: "Failed to load resource: the server responded with a status of 404 (Not Found)",
    503: "Failed to load resource: the server responded with a status of 503 (Service Unavailable)",
  };
  const match = scope.failures.some(failure =>
    failure.url === event.url && messages[failure.status] === event.text,
  );
  return {expected: match, scenario: scope.scenario, category: match ? "http-resource" : null};
}

/** A scope belongs to one page and is always removed, including on exceptions. */
export async function withConsoleScope(scopes, page, scope, operation) {
  if (scopes.has(page)) throw new Error("Overlapping expected-console scopes");
  scopes.set(page, scope);
  try {
    return await operation();
  } finally {
    scopes.delete(page);
  }
}
