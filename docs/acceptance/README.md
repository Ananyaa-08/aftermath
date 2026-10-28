# Acceptance evidence

Browser evidence belongs under `docs/acceptance/step2b/<timestamp>-<state>/`. Each run is independent and must include `results.json`, `summary.md`, and its screenshots. The Step 2B harness exits non-zero and labels the run `REJECTED` when any check or unexpected browser error fails.

The required states are `healthy`, `db-down`, `backend-down`, and `unconfigured`. A healthy run creates a fresh disposable workspace and uniquely named corpus, then applies the r1→r5 sequence through the live same-origin API. Generated corpus data is intentionally not deleted because the corpus store is append-only; use a disposable database when cleanup is required.

Harness-authored checks and screenshots are review material, not self-certifying acceptance. Review exact spans, lineage/timeline separation, applicability intervals, responsive screenshots, focus behavior, reduced motion, and failure-state truthfulness independently.

## Selected evidence after blocker repair

The complete user-run local browser sequence passed on 4 November 2026. These are the selected current artifacts for independent review; their passing status does not itself accept Step 2B:

- `step2b/2026-11-04T04-48-19-435Z-healthy/` — 68/68 passed.
- `step2b/2026-11-04T05-51-07-460Z-db-down/` — 9/9 passed.
- `step2b/2026-11-04T06-08-47-306Z-backend-down/` — 9/9 passed.
- `step2b/2026-11-04T06-23-26-760Z-unconfigured/` — 9/9 passed.

The healthy artifact covers r1→r5, exact spans, AS-24 lineage/timeline separation, applicability, stale-error recovery, responsive widths, keyboard behavior, focus, and reduced motion. The other three artifacts prove truthful failure behavior without example substitution or fake comparison content. Their `results.json` files retain expected, exactly scoped HTTP console entries and record no unexpected console or page errors.

## Superseded evidence before independent rejection

Step 2B is not yet accepted. These counts were reported by the earlier harness before the insert/delete context and passage/version integrity blockers were found. Its global expected-error flag could also suppress unrelated console errors. Preserve these artifacts as history; they are not selected evidence for the repaired implementation.

- `step2b/2026-11-03T14-20-03-933Z-healthy/` — 68/68 passed.
- `step2b/2026-11-03T16-10-20-032Z-db-down/` — 9/9 passed.
- `step2b/2026-11-03T16-19-01-704Z-backend-down/` — 9/9 passed.
- `step2b/2026-11-03T16-42-44-084Z-unconfigured/` — 9/9 passed.

Earlier incomplete or failing directories are intentionally retained as rejected historical evidence. A passing directory does not erase an earlier failure and does not substitute for independent review.

The repaired harness classifies expected errors using an exact scenario request URL and the known Chromium HTTP-resource message/status. Scopes belong to one page and reset after each operation in `finally`. Unmatched console errors and every uncaught page error fail the run; all entries remain in `results.json`. `tests/console-classifier.test.ts` exercises unrelated React/hydration/JavaScript errors, wrong URLs/statuses, and scope cleanup. Backend/PostgreSQL and frontend prerequisites passed before the selected browser sequence was run.
