# Card round, 2026-11-07 (after the retro)

Owner: "give the whole team a short round to reflect on their agent card, with access to these
retro notes, and allow them to make changes as they please."

Your **card** is your own file `meta/team/<your seat>.md`: the header (name, role, about) and
your memory. Read first:
- `meta/sprints/2026-11-07/retro.md` (round 1, every member's answers)
- P16 in `meta/team-optimisation.md` (what the owner agreed next: lessons injected
  automatically at the moment of work, about five tool entry points, stream types, rule
  changes reviewed by the seats they touch)

Then change your card as you please:
- Header lines (`name`, `role`, `about`): edit your own file directly and keep the exact
  `- **field:** value` format. A new name must be one capitalised word, unique on the roster
  (`member.py roster`). Leave `seat` and `since` alone.
- Memory: `member.py remember --seat <seat> -` (replaces it; cap 500 words). Lessons that
  are really facts or rules belong elsewhere: the hook-injected facts/hazards (P16) will carry
  them better than memory.

You may touch **only your own card**. No other file, no commits, no board posts. If you'd change
your shared agent definition (`.claude/agents/<role>.md`), say so in your answer: it feeds P16
step 1, which your seat reviews before it lands.

Return at most about 120 words: what you changed on your card and why (or "unchanged"), and any
proposed agent-file change.
