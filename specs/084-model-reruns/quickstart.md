# Quickstart: 084

    python3 .claude/team/check.py run backend/tests/test_084_reruns.py backend/tests/test_084_runner_edges.py \
      backend/tests/test_079_claude_cache_budget.py backend/tests/test_080_thinking_runner.py \
      backend/tests/test_046_empty_turn.py backend/tests/test_model_retry.py --as vera

Live (team-lead): vertex + gemini-3.1-pro-preview, fresh chat "is frost mage difficult?" answers;
`turn stats` lines carry `empty_retries=`/`budget_retries=`.
