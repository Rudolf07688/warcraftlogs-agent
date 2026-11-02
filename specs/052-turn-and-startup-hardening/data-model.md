# Data model: Turn and startup hardening

No stored entities change. In-process state only:

- **Breaker** (process-wide): `open_until`, `trial`, `recent: deque[(t, timed_out)]` (the ratio,
  pruned to the 60 s window, at most 256), `slow: OrderedDict[workspace, deque[t]]` (each
  workspace's latest timeouts, at most 3 each and 1024 workspaces; a workspace at 3 inside the
  window skips the store). States: closed → open (connection error, or timeouts from ≥ 2
  workspaces at ≥ half the window) → half-open after 30 s (one trial) → closed (trial success) /
  open (trial failure). `is_open()` and `skips(workspace)` read it without taking a trial.
- **Turn** (`cache._Turn`, per chat turn): `external`. Closed counted (normal end) or abandoned
  (setup failed: not counted).
- **Store-ops metrics hash** (Redis, new daily hash `wcl:metrics:v1:store_ops:<day>`, same
  retention as the others): fields `store_<outcome>@<operation>`, operation one of the app's own
  names or "custom". The existing local hash is unchanged.
