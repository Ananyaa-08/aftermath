# Step 2B commit inventory — untracked paths reconciled

Step 2B has passed the user-run local verification sequence but remains unaccepted pending independent re-review. No staging or commit is authorized here. On 4 November 2026, the user supplied `git status --short --untracked-files=all`, `git diff --check`, `git diff --stat`, `git diff --name-status`, and `git ls-files --others --exclude-standard` from the repository root. All 158 then-listed untracked paths were classified with no missing entries: A=21, B=5, C=6, D=12, E=0, F=109, G=4, H=1, J=0. Forty selected evidence files were subsequently created and are now listed in E, for 198 known untracked paths; a final read-only Git inventory must confirm that count and detect any other additions. Category I additionally identifies one ignored `.DS_Store` observed during directory inspection; it is not in the Git list. The initial `git diff --check` returned no diagnostics for tracked changes. No blanket staging command is recommended.

A–D are proposed required project files, including inherited Step 2A/2B modules, migrations 0002–0006, frontend assets, and the bundled font license. D also includes preserved design documentation/screenshots that require the user's scope review; their presence does not mean this repair authored them. E contains the selected current review evidence, not a self-certification of acceptance. F must stay identifiable as superseded, even when its historical summary says PASSED; whether to retain it in the future commit is a user review decision. G–J are excluded from the source commit proposal. Nothing is deleted.

Tracked modifications require a separate review of the user-provided diff. `git diff --check` does not cover untracked files.

Final user-supplied output on 4 November 2026 confirms all 198 untracked paths match the entries below exactly; no supplied untracked path is unclassified. Category totals are A=21, B=5, C=6, D=12, E=40, F=109, G=4, H=1, J=0. The ignored `.DS_Store` remains separate. The final `git diff --check` produced no diagnostics before the closing documentation edits. Follow-up non-paged output reconciled all 21 tracked modifications: the seven backend files omitted from the earlier pasted diff are present in the unstaged diff, and the backend cached diff is empty. No tracked-output discrepancy remains.

## A. Required source and runtime assets

- `apps/web/app/api/storage/[...path]/route.ts`
- `apps/web/app/fonts/Fraunces.ttf`
- `apps/web/app/workspace/page.tsx`
- `apps/web/components/live-changes.tsx`
- `apps/web/components/live-corpus.tsx`
- `apps/web/lib/change-inspection.ts`
- `apps/web/lib/same-origin.ts`
- `apps/web/lib/storage.ts`
- `apps/web/scripts/console-classifier.d.mts`
- `apps/web/scripts/console-classifier.mjs`
- `apps/web/scripts/step2b-acceptance.mjs`
- `services/backend/src/aftermath/adapters/persistence/corpus.py`
- `services/backend/src/aftermath/adapters/storage/local.py`
- `services/backend/src/aftermath/api/corpus.py`
- `services/backend/src/aftermath/api/limits.py`
- `services/backend/src/aftermath/application/changes.py`
- `services/backend/src/aftermath/application/corpus.py`
- `services/backend/src/aftermath/core/changes.py`
- `services/backend/src/aftermath/core/corpus.py`
- `services/backend/src/aftermath/core/errors.py`
- `services/backend/src/aftermath/ports/corpus.py`

## B. Required migrations

- `services/backend/migrations/versions/0002_corpus.py`
- `services/backend/migrations/versions/0003_changes.py`
- `services/backend/migrations/versions/0004_step2b_repair.py`
- `services/backend/migrations/versions/0005_timeline_event_integrity.py`
- `services/backend/migrations/versions/0006_span_passage_integrity.py`

## C. Required tests

- `apps/web/tests/change-inspection.test.tsx`
- `apps/web/tests/console-classifier.test.ts`
- `apps/web/tests/storage.test.ts`
- `services/backend/tests/test_changes.py`
- `services/backend/tests/test_corpus.py`
- `services/backend/tests/test_span_integrity.py`

## D. Required documentation and licenses

- `apps/web/app/fonts/OFL.txt`
- `docs/acceptance/README.md`
- `docs/change-detection.md`
- `docs/corpus-and-time.md`
- `docs/homepage-visual-research.md`
- `docs/screenshots/home-320.jpg`
- `docs/screenshots/home-390.jpg`
- `docs/screenshots/home-desktop.jpg`
- `docs/screenshots/workspace-live-390.jpg`
- `docs/screenshots/workspace-live-tablet.jpg`
- `docs/step2b-commit-inventory.md`
- `docs/third-party-assets.md`

## E. Selected current acceptance evidence

- `docs/acceptance/step2b/2026-11-04T04-48-19-435Z-healthy/healthy-workspace-1280.png`
- `docs/acceptance/step2b/2026-11-04T04-48-19-435Z-healthy/home-1280.png`
- `docs/acceptance/step2b/2026-11-04T04-48-19-435Z-healthy/home-320.png`
- `docs/acceptance/step2b/2026-11-04T04-48-19-435Z-healthy/home-390.png`
- `docs/acceptance/step2b/2026-11-04T04-48-19-435Z-healthy/home-760.png`
- `docs/acceptance/step2b/2026-11-04T04-48-19-435Z-healthy/inspect-r1-1280.png`
- `docs/acceptance/step2b/2026-11-04T04-48-19-435Z-healthy/inspect-r2-1280.png`
- `docs/acceptance/step2b/2026-11-04T04-48-19-435Z-healthy/inspect-r3-1280.png`
- `docs/acceptance/step2b/2026-11-04T04-48-19-435Z-healthy/inspect-r3-320.png`
- `docs/acceptance/step2b/2026-11-04T04-48-19-435Z-healthy/inspect-r3-390.png`
- `docs/acceptance/step2b/2026-11-04T04-48-19-435Z-healthy/inspect-r3-760.png`
- `docs/acceptance/step2b/2026-11-04T04-48-19-435Z-healthy/inspect-r4-1280.png`
- `docs/acceptance/step2b/2026-11-04T04-48-19-435Z-healthy/inspect-r5-1280.png`
- `docs/acceptance/step2b/2026-11-04T04-48-19-435Z-healthy/keyboard-inspect-390.png`
- `docs/acceptance/step2b/2026-11-04T04-48-19-435Z-healthy/recovery-1-failed.png`
- `docs/acceptance/step2b/2026-11-04T04-48-19-435Z-healthy/recovery-2-recovered.png`
- `docs/acceptance/step2b/2026-11-04T04-48-19-435Z-healthy/results.json`
- `docs/acceptance/step2b/2026-11-04T04-48-19-435Z-healthy/summary.md`
- `docs/acceptance/step2b/2026-11-04T04-48-19-435Z-healthy/workspace-1280.png`
- `docs/acceptance/step2b/2026-11-04T04-48-19-435Z-healthy/workspace-320.png`
- `docs/acceptance/step2b/2026-11-04T04-48-19-435Z-healthy/workspace-390.png`
- `docs/acceptance/step2b/2026-11-04T04-48-19-435Z-healthy/workspace-760.png`
- `docs/acceptance/step2b/2026-11-04T05-51-07-460Z-db-down/db-down-inspect-1280.png`
- `docs/acceptance/step2b/2026-11-04T05-51-07-460Z-db-down/db-down-inspect-390.png`
- `docs/acceptance/step2b/2026-11-04T05-51-07-460Z-db-down/db-down-workspace-1280.png`
- `docs/acceptance/step2b/2026-11-04T05-51-07-460Z-db-down/db-down-workspace-390.png`
- `docs/acceptance/step2b/2026-11-04T05-51-07-460Z-db-down/results.json`
- `docs/acceptance/step2b/2026-11-04T05-51-07-460Z-db-down/summary.md`
- `docs/acceptance/step2b/2026-11-04T06-08-47-306Z-backend-down/backend-down-inspect-1280.png`
- `docs/acceptance/step2b/2026-11-04T06-08-47-306Z-backend-down/backend-down-inspect-390.png`
- `docs/acceptance/step2b/2026-11-04T06-08-47-306Z-backend-down/backend-down-workspace-1280.png`
- `docs/acceptance/step2b/2026-11-04T06-08-47-306Z-backend-down/backend-down-workspace-390.png`
- `docs/acceptance/step2b/2026-11-04T06-08-47-306Z-backend-down/results.json`
- `docs/acceptance/step2b/2026-11-04T06-08-47-306Z-backend-down/summary.md`
- `docs/acceptance/step2b/2026-11-04T06-23-26-760Z-unconfigured/results.json`
- `docs/acceptance/step2b/2026-11-04T06-23-26-760Z-unconfigured/summary.md`
- `docs/acceptance/step2b/2026-11-04T06-23-26-760Z-unconfigured/unconfigured-inspect-1280.png`
- `docs/acceptance/step2b/2026-11-04T06-23-26-760Z-unconfigured/unconfigured-inspect-390.png`
- `docs/acceptance/step2b/2026-11-04T06-23-26-760Z-unconfigured/unconfigured-workspace-1280.png`
- `docs/acceptance/step2b/2026-11-04T06-23-26-760Z-unconfigured/unconfigured-workspace-390.png`

## F. Historical rejected or superseded evidence

- `apps/web/docs/acceptance/step2b/2026-11-02T17-32-10-313Z-healthy/results.json`
- `apps/web/docs/acceptance/step2b/2026-11-02T17-32-10-313Z-healthy/summary.md`
- `apps/web/docs/acceptance/step2b/2026-11-02T17-32-23-799Z-healthy/results.json`
- `apps/web/docs/acceptance/step2b/2026-11-02T17-32-23-799Z-healthy/summary.md`
- `apps/web/docs/acceptance/step2b/2026-11-02T17-32-35-893Z-healthy/results.json`
- `apps/web/docs/acceptance/step2b/2026-11-02T17-32-35-893Z-healthy/summary.md`
- `apps/web/docs/acceptance/step2b/2026-11-02T17-32-50-932Z-healthy/results.json`
- `apps/web/docs/acceptance/step2b/2026-11-02T17-32-50-932Z-healthy/summary.md`
- `apps/web/docs/acceptance/step2b/2026-11-02T17-46-10-809Z-healthy/results.json`
- `apps/web/docs/acceptance/step2b/2026-11-02T17-46-10-809Z-healthy/summary.md`
- `apps/web/docs/acceptance/step2b/2026-11-02T17-46-19-577Z-healthy/results.json`
- `apps/web/docs/acceptance/step2b/2026-11-02T17-46-19-577Z-healthy/summary.md`
- `apps/web/docs/acceptance/step2b/2026-11-02T17-46-26-207Z-healthy/results.json`
- `apps/web/docs/acceptance/step2b/2026-11-02T17-46-26-207Z-healthy/summary.md`
- `apps/web/docs/acceptance/step2b/2026-11-02T17-54-31-306Z-healthy/results.json`
- `apps/web/docs/acceptance/step2b/2026-11-02T17-54-31-306Z-healthy/summary.md`
- `apps/web/docs/acceptance/step2b/2026-11-02T18-02-46-051Z-healthy/healthy-workspace-1280.png`
- `apps/web/docs/acceptance/step2b/2026-11-02T18-02-46-051Z-healthy/inspect-r1-1280.png`
- `apps/web/docs/acceptance/step2b/2026-11-02T18-02-46-051Z-healthy/inspect-r2-1280.png`
- `apps/web/docs/acceptance/step2b/2026-11-02T18-02-46-051Z-healthy/inspect-r3-1280.png`
- `apps/web/docs/acceptance/step2b/2026-11-02T18-02-46-051Z-healthy/inspect-r4-1280.png`
- `apps/web/docs/acceptance/step2b/2026-11-02T18-02-46-051Z-healthy/inspect-r5-1280.png`
- `apps/web/docs/acceptance/step2b/2026-11-02T18-02-46-051Z-healthy/results.json`
- `apps/web/docs/acceptance/step2b/2026-11-02T18-02-46-051Z-healthy/summary.md`
- `docs/acceptance/step2b/2026-11-02T20-47-52-600Z-healthy/healthy-workspace-1280.png`
- `docs/acceptance/step2b/2026-11-02T20-47-52-600Z-healthy/results.json`
- `docs/acceptance/step2b/2026-11-02T20-47-52-600Z-healthy/summary.md`
- `docs/acceptance/step2b/2026-11-03T13-51-35-303Z-healthy/healthy-workspace-1280.png`
- `docs/acceptance/step2b/2026-11-03T13-51-35-303Z-healthy/results.json`
- `docs/acceptance/step2b/2026-11-03T13-51-35-303Z-healthy/summary.md`
- `docs/acceptance/step2b/2026-11-03T13-58-52-706Z-healthy/results.json`
- `docs/acceptance/step2b/2026-11-03T13-58-52-706Z-healthy/summary.md`
- `docs/acceptance/step2b/2026-11-03T14-02-27-744Z-healthy/healthy-workspace-1280.png`
- `docs/acceptance/step2b/2026-11-03T14-02-27-744Z-healthy/results.json`
- `docs/acceptance/step2b/2026-11-03T14-02-27-744Z-healthy/summary.md`
- `docs/acceptance/step2b/2026-11-03T14-05-58-181Z-healthy/results.json`
- `docs/acceptance/step2b/2026-11-03T14-05-58-181Z-healthy/summary.md`
- `docs/acceptance/step2b/2026-11-03T14-11-49-316Z-healthy/results.json`
- `docs/acceptance/step2b/2026-11-03T14-11-49-316Z-healthy/summary.md`
- `docs/acceptance/step2b/2026-11-03T14-13-22-675Z-healthy/healthy-workspace-1280.png`
- `docs/acceptance/step2b/2026-11-03T14-13-22-675Z-healthy/inspect-r1-1280.png`
- `docs/acceptance/step2b/2026-11-03T14-13-22-675Z-healthy/inspect-r2-1280.png`
- `docs/acceptance/step2b/2026-11-03T14-13-22-675Z-healthy/inspect-r3-1280.png`
- `docs/acceptance/step2b/2026-11-03T14-13-22-675Z-healthy/inspect-r4-1280.png`
- `docs/acceptance/step2b/2026-11-03T14-13-22-675Z-healthy/inspect-r5-1280.png`
- `docs/acceptance/step2b/2026-11-03T14-13-22-675Z-healthy/results.json`
- `docs/acceptance/step2b/2026-11-03T14-13-22-675Z-healthy/summary.md`
- `docs/acceptance/step2b/2026-11-03T14-16-48-632Z-healthy/healthy-workspace-1280.png`
- `docs/acceptance/step2b/2026-11-03T14-16-48-632Z-healthy/home-1280.png`
- `docs/acceptance/step2b/2026-11-03T14-16-48-632Z-healthy/home-320.png`
- `docs/acceptance/step2b/2026-11-03T14-16-48-632Z-healthy/home-390.png`
- `docs/acceptance/step2b/2026-11-03T14-16-48-632Z-healthy/home-760.png`
- `docs/acceptance/step2b/2026-11-03T14-16-48-632Z-healthy/inspect-r1-1280.png`
- `docs/acceptance/step2b/2026-11-03T14-16-48-632Z-healthy/inspect-r2-1280.png`
- `docs/acceptance/step2b/2026-11-03T14-16-48-632Z-healthy/inspect-r3-1280.png`
- `docs/acceptance/step2b/2026-11-03T14-16-48-632Z-healthy/inspect-r3-320.png`
- `docs/acceptance/step2b/2026-11-03T14-16-48-632Z-healthy/inspect-r3-390.png`
- `docs/acceptance/step2b/2026-11-03T14-16-48-632Z-healthy/inspect-r3-760.png`
- `docs/acceptance/step2b/2026-11-03T14-16-48-632Z-healthy/inspect-r4-1280.png`
- `docs/acceptance/step2b/2026-11-03T14-16-48-632Z-healthy/inspect-r5-1280.png`
- `docs/acceptance/step2b/2026-11-03T14-16-48-632Z-healthy/keyboard-inspect-390.png`
- `docs/acceptance/step2b/2026-11-03T14-16-48-632Z-healthy/recovery-1-failed.png`
- `docs/acceptance/step2b/2026-11-03T14-16-48-632Z-healthy/recovery-2-recovered.png`
- `docs/acceptance/step2b/2026-11-03T14-16-48-632Z-healthy/results.json`
- `docs/acceptance/step2b/2026-11-03T14-16-48-632Z-healthy/summary.md`
- `docs/acceptance/step2b/2026-11-03T14-16-48-632Z-healthy/workspace-1280.png`
- `docs/acceptance/step2b/2026-11-03T14-16-48-632Z-healthy/workspace-320.png`
- `docs/acceptance/step2b/2026-11-03T14-16-48-632Z-healthy/workspace-390.png`
- `docs/acceptance/step2b/2026-11-03T14-16-48-632Z-healthy/workspace-760.png`
- `docs/acceptance/step2b/2026-11-03T14-20-03-933Z-healthy/healthy-workspace-1280.png`
- `docs/acceptance/step2b/2026-11-03T14-20-03-933Z-healthy/home-1280.png`
- `docs/acceptance/step2b/2026-11-03T14-20-03-933Z-healthy/home-320.png`
- `docs/acceptance/step2b/2026-11-03T14-20-03-933Z-healthy/home-390.png`
- `docs/acceptance/step2b/2026-11-03T14-20-03-933Z-healthy/home-760.png`
- `docs/acceptance/step2b/2026-11-03T14-20-03-933Z-healthy/inspect-r1-1280.png`
- `docs/acceptance/step2b/2026-11-03T14-20-03-933Z-healthy/inspect-r2-1280.png`
- `docs/acceptance/step2b/2026-11-03T14-20-03-933Z-healthy/inspect-r3-1280.png`
- `docs/acceptance/step2b/2026-11-03T14-20-03-933Z-healthy/inspect-r3-320.png`
- `docs/acceptance/step2b/2026-11-03T14-20-03-933Z-healthy/inspect-r3-390.png`
- `docs/acceptance/step2b/2026-11-03T14-20-03-933Z-healthy/inspect-r3-760.png`
- `docs/acceptance/step2b/2026-11-03T14-20-03-933Z-healthy/inspect-r4-1280.png`
- `docs/acceptance/step2b/2026-11-03T14-20-03-933Z-healthy/inspect-r5-1280.png`
- `docs/acceptance/step2b/2026-11-03T14-20-03-933Z-healthy/keyboard-inspect-390.png`
- `docs/acceptance/step2b/2026-11-03T14-20-03-933Z-healthy/recovery-1-failed.png`
- `docs/acceptance/step2b/2026-11-03T14-20-03-933Z-healthy/recovery-2-recovered.png`
- `docs/acceptance/step2b/2026-11-03T14-20-03-933Z-healthy/results.json`
- `docs/acceptance/step2b/2026-11-03T14-20-03-933Z-healthy/summary.md`
- `docs/acceptance/step2b/2026-11-03T14-20-03-933Z-healthy/workspace-1280.png`
- `docs/acceptance/step2b/2026-11-03T14-20-03-933Z-healthy/workspace-320.png`
- `docs/acceptance/step2b/2026-11-03T14-20-03-933Z-healthy/workspace-390.png`
- `docs/acceptance/step2b/2026-11-03T14-20-03-933Z-healthy/workspace-760.png`
- `docs/acceptance/step2b/2026-11-03T16-10-20-032Z-db-down/db-down-inspect-1280.png`
- `docs/acceptance/step2b/2026-11-03T16-10-20-032Z-db-down/db-down-inspect-390.png`
- `docs/acceptance/step2b/2026-11-03T16-10-20-032Z-db-down/db-down-workspace-1280.png`
- `docs/acceptance/step2b/2026-11-03T16-10-20-032Z-db-down/db-down-workspace-390.png`
- `docs/acceptance/step2b/2026-11-03T16-10-20-032Z-db-down/results.json`
- `docs/acceptance/step2b/2026-11-03T16-10-20-032Z-db-down/summary.md`
- `docs/acceptance/step2b/2026-11-03T16-19-01-704Z-backend-down/backend-down-inspect-1280.png`
- `docs/acceptance/step2b/2026-11-03T16-19-01-704Z-backend-down/backend-down-inspect-390.png`
- `docs/acceptance/step2b/2026-11-03T16-19-01-704Z-backend-down/backend-down-workspace-1280.png`
- `docs/acceptance/step2b/2026-11-03T16-19-01-704Z-backend-down/backend-down-workspace-390.png`
- `docs/acceptance/step2b/2026-11-03T16-19-01-704Z-backend-down/results.json`
- `docs/acceptance/step2b/2026-11-03T16-19-01-704Z-backend-down/summary.md`
- `docs/acceptance/step2b/2026-11-03T16-42-44-084Z-unconfigured/results.json`
- `docs/acceptance/step2b/2026-11-03T16-42-44-084Z-unconfigured/summary.md`
- `docs/acceptance/step2b/2026-11-03T16-42-44-084Z-unconfigured/unconfigured-inspect-1280.png`
- `docs/acceptance/step2b/2026-11-03T16-42-44-084Z-unconfigured/unconfigured-inspect-390.png`
- `docs/acceptance/step2b/2026-11-03T16-42-44-084Z-unconfigured/unconfigured-workspace-1280.png`
- `docs/acceptance/step2b/2026-11-03T16-42-44-084Z-unconfigured/unconfigured-workspace-390.png`

## G. Temporary ZIP/reference bundles

- `aftermath-step2b-review-clean.zip`
- `aftermath-step2b-review.zip`
- `step2b-reference-bundle.zip`
- `step2b-test-fixes.zip`

## H. Dead discarded source

- `discarded-0004_temporal_integrity.py`

## I. Generated or ignored artifacts

- `apps/web/scripts/.DS_Store`

## J. Secret/local configuration

None identified in the supplied inventory.

## Completeness gates

- Confirm all migrations 0002, 0003, 0004, 0005, and 0006 are included; applied migrations are preserved.
- Include backend core/application/ports/adapters/API modules and both old and new regression tests.
- Include frontend routes, live components, API clients, reducer, classifier, behavioral tests, and acceptance scripts.
- Include `apps/web/app/fonts/Fraunces.ttf`, `apps/web/app/fonts/OFL.txt`, and `docs/third-party-assets.md` together.
- Include required documentation and selectively reviewed current evidence after verification.
- Keep ZIPs, discarded source, ignored generated files, and any local configuration out of the required implementation set. Local .env files may exist but their contents are not read or included here.
- All 198 supplied untracked paths and 21 tracked modifications are reconciled, including the 40 selected current evidence files. The user's final commit selection remains their decision; this inventory authorizes no Git mutation.

