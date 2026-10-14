# Quickstart: Multiple Own Characters on the Profile

**Feature**: 012-multi-character-profile | **Date**: 2026-10-14

## Run

```bash
docker compose up --build
```

No migration and no new environment variables.

## Automated checks

```bash
uv run pytest backend/tests/test_profile.py backend/tests/test_profile_context.py \
  backend/tests/test_roles.py backend/tests/test_tenant_isolation.py -q
uv run pytest -q
cd frontend && npm run build
```

## Verify US1: register several own characters

1. Open **Profile → Characters**. If you had a character before the upgrade, it is listed under **Your characters** with its role and guide badge (FR-006).
2. Add two more own characters. All three are listed. Guide badges go `pending` → `ready` on their own.
3. Change the role of one. Only that one changes.
4. Remove one, then reload. Two remain.
5. Add a character that is already in your list. The message reads "already added".
6. Add, as your own, a character saved as a friend. The message says it is saved as a friend. Do the reverse from the Friends card.
7. With 10 own characters, the Add button is disabled and its caption names the limit.

## Verify US2: the assistant resolves "I/me" across characters

1. With two own characters, open a new chat and ask any question. In the backend logs, or by setting a breakpoint in `build_preamble`, check that the "You" line lists both characters.
2. Pick a report that contains only your second character and ask "how did I do on <boss>?". The answer is about that character. You do not have to name it.
3. Pick a report that contains both characters and ask "how did I do?". The answer covers both by name, or asks which one you mean.
4. Pick a report that contains neither character and ask "how did I do?". The assistant says none of your characters were found.
5. Remove all but one own character and ask again. Behaviour matches the pre-feature single-character behaviour.
