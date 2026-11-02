# Quickstart: verify 052

```sh
python3 .claude/team/check.py run backend/tests/test_052_*.py --as tomas
python3 .claude/team/pg.py up tomas && python3 .claude/team/check.py run --pg tomas --as tomas && python3 .claude/team/pg.py down tomas
```

Live (team-lead): start the stack with `SITE_URL=https://example.org` and the dev `SECRET_KEY`:
the backend must refuse to start with a message naming `SECRET_KEY`.
