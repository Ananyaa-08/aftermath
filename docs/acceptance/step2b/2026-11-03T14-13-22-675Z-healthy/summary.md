# Step 2B browser acceptance: healthy

- Outcome: REJECTED
- Web: http://127.0.0.1:3001
- Browser: chromium 156.0.8078.4
- Started: 2026-11-03T14:13:22.676Z
- Checks: 19/20 passed

- PASS connectivity reports API + PostgreSQL ready
- PASS r1→r5 deliveries applied through the same-origin proxy
- PASS replaying the identical r3 delivery is idempotent
- PASS old snapshots remain independently resolvable after r5
- PASS API r2: exact 12→15 span at code points [14,16) on both sides
- PASS API r3 (AS-24): exactly one lineage edge, IDENTICAL r2→r3
- PASS API r3: one timeline-v1 comparison r1→r3, outside lineage
- PASS API r3: timeline span 12→15 has no lineage edge and names its timeline alignment
- PASS API r4: legal_notice authority-only change has no text side or invented timeline comparison
- PASS API r5: latest observed r4, effective predecessor r2, interval 2027-01-01→open
- PASS UI r1: DOCUMENT_ADDED and ADDITION interval from 2026-01-01
- PASS UI r2: struck 12 and inserted 15 at 14–16
- PASS UI r3: lineage section shows only IDENTICAL
- PASS UI r3: 'Timeline comparison · not lineage' lists MODIFIED r1→r3
- PASS UI r3: TIMELINE span 12→15 and April→December interval r1→r3
- PASS UI r4: AUTHORITY_CHANGED shows no textual side and no timeline section
- PASS UI r5: DOCUMENT_DELETED, before = r4, DELETION from r2 to Absent
- PASS UI: no inspection page shows an error alert
- FAIL harness completed without an exception
- PASS no unexpected browser console or page errors

Notes (informational, not pass/fail):

Screenshots (review visually):
- healthy-workspace-1280.png
- inspect-r1-1280.png
- inspect-r2-1280.png
- inspect-r3-1280.png
- inspect-r4-1280.png
- inspect-r5-1280.png
