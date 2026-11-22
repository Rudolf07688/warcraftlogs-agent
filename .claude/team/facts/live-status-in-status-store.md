---
id: live-status-in-status-store
anchors: [file:frontend/src/lib/statusStore.ts, sym:frontend/src/components/MessageList.tsx::TurnStatus]
by: dev-5 Edda
verified: a3e43e5 2026-11-22
---
The live turn status (indicator label, thought line, retry/fallback notice, quietSince) lives in
lib/statusStore.ts, not App state (085); only TurnStatus and TurnNotice (the notice under answer text, 088b) subscribe. App.handleFrame builds one
patch per frame and applies it after the switch; the store cleans every text (cleanStatus:
controls stripped, 120 code points). MessageList takes no status props. The store is a module
singleton: tests start each turn with send (statusStore.reset) or state leaks between tests.
