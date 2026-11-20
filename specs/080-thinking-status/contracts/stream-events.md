# Contract: new stream events (server → client, chat turns only)

## `thinking`
```json
{"type": "thinking", "text": "Comparing the death times across pulls."}
```
- `text`: plain text, 1–81 chars (80 + "…"), no control/format characters, no markdown markers.
- At most one per second per turn; never after answer text of the current segment started;
  never from a sub-agent's events. Transient: never saved, never indexed.
- Client: shows it as the one-line status under the spell cards; renders as text only, capped
  again at 120 chars; ignores it once answer text is showing; cleared on `tool_end`, `interim`
  replaces it, `done`/`error`/drop clear it.

## `interim`
```json
{"type": "interim", "text": "Warcraft Logs is throwing server errors on the player lists."}
```
- Meaning: all answer text streamed so far in this turn was progress, not answer.
- Server (`ws.py`): clears its accumulated tokens (what `done` saves); forwards the frame.
- Client: clears the streaming text; shows `text` (same rules as `thinking`; may be empty) as the
  status line.
- Invariant: concatenating the `token` frames after the last `interim` = the stored answer =
  the answer shown at `done`.

## Client → server
Frames of either type sent by a client are not chat turns: they fail `ChatTurn` validation
(`empty_message` error) and start nothing.
