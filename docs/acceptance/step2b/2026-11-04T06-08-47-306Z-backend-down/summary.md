# Step 2B browser acceptance: backend-down

- Outcome: PASSED
- Web: http://127.0.0.1:3001
- Browser: chromium 156.0.8078.4
- Started: 2026-11-04T06:08:47.310Z
- Checks: 9/9 passed

- PASS @1280: /api/connectivity reports unreachable
- PASS @1280: connection bar shows "Backend could not be reached"
- PASS @1280: inspect view shows UNREACHABLE, substitutes no examples, renders no comparison
- PASS @1280: requested, inner and client widths match with no overflow
- PASS @390: /api/connectivity reports unreachable
- PASS @390: connection bar shows "Backend could not be reached"
- PASS @390: inspect view shows UNREACHABLE, substitutes no examples, renders no comparison
- PASS @390: requested, inner and client widths match with no overflow
- PASS no unexpected browser console or page errors

Notes (informational, not pass/fail):

Screenshots (review visually):
- backend-down-workspace-1280.png
- backend-down-inspect-1280.png
- backend-down-workspace-390.png
- backend-down-inspect-390.png
