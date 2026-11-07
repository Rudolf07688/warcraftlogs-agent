---
id: tokens-wrapper-reruns-itself
anchors: [file:.claude/team/tokens.py]
by: dev-2 Tomas
verified: d4d875d 2026-11-07
---
tokens.py re-runs itself under uv in the repo root (cwd=REPO), so the wrapper hands the inner
run the caller's --history as an absolute path in WCL_TOKENS_HISTORY, not by rewriting argv:
argparse accepts --history=F, --hist F and prefixes, which argv rewriting missed. Any other
cwd-relative input needs the same treatment. indiff.py likewise blames from the repo root.
