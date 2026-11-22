# Implementation Plan: Status frames and turn costs

**Branch**: `085-status-frames` | **Date**: 2026-11-22 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/085-status-frames/spec.md`

## Summary

Socket side (`backend/app/api/ws.py`): clear the turn's tokens before sending `interim` (BUG-004);
on a drop after a retraction with nothing kept, save "(no response)" as the partial (SEC-002
residual); send `model_retry` with finite, non-negative numbers; read only main class/spec for the
preamble through a new narrow repository read. Browser side (`frontend/src`): a `statusStore` next
to `streamStore` holds the live status (label, thought, model notice, last-event time); only the
live message subscribes; the status line shows the retry/fallback notice under spell cards; status
text is cleaned (bidi/zero-width controls), clamped by code point and rendered `dir="auto"`.

## Technical Context

**Language/Version**: Python 3.12 (FastAPI, async SQLAlchemy); TypeScript + React 18 (Vite)
**Primary Dependencies**: existing only; no new package
**Storage**: Postgres (SQLite in unit tests); no migration
**Testing**: pytest (+ `pg.py` Postgres for RLS), vitest + testing-library
**Target Platform**: web app (browser + FastAPI WebSocket)
**Project Type**: web application (backend + frontend)
**Performance Goals**: 0 App / MessageList re-renders per thinking frame; 1 two-column settings query per turn
**Constraints**: `contract:chat-status-records` shapes unchanged; no DB session across a frame send or the cancel wait; no per-frame DB write
**Scale/Scope**: thinking frames ≤ 1/s per turn (runner throttle); status text ≤ 120 code points

## Constitution Check

- I Reuse-first: `statusStore` copies the `streamStore` pattern; ws test helpers from `test_proposal_ws` / `test_076`; existing "(no response)" wording. PASS
- II Small verified steps: hostile-input and bound tests first, then each fix. PASS
- III Simplicity: no new frame type, no new wire field, no migration; one repo function. PASS
- IV Typed boundaries: frames stay Pydantic (`ModelRetryFrame`); store state typed in TS. PASS
- V Async FastAPI: no blocking calls added; no session held across awaits on the socket. PASS
- VI GitNexus: impact run on `_run_chat_turn`, `_persist_partial`, `_build_turn_preamble`, `TurnStatus`, `LiveMessage` (all LOW; `MessageListImpl` UNKNOWN, used only via `MessageList` in App and its tests). PASS
- VII shadcn: no new UI component (a text line). N/A
- VIII Backlog: sc-582/sc-583 In Progress. PASS

## Project Structure

### Documentation (this feature)

```text
specs/085-status-frames/
├── spec.md, plan.md, research.md, data-model.md, quickstart.md, tasks.md, checkpoint.md
└── contracts/status-frames.md
```

### Source Code (files touched)

```text
backend/app/api/ws.py                 # retraction order, drop placeholder, retry frame numbers, narrow preamble read
backend/app/db/repository.py          # + get_main_selection (two columns, tenant-scoped)
backend/tests/test_085_status_frames.py   # new: cancel/drop/save races, retry frame, bounds
backend/tests/test_085_main_selection_pg.py  # new: RLS + selected columns on Postgres
backend/tests/test_080_thinking_ws.py # SEC-002 drop test now expects the placeholder
backend/tests/test_082b_preamble_main.py  # unchanged unless the read moves (kept green)
frontend/src/lib/statusStore.ts       # new store
frontend/src/lib/statusText.ts        # new: clean + clamp status text
frontend/src/App.tsx                  # writes the store instead of state; reload logic unchanged
frontend/src/components/MessageList.tsx  # LiveMessage/TurnStatus read the store; notice under cards
frontend/src/App.thinking.test.tsx    # hostile text, retry under cards, render-count bound
frontend/src/components/MessageList.test.tsx  # drop the removed `status` prop if needed
```

**Structure Decision**: existing web-app layout; no new module outside `frontend/src/lib`.

## Complexity Tracking

None.
