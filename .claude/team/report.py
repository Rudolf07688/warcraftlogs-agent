#!/usr/bin/env python3
"""Owner-facing HTML reports (plan, sprint review, team report) from a body fragment.

Agent-facing. The shared page shell (light/dark tokens, the CSS below, tab script, no network
requests) lives in report-shell.html next to this file, so nobody re-reads or re-types an old
report to copy its style. Write only the body, then build:

  report.py build BODY.html OUT.html --title "WCL Sprint <date> Review"
  report.py classes            the class vocabulary with a one-line example each

Look at what you built before handing it over: screenshot each tab and read the images.
  google-chrome --headless=new --hide-scrollbars --window-size=1300,1800 \
    --screenshot=/tmp/<scratch>/tab.png "file://$PWD/OUT.html#<tab id without p->"
(2026-11-02: three reports went to the owner with one word per line; nobody had looked.)

The body goes inside <div class="wrap">; the shell adds doctype, head, footer script and
closing tags. Tabs work when the body has the tablist + tabpanel markup shown by `classes`.
"""
import argparse
import html
import os
import re
import sys

SHELL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "report-shell.html")

CLASSES = """\
<header> <div class="eyebrow">Sprint review · WCL Agent App · local report</div> <h1>…</h1>
  <div class="meta"><span>Branch <b class="mono">sprint-…</b></span> …</div> <p>summary</p> </header>
<div class="kpis"><div class="kpi"><span class="eyebrow">Delivered</span>
  <span class="v">20<small> / 20 pts</small></span><span class="s">10 stories</span></div> …</div>
<nav class="tabs"><div class="tablist" role="tablist">
  <button class="tab" role="tab" id="tab-x" aria-controls="p-x" aria-selected="true">X <span class="count">3</span></button>
  (other tabs: aria-selected="false" tabindex="-1")</div></nav>
<div role="tabpanel" id="p-x" aria-labelledby="tab-x" tabindex="0"><h2 class="panel-title">X</h2> …</div>
  (other panels add the hidden attribute; all panels show in print and without JS)
<div class="card">…</div>   <div class="grid2">two cards side by side</div>   <div class="stack">…</div>
<table class="tbl"><tr><th>…</th><td class="num">12</td></tr></table>
<span class="tag t-ok|t-warn|t-bad|t-acc">label</span>   <span class="pts p1|p2|p3">2</span> (points badge)
<div class="callout ok|warn"><p>…</p></div>   (callouts, cards and checks are block flow: mix text and inline tags freely)
<ul class="checks"><li class="ok|no">sentence… <span class="ref">sc-…</span></li></ul>   (ok = done/green bar, no = to change/amber bar)
  numbered: <li><span class="no">1</span>sentence…</li>   (span.no is the number badge; never put class="no" on text)
<div class="flow"><span>step</span><i>→</i><span>step</span></div>
<div class="timeline"><div class="tl ok|warn"><span class="t">15:08Z</span> event</div></div>
<div class="bars"><div class="bar"><span>label</span><span class="track"><span class="fill" style="width:40%"></span>
  <span class="fill base" style="width:60%"></span></span><span class="n">40</span></div></div>
Text: class="mono" "muted" "small" "eyebrow"; <code>…</code>; <footer>Written by …</footer>"""


def build(body_path, out_path, title):
    shell = open(SHELL).read()
    body = open(body_path).read()
    if re.search(r"<!doctype|<head[\s>]|<body[\s>]", body, re.I):
        sys.exit("refused: BODY must be a fragment (no doctype/head); the shell adds those")
    page = shell.replace("{{TITLE}}", html.escape(title), 1).replace("<!--BODY-->", body.rstrip("\n"), 1)
    with open(out_path, "w") as f:
        f.write(page)
    print(f"wrote {out_path} ({len(page)} bytes; body {len(body)} bytes)")


def main():
    p = argparse.ArgumentParser(prog="report.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    s = p.add_subparsers(dest="cmd", required=True)
    b = s.add_parser("build")
    b.add_argument("body")
    b.add_argument("out")
    b.add_argument("--title", required=True)
    s.add_parser("classes")
    a = p.parse_args()
    if a.cmd == "build":
        build(a.body, a.out, a.title)
    else:
        print(CLASSES)


if __name__ == "__main__":
    main()
