# Research: 080 thinking status

## How thoughts arrive (live pre-check, team-lead #65; Vera #53)
- Claude (claude-sonnet-5-5, ADK 2.10): thinking deltas stream as partial events with one
  `Part(text, thought=True)` each, 2–33 chars per chunk (~12 chunks per call); the call's final
  non-partial event repeats the whole summary as thought parts, then the text. A call can stream no
  thought at all. All thoughts authored by `wcl_agent`.
- Gemini: pending (ADC expired on the host); Gemini summaries are known to start with a bold
  heading line ("**Analyzing X**") and stream in chunks too.
- Decision: accumulate partial thought text per model call; use the non-partial aggregate only
  when the call streamed no partials; reset at every non-partial event and every tool result.

## Retraction vs buffering (sc-572)
- Decision: retract on the round's first new tool call (`interim`); text after a call is
  retracted at the round's tool result.
- Rationale: the answer keeps streaming token by token; the server and browser apply one
  identical rule ("drop all answer text so far"), so stored = live.
- Alternatives: buffer text until the model call ends (answer arrives in one block, TTFT lost);
  segment offsets (two indexes to keep in sync across ws.py and the browser).

## Status-line text
- Decision: first sentence of the latest paragraph; heading line = sentence; a still-open
  paragraph counts once it has a sentence end or ≥ 80 chars; else the previous paragraph.
  Cleaning: strip ANSI CSI/OSC sequences, drop Unicode Cc/Cf (controls, bidi, zero-width),
  drop markdown markers (`*`, `` ` ``, leading `#`, `>`, `-`), collapse whitespace, cap 80 + "…".
- Throttle: ≥ 1.0 s between frames (module constant, injectable clock for tests).

## Generic line
- Decision: browser-side, from the last turn-event time; shown after 3 s while no card is casting
  and no thought line is current; ticks once a second in a small component so only it re-renders.
