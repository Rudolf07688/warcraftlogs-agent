# Quickstart: Verifying Phase 5 (Captured-Metadata Reuse, Findings Reports, Role-Aware Profiles)

Manual verification of the three slices. Assumes the app runs locally (FastAPI backend + React frontend), an activated account, and a Warcraft Logs report code to query. Run migrations first: `uv run alembic upgrade head` (applies `0005_known_entities` then `0006_raid_role`).

## Prereqs
- `uv sync` and the backend running (`uv run uvicorn backend.app.main:app --reload` or the project's run skill).
- Frontend running (Vite dev server).
- Signed in as a tenant user; a second account available to prove isolation.

---

## US1 — Captured metadata reused across conversations (P1)

1. **Capture**: In a new chat, ask about a specific report (e.g. "analyze report `<code>`") so report tools succeed, and ask about a named character's rankings and a boss by name (triggers `find_encounter`).
2. **Verify capture (DB)**: `known_players` and `known_encounters` have rows for your tenant; `tracked_raids` has the report. All rows carry your `tenant_id`.
3. **Reuse**: Open a **brand-new** conversation and reference the raid loosely ("that pull from earlier" / by guild / by zone), and the player/boss by name.
   - ✅ The assistant resolves them **without** re-issuing the report-metadata lookup (watch tool_start frames — the cold lookup should not recur).
4. **Bounded**: With many captures, the injected `RECENTLY SEEN (this account)` block stays within its char cap (inspect the preamble if logging it in dev).
5. **Isolation**: Sign in as the second account → none of the first account's raids/players/encounters appear in context or DB queries scoped to that tenant.
6. **Empty-state**: A fresh tenant with no captures behaves exactly as before (no `RECENTLY SEEN` block).

Pass = scenarios US1-2..US1-7 in spec hold; SC-001/SC-002/SC-003 observable.

---

## US2 — Conversation-level findings report (P1)

1. Have a multi-turn analysis conversation (several bosses, parse numbers, a recommendation), ideally producing a chart.
2. Click the conversation **Download report**.
   - ✅ The PDF body is organized by **findings/topic** (Summary, Key Findings, per-boss/per-player results, Recommendations) — **not** a Q&A transcript.
   - ✅ The headline metrics discussed appear under Key Findings; charts still appear.
   - ✅ Title still prefers the tracked-raid label.
3. **No-findings**: Export a chit-chat-only conversation → the report states there were no substantive findings (no fabrication).
4. **Failure**: Simulate synthesis failure (e.g. invalid `wcl_report_model`) → `500` and no file downloads (never a partial PDF).

Pass = US2 scenarios; SC-004/SC-006.

---

## US3 — Per-message findings report (P2)

1. On one substantive agent reply, click its **Download report** (⬇).
   - ✅ The PDF synthesizes **only that reply's** findings, using its originating question as context.
   - ✅ Only that reply's charts appear; other replies' findings are absent.
2. A short/acknowledgement reply → "no substantive findings" doc.

Pass = US3 scenarios; SC-005.

---

## US4 — Role-aware profile: multiple friends + raid roles (P2)

1. **Multiple friends**: Add 3 friends with distinct identities → all persist, no cap. Re-add an existing one → friendly **"already added"** message (not a generic failure).
2. **Inferred role**: For a friend whose spec resolves (guide task → `active_spec`), the profile shows an **inferred** role (e.g. a Protection spec → Tank) with no override set.
3. **Override**: Set one friend to a different role via the UI (hits `PATCH /api/profile/friends/{id}`) and set your self role (`PUT /self`). Reload → overrides persist over the inferred default.
4. **Unset**: A character with no resolved spec and no override shows no role cleanly (no empty "— " artifact), in UI and in the preamble.
5. **Validation**: `PATCH` with an invalid role value → `422`, character unchanged.
6. **Role-aware answer**: Ask a role-sensitive question about a character → the `KNOWN PLAYER CONTEXT` preamble line includes its effective role (e.g. `… — Tank`).

Pass = US4 scenarios; SC-007. Confirm SC-008: with empty metadata and no roles set, behavior is unchanged.

---

## Automated checks (pytest)
```
uv run pytest backend/tests -k "known or preamble or synthesis or role or friend"
```
Covers: `role_for_spec` mapping; player/encounter extractors; `build_preamble` empty-state byte-equality and capped output; `synthesize_findings` empty/failure paths (genai mocked); friends PATCH + duplicate-friend path.
