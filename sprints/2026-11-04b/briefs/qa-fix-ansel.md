# Brief: QA fix round, build telemetry (055), tier S

- **Seat:** `dev-1` (Ansel). Fresh run: you don't have your build history; the reports below are your source. In parallel: Nils (dev-3) fixes 056 in `dev-b`, Tomas (dev-2) updates docs in `dev-c`. Disjoint files.
- **Tier S:** a short plan, then implement. No Spec Kit. Record decisions on the board (key `scope:055-fix:*`).
- **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-a`. Base: sprint tip `sprint-2026-11-04b` = `1c7a931`. Branch `055-qa-fix` from it.
- **Reports:** `/home/rudolf/dev/wcl-worktrees/sprint/qa-reports/2026-11-04b-sweep/{performance,security,bugs,spec-conformance}.md`; team-lead's live fail is board #66 (`live-check:055:board`), my triage #67.

## Fix these (and nothing else)
1. **Board-to-Loki never delivers / stuck log queue** (live fail #66; sweep PERF-001 Critical, SPEC-001, security SEC-001). Loki answers 503 for entries before its schema start (`observability/loki/loki.yaml:21`, from 2026-11-01); the exporter retries forever (`max_elapsed_time = "0s"`, file-backed queue) and current entries in the same batch never land.
   - Bound record timestamps before the shared batch so nothing older than Loki's accept window (or in the future beyond a small skew) can reach the Loki exporter from any source: drop it, or clamp it to the receive time with the original kept as an attribute. Your choice; say why on the board.
   - Move Loki's schema `from` date earlier (no data exists before it). Grant: `observability/loki/loki.yaml`, this change only.
   - Retry policy: make a refusal that can never succeed stop blocking the queue, while keeping T1's persistence promise (data sent while the backends are down lands after they restart; `persistence.sh` must still pass). A finite `max_elapsed_time` long enough for a normal outage is acceptable if you show the trade-off.
   - Proof: `board.sh` seeded with a board file dated before the schema start (and a far-future entry): current entries land; the stuck-queue case drains. A mutation that removes the bound makes it fail.
2. **Ratio panels 60× too high** (BUG-002 High / SPEC-002): `sum(A)*60 / sum(B)*60` in `claude-code-overview.json` (~227 cache hit ratio, ~552 edit accept rate) and `agent-team.json` (~148 sub-agent share, ~257 cache hit ratio). Fix the precedence, and make `test_team_dashboards.py` catch it (e.g. evaluate each ratio expr shape, or forbid an unparenthesised `* N` after a division); mutation must bite.
3. **`cc:cache_hit_ratio` denominator** (SPEC-009): spec §5.5 means cache reads over input-side tokens; output tokens don't belong in the denominator. Fix the rule in `build.yaml` and its test.
4. **Team-board carve-out by path, not payload** (sweep security SEC-002): the classify exception must apply only to records from the board tail branch, not to any sender claiming `service.name=team-board`. Show a spoofed OTLP record with that name still lands in the content stream.
5. **Narrow the board tail** (sweep security SEC-003): only board files (the board's own naming), and drop lines that aren't board entries (no `text`/`kind`).
6. **Sub-agents completed panel scans content** (PERF-004): add `content!="true"` (or the equivalent stream selector) at `agent-team.json` ~673.
7. **Spanmetrics stale series** (PERF-002): set `metrics_expiration` (and whatever the pinned Alloy needs so a new `service.version` doesn't leave frozen series). Verify the argument against the v1.21.3 docs.

8. **Live pass findings (board #68, team-lead on 1c7a931), yours:** (a) the D1/D2 ratio stats (item 2: 341749 %, 360000 %, 257886 % live); (b) D1 "Sessions" shows 0 during an active session; (d) counts shown as fractions on D1 (Lines of code 15.7, Commits 1.03): counts over a range must use `increase()` on the raw counter (or a counter-total alias), not `sum_over_time(rate alias) * 60`. Check every D1/D2 count stat for the same pattern. Note: alias panels start when the ruler started (no backfill); that is expected, not a bug.
9. **Gemini Flash prices (board #69):** set the gemini-3.6/3.7/3.8-flash rows in `observability/pricing/pricing.yaml` to $0.75 input / $3.75 output per M (cached input $0.075), with a comment naming the source (Vertex pricing page, 2026-11-04, introductory global-endpoint price through 2026-12-31; standard $1.50 / $7.50 from 2027-01-01). Regenerate `cost.yaml` with `generate.py`. Flash-Lite and 3.1 Pro stay marked unverified.

**Proof for every dashboard fix:** a headless screenshot (google-chrome or Grafana's render) of the fixed panel populated, on your own stack fed with synthetic data, plus a test that bites. Name the screenshot paths in your hand-off (scratch files, not committed). Team-lead re-checks on the tip afterwards.

Not in this round (Backlog): separate Faro exporters, native-histogram spanmetrics, PyYAML declaration, Tempo serviceMap datasource.

## Footprint
`observability/alloy/config.alloy` (your sections and the shared chain; not the Faro section at the end), `observability/loki/loki.yaml` (schema date only), `observability/mimir/rules/anonymous/{build,cost}.yaml`, `observability/pricing/**`, `observability/grafana/dashboards/build/**`, `observability/test/**` (not `faro*`), `backend/tests/test_team_*.py`, `specs/055-build-telemetry/**`. Not `observability/README.md` (Tomas updates docs in parallel; put any README facts in your hand-off and on the board under `docs:055-fix`).

## Docker
As before: `docker compose -p wcl-obs-ansel --profile observability ...` on 25xxx ports, observability services only, never the `warcraftlogs-agent` project; `down -v` after.

## Hand-off
Commit, `check.py run --as ansel` (receipt), rerun board/red/rules/dashboards/persistence/mutation scripts on the committed tree, board `handoff` with key `status:055-fix` naming each item and its proof, and return branch, head, RESULT/RECEIPT lines, per-item proof. Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
