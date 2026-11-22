# Checkpoint 085

Decisions (board): scope:085:retraction-order, scope:085:drop-placeholder, scope:085:retry-under-cards, scope:085:status-text.

Files: backend/app/api/ws.py, backend/app/db/repository.py (get_main_selection only), backend/tests/test_085_status_frames.py, backend/tests/test_085_main_selection_pg.py, backend/tests/test_080_thinking_ws.py, frontend/src/lib/statusStore.ts, frontend/src/lib/statusText.ts, frontend/src/App.tsx, frontend/src/components/MessageList.tsx, frontend/src/App.thinking.test.tsx, frontend/src/components/MessageList.test.tsx.

Constraints: `_persist_partial` keeps its 4 positional args (tests patch it); `set_refresh_actor` call unchanged; contract shapes unchanged; Vera's 084 may send an empty `interim` after answer tokens at the end of a turn (#48), which the clear-before-send order handles.

Implementation starts at T004 (backend tests), then T006.
