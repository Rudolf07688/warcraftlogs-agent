#!/usr/bin/env bash
# sc-408: the build dashboards D1 (Claude Code: Overview) and D2 (Claude Code: Agent Team)
# provision from the repository, D13 still loads and links to D2, and every panel query is
# valid against the live backends (Mimir PromQL, Loki LogQL, Tempo TraceQL). The static rules
# (aliases only, cost labels) are pinned by backend/tests/test_team_dashboards.py.
#   observability/test/dashboards.sh        (KEEP=1 leaves the stack up)
source "$(dirname "$0")/lib.sh"
trap stack_down EXIT

stack_up
for uid in wcl-cc-overview wcl-agent-team wcl-team-improvement; do
  if curl -sf "${GRAFANA_ADMIN[@]}" "$GRAFANA/api/dashboards/uid/$uid" > "/tmp/dash-$COMPOSE_PROJECT-$uid.json"; then
    pass "dashboard $uid provisioned"
  else
    fail "dashboard $uid missing"
  fi
done

if python3 - "$GRAFANA" "$COMPOSE_PROJECT" <<'PY'
import json, sys, urllib.parse, urllib.request
grafana, project = sys.argv[1], sys.argv[2]
fails = 0
def get(path, **params):
    url = f"{grafana}/api/datasources/proxy/uid/{path}?{urllib.parse.urlencode(params)}"
    try:
        return urllib.request.urlopen(url, timeout=15).status, None
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:200]
for uid in ("wcl-cc-overview", "wcl-agent-team"):
    d = json.load(open(f"/tmp/dash-{project}-{uid}.json"))["dashboard"]
    panels = [q for p in d["panels"] for q in [p, *p.get("panels", [])]]
    for p in panels:
        for t in p.get("targets", []):
            ds = (t.get("datasource") or p.get("datasource") or {}).get("uid")
            if ds == "mimir":
                q = t["expr"].replace("$__range", "1h").replace("$__interval", "5m")
                code, err = get("mimir/api/v1/query", query=q)
            elif ds == "loki":
                code, err = get("loki/loki/api/v1/query_range", query=t["expr"], limit="1")
            elif ds == "tempo":
                code, err = get("tempo/api/search", q=t["query"], limit="1")
            else:
                continue
            ok = code == 200
            fails += not ok
            print(("PASS  " if ok else "FAIL  ") + f"{uid} '{p['title']}' query is valid" + ("" if ok else f" ({code} {err})"))
    print(f"dashboards: {uid} has {len(panels)} panels")
sys.exit(1 if fails else 0)
PY
then :; else FAILURES=$((FAILURES + 1)); fi
rm -f /tmp/dash-"$COMPOSE_PROJECT"-*.json

if (( FAILURES == 0 )); then echo "RESULT PASS"; else echo "RESULT FAIL ($FAILURES)"; exit 1; fi
