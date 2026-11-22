# Research: 084

- **Empty STOP shape (ADK google_llm, SSE)**: the aggregator's `close()` gives a non-partial
  response with `finish_reason=STOP`, content `None` or a part with empty text, and the last
  usage (`candidates_token_count` 0 or None). Decision: detect on the final response only.
- **Claude streaming (ADK anthropic_llm)**: thought deltas stream as partials, the final
  aggregated response comes after `message_stop`; effort only via `AnthropicGenerateContentConfig`.
  No time limit of its own (SDK timeout 10 min). Decision: wall-clock deadline in the wrapper.
  Alternatives: effort cap on every call (changes answer quality, does not bound time);
  SDK `timeout` (covers the whole HTTP call but is per-client, read-timeout semantics, and gives
  no hook for the re-run).
- **Closing a cut stream**: `anthropic.AsyncStream.__stream__` closes its HTTP response in a
  `finally`; cancellation inside the read runs it. `_within` also `aclose()`s the generator chain.
- **Rate of empty STOP vs 082** (live-check:084-pre, team-lead #58): Loki holds Gemini turn stats
  only from 2026-11-20 16:02Z, all after 082 merged (2 empty of 10 turns), so no before/after
  comparison is possible. A fresh baseline at base (vertex, gemini-3.1-pro-preview, 6 frost chats
  + 3 deaths turns) gave 0 empty STOP in 35 calls, 9/9 answered. Rare and not reproducible on
  demand: nothing to tune on the prompt side; the re-run is proven with fakes. Every final Gemini
  event carries a trailing empty text part after the real text, so detection looks for any
  non-empty answer part, not for the absence of empty ones.
