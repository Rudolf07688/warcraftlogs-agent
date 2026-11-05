---
id: vitest-no-jest-dom
anchors: [file:frontend/package.json, file:frontend/src/]
by: dev-2 Tomas
source: meta/team/dev-2.md L26
verified: 1ee750a 2026-11-05
---
The frontend's Vitest setup has no `@testing-library/jest-dom`, so matchers like
`toBeInTheDocument` don't exist. Assert on `textContent`, `toBeTruthy()` and plain values.
