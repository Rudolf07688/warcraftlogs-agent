---
id: app-tests-mock-router-usematch
anchors: [file:frontend/src/App.tsx, file:frontend/src/App.test.tsx]
by: dev-2 Tomas
verified: 03a3982 2026-11-07
---
App.test.tsx and App.reconnect.test.tsx mock react-router-dom as { useNavigate, useMatch: () =>
null }: any new react-router hook App.tsx calls must be added to both mocks, or every App test
throws. App.modelFallback.test and App.raids.test use a real MemoryRouter instead (App has no
Routes of its own, so initialEntries picks /app or /app/raids/:code).
