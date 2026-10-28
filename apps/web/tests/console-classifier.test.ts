import assert from "node:assert/strict";
import test from "node:test";
import {classifyConsoleError, withConsoleScope, type ConsoleScope} from "../scripts/console-classifier.mjs";

test("expected HTTP errors never hide React, hydration, JavaScript, or another URL", () => {
  const url = "http://127.0.0.1:3001/api/storage/workspaces/w/comparison";
  const scope = {scenario: "injected-not-found", failures: [{url, status: 404}]};
  const resource = "Failed to load resource: the server responded with a status of 404 (Not Found)";
  assert.equal(classifyConsoleError({kind: "console", text: resource, url}, scope).expected, true);
  for (const text of ["Hydration failed", "Minified React error #418", "TypeError: x is undefined", "Uncaught ReferenceError", resource + " unrelated"]) {
    assert.equal(classifyConsoleError({kind: "console", text, url}, scope).expected, false);
  }
  for (const other of ["", "http://evil.example/api/storage/workspaces/w/comparison", url + "?different=1", "http://127.0.0.1:3001/_next/static/chunk.js"]) {
    assert.equal(classifyConsoleError({kind: "console", text: resource, url: other}, scope).expected, false);
  }
  assert.equal(classifyConsoleError({kind: "pageerror", text: resource, url}, scope).expected, false);
  assert.equal(classifyConsoleError({kind: "console", text: resource, url}).expected, false);
  const unavailable = {scenario: "db-down", failures: [{url, status: 503}]};
  assert.equal(classifyConsoleError({kind: "console", text: resource, url}, unavailable).expected, false);
  assert.equal(classifyConsoleError({kind: "console", text: resource.replace("404 (Not Found)", "503 (Service Unavailable)"), url}, unavailable).expected, true);
});

test("console scopes are page-local and reset on success and failure", async () => {
  const scopes = new WeakMap<object, ConsoleScope>();
  const page = {}, otherPage = {};
  const scope = {scenario: "retry", failures: []};
  await withConsoleScope(scopes, page, scope, async () => {
    assert.equal(scopes.get(page), scope);
    assert.equal(scopes.has(otherPage), false);
    await assert.rejects(withConsoleScope(scopes, page, scope, async () => {}), /Overlapping/);
  });
  assert.equal(scopes.has(page), false);
  await assert.rejects(withConsoleScope(scopes, page, scope, async () => {
    throw new Error("operation failed");
  }), /operation failed/);
  assert.equal(scopes.has(page), false);
});
