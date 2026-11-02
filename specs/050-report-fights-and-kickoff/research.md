# Research: Report fights and kickoff

## R1 Why the live turn picked fight 2 (sc-365)

- Finding: not the result cap. Report BKNtypgnhrxXvj84 has ~32 fights; at ~400 characters per
  fight the list is ~13k characters, well under the 60k cap. Fights 1-2 are timed Mythic+ keys
  (`livecheck.py --facts`), so "Den of Nalorakk" fight 2 is a `kill: true` row with an
  encounter id. The fight list has no times and no kill marker, so "the last boss kill" was a
  guess over `kill: true` rows. The cap is a second real path on long nights (100+ trash pulls:
  the list becomes a text prefix of early fights).
- Decision: compute `last_kill` and `bosses` server-side from the full summary, outside the
  capped list; exclude key runs; tell the model to use `last_kill`.

## R2 End time vs start time

- Decision: order by `start_time_ms`, falling back to fight id.
- Rationale: fights in one report do not overlap, so the latest start is the latest end. The
  summary query does not fetch `endTime`; adding it changes `queries.py`, `cache_models.py`
  (outside the footprint) and every cached summary.
- Alternative: fetch `endTime` — rejected (footprint, cache churn, no behavioural gain).

## R3 Kickoff playbook placement

- Decision: `build_instruction(ctx)` appends the playbook (before `<CURRENT_TIME>`) when the
  turn's user message (`ctx.user_content`) starts with `RAID_KICKOFF_OPENING`;
  `kickoff_prompt_for` builds from that constant.
- Rationale: the kickoff prompt is the visible first user bubble; the playbook is model-facing.
  Placing it late keeps the shared instruction prefix cacheable.
- Alternative: move the playbook into the kickoff prompt — rejected (visible noise).

## R4 Slim view

- Decision: `get_report_table(..., overview=False)`; `overview=True` projects every list to its
  top 10 rows (plain fields), drops nested dicts (`playerDetails`) and `composition`.
- Measured (20-player Summary fixture): compact 15,395 chars; overview ~4.6k chars.
- Same WCL query text, so the kickoff pre-fetch and raw store still answer it.

## R5 Neutralising

- Decision: html-unescape then NFKC, repeated to a fixed point (bounded), then map every
  angle-bracket look-alike (ASCII, the old `‹ ›`, `« »`, CJK and math angle brackets, modifier
  letters, Canadian syllabics, ornaments) to `(` / `)`.
- Rationale: NFKC folds full-width `＜` and small-form `﹤` to `<`; entity decoding catches
  `&lt;`, `&#60;`, `&#x3c;` and double-encoded forms; the old replacements were themselves
  look-alikes.
- Alternative: a per-call random marker — rejected (changes the instruction's fixed `<data>`
  clause, pinned by the prompt contract tests).
