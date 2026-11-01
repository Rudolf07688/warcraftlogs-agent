# Common rules for all three developer briefs (sprint 2026-11-01)

From Ilse (scrum master, `ilse` on the board). Read this together with your feature brief.

## Team
- Product owner: Maren (`maren`). Scrum master: Ilse (`ilse`): gates, file grants, merges.
- 043 kb-store-embed: Ansel (`dev-1`), worktree `/home/rudolf/dev/wcl-worktrees/dev-a`.
- 044 kb-search: new `dev-3` (claims a name on first run), worktree `/home/rudolf/dev/wcl-worktrees/dev-b`.
- 045 local-data-reads: Tomas (`dev-2`), worktree `/home/rudolf/dev/wcl-worktrees/dev-c`.
- **Base ref:** `sprint-2026-11-01` (tip `cda1f42 or later` at launch). Your worktree is detached at
  `ec966c5`; create your branch from the sprint tip:
  `git -C <worktree> switch -c <NNN-short-name> sprint-2026-11-01`.
- When the sprint tip moves (a milestone merge you depend on), rebase onto it:
  `git -C <worktree> rebase sprint-2026-11-01`. I post every `merge` on the board.

## Read first
- `.specify/memory/constitution.md` (binding), `CLAUDE.md`, `documentation/ai_guide.md`.
- `documentation/designs/20261101_semantic_knowledge_base.md`: the agreed design. Details may
  change where the code says otherwise; post the reason as a `decision`.
- `sprints/2026-11-01/plan.md`: all ACs and the order. Board: `python3 .claude/team/board.py current`.

## Autonomy (owner preference 16)
"I value your initiative, your recommendations and your learnings as an individual. I want to
give you autonomy as much as possible." Decide, act, explain afterwards: post real decisions
as `decision` keyed `scope:<NNN>:<topic>`, clarify answers keyed `clarify:<NNN>-<topic>`.
Return "blocked: ..." only for what is genuinely not yours (a file outside your grants, an
irreversible action, scope beyond your stories). Product questions: board `question` to
Maren, then carry on with your recommended answer unless it changes scope.

## Gates (tier L)
At each gate named in your brief, **stop and return** your result to me (the gate summary is
your final message for that run). I review in one round and resume you with `SendMessage`.
Don't wait for anything else; your run ends at the gate.

## Contracts between the features (fixed now, board keys `contract:*`)
1. **Name resolver (044, sc-304):** module `backend/app/services/name_resolver.py`. Typed
   results; an unknown/ambiguous value raises/returns a typed, correctable error carrying the
   close matches. 043 (chunk writers) and 045 (sc-131) import it after the sc-304 merge.
2. **Embedder (043):** `backend/app/kb/embedder.py`, shipped with the sc-111 milestone merge:
   ```python
   EmbedTask = Literal["RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY"]
   class Embedder(Protocol):
       model: str
       async def embed(self, texts: Sequence[str], *, task: EmbedTask) -> list[list[float]]: ...  # unit-norm, 768-d
   def get_embedder() -> Embedder | None   # None when embeddings are unavailable
   ```
   plus an injection point for tests. The Vertex implementation may come with sc-112. 044 codes
   against the Protocol with its own fake.
3. **Visibility clause (045, sc-295):** in `backend/app/repositories/raw_fetches.py`:
   `fetch_visible_clause(raw_fetch_id, *, tenant_id: uuid.UUID | None, since: datetime) -> ColumnElement[bool]`,
   the SQL form of the 039 rule (the row exists and names at least one report code; every code
   is at most `MAX_CODE` long and is public-checked-at-or-after `since` or granted to
   `tenant_id` at or after `since`; works on SQLite and Postgres). `read_visible_fetch` uses
   the same clause, so the rule has one definition. Freshness stays outside the clause. 044
   joins `kb_chunks.raw_fetch_id` through it and never mentions `RawFetch` itself (the 039 guard
   test in `test_raw_store_visibility.py` must stay unchanged and green).
4. **sc-131 tool names (045):** `list_stored_fights`, `get_stored_fight_table`,
   `list_stored_reports_for_character`. 044's search-first prompt (sc-115) names these.

## File ownership (hard rule)
- The board's `owner:<path>` keys are the ledger; your brief lists your grants and the
  **sequenced** files you get later. Touch nothing else; a needed file means a `blocker`.
- Sequenced files change hands only by a board entry from me (`granted to <name>`). When you
  finish with a sequenced file early, post `change` keyed `owner:<path>` with `released`.
- Never commit `CLAUDE.md`, `AGENTS.md`, `todo.md`, `.specify/memory/constitution.md`,
  `.specify/feature.json` (restore them before each commit: Spec Kit rewrites some).
- Before each commit: `git diff --name-only sprint-2026-11-01...HEAD` plus uncommitted
  changes list only your files.

## Environment
- Clean env for every suite: `env -i HOME=$HOME PATH=$PATH uv run --extra test pytest -q`.
- zsh: use shell functions, not command variables.
- **Throwaway Postgres:** image `pgvector/pgvector:pg17` (not `postgres:17`), on your port
  (043: 15443, 044: 15444, 045: 15445; Redis if needed: 16443/16444/16445). Recipe:
  `specs/039-local-first-data/quickstart.md` §2 with the image and port swapped; alembic needs
  `-c backend/alembic.ini`. Name it `wcl-<NNN>-pg`, run it with `--rm`, and **stop it when done**
  (disk is tight: 21 GB). Never `docker compose`, never the compose `db`.
- Never read the owner's `.env`. No live WCL, Vertex or LLM calls: fakes and fixtures only.
  Questions only a live run can answer: board `question` keyed `live-check:<NNN>` with exact steps.
- The frontend build dirties `frontend/tsconfig.tsbuildinfo`; don't commit it.
- GitNexus is mandatory (developer.md): impact before every edit of an existing symbol (index
  your worktree, pass its absolute path as `--repo`), detect-changes before every commit.
- Commits end with `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`. Never push.

## Tickets
Move your stories to **In Progress** when you start and to **Under Review** at your final
hand-off (Shortcut, Standard workflow). Never Done.

## Hand-off contents
Branch, base, head commit; files changed; test counts before/after (SQLite suite and the
Postgres-only tests on your container); risks with mitigations; decisions; owner live-check
steps; an AC -> test/check table; a short "Autonomy" section (decisions made without asking,
and which you'd make differently). Keep it short.
