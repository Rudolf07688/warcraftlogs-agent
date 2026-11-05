# Brief docs-closeout (tier S): architecture docs + team facts, one pass

- Branch `docs-2026-11-05b` from `sprint-2026-11-05b` at b60f3ff (the tip after every fix round), worktree `/home/rudolf/dev/wcl-worktrees/dev-c` (check out the branch there). Seat dev-2 (Tomas), fresh run. Model sonnet, effort high.
- Footprint: `documentation/architecture/**` and `.claude/team/facts/**` only. No code changes.

## 1. Architecture docs (owner's rule: they always show the current state)
Follow `documentation/architecture/pages/maintaining.html`. `python3 .claude/team/archdocs.py changed` lists six pages whose code moved this sprint:
- `pages/agent.html` — 064: shorter instruction and tool docstrings; new `drop_schema_titles` before-model hook in `wcl_agent/agent.py`; fixed-part budget test.
- `pages/deployment.html` — 061: new `KB_EMBED_LOCATION` setting (default europe-west1) in `backend/app/config.py` / `.env.example`.
- `pages/frontend.html` — 063 + 063-fix: a dropped socket mid-turn ends the turn locally (`handleStatus`, `reloadAfterDrop`, stray-frame guard), answers only land in their own chat.
- `pages/knowledge-base.html` — 061 + 061-fix: query embeddings concurrent in a TaskGroup under a process-wide semaphore (5), regional endpoint, 3 s query deadline; cancelled requests recorded (queries only).
- `pages/models.html` — 061: `provider.genai_client(location)` and a per-location client for embeddings; `embed_texts(location=, deadline=)`.
- `pages/observability.html` — 062: service-graph copy rules take client-side latency for virtual-node servers; guarded ratio rules; D1 cache ratio panel bounded; `record_embedding` accepts BaseException.
Re-verify those sections **against the code** (not the specs or this list), fix what is wrong, add what is new, remove what is gone. Check `index.html` (layer table, system diagram) only changes if a layer changed (probably not). Then `archdocs.py stamp` and `archdocs.py check`; screenshot each changed page with headless Chrome (window taller than the page) and look at it.

## 2. Team facts, same pass
`python3 .claude/team/facts.py stale` lists the facts whose anchor moved this sprint. Re-check each against the code: `facts.py verify <id>` if still true, edit then verify if partly, `facts.py retire <id> --why "..."` if not. Then `facts.py lint` must be clean.

## Hand-off
Commit on your branch (message ends with `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`; never push). Board `handoff` key `status:docs` with: pages changed (one line each on what changed), facts verified / edited / retired, `archdocs.py check` and `facts.py lint` output, and one `Retro:` line. No check.py run needed (no code); I verify on merge.
