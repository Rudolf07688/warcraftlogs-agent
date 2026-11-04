# QA triage, sprint 2026-11-04 (telemetry 1)

Sources: P7 review `qa-reports/2026-11-04/qa-security-054.md` (0 H / 3 M / 8 L) and the end sweep
`qa-reports/2026-11-04-sweep/README.md` on c212475 (0 C / 2 H / 10 M / 15 L). Both live in the
sprint worktree (gitignored).

## Fixed in the sprint
| Finding | Fix | Merge |
|---|---|---|
| P7 SEC-001 M: content and SQL values in exception text outside dev | exception type only outside dev; params cut | c212475 (rework) |
| P7 SEC-002/008 M: quadratic redaction regex, no attribute limits | linear pattern, 16 KiB cap, span limits | c212475 |
| P7 SEC-003 M: Host header as an unbounded metric label | metrics View allowlist | c212475 |
| P7 SEC-005 L (this sprint's regression): wrapper env turns telemetry on in tests | conftest strips OTEL_*; 2 s export timeout | c212475 |
| Sweep security SEC-001 H = SPEC-003: build-layer secrets pass Alloy | KEY=value, URL creds, ya29, gh tokens, PEM, Basic, bearer rules | 9501550 |
| Sweep security SEC-003 M: content routing fails open | fail-closed routing with a content-free allowlist | 9501550 |
| Sweep security SEC-002 M + PERF-003: Grafana anonymous Admin, memory cap | anonymous Viewer, admin password from .env, 512m, no preinstall | 9501550 |
| Sweep BUG-001 M: mutation.sh edits the live-mounted config | temp copy | 9501550 |
| Sweep BUG-002 M = SPEC-002 + SEC-006 L: wrapper gRPC endpoint leak, port injection | http/protobuf 4318, numeric port as argument | 9501550 |
| Sweep SPEC-001 M = BUG-006: service.version unknown | WCL_GIT_SHA exported by bin/01_start_app.sh | 9501550 |
| Sweep SPEC-005 L: Claude Code user/org ids as metric labels | dropped | 9501550 |
| Sweep PERF-001 H: dev content log record grows with the conversation | 32k-char cap, newest first, truncation mark | 1dce358 |
| Sweep BUG-003 M: shutdown ~9 s with a hung collector | one shared 3 s bound for all providers | 1dce358 |

## Accepted as designed
- P7 SEC-004: compose sets `WCL_ENVIRONMENT=dev` (the owner's decision: content on in dev).
- P7 SEC-010: `dev` in any letter case counts as dev; it is still an explicit opt-in.

## Deferred (all labelled qa-deferred, grouped by root cause)
| Ticket | Findings |
|---|---|
| sc-429 telemetry redaction gaps (3) | sweep SEC-004, SEC-007; P7 SEC-006; SPEC-008; board backlog notes (slices, extra shapes, auth key words) |
| sc-430 unauthenticated receivers and backends (2) | sweep SEC-005 |
| sc-431 span privacy (2) | P7 SEC-007, SEC-011 |
| sc-432 telemetry robustness and trace noise (2) | P7 SEC-009, sweep BUG-004, BUG-005, live-check CancelledError span, SDK handler deprecation |
| sc-433 telemetry cost (2) | sweep PERF-002, PERF-004, PERF-005, PERF-006 |
| sc-434 telemetry docs drift (1) | SPEC-004, SPEC-006, SPEC-007 |
| sc-435 NUL in chat message breaks the insert (1) | P7 SEC-001 residual |
| sc-436 flaky raw-store breaker trial test (1) | full-suite run on the 054 merge |

Matches with existing tickets: sc-329 (hide SQL params in error logs) got a dated breadcrumb.
No existing ticket was in this sweep's scope, so there are no "Not reported" comments.
Team-lead's live finding "Knowledge-base semantic search is always down" (sc-428) predates this sprint and is not a telemetry finding.
