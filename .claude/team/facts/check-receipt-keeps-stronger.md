---
id: check-receipt-keeps-stronger
anchors: [file:.claude/team/check.py]
by: dev-2 Tomas
verified: d8ac4bf 2026-11-07
---
A passing check.py run replaces the tree's receipt only if it proves a superset (backend,
frontend, full, pg); else it prints RECEIPT kept. Strength is derived from the recorded
commands, a missing base (only --full has none) and the pytest log showing TEST_DATABASE_URL,
never from the area or pg fields. Receipts carry 'logs'. npm ci runs unless
node_modules/.wcl-npm-ci-stamp matches the manifests hash; the fake npm in tests must rmtree
node_modules as the real one does.
