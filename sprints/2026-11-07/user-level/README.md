# User-level QA files, proposed (sprint 2026-11-07, story 065)

These live outside git in `~/.claude/` and were not edited (board `decision:user-level-files`).
Each file here is a full replacement for the file of the same name; team-lead copies them after
review:

- `skills/qa-sweep/SKILL.md` → `~/.claude/skills/qa-sweep/SKILL.md`
- `agents/qa-*.md` → `~/.claude/agents/qa-*.md`

The first commit on the branch holds the unchanged originals, so `git diff 9e5d04b -- sprints/2026-11-07/user-level`
shows exactly what changed.

## What changed and why (D21, layer 3: one independent read of the sprint diff)

- **Diff scope.** Given a range `<base>...<tip>`, each agent reviews only the lines it adds or
  changes and lists older-code problems in a short, uncounted "Outside the diff" list. Each
  finding carries `In diff: yes | no`. (Retro 2026-11-05b: sweeps of old code sent fix rounds
  down rabbit holes.)
- **Already-reviewed paths are skipped.** Code that had a D18 security review at hand-off is
  not swept again (Ilse, Maren).
- **No second suite run.** The agents don't run the full test suite when the caller says it
  already ran at the tip; linters and type checkers on changed files stay.
- **Fix bar in the index.** "Fix first" lists only findings that meet the bar (broken AC,
  security hole, data loss: Medium and above in the diff). Lows are one line each, and the
  index groups them by root cause into "Backlog groups", one ticket per group.

Word counts (before → after): qa-sweep 493 → 656, qa-bug-hunter 777 → 880, qa-performance
769 → 857, qa-security 650 → 746, qa-spec-conformance 715 → 819. These grew: each gained
the diff-scope rule, and they had no rule it replaces.
