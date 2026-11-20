# Implementation Plan: Thinking status line and interim text as status

**Branch**: `080-thinking-status` | **Date**: 2026-11-20 | **Spec**: [spec.md](spec.md)

## Summary

The runner (`_run_turn`) stops dropping `thought` parts on chat turns: it accumulates the current
model call's thought text, derives a cleaned one-line status (first sentence of the latest
paragraph, 80 chars) and yields `{"type":"thinking","text"}` at most once a second, only while the
current segment has no answer text and only for the root agent's events. Text streamed in a round
that then calls a tool is retracted with `{"type":"interim","text"}`: `ws.py` clears its
accumulated tokens and forwards the frame; the browser clears its stream text and shows the line as
status. The live message gets a one-line status under the spell cards (thought line, or
"Thinking… Ns" after 3 s of silence while no tool casts). Greeting, guide jobs and evals
(`USER_ID`) are untouched.

## Technical Context

**Language/Version**: Python 3.12 (backend), TypeScript/React 19 (frontend)
**Primary Dependencies**: google-adk (runner events), FastAPI WebSocket, Vite/Vitest
**Storage**: none new (messages table unchanged; the saved text simply excludes interim text)
**Testing**: pytest with fake ADK runners (`SimpleNamespace` events); ws tests with the
`test_proposal_ws.py` helpers; Vitest + Testing Library for App/MessageList
**Project Type**: web app (backend/ + frontend/)
**Performance Goals**: ≤ 1 thinking frame/s per turn; status-line ticks re-render only the live
message
**Constraints**: chat-only (fact stream-response-shared-by-jobs); no prompt change (budget +0)
**Scale/Scope**: 2 backend files, 1 schema file (grant requested), ~5 frontend files

## Constitution Check

- **I Reuse-first**: reuses `_run_turn`'s round state (`streamed`, `text_sent`), the existing
  flag-on-record pattern (fact runner-outcome-flag-on-record), `_send` + Pydantic frames, the
  existing `.thinking` indicator styles, `streamStore`. PASS
- **II Small steps**: runner → ws → frontend, each with its tests. PASS
- **III Simplicity**: one retraction event meaning "drop all answer text so far" instead of
  segment offsets; no config knobs (two module constants). PASS
- **IV Typed boundaries**: `ThinkingFrame`, `InterimFrame` in `schemas.py` (grant requested on
  the board; fallback: dict frames like `token`). PASS (pending grant)
- **V Async**: no blocking work added. PASS
- **VI GitNexus**: impact on `_run_turn` (CRITICAL, shared by jobs: gated on `chat`),
  `_run_chat_turn`, `handleFrame`; detect-changes before hand-off. PASS
- **VII shadcn**: the status line is one line of muted text inside the existing live message;
  no registry component fits a single text line (Badge/Alert would add chrome the transient
  status must not have). Justified. PASS
- **VIII Backlog**: sc-569/sc-572 In Progress. PASS

## Project Structure

```text
specs/080-thinking-status/
├── spec.md, plan.md, research.md, quickstart.md, tasks.md, checkpoint.md
├── contracts/stream-events.md
└── livecheck_thoughts.py          # live pre-check script (team-lead runs it)

backend/app/agent_runner.py        # thinking + interim records, status-line helper
backend/app/api/ws.py              # forward thinking, clear tokens on interim
backend/app/schemas.py             # ThinkingFrame, InterimFrame (grant requested)
backend/tests/test_080_thinking_runner.py   # runner: thinking, throttle, hostile text, interim, jobs unchanged
backend/tests/test_080_thinking_ws.py       # ws: frames sent, stored = live, partial saves, KB, client frame
frontend/src/api/wsClient.ts       # Frame union: thinking, interim
frontend/src/App.tsx               # thought state, interim handling, activity time
frontend/src/components/MessageList.tsx   # status line in LiveMessage (ThinkingLine)
frontend/src/toolLabels.ts         # thinkingElapsedLabel
frontend/src/styles.css            # .thinking-status (transient look)
frontend/src/App.thinking.test.tsx # frames → DOM: hostile text, interim, after-answer, generic timer
```

No data-model change: no `data-model.md`.
