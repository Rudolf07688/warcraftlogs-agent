# Quickstart: check the history cache

Offline (no network, no credentials):

```sh
env -i HOME=$HOME PATH=$PATH uv run --extra test pytest -q backend/tests/test_087_history_cache.py
```

The replay test prints nothing; it asserts that from turn 4 on each turn's first request reads
the stubbed history and that a 30-turn replay costs at least 25% less than the 079 layout.

Live (team-lead, owner stack, Claude model): a 4-turn chat with a tool call per turn, turns less
than 5 minutes apart. In Loki/Tempo, the 4th turn's first model call shows
`cache_read_input_tokens` above the head size (tools + instruction) and
`cache_creation_input_tokens` covering only the previous turn and the new message.
