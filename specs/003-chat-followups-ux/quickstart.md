# Quickstart: Chat Follow-ups & UX Enhancements

Manual verification for each user story. Backend slices also have pytest coverage;
frontend/persona slices are verified here (no frontend test harness).

## Prerequisites

```bash
uv sync                      # Python 3.14 env
# backend (from repo root)
uv run uvicorn backend.app.main:app --reload
# frontend (in another shell)
cd frontend && npm install && npm run dev
```

Open the dev URL (default http://localhost:5173).

## Automated tests (backend)

```bash
uv run pytest backend/tests/test_suggestions.py \
              backend/tests/test_parallel_tools.py \
              backend/tests/test_api.py -q
```

Expected: suggestions capped at ≤3 and empty for trivial turns; concurrent tools finish
faster than sequential and all large outputs are captured intact; one failing tool leaves
the others usable; the WS turn emits a `suggestions` frame before `done` when applicable.

## US1 — Follow-up suggestions (P1)

1. Ask an analytical question (e.g. "How is my guild's DPS on the latest boss?").
2. **Verify**: after the answer finishes, **0–3** suggestion buttons appear beneath it,
   each a relevant next question. Never more than 3.
3. Click a suggestion. **Verify**: its text is submitted as your next message verbatim and
   answered; previous turn's buttons do not linger on the new turn.
4. Send a greeting ("hi"). **Verify**: no suggestion buttons appear (nothing useful to
   suggest).
5. While a response is streaming, **verify** suggestion buttons are disabled (no interleaved
   turns).

## US2 — Reliable parallel tools + shared scratch (P2)

1. Ask a multi-lookup question (e.g. "compare arcane, fire, and frost mage on this boss").
2. **Verify** (logs/timing): the independent lookups run concurrently (turn is faster than
   running them one at a time) and the answer reflects **all** successful lookups.
3. Trigger a large-output lookup (full report table). **Verify** the answer uses the full
   data (no truncation) and any PDF/graph capture still works.
4. (Fault injection in test) one lookup fails: **verify** the others' results are still used
   and the failed one is called out, not a whole-turn failure.

## US3 — Response panel sizing (P2)

1. Send a very long answer and a one-line answer. **Verify** the panel grows for the long
   one (scrolls normally) and doesn't reserve a fixed empty block for the short one.
2. Resize the browser window narrow→wide. **Verify** response panels reflow to use the
   available width (no clipping, no stuck fixed width).

## US4 — Barnaby persona (P3)

1. Ask "who are you?". **Verify** it introduces itself as **Barnaby**, the tavern/innkeeper.
2. Share a weak parse / obvious mistake. **Verify** Barnaby plainly names the mistake with
   good humor (not just praise) while the numbers stay accurate and data-grounded.

## US5 — Resizable side panel (P3)

1. Drag the sidebar's right edge. **Verify** it resizes smoothly and the chat reflows.
2. Drag to both extremes. **Verify** it stops at sensible min/max and the handle stays
   reachable.
3. Reload the page. **Verify** the chosen width is restored.

## US6 — Togglable background (P3)

1. Load the app. **Verify** the new `morgan-howell-img-1760.jpg` is the background by
   default and chat text is legible over it.
2. Switch the background (toggle/config) to the classic/previous option and to "solid".
   **Verify** the background changes and text stays legible; reload restores the choice.
3. (Negative) point the config at a missing image. **Verify** it falls back to the solid
   color rather than breaking the layout.

## Done when

All six sections pass and `uv run pytest -q` is green. Run `gitnexus_detect_changes()`
before committing to confirm only the expected symbols/flows changed.
