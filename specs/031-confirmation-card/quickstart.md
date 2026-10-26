# Quickstart: verify 031

## Automated

```bash
cd /home/rudolf/dev/wcl-worktrees/dev-b
uv run --extra test pytest -q                                       # backend: no new failures
uv run --extra test pytest -q backend/tests/test_proposal_ws.py backend/tests/test_proposal_routes.py
cd frontend && npm test && npm run build                            # card test + typecheck + build
```

## sc-208 widths (headless Chrome, port 18031)

```bash
cd frontend && npm run build && npx vite preview --port 18031 --strictPort &
# For 390, 1280 and 1920: load a page that renders long messages and a wide table, then assert
# document.documentElement.scrollWidth <= window.innerWidth, and that the bubble widths are
# ≤ min(90%, 1200px) (agent) and ≤ min(75%, 900px) (user).
```

## Live check (owner, Under Review)

1. Ask Barnaby: "add the people from my last dungeon to my friends, except the shaman".
2. The card appears under his answer, with every player except the shaman. Approve N counts the
   valid rows.
3. With the profile page open in a second tab: Approve. The card shows per-row results, a
   "Done. Added …" line appears, and the second tab's friend list updates on its own.
4. Reload the chat: the card shows Applied with the same results.
5. Ask for another change and wait 30 min (or edit `expires_at`): the card shows "This proposal
   expired. Ask Barnaby again."
6. Resize to 390 / 1280 / 1920: no sideways page scroll; wide tables scroll inside the bubble.
