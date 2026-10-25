# Contract: `model_fallback` WebSocket frame (feature 021)

Additive to the chat socket contract (features 005 and 011). Clients that do not know
the type ignore it.

## Server → client

```json
{"type": "model_fallback", "from_model": "gemini-3.8-flash", "to_model": "gemini-3.7-flash"}
```

- Sent at most once per turn, when the turn's model stays rate limited after the retry
  policy and the turn continues on its sibling. Sent before the sibling's first answer
  token or tool frame of that request.
- `model_retry` frames may come before it (retries on the original model) and after it
  (retries on the sibling).
- The turn then ends as usual with `done`, or with
  `{"type": "error", "code": "rate_limited", "message": <feature 011 wording>}` if the
  sibling stays rate limited too. No further `model_fallback` follows in that turn.
- When the class has no sibling, no `model_fallback` is sent; the turn ends with the
  `rate_limited` error exactly as in feature 011.

## Client behaviour

- While streaming: the status line reads
  `"<from_model> is rate-limited — switching to <to_model>…"`.
- On `done`: the agent message carries a note
  `"Answered by <to_model> (<from_model> was rate-limited)"`. Not persisted.
- The model selector is not changed. The next turn is sent with the chosen model.

## Unchanged

- `ChatTurn` (client → server) is unchanged.
- `model_retry`, `error` and `done` shapes are unchanged.
