#!/usr/bin/env python3
"""SessionStart hook: re-inject meta/CURRENT.md and the lead memory after compaction, a resume
or a new session.

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
        lead = os.path.join(os.path.dirname(path), "team", "lead.md")
        if os.path.exists(lead):  # the lead's own lessons, written in the first person
            body += "\n\n[meta] Your lead memory (meta/team/lead.md):\n" + open(lead).read().partition("## Memory")[2].strip()
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": f"[meta] An owner meta discussion is in progress ({event.get('source', 'start')}). "
                                 "Current focus from meta/CURRENT.md:\n" + body}}))
except Exception:
    pass
