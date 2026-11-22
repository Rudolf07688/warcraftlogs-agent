# Data model: 084

- `TurnStats.empty_retries: int = 0` (Gemini empty-STOP re-runs this turn).
- `TurnStats.reruns` (property): `budget_retries + empty_retries`; the runner watches it to tell
  a re-run's thoughts from the call before.
No storage, no migration.
