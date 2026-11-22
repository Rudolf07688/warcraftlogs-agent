# Contract: status frames (consumer side of `contract:chat-status-records`)

Shapes unchanged (server → browser):

```json
{"type":"thinking","text":"<= 120 chars"}
{"type":"interim","text":"<= 120 chars, may be empty"}
{"type":"model_retry","attempt":1,"max_attempts":5,"wait_s":4.0}
{"type":"model_fallback","from_model":"claude-a","to_model":"claude-b"}
```

085 guarantees on what the socket sends:
- `model_retry` numbers are finite and ≥ 0 (a non-finite or negative `wait_s` is sent as 0.0), so the frame is always valid JSON.
- `interim`: the turn's tokens are dropped before the frame is sent.

Browser → server: a frame typed `thinking` / `interim` is not a chat turn; it is rejected as `empty_message` and starts nothing.
