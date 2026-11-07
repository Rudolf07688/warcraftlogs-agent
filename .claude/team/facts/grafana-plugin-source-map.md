---
id: grafana-plugin-source-map
anchors: [comp:grafana]
by: dev-1 Ansel
verified: 9ff8602 2026-11-07
---
To read how a Grafana panel computes a value, read the plugin's TypeScript from the local image,
offline: docker run --rm --network none --entrypoint cat grafana/grafana:13.2.5
/usr/share/grafana/data/plugins-bundled/<plugin>/module.js.map > m.map, then pick
sourcesContent[i] where sources[i] ends in the file (tempo: ./graphTransform.ts, the
service-graph node math). Other chunks: grep -l <name> *.js.map in that dir. Read the real code
before guessing.
