# Fix brief (tier S): 058 sweep + live-pass fixes, Ansel

- **Seat:** `dev-1` (Ansel). Parallel fixers: Nils (dev-3, 059 fixes; he now owns all of `backend/app/telemetry/setup.py` incl. the SQLAlchemy line, keeping your commenter options), Tomas (dev-2, 060 fixes). Board keys bind you.
- **Tier:** S (short plan, then implement; no Spec Kit). Branch `058-fix` from the sprint tip `sprint-2026-11-05` = `fcef188`, in worktree `/home/rudolf/dev/wcl-worktrees/dev-a`.
- **Security-core:** no (the security sweep confirmed your rework holds). Reports: `/home/rudolf/dev/wcl-worktrees/sprint/qa-reports/2026-11-05-sweep/{bugs,spec-conformance}.md` and board #76, #77.
- **Migration:** none (0022 stays as merged).

## Fix these
1. **Live FAIL #76, Mimir discards ~2.2 samples/s (`sample_duplicate_timestamp`).** On the live stack two series collapse to the same labels somewhere in the 058 scrape chain (suspects: the `labeldrop id|name|image|container_label_.*` applied to every job, or a family scraped/pushed twice). Find the series on your stack with cAdvisor and real-ish containers, fix it, and make `datastores.sh` assert Mimir's discarded-samples counter stays 0 for the run.
2. **Medium, D11 host line never appears (bugs.md = spec Low).** The drop rule `cadvisor;;.+` (`config.alloy:867`) matches the root cgroup `id="/"`, so the keep and `host` rewrite never fire. Fix the order or regex; `datastores.sh` must require the `host` series, not just allow it.
3. **Live FAIL #77, D9 top-statements table.** queryid renders as a number ("2.33 Quint") and stray `__name__ 1/2` columns show. Make queryid a string column and hide `__name__`; screenshot the panel as proof (headless chrome with a window taller than the page).
4. **Low, D9 "Statement time by queryid" unit (bugs.md).** It plots seconds per second with unit `s`; label/unit it so it doesn't read as a per-call latency.
5. **Docs drift (spec-conformance.md).** `specs/058-datastore-telemetry` spec/plan/research/tasks and the README 058 section still describe the docker-proxy / Docker-logs path the rework removed. Make them say what was built.

## Footprint
`observability/alloy/config.alloy` (the 058 section only), `observability/grafana/dashboards/infra/**`, `observability/mimir/rules/anonymous/datastores.yaml`, `observability/test/{datastores.sh,datastores_check.py}`, `backend/tests/test_telemetry_datastores.py`, `observability/README.md` (058 section), `specs/058-datastore-telemetry/**`. Nothing else (not compose, not setup.py).

## Proof and hand-off
`check.py run --as ansel` (receipt). Stack runs only as before (`wcl-obs-ansel`, 25xxx, `down -v`). Board `handoff` + final result: branch, commits, RESULT/RECEIPT lines, the duplicate series you found and why, finding-by-finding mapping. Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
