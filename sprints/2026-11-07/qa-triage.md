# QA triage, sprint 2026-11-07

Sweep: `qa-bug-hunter` + `qa-security` over `9ff8602...894274d` only (tier-S sprint, D21).
Reports (gitignored): `/home/rudolf/dev/wcl-worktrees/sprint/qa-reports/2026-11-07-sweep/{bugs,security}.md`.
Totals: bugs 0 Critical / 1 High / 4 Medium / 9 Low; security 0 / 0 / 4 / 7.
Fix bar (D21): a broken AC, a security hole or data loss, Medium and above in new code; Lows only
when in a hunk being fixed anyway.

## Fixed (fix round, fresh agents per author)

| Finding | Sev | What | Fix |
|---|---|---|---|
| BUG-001 | High | Hook truncation hid the newest entries and moved the cursor past them (lost for good) | 069 Nils: oldest first, cursor only past what was shown |
| BUG-002 = SEC-002 | Medium | Reader alias learned from any `--as` text on a board.py line; relabelled QA agents, Nils and Maren live | 069: real `board.py` argv only, roster names, set once per agent id |
| BUG-003 + SEC-005 | Medium + Low (same hunk) | `--to` unvalidated: seat ids/typos reached nobody; newlines forged lines | 069: roster names, seat ids mapped, `all`; else refused |
| SEC-001 | Medium | browse.py: `\` URL parser differential passed the loopback guard | 070 Ansel: strict plain-URL rule |
| SEC-004 | Medium | browse.py checked only the first URL (redirects, JS, subresources) | 070: browser-wide Fetch interception fails every refused request |
| SEC-003 | Medium | stack.py let compose parse the owner's `.env` via unselected services' `env_file` | 070: up and down refuse a checkout with a `.env` |
| BUG-005 | Medium (same function) | Chrome leaked when launch failed after Popen | 070: started inside main's try |
| BUG-004 | Medium | A receipt's area depended on the chosen `--base`; verify could REUSE an `area=config` receipt for a backend branch | 071 Tomas: verify recomputes the touched area, shows the base, refuses |
| SEC-010 | Low (same hunk) | `--base` option injection into git argv | 071: refuse `-`, `rev-parse --verify --end-of-options` |

## Deferred (grouped by root cause, label `qa-deferred`, epic 525, Backlog)

No earlier QA tickets cover these tools (all new this sprint); no duplicates.

- **sc-538** browse.py hardening: SEC-011 (DevTools port reachable locally), ws:// and lib.sh 24xxx ports not guarded (#64), BUG-006 profile dir survives, BUG-007 timeout traceback.
- **sc-539** obsq.py credentials and edge cases: SEC-006, SEC-007, SEC-008, BUG-010, BUG-011.
- **sc-540** stack.py: SEC-009 (down removes any `wcl-obs-NAME`), up returns before Grafana is ready (live check #46).
- **sc-541** small CLI bugs: BUG-012, BUG-013 (check.py), BUG-008 (tokens), BUG-009 (indiff), BUG-014 (facts --runs).
- **sc-542** (chore, not QA) facts.py comp overlap noise (#37), boardwatch pre-check key (#30), facts.py "GitNexus unavailable".

## Side effects of the sweep itself

Both QA agents were relabelled by the old hook (BUG-002) and moved Ansel's and Nils's cursors;
both were finished. Stray cursor/alias files removed by Maren. The fix only takes effect after the
merge to main, because the hook runs main's board.py.
