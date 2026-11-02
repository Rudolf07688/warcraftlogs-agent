# Quickstart: verify 050

```bash
cd /home/rudolf/dev/wcl-worktrees/dev-a
python3 .claude/team/check.py run backend/tests/test_050_report_fights.py backend/tests/test_050_kickoff_overview.py backend/tests/test_050_untrusted_text.py --as nils
python3 .claude/team/check.py run --as nils   # full suite, receipt on a clean committed tree
```

Live (team-lead), from `.claude/team/livecheck.py`:

1. `topdmg` then `chart5` on BKNtypgnhrxXvj84: both name Ula'tek (fight 32).
2. A recent-raid kickoff: turn stats `max_prompt_tokens` under about 35k.
