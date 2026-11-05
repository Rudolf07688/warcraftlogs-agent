---
id: tsbuildinfo-tracked
anchors: [file:frontend/tsconfig.tsbuildinfo, file:frontend/package.json]
by: dev-2 Tomas
source: meta/team/dev-2.md L26
verified: b9cf9a3 2026-11-05
---
`npm run build` (`tsc -b`) rewrites `frontend/tsconfig.tsbuildinfo`, which is tracked in
git. Run `git checkout frontend/tsconfig.tsbuildinfo` before every commit so it doesn't
ride along.
