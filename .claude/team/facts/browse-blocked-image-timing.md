---
id: browse-blocked-image-timing
anchors: [file:.claude/team/browse.py]
by: dev-1 Ansel
verified: 0f91900 2026-11-07
---
browse.py fails external requests (BlockedByClient) only while it pumps DevTools events inside a
step, so an <img> that removes itself on error (ClassAvatar) is still counted by one eval and
gone by the next. Image counts on external URLs are timing, not app behaviour: count matches via
performance resource entries or the src set, never surviving <img> elements.
