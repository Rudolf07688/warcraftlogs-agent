---
id: httpx-collapses-dot-segments
anchors: [file:backend/app/services/portraits.py, file:backend/app/services/guide_pipeline/research.py]
by: dev-1 Ansel
verified: b833929 2026-11-07
---
httpx 0.28 normalises literal '.' and '..' path segments when it builds a URL ('/a/x/../y'
becomes '/a/y'), so urllib quote(safe='') on a user value is not enough to pin an outbound path:
'..' survives quoting. Allow-list the segment's shape first (portraits.realm_slug / char_name),
then quote. '%2E%2E' is kept as is.
