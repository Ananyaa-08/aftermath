# Frontend refinement — 1 November 2026

Implemented locally; not deployed. Foundation only. No working semantic revalidation pipeline or research performance result is claimed.

## Design and interactions

Pale-blue connected work surfaces, oversized ganache wordmark, butter selection states, precise monospace annotations and readable evidence text. A custom static SVG linked-ribbon sculpture adds shaded depth and restrained grain without WebGL, a rendering dependency, continuous animation, or interaction handlers. It is decorative, aria-hidden and ignores pointer events. If SVG/filter rendering is unavailable, all text and controls remain ordinary HTML.

One route provides three views: Overview, Inspect changes, Experiments. The live workspace is the default. A persistent labeled Example workspace mode exposes a fictional export-policy change, searchable/filterable archived answers, sorting by represented fields, claim selection, earlier/applicable evidence, scope, snapshot and history. Examples include all four semantic statuses plus failed, queued, withheld and unassessed work. Long questions/passages and an empty-filter case are included.

Live data: actual backend readiness through the existing server-only proxy. Both successful HTTP status and a healthy PostgreSQL dependency are required before displaying ready. Last-check timestamps are actual browser time, explicitly UTC. Checking, unavailable database, unreachable backend and unconfigured URL have distinct labels; retry is real.

Illustrative data: `fixtures/example-workspace.ts` contains deterministic authored display records. These are not model output, evaluation gold, measured costs, activity from a live service, or research results. `workspaceForMode` never provides fixtures in live mode. Pending/failed/withheld/unassessed work cannot display a current verdict, even if a stale verdict field is supplied. Completed verdicts must match the displayed snapshot. A historical verdict is not newly verified.

Unavailable: corpus ingestion, source/answer APIs, candidate selection, semantic assessment, model calls, queue execution, live history and experiment execution. Experiments presents a useful unavailable state in both modes, with no invented charts or performance. No backend contract was changed.

## Verification

- `npm test`: **6 passed**, covering live/example isolation, workflow versus semantic status, snapshot binding, fixture enum use, empty filtering, and strict readiness parsing.
- `npm run typecheck`: **passed**.
- `npm run build`: **passed**, Next.js production webpack build. Final production app was started and inspected.
- Backend `.venv/bin/pytest -q` with `AFTERMATH_TEST_DATABASE_URL`: **16 passed**, including real PostgreSQL integration. One existing non-failing Starlette/httpx deprecation warning remains.
- Backend Ruff lint and formatting checks: **passed**, 24 files formatted. Strict mypy: **passed**, 19 source files.
- New dev-only dependency: `tsx 4.23.15`, locked with npm. CI now runs `npm test` before frontend type checking and build. Hosted CI was not run here.

Browser inspection used Chrome at the desktop viewport (1440px), 390×844, and a 320×740 overview check. A narrow-screen wordmark overflow was found and corrected; final overview widths were exactly 390 and 320, and the 390px inspector also had no horizontal overflow. Evidence stacks vertically on mobile; the answer list has its own bounded scroll area.

Verified in the running UI: actual ready state; stopping PostgreSQL produces “API responded · readiness unavailable”; stopping FastAPI produces “Backend could not be reached”; restarting it and retrying restores ready. No success response was mocked. Verified claim switching (contradicted claim versus supported CSV claim), long question and evidence, IN_PROGRESS filter with zero matches, clearing filters, FAILED/no-verdict display, keyboard Enter navigation and Tab focus outline, live/example switching, historical versus current example verdicts in the expanded history, and the unavailable experiment/live-inspection views.

Reduced motion: inspected the installed CSS guard and confirmed zero active element animations. The SVG is static; no render loop exists. OS reduced-motion emulation was not toggled. `pointer-events: none` on the sculpture was verified in the browser. This was not a formal screen-reader audit or exhaustive accessibility certification.

Calculated contrast using the actual palette tokens (WCAG relative luminance): ganache/sky **11.01:1**, ganache/butter **10.85:1**, ganache/paper **13.96:1**, muted/sky **6.67:1**, success/paper **8.29:1**, error/paper **8.50:1**, focus blue/sky **4.98:1**. Status information always includes text; red/green alone never conveys meaning.

Initial tsx execution was blocked by sandbox IPC permissions; the approved retry and final suite passed. Local servers required socket permission. No unresolved build/test failure remains.

## Screenshots

Captured from the actual running application, not design mockups:

- [Desktop overview](screenshots/overview-desktop.jpg)
- [Desktop source and answer inspection](screenshots/inspection-desktop.jpg)
- [Mobile overview](screenshots/overview-mobile.jpg)
- [Mobile inspection](screenshots/inspection-mobile.jpg)
- [Mobile failure/detail viewport](screenshots/mobile-detail.jpg)

## Files to review

- `apps/web/components/workspace.tsx`: view navigation and explicit data-mode boundary.
- `apps/web/components/answer-inspector.tsx`: filtering, selection, claim/evidence/history presentation.
- `apps/web/components/source-change.tsx`: labeled source comparison.
- `apps/web/components/connection.tsx`, `lib/connectivity.ts`, `app/api/connectivity/route.ts`: real readiness and failure states.
- `apps/web/lib/workspace.ts`: presentation-only contracts and conservative verdict display.
- `apps/web/fixtures/example-workspace.ts`: isolated authored examples.
- `apps/web/components/sculpture.tsx`, `app/globals.css`: SVG and centralized design tokens/responsive styling.
- `apps/web/tests/workspace.test.ts`, `package.json`, `package-lock.json`, `.github/workflows/checks.yml`: tests and repeatability.

Next.js generated `apps/web/AGENTS.md` during development; it is retained. The obsolete `app/connectivity.tsx` was replaced by the new presentation component. Existing backend and research references are preserved.

## Commit status

The foundation was **not committed**. Git initialization was declined during the preceding task; `git status --short` confirms this directory is not a Git repository. No files were reverted or discarded, and no commit or deployment was attempted during this refinement.

Local preview/API processes and the PostgreSQL container were stopped after verification; the database volume and all source files are retained. Restart instructions are in README.
