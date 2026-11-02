# Sprint 2026-11-02 plan (PO: Maren)

Steer: "Ok start and complete the sprint. No further interactions from me." Fully autonomous.
Goal: close out the open bugs and qa-deferred items on the two epics the last sprints opened
(big-report turns, every fetch stored) plus small hardening debt, 20 points, no UI judgment.
Iteration: Sprint 2026-11-02 (id 366). Base: sprint-2026-11-02 @ 3b5e3ca.

## Features (all tier M, three parallel streams, disjoint files)

### 050-report-fights-and-kickoff (Nils, dev-3, opus/high, security-core) - 7 pts
- Agent picks the wrong last boss kill (sc-365, 2, bug, epic 340)
- Recent-raid kickoff answer still ~55k prompt tokens (sc-358, 2, epic 340)
- Untrusted text outside the data block (sc-351, 2, epic 100)
- One difficulty id-to-name map (sc-330, 1)

### 051-raw-store-hardening (Ansel, dev-1, opus/high, security-core, migration 0021) - 6 pts
- Stored-reports lookup: own-summary flag and grants-driven scan (sc-354, 3, epic 103)
- Private-report tombstones flushable by flooding; full queue drops gone signals (sc-353, 2, epic 103)
- Migration 0020 index without CONCURRENTLY (sc-359, 1, epic 103)

### 052-turn-and-startup-hardening (Tomas, dev-2, opus/high, security-core) - 7 pts
- Raw-store breaker counts one turn's timeouts as an outage (sc-355, 1, epic 103)
- Raw-store probe counters per operation (sc-332, 1, epic 103)
- No per-user limit on recent-raid investigate; pre-fetch while breaker open (sc-352, 1, epic 340)
- Local-answer count edge cases and turn-setup reset in ws.py (sc-357, 1, epic 103)
- App starts silently on the dev secret key (sc-356, 1)
- One set_config round trip; cache parsed TRUSTED_PROXIES (sc-270, 1)
- Both-limited wait budget counts only sleep time (sc-297, 1)

Ticket text (problems, locations, suggested fixes) is copied into each brief under briefs/.

## Decisions
- Accept team-lead's candidate sc-365, with one addition from the code: get_report_fights
  passes the whole fight list through `_cap` (60k chars); a long night with many trash pulls
  becomes a text prefix that keeps only the early fights, so the last kill can drop out.
  AC added: the last kill is visible even when the fight list is capped.
- Tier M for 051 although it pairs a migration with security work: the migration is additive
  (one flag column + indexes), the security items are Lows; P7 review covers the risk.
- All three streams security-core (D18): 050 marks untrusted text for the model, 051 touches
  tenant visibility and tombstones, 052 touches the shared store breaker, a rate limit and the
  secret key. One scoped qa-security review per hand-off.
- Out: UI epics (portraits, raids page, chat layout), worker server, upload, sub-agents
  (product direction). KB perf tickets (318-325) next sprint as a group.

## Drop first
sc-330 (refactor), then sc-270/sc-297 (small perf), then sc-332 (counters).
