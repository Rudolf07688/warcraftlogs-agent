#!/usr/bin/env python3
"""Persistent team members: a self-chosen name per seat, plus a small curated memory.

The `lead` seat is team-lead (the main session): it has no persona name, only a memory.

Agent-facing. Seats are stable slots (lead, po, sm, dev-1, dev-2, ...). Whoever is launched into
a seat inherits its name and memory. Files live in the MAIN checkout's meta/team/, so
every worktree reads and writes the same copy. team-lead commits them at wrap-up.

  member.py me --seat SEAT                       who you are + your memory (run this first)
  member.py claim --seat SEAT --name NAME --role ROLE --about "one line"   (lead: no --name)
  member.py remember --seat SEAT [-|PATH]         REPLACE your memory (max 500 words; lead 1000)
  member.py roster                               everyone on the team, one line each
"""
import argparse
import os
import re
import subprocess
import sys
from datetime import date

WORD_CAP = 500
LEAD_WORD_CAP = 1000  # owner, 2026-11-01: team-lead gets a larger memory
SEP = "\n## Memory\n"


def team_dir():
    common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                            capture_output=True, text=True, check=True).stdout.strip()
    path = os.path.join(os.path.dirname(common), "meta", "team")
    os.makedirs(path, exist_ok=True)
    return path


def seat_file(seat):
    if not re.fullmatch(r"lead|po|sm|dev-[0-9]+", seat):
        sys.exit("member: seat must be lead, po, sm or dev-<n>")
    return os.path.join(team_dir(), f"{seat}.md")


def parse(path):
    text = open(path).read()
    head, _, memory = text.partition(SEP)
    fields = dict(re.findall(r"^- \*\*(\w+):\*\* (.*)$", head, re.M))
    return fields, memory.strip()


def write(path, fields, memory):
    head = f"# {fields['name']}\n\n" + "\n".join(
        f"- **{k}:** {fields[k]}" for k in ("name", "seat", "role", "since", "about"))
    open(path, "w").write(head + "\n" + SEP + "\n" + (memory.strip() + "\n" if memory.strip() else ""))


def words(text):
    return len(re.findall(r"\S+", text))


def cap(seat):
    return LEAD_WORD_CAP if seat == "lead" else WORD_CAP


def cmd_me(a):
    path = seat_file(a.seat)
    if not os.path.exists(path) and a.seat == "lead":
        print("member: the lead seat is unclaimed. Run\n  python3 .claude/team/member.py claim --seat lead "
              "--role \"team lead (main session)\" --about \"<one line>\"")
        return
    if not os.path.exists(path):
        taken = ", ".join(r["name"] for r in roster_rows()) or "none yet"
        print(f"member: seat {a.seat} is unclaimed. You are its first holder: pick a short, "
              f"distinct first name for yourself (taken: {taken}) and run\n"
              f"  python3 .claude/team/member.py claim --seat {a.seat} --name <Name> "
              f"--role <role> --about \"<one line about how you work>\"\n"
              "Use that name as your board --as from now on.")
        return
    fields, memory = parse(path)
    print(f"You are {fields['name']} ({fields['role']}, seat {a.seat}, since {fields['since']}). "
          f"{fields['about']}\nUse --as {fields['name'].lower()} on the board.\n")
    print(f"Your memory ({words(memory)}/{cap(a.seat)} words):\n{memory or '(empty)'}")


def roster_rows():
    rows = []
    for f in sorted(os.listdir(team_dir())):
        if f.endswith(".md") and f != "README.md":
            fields, memory = parse(os.path.join(team_dir(), f))
            rows.append({**fields, "words": words(memory)})
    return rows


def cmd_claim(a):
    path = seat_file(a.seat)
    if os.path.exists(path):
        sys.exit(f"member: seat {a.seat} already belongs to {parse(path)[0]['name']}")
    if a.seat == "lead":
        a.name = "team-lead"  # the lead keeps a memory, not a persona
    elif not a.name or not re.fullmatch(r"[A-Z][A-Za-z-]{1,19}", a.name):
        sys.exit("member: name must be one capitalised word, 2-20 letters")
    elif any(r["name"].lower() == a.name.lower() for r in roster_rows()):
        sys.exit(f"member: {a.name} is taken; pick another")
    write(path, {"name": a.name, "seat": a.seat, "role": a.role, "since": date.today().isoformat(),
                 "about": " ".join(a.about.split())}, "")
    print(f"member: welcome, {a.name}. Seat {a.seat} is yours; use --as {a.name.lower()} on the board.")


def cmd_remember(a):
    path = seat_file(a.seat)
    if not os.path.exists(path):
        sys.exit(f"member: claim seat {a.seat} first")
    src = a.file_opt or a.file
    text = sys.stdin.read() if src in (None, "-") else open(src).read()
    n = words(text)
    if n > cap(a.seat):
        sys.exit(f"member: {n} words is over the {cap(a.seat)}-word cap. Nothing saved. "
                 "Cut the least useful lines and try again.")
    fields, _ = parse(path)
    write(path, fields, text)
    print(f"member: memory saved for {fields['name']} ({n}/{cap(a.seat)} words)")


def cmd_roster(a):
    rows = roster_rows()
    if not rows:
        print("member: no one has claimed a seat yet")
    for r in rows:
        print(f"{r['seat']:6} {r['name']:12} {r['role']:16} since {r['since']}  {r['about']}  "
              f"[memory {r['words']}w]")


def main():
    p = argparse.ArgumentParser(prog="member.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    s = p.add_subparsers(dest="cmd", required=True)
    q = s.add_parser("me")
    q.add_argument("--seat", required=True)
    q = s.add_parser("claim")
    q.add_argument("--seat", required=True)
    q.add_argument("--name")
    q.add_argument("--role", required=True)
    q.add_argument("--about", required=True)
    q = s.add_parser("remember")
    q.add_argument("--seat", required=True)
    q.add_argument("file", nargs="?", help='a file path, or "-" (default) for stdin')
    q.add_argument("--file", dest="file_opt")
    s.add_parser("roster")
    a = p.parse_args()
    {"me": cmd_me, "claim": cmd_claim, "remember": cmd_remember, "roster": cmd_roster}[a.cmd](a)


if __name__ == "__main__":
    main()
