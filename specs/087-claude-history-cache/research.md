# Research: Claude history cache across turns

Method (board `measure:087`): the real agent path (`agent_runner.stream_response`, `build_agent`)
on a scripted Anthropic transport; each captured request body replayed through a simulator of
Claude's prefix cache (entries at breakpoints, a hit is the longest stored prefix within 20 blocks
before a breakpoint). Cost units: read 0.1, write 1.25, uncached 1.0; tokens = chars / 4.
Scenario: 3 tool calls per turn, 8 kB results, 6 kB preamble, 1.5 kB answers, keep window 2.

| Layout | 8 turns | change | notes |
|---|---|---|---|
| base (079) | 238.7k | | turn 2 24.6k, rising +1.9k per turn |
| A: time + preamble after history | 238.7k | 0% | the trim boundary already diverges first |
| B: A + earlier preamble copies kept | 246.6k | +3% | turn 2 -26%, later turns +7% |
| C: B + stub in batches of 2 / 3 | 215.6k / 210.6k | -10 / -12% | prompt +16 / +27%, trim behaviour change |
| D: time into turn message + history breakpoint | 217.5k | -9% | per-turn growth +0.5k; no state |
| D, 30 turns | 981k vs 1,517k | -35% | turn 30: 39.9k vs 78.2k (-49%) |
| keep window 1 (any layout) | 182.1k | -24% | PERF-004 product choice, out of scope |

## Decisions

- **Decision**: layout D. **Rationale**: the only option that gains on every later turn without
  growing the prompt, keeping state or changing what the model sees from earlier turns.
  **Alternatives**: A (no gain), B (state, growth, net loss), C (behaviour change, bigger
  prompts), keep=1 (product decision).
- **Decision**: the change lives after ADK's breakpoint placement in `_build_anthropic_kwargs`.
  **Rationale**: Claude-only by construction; Gemini and `inject_preamble` (CRITICAL blast radius)
  stay untouched; each provider attempt rebuilds the dicts, so nothing doubles.
- **Known limits**: first history read at turn 4; a turn of 20+ blocks misses the look-back once;
  the wrap-up request and an effort or model change rewrite (as today).
