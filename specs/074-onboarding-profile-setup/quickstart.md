# Quickstart: 074

1. `uv run alembic -c backend/alembic.ini upgrade head` (adds 0023; existing workspaces are marked skipped).
2. Invite a new user, open the link, set a password → the browser lands on `/profile` with the
   welcome prompt.
3. Pick a class, spec and content, Save → reload shows the same values.
4. "Skip for now" → prompt gone; reload and sign out/in → still gone, chat opens normally.
5. Tests: `python3 .claude/team/check.py run backend/tests/test_074_onboarding.py --as <you>`;
   `cd frontend && npx vitest run src/auth src/components/onboarding`.
