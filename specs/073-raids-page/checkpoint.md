# Checkpoint: 073 Raids page
Decisions: scope:073:route (page inside App via useMatch, no routes.tsx change), :analyze (reuse handleInvestigateRaid,
navigate only if a chat started), :summary (own api module, cancelled-flag per panel), :speckit (compressed pass).
Files: pages/RaidsPage.tsx, components/raids/*, api/raidSummary.ts, App.tsx, components/Sidebar.tsx, styles.css, index.css,
App.test.tsx, App.reconnect.test.tsx, App.raids.test.tsx (new). Implementation started and finished in one pass.
