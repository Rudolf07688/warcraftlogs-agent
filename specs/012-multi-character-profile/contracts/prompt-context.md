# Contract: KNOWN PLAYER CONTEXT preamble and agent instruction

The preamble is built by `build_preamble` in `backend/app/services/profile_context.py`. It is prepended to the model input for a turn and never persisted.

## "You" line

| Own characters | Line |
|---|---|
| 0 | No line. If friends and guild are also empty and no metadata was captured, the preamble is `""`, as today. |
| 1 | `- You (self): {ident}`, **byte-identical to pre-feature output** |
| ≥2 | `- You (self) — the user plays all of these characters; "I/me/my" can mean any of them: {ident}; {ident}` |

`{ident}` is unchanged: `Name-Server (region) — Class — Spec — Role`. Parts that are not resolved are omitted.

Example with two own characters:

```text
KNOWN PLAYER CONTEXT (use only when the question is about the user, their friends, or their guild; answer population-level questions normally):
- You (self) — the user plays all of these characters; "I/me/my" can mean any of them: Alpha-Draenor (EU) — Mage — Frost — DPS; Beta-Draenor (EU) — Priest — Holy — Healer
- Friends: Thrall-Draenor (EU) — Shaman — Enhancement — DPS
```

## Spec guides

- Guides are grouped by `(class_name, active_spec)` across own characters and friends. Each distinct pair is injected once.
- The heading lists every profile character with that spec: `  ## Alpha, Gamma — Frost (guide for patch 12.1 · current)`.
- The per-guide (1500 characters) and total (4000 characters) caps are unchanged.
- With one character per pair, the output is byte-identical to today.

## RECENTLY SEEN reconciliation

Players already in the profile, now including every own character, are left out of the `- Players:` line. The behaviour is unchanged; the list it checks against just grows.

## Agent instruction (`wcl_agent/agent.py`, `<CONTEXT_RESOLUTION>`)

The first bullet is replaced with:

```text
- A KNOWN PLAYER CONTEXT block may list the user's own characters (one or several),
  their friends, and their main guild (with class/spec and spec guides). "I/me/my/mine"
  refers to the user's own characters — any of them. When a question about the user
  involves a report, check which of their own characters appear in it: if one does,
  answer about that character; if several do, cover each by name or ask which one is
  meant, never silently pick one; if none do, say none of their characters were found
  rather than answering about someone else. Use the block for "we/us", named friends,
  and the guild too, so the user need not re-type names. Do not narrow
  population-level or unrelated questions (best spec this tier, patch notes) to known
  players.
```
