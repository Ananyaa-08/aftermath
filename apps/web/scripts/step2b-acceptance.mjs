#!/usr/bin/env node
/**
 * Step 2B browser acceptance. Writes reviewable evidence (results.json, summary.md,
 * screenshots) to docs/acceptance/step2b/<timestamp>-<state>/ and exits non-zero on any
 * failed check. Never substitutes fixtures and never deletes data.
 *
 *   node scripts/step2b-acceptance.mjs --state=healthy        seeds a NEW workspace (disposable data)
 *   node scripts/step2b-acceptance.mjs --state=db-down        API running, PostgreSQL stopped
 *   node scripts/step2b-acceptance.mjs --state=backend-down   API process stopped
 *   node scripts/step2b-acceptance.mjs --state=unconfigured   web started with BACKEND_URL empty
 *
 * Options: --web=http://localhost:3000  --out=docs/acceptance/step2b
 * (AFTERMATH_ACCEPTANCE_STATE / AFTERMATH_BASE_URL are accepted as fallbacks.)
 */
import {mkdir, writeFile} from "node:fs/promises";
import path from "node:path";
import {fileURLToPath} from "node:url";
import {chromium} from "playwright";
import {classifyConsoleError, withConsoleScope} from "./console-classifier.mjs";

const args = Object.fromEntries(process.argv.slice(2).map(item => item.replace(/^--/, "").split("=")));
const state = args.state ?? process.env.AFTERMATH_ACCEPTANCE_STATE ?? "healthy";
const web = (args.web ?? process.env.AFTERMATH_BASE_URL ?? "http://localhost:3000").replace(/\/$/, "");
if (!["healthy", "db-down", "backend-down", "unconfigured"].includes(state)) throw new Error(`Unknown state ${state}`);
const stamp = new Date().toISOString().replace(/[:.]/g, "-");
const repository = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const out = path.resolve(args.out ?? path.join(repository, "docs/acceptance/step2b"), `${stamp}-${state}`);
await mkdir(out, {recursive: true});

const results = {state, web, started_at: new Date().toISOString(), browser: null, checks: [], notes: [], measurements: {}, screenshots: [], console: []};
const check = (name, passed, detail = {}) => { results.checks.push({name, passed: Boolean(passed), ...detail}); console.log(`${passed ? "PASS" : "FAIL"} ${name}`); };
const note = (name, detail = {}) => { results.notes.push({name, ...detail}); console.log(`NOTE ${name}`); };
const shot = async (page, name) => { const file = `${name}.png`; await page.screenshot({path: path.join(out, file), fullPage: true}); results.screenshots.push(file); };
const widths = [1280, 760, 390, 320];
const browser = await chromium.launch();
results.browser = `chromium ${browser.version()}`;
const consoleScopes = new WeakMap();
const observe = (page, label) => {
  page.on("console", message => {
    if (message.type() === "error") {
      const event = {label, kind: "console", text: message.text(), url: message.location().url};
      results.console.push({...event, ...classifyConsoleError(event, consoleScopes.get(page))});
    }
  });
  page.on("pageerror", error => results.console.push({label, kind: "pageerror", text: String(error), expected: false}));
};

/** Same-origin browser call using the live client's explicit CSRF/preflight header. */
async function call(page, route, body) {
  return page.evaluate(async ({route, body}) => {
    const response = await fetch(`/api/storage/workspaces${route}`, {method: body ? "POST" : "GET", headers: body ? {"Content-Type": "application/json", "X-AFTERMATH-Request": "same-origin-browser"} : undefined, body: body ? JSON.stringify(body) : undefined, cache: "no-store"});
    let data = null; try { data = await response.json(); } catch { data = null; }
    return {status: response.status, body: data};
  }, {route, body});
}
const connectivity = page => page.evaluate(async () => { const response = await fetch("/api/connectivity", {cache: "no-store"}); return {status: response.status, body: await response.json()}; });

async function measure(page) {
  return page.evaluate(() => {
    const box = selector => { const node = document.querySelector(selector); if (!node) return null; const r = node.getBoundingClientRect(); return {left: r.left, top: r.top + scrollY, right: r.right, bottom: r.bottom + scrollY}; };
    const overlap = (a, b) => a && b ? Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left)) * Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top)) : null;
    const title = box(".title-composition h1"), sculpture = box(".sculpture"), wordmark = box(".home .wordmark");
    return {innerWidth, clientWidth: document.documentElement.clientWidth, scrollWidth: document.documentElement.scrollWidth, bodyScrollWidth: document.body.scrollWidth, title, sculpture, titleSculptureOverlap: overlap(title, sculpture), wordmark};
  });
}

async function seed(page) {
  const encode = text => Buffer.from(text, "utf8").toString("base64");
  const run = stamp.toLowerCase().replace(/[^a-z0-9-]/g, "").slice(0, 24);
  const corpusId = `acceptance-${run}`;
  const workspace = await call(page, "", {name: `Step 2B acceptance ${stamp}`});
  if (workspace.status !== 201) throw new Error(`workspace creation failed: ${workspace.status} ${JSON.stringify(workspace.body)}`);
  const id = workspace.body.id;
  const corpus = await call(page, `/${id}/corpora`, {corpus_id: corpusId, name: `Step 2B acceptance ${run}`});
  if (corpus.status !== 201) throw new Error(`corpus creation failed: ${corpus.status} ${JSON.stringify(corpus.body)}`);
  const revisions = [
    ["r1", "Starter costs 12 USD.", "2026-01-01T00:00:00Z", {}, false],
    ["r2", "Starter costs 15 USD.", "2026-12-01T00:00:00Z", {}, false],
    ["r3", "Starter costs 15 USD.", "2026-04-01T00:00:00Z", {}, false],
    ["r4", "Starter costs 15 USD.", "2026-04-01T00:00:00Z", {}, false, "legal_notice"],
    ["r5", "", "2027-01-01T00:00:00Z", {}, true, "legal_notice"],
  ];
  let head = null;
  const deliveries = [];
  const payloads = {};
  const deliveryIds = {};
  for (const [index, [rev, text, effective, authority, deleted, sourceType = "product_doc"]] of revisions.entries()) {
    const deliveryId = `acc-${run}-${rev}`;
    const delivery = {delivery_id: deliveryId, expected_head: head, as_of: "2026-11-02T00:00:00Z", documents: [{document_id: "pricing", source_revision_id: rev, source_seq: index + 1, source_timestamp: `2026-0${index + 1}-15T00:00:00Z`, declared_effective_from: effective, source_type: sourceType, authority, source_base64: encode(text), deleted}]};
    const result = await call(page, `/${id}/corpora/${corpusId}/deliveries`, delivery);
    deliveries.push({delivery_id: delivery.delivery_id, http: result.status, ...result.body});
    payloads[rev] = delivery;
    deliveryIds[rev] = deliveryId;
    if (result.body?.status !== "APPLIED") throw new Error(`delivery ${rev} not applied: ${result.status} ${JSON.stringify(result.body)}`);
    head = result.body.snapshot_id;
  }
  return {workspace: id, corpus: corpusId, deliveries, delivery_ids: deliveryIds, payloads};
}

async function readInspection(page, delivery) {
  await page.locator(".change-inspection h3").filter({hasText: `${delivery} / pricing`}).first().waitFor({timeout: 15000});
  return page.evaluate(() => {
    const clean = node => (node?.textContent ?? "").replace(/\s+/g, " ").trim();
    const section = id => document.querySelector(`section[aria-labelledby='${id}']`);
    return {
      before: clean(document.querySelector(".revision-pair > div:first-child strong")),
      lineage: [...(section("lineage-title")?.querySelectorAll("li strong") ?? [])].map(clean),
      timeline: [...(section("timeline-alignment-title")?.querySelectorAll("li") ?? [])].map(clean),
      spans: [...document.querySelectorAll(".live-span")].map(node => ({kind: clean(node.querySelector(".outline-label")), header: clean(node.querySelector("header .mono")), before: clean(node.querySelector(".before-passage")), after: clean(node.querySelector(".after-passage"))})),
      applicability: [...document.querySelectorAll(".applicability-panel li")].map(clean),
      alerts: [...document.querySelectorAll("[role=alert]")].map(clean),
    };
  });
}
const deepLink = (seeded, delivery) => `${web}/workspace?view=inspect&workspace=${seeded.workspace}&corpus=${seeded.corpus}&delivery=${delivery}&document=pricing`;
const heading = (page, delivery) => page.locator(".change-inspection h3").filter({hasText: `${delivery} / pricing`});
const selectControl = (page, label) => page.locator("label").filter({hasText: label}).locator("select");
const storageAlert = page => page.locator(".storage-error[role='alert']");

try {
  if (state === "healthy") {
    const context = await browser.newContext({viewport: {width: 1280, height: 900}});
    const page = await context.newPage();
    observe(page, "healthy-main");
    await page.goto(`${web}/workspace`, {waitUntil: "networkidle"});
    const health = await connectivity(page);
    results.measurements.connectivity = health;
    check("connectivity reports API + PostgreSQL ready", health.status === 200 && health.body.status === "ready", health);
    await page.getByText("API connected · PostgreSQL ready").waitFor({timeout: 10000});
    await shot(page, "healthy-workspace-1280");

    const seeded = await seed(page);
    results.measurements.seeded = seeded;
    check("r1→r5 deliveries applied through the same-origin proxy", seeded.deliveries.every(item => item.status === "APPLIED"), {deliveries: seeded.deliveries});
    const replay = await call(page, `/${seeded.workspace}/corpora/${seeded.corpus}/deliveries`, seeded.payloads.r3);
    check("replaying the identical r3 delivery is idempotent", replay.status === 200 && replay.body?.duplicate === true && replay.body?.snapshot_id === "snap:000003", replay);

    const historical = {
      r1: await call(page, `/${seeded.workspace}/corpora/${seeded.corpus}/documents/pricing/resolve`, {snapshot_id: "snap:000001", evaluation_time: "2027-02-01T00:00:00Z"}),
      r2: await call(page, `/${seeded.workspace}/corpora/${seeded.corpus}/documents/pricing/resolve`, {snapshot_id: "snap:000002", evaluation_time: "2027-02-01T00:00:00Z"}),
      r3: await call(page, `/${seeded.workspace}/corpora/${seeded.corpus}/documents/pricing/resolve`, {snapshot_id: "snap:000003", evaluation_time: "2026-05-01T00:00:00Z"}),
    };
    results.measurements.historical_resolution = historical;
    check("old snapshots remain independently resolvable after r5", historical.r1.body?.selected_version_id === "dv:pricing@r1" && historical.r2.body?.selected_version_id === "dv:pricing@r2" && historical.r3.body?.selected_version_id === "dv:pricing@r3", historical);

    // API contract checks (read model).
    const api = {};
    for (const rev of ["r1", "r2", "r3", "r4", "r5"]) api[rev] = (await call(page, `/${seeded.workspace}/corpora/${seeded.corpus}/updates/${seeded.delivery_ids[rev]}/documents/pricing/comparison`)).body;
    results.measurements.api = api;
    const r2span = api.r2.spans.find(item => item.old_text === "12" && item.new_text === "15");
    check("API r2: exact 12→15 span at code points [14,16) on both sides", r2span && r2span.old_start === 14 && r2span.old_end === 16 && r2span.new_start === 14 && r2span.new_end === 16, {span: r2span});
    check("API r3 (AS-24): exactly one lineage edge, IDENTICAL r2→r3", api.r3.edges.length === 1 && api.r3.edges[0].relation === "IDENTICAL" && api.r3.edges[0].from_passage_version_ids[0]?.includes("@r2"), {edges: api.r3.edges});
    const ta = api.r3.timeline_alignments;
    check("API r3: one timeline-v1 comparison r1→r3, outside lineage", ta.length === 1 && ta[0].recorded_by === "timeline-v1" && ta[0].from_passage_version_ids[0]?.includes("@r1") && ta[0].to_passage_version_ids[0]?.includes("@r3"), {timeline_alignments: ta});
    const tspan = api.r3.spans.find(item => item.origin === "TIMELINE");
    check("API r3: timeline span 12→15 has no lineage edge and names its timeline alignment", tspan && tspan.lineage_edge_id === null && tspan.timeline_alignment_edge_id === ta[0]?.timeline_alignment_edge_id && tspan.old_text === "12" && tspan.new_text === "15", {span: tspan});
    check("API r4: legal_notice authority-only change has no text side or invented timeline comparison", api.r4.new_version.source_type === "legal_notice" && api.r4.spans.some(item => item.kind === "AUTHORITY_CHANGED" && item.old_text === null && item.new_text === null) && api.r4.timeline_alignments.length === 0);
    check("API r5: latest observed r4, effective predecessor r2, interval 2027-01-01→open", api.r5.old_version?.document_version_id === "dv:pricing@r4" && api.r5.applicability_changes.some(item => item.old_effective_version_id === "dv:pricing@r2" && item.new_effective_version_id === null && item.interval_to === null && item.interval_from.startsWith("2027-01-01")), {applicability: api.r5.applicability_changes});

    // Live UI for every delivery.
    const ui = {};
    for (const rev of ["r1", "r2", "r3", "r4", "r5"]) {
      await page.goto(deepLink(seeded, seeded.delivery_ids[rev]), {waitUntil: "networkidle"});
      ui[rev] = await readInspection(page, seeded.delivery_ids[rev]);
      await shot(page, `inspect-${rev}-1280`);
    }
    results.measurements.ui = ui;
    check("UI r1: DOCUMENT_ADDED and ADDITION interval from 2026-01-01", ui.r1.spans.some(s => s.kind === "DOCUMENT_ADDED") && ui.r1.applicability.some(a => a.startsWith("ADDITION") && a.includes("2026-01-01T00:00:00.000Z → open")));
    const u2 = ui.r2.spans.find(s => s.kind === "MODIFIED");
    check("UI r2: struck 12 and inserted 15 at 14–16", u2 && u2.before.includes("14–16") && u2.before.endsWith("12") && u2.after.includes("14–16") && u2.after.endsWith("15"), {span: u2});
    check("UI r3: lineage section shows only IDENTICAL", JSON.stringify(ui.r3.lineage) === JSON.stringify(["IDENTICAL"]), {lineage: ui.r3.lineage});
    check("UI r3: 'Timeline comparison · not lineage' lists MODIFIED r1→r3", ui.r3.timeline.length === 1 && ui.r3.timeline[0].includes("MODIFIED") && ui.r3.timeline[0].includes("@r1") && ui.r3.timeline[0].includes("@r3"), {timeline: ui.r3.timeline});
    check("UI r3: TIMELINE span 12→15 and April→December interval r1→r3", ui.r3.spans.some(s => s.header.startsWith("TIMELINE") && s.before.endsWith("12") && s.after.endsWith("15")) && ui.r3.applicability.some(a => a.includes("2026-04-01T00:00:00.000Z → 2026-12-01T00:00:00.000Z") && a.includes("dv:pricing@r1 → dv:pricing@r3")), {applicability: ui.r3.applicability});
    check("UI r4: AUTHORITY_CHANGED shows no textual side and no timeline section", ui.r4.spans.some(s => s.kind === "AUTHORITY_CHANGED" && s.before.includes("No textual side") && s.after.includes("No textual side")) && ui.r4.timeline.length === 0);
    check("UI r5: DOCUMENT_DELETED, before = r4, DELETION from r2 to Absent", ui.r5.spans.some(s => s.kind === "DOCUMENT_DELETED" && s.after.includes("No textual side")) && ui.r5.before === "dv:pricing@r4" && ui.r5.applicability.some(a => a.startsWith("DELETION") && a.includes("2027-01-01T00:00:00.000Z → open") && a.includes("dv:pricing@r2 → Absent")), {before: ui.r5.before, applicability: ui.r5.applicability});
    check("UI: no inspection page shows an error alert", Object.values(ui).every(item => item.alerts.length === 0));

    // Failed request → successful selection (injected network failure, real UI and reducer).
    await page.goto(deepLink(seeded, seeded.delivery_ids.r3), {waitUntil: "networkidle"});
    await heading(page, seeded.delivery_ids.r3).waitFor({timeout: 15000});
    const r2Comparison = `**/api/storage/workspaces/*/corpora/${seeded.corpus}/updates/${seeded.delivery_ids.r2}/documents/pricing/comparison`;
    const r2ComparisonUrl = `${web}/api/storage/workspaces/${seeded.workspace}/corpora/${seeded.corpus}/updates/${seeded.delivery_ids.r2}/documents/pricing/comparison`;
    await withConsoleScope(consoleScopes, page, {
      scenario: "injected-not-found", failures: [{url: r2ComparisonUrl, status: 404}],
    }, async () => {
      await page.route(r2Comparison, route => route.fulfill({status: 404, contentType: "application/json", body: JSON.stringify({error: {code: "NOT_FOUND", message: "Injected missing comparison for acceptance"}})}));
      await selectControl(page, "Applied update").selectOption(seeded.delivery_ids.r2);
      await storageAlert(page).waitFor({timeout: 10000});
      await page.waitForLoadState("networkidle");
    });
    const failedText = (await storageAlert(page).textContent()) ?? "";
    check("injected r2 comparison failure shows a NOT_FOUND alert and no stale r3 data", failedText.includes("NOT_FOUND") && (await heading(page, seeded.delivery_ids.r3).count()) === 0, {alert: failedText});
    await shot(page, "recovery-1-failed");
    await page.unroute(r2Comparison);
    await selectControl(page, "Applied update").selectOption(seeded.delivery_ids.r3);
    await heading(page, seeded.delivery_ids.r3).waitFor({timeout: 15000});
    check("selecting r3 after the failure renders r3 with no stale alert", (await storageAlert(page).count()) === 0);
    await shot(page, "recovery-2-recovered");

    // Retry path on a page WITHOUT a deep link, so Retry is not confounded by URL presets.
    await page.goto(`${web}/workspace?view=inspect`, {waitUntil: "networkidle"});
    await selectControl(page, "Workspace").selectOption(seeded.workspace);
    await selectControl(page, "Corpus").selectOption(seeded.corpus);
    await withConsoleScope(consoleScopes, page, {
      scenario: "injected-retry-failure", failures: [{url: r2ComparisonUrl, status: 503}],
    }, async () => {
      await page.route(r2Comparison, route => route.fulfill({status: 503, contentType: "application/json", body: JSON.stringify({error: {code: "STORAGE_FAILURE", message: "Injected failure for acceptance"}})}));
      await selectControl(page, "Applied update").selectOption(seeded.delivery_ids.r2);
      await storageAlert(page).waitFor({timeout: 10000});
      await page.waitForLoadState("networkidle");
    });
    await page.unroute(r2Comparison);
    await page.getByRole("button", {name: /Retry \/ refresh/}).click();
    await heading(page, seeded.delivery_ids.r2).waitFor({timeout: 15000});
    check("Retry after a failure renders the current selection (r2) and clears the alert", (await storageAlert(page).count()) === 0);

    // Observation only: does Retry on a deep-linked page keep the user's current selection?
    await page.goto(deepLink(seeded, seeded.delivery_ids.r3), {waitUntil: "networkidle"});
    await heading(page, seeded.delivery_ids.r3).waitFor({timeout: 15000});
    await selectControl(page, "Applied update").selectOption(seeded.delivery_ids.r2);
    await heading(page, seeded.delivery_ids.r2).waitFor({timeout: 15000});
    await page.getByRole("button", {name: /Retry \/ refresh/}).click();
    await page.waitForTimeout(3000);
    check("Retry on a deep-linked page keeps the user's current r2 selection", await heading(page, seeded.delivery_ids.r2).count() === 1 && await heading(page, seeded.delivery_ids.r3).count() === 0);

    // Response race: a slow r2 comparison must not replace a newer r3 selection.
    await selectControl(page, "Applied update").selectOption(seeded.delivery_ids.r1);
    await heading(page, seeded.delivery_ids.r1).waitFor({timeout: 15000});
    await page.route(r2Comparison, async route => { await new Promise(resolve => setTimeout(resolve, 3000)); try { await route.continue(); } catch { /* request aborted by the UI */ } });
    const slow = page.waitForRequest(request => request.url().includes(`/updates/${seeded.delivery_ids.r2}/documents/pricing/comparison`), {timeout: 10000});
    await selectControl(page, "Applied update").selectOption(seeded.delivery_ids.r2);
    await slow;
    await selectControl(page, "Applied update").selectOption(seeded.delivery_ids.r3);
    await heading(page, seeded.delivery_ids.r3).waitFor({timeout: 15000});
    await page.waitForTimeout(4000);
    check("slow superseded r2 response never replaces the newer r3 selection", (await heading(page, seeded.delivery_ids.r3).count()) === 1 && (await heading(page, seeded.delivery_ids.r2).count()) === 0 && (await storageAlert(page).count()) === 0);
    await page.unroute(r2Comparison);
    await context.close();

    // Exact viewports, overflow, decoration legibility.
    for (const width of widths) {
      const ctx = await browser.newContext({viewport: {width, height: 900}, deviceScaleFactor: 1});
      const view = await ctx.newPage();
      observe(view, `healthy-${width}`);
      for (const [name, url] of [["home", `${web}/`], ["workspace", `${web}/workspace`], ["inspect-r3", deepLink(seeded, seeded.delivery_ids.r3)]]) {
        await view.goto(url, {waitUntil: "networkidle"});
        if (name === "inspect-r3") await view.locator(".change-inspection").waitFor({timeout: 15000});
        const m = await measure(view);
        results.measurements[`${name}-${width}`] = {requestedWidth: width, ...m};
        check(`${name} @${width}: requested, inner and client widths are exactly ${width}`, m.innerWidth === width && m.clientWidth === width, {requestedWidth: width, innerWidth: m.innerWidth, clientWidth: m.clientWidth});
        check(`${name} @${width}: no horizontal document overflow`, m.scrollWidth <= m.innerWidth && m.bodyScrollWidth <= m.innerWidth, {scrollWidth: m.scrollWidth, bodyScrollWidth: m.bodyScrollWidth});
        if (m.title && width <= 760) check(`${name} @${width}: decoration does not overlap the title`, m.titleSculptureOverlap === 0, {overlap: m.titleSculptureOverlap});
        else if (m.title) note(`${name} @${width}: desktop composition overlap (px², bounding boxes) for visual review`, {overlap: m.titleSculptureOverlap});
        if (m.wordmark) check(`${name} @${width}: wordmark fully inside the viewport`, m.wordmark.left >= 0 && m.wordmark.right <= m.innerWidth + 0.5, {wordmark: m.wordmark});
        await shot(view, `${name}-${width}`);
      }
      await ctx.close();
    }

    // Reduced motion.
    const motion = await browser.newContext({viewport: {width: 390, height: 844}, reducedMotion: "reduce"});
    const motionPage = await motion.newPage();
    observe(motionPage, "reduced-motion");
    await motionPage.goto(`${web}/`, {waitUntil: "networkidle"});
    const reduced = await motionPage.evaluate(() => ({matches: matchMedia("(prefers-reduced-motion: reduce)").matches, animation: getComputedStyle(document.querySelector(".home .wordmark")).animationName, scrollBehavior: getComputedStyle(document.documentElement).scrollBehavior}));
    results.measurements.reduced_motion = reduced;
    check("reduced motion disables animation and smooth scrolling", reduced.matches && reduced.animation === "none" && reduced.scrollBehavior === "auto", reduced);
    await motion.close();

    // Keyboard reach and visible focus at 390px.
    const kctx = await browser.newContext({viewport: {width: 390, height: 844}});
    const kpage = await kctx.newPage();
    observe(kpage, "keyboard");
    await kpage.goto(`${web}/workspace`, {waitUntil: "networkidle"});
    const focusInfo = () => kpage.evaluate(() => { const node = document.activeElement; const style = getComputedStyle(node); const label = node.closest("label")?.childNodes[0]?.textContent?.trim() || (node.getAttribute("aria-label") || node.textContent || "").replace(/\s+/g, " ").trim().slice(0, 50); return {tag: node.tagName, label, visible: style.outlineStyle !== "none" && parseFloat(style.outlineWidth) >= 2}; });
    const sequence = [];
    for (let index = 0; index < 14; index += 1) { await kpage.keyboard.press("Tab"); sequence.push(await focusInfo()); }
    results.measurements.keyboard_workspace = sequence;
    check("first Tab reaches the skip link", sequence[0]?.label.startsWith("Skip to workspace content"), {first: sequence[0]});
    const interactive = sequence.filter(item => ["A", "BUTTON", "SELECT", "SUMMARY"].includes(item.tag));
    check("every focused control on the workspace shows a visible focus outline", interactive.length > 0 && interactive.every(item => item.visible), {sequence});
    const inspectIndex = sequence.findIndex(item => item.label.includes("Inspect changes"));
    check("Inspect changes is reachable by keyboard", inspectIndex >= 0);
    if (inspectIndex >= 0) {
      await kpage.goto(`${web}/workspace`, {waitUntil: "networkidle"});
      for (let index = 0; index <= inspectIndex; index += 1) await kpage.keyboard.press("Tab");
      await kpage.keyboard.press("Enter");
      await kpage.getByRole("heading", {name: "Inspect what moved."}).waitFor({timeout: 10000});
      check("Enter on the focused nav button opens Inspect changes", true);
    }
    await kpage.goto(deepLink(seeded, seeded.delivery_ids.r3), {waitUntil: "networkidle"});
    await kpage.locator(".change-inspection").waitFor({timeout: 15000});
    const reached = [];
    for (let index = 0; index < 40; index += 1) { await kpage.keyboard.press("Tab"); reached.push(await focusInfo()); }
    results.measurements.keyboard_inspect = reached;
    for (const name of ["Workspace", "Corpus", "Applied update", "Changed document"]) check(`${name} selector reachable by keyboard with visible focus`, reached.some(item => item.tag === "SELECT" && item.label === name && item.visible));
    check("Retry control reachable by keyboard with visible focus", reached.some(item => item.tag === "BUTTON" && item.label.startsWith("Retry / refresh") && item.visible));
    await shot(kpage, "keyboard-inspect-390");
    await kctx.close();
  } else {
    const expected = {
      "db-down": {connectivity: "unavailable", label: "API responded · readiness unavailable", code: "STORAGE_FAILURE"},
      "backend-down": {connectivity: "unreachable", label: "Backend could not be reached", code: "UNREACHABLE"},
      unconfigured: {connectivity: "unconfigured", label: "Backend URL not configured", code: "UNCONFIGURED"},
    }[state];
    for (const width of [1280, 390]) {
      const ctx = await browser.newContext({viewport: {width, height: 900}});
      const page = await ctx.newPage();
      observe(page, `${state}-${width}`);
      await withConsoleScope(consoleScopes, page, {
        scenario: `${state}-${width}-overview`,
        failures: ["/api/connectivity", "/api/storage/workspaces?limit=100"].map(route => ({url: `${web}${route}`, status: 503})),
      }, async () => {
        await page.goto(`${web}/workspace`, {waitUntil: "networkidle"});
        const health = await connectivity(page);
        results.measurements[`connectivity-${width}`] = health;
        check(`@${width}: /api/connectivity reports ${expected.connectivity}`, health.status === 503 && health.body.status === expected.connectivity, health);
        await page.getByText(expected.label).waitFor({timeout: 15000});
        check(`@${width}: connection bar shows "${expected.label}"`, true);
        await shot(page, `${state}-workspace-${width}`);
      });
      await withConsoleScope(consoleScopes, page, {
        scenario: `${state}-${width}-inspection`,
        failures: ["/api/connectivity", "/api/storage/workspaces?limit=100"].map(route => ({url: `${web}${route}`, status: 503})),
      }, async () => {
        await page.goto(`${web}/workspace?view=inspect`, {waitUntil: "networkidle"});
        await storageAlert(page).waitFor({timeout: 20000});
        const text = (await storageAlert(page).textContent()) ?? "";
        results.measurements[`inspect-alert-${width}`] = text;
        check(`@${width}: inspect view shows ${expected.code}, substitutes no examples, renders no comparison`, text.includes(expected.code) && text.includes("No example changes were substituted") && (await page.locator(".change-inspection").count()) === 0, {alert: text});
        const m = await measure(page);
        results.measurements[`layout-${state}-${width}`] = {requestedWidth: width, ...m};
        check(`@${width}: requested, inner and client widths match with no overflow`, m.innerWidth === width && m.clientWidth === width && m.scrollWidth <= m.innerWidth, {requestedWidth: width, innerWidth: m.innerWidth, clientWidth: m.clientWidth, scrollWidth: m.scrollWidth});
        await shot(page, `${state}-inspect-${width}`);
      });
      await ctx.close();
    }
  }
} catch (error) {
  check("harness completed without an exception", false, {error: String(error?.stack ?? error)});
} finally {
  await browser.close();
  const unexpectedConsole = results.console.filter(item => !item.expected);
  check("no unexpected browser console or page errors", unexpectedConsole.length === 0, {errors: unexpectedConsole});
  results.finished_at = new Date().toISOString();
  const failed = results.checks.filter(item => !item.passed);
  await writeFile(path.join(out, "results.json"), JSON.stringify(results, null, 2) + "\n");
  await writeFile(path.join(out, "summary.md"), [
    `# Step 2B browser acceptance: ${state}`, "",
    `- Outcome: ${failed.length ? "REJECTED" : "PASSED"}`,
    `- Web: ${web}`, `- Browser: ${results.browser}`, `- Started: ${results.started_at}`,
    `- Checks: ${results.checks.length - failed.length}/${results.checks.length} passed`, "",
    ...results.checks.map(item => `- ${item.passed ? "PASS" : "FAIL"} ${item.name}`), "",
    "Notes (informational, not pass/fail):", ...results.notes.map(item => `- ${item.name}: ${JSON.stringify(Object.fromEntries(Object.entries(item).filter(([key]) => key !== "name")))}`), "",
    "Screenshots (review visually):", ...results.screenshots.map(file => `- ${file}`), "",
  ].join("\n"));
  console.log(`\nEvidence: ${out}\n${results.checks.length - failed.length}/${results.checks.length} checks passed`);
  process.exitCode = failed.length ? 1 : 0;
}
