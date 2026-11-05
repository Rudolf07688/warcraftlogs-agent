---
id: stack-scripts-faro-pyroscope-ports
anchors: [file:observability/test/lib.sh, comp:compose]
by: dev-3 Nils
source: meta/team/dev-3.md L34
verified: 32010a6 2026-11-05
---
`observability/test/lib.sh` is bash (`BASH_SOURCE`, `[[ ]]`): run the scripts with bash.
It moves only the OTLP, UI and Grafana ports (24xxx). `ALLOY_FARO_PORT` and `PYROSCOPE_PORT`
keep compose's 12347 and 4040 unless the script sets them (faro, frontend,
redaction-e2e and build-runtime set the Faro port; provisioning sets the Pyroscope port), so a second stack's Alloy fails to bind.
Set both with your port block (Nils: 27347/27040).
