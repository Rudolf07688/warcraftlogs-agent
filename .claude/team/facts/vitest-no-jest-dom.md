---
id: vitest-no-jest-dom
anchors: [file:frontend/package.json, file:frontend/src/]
by: dev-2 Tomas
source: meta/team/dev-2.md L26
verified: 8986855 2026-11-20
---
The frontend's Vitest setup has no `@testing-library/jest-dom`, so matchers like
`toBeInTheDocument` don't exist. Assert on `textContent`, `toBeTruthy()` and plain values.
