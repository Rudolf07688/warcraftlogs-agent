#!/usr/bin/env python3
"""SessionStart hook: re-inject meta/CURRENT.md after compaction, a resume or a new session.

Silent unless meta/CURRENT.md exists and says "Status: active". It never fails the session.
"""
import json
import os
import sys

MAX_CHARS = 4000

try:
    event = json.load(sys.stdin)
    if event.get("agent_id"):  # sub-agents don't need the owner's meta thread
        sys.exit(0)
    path = os.path.join(os.environ.get("CLAUDE_PROJECT_DIR", "."), "meta", "CURRENT.md")
    text = open(path).read()
    if "Status: active" in text:
        body = text if len(text) <= MAX_CHARS else text[:MAX_CHARS] + "\n... (truncated; read the file)"
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": f"[meta] An owner meta discussion is in progress ({event.get('source', 'start')}). "
                                 "Current focus from meta/CURRENT.md:\n" + body}}))
except Exception:
    pass
