# Data model: Turn and startup hardening

No stored entities change. In-process state only:

- **Breaker** (process-wide): `open_until`, `trial`, `recent: deque[(t, turn, timed_out)]`
  (pruned to the 60 s window, bounded). States: closed → open (connection error, or the window
  rule) → half-open after 30 s (one trial) → closed (trial success) / open (trial failure).
- **Turn** (`cache._Turn`, per chat turn): `external`. Closed counted (normal end) or abandoned
  (setup failed: not counted).
- **Local metrics hash** (Redis, existing): new fields `store_<outcome>@<operation>`.
