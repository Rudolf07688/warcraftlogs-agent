# Implementation Plan: Raids page

**Branch**: `073-raids-page` | **Spec**: [spec.md](spec.md) | **Tier**: M, frontend only

## Summary
The sidebar's collapsible raid list becomes one "Raids" entry that opens `/app/raids/:reportCode?`,
rendered by App in place of the chat body (so the socket and `handleInvestigateRaid` stay in App).
One shadcn tab per tracked raid; each tab shows the stored summary (`contract:raid-summary`) and an
"Analyze this raid" button that reuses `handleInvestigateRaid`.

## Design (decisions: scope:073:route, :analyze, :summary on the board)
- `api/raidSummary.ts`: types + `getRaidSummary` on the exported `send` (`encodeURIComponent`).
- `components/raids/RaidSummaryPanel.tsx`: per-raid fetch with loading / ready / not found / error+retry;
  an effect `cancelled` flag drops a late answer after a tab switch or unmount.
- `components/raids/RaidTab.tsx`, `raidFormat.ts` (date, boss summary, duration moved/added).
- `pages/RaidsPage.tsx` (lazy chunk): sorts newest first, `Tabs value` = URL code (default newest);
  a code not in the list selects no tab, mounts no panel (no request) and shows "Raid not found".
- `Sidebar.tsx`: `raids` list replaced by `raidCount`, `raidsActive`, `onOpenRaids`; dead raid-list CSS removed.
- `App.tsx`: `useMatch("/app/raids/:reportCode?")`, `raidsStatus`, `analyzeRaid` (navigates to `/app` only
  when a chat actually started), sidebar select / new chat leave the page. `routes.tsx` unchanged (`/app/*`).
- Text safety: everything is a React text node; long names truncate with `truncate` / `max-w-56`.

## Tests (D21)
`RaidSummaryPanel.test.tsx` (contract example via mocked fetch, states, encoding, late answer, hostile text),
`RaidsPage.test.tsx` (tabs, URL, unknown codes, Analyze, streaming, states, hostile label),
`App.raids.test.tsx` (sidebar entry opens page without a chat; Analyze starts the chat and leaves; failure stays).
Existing App tests: `react-router-dom` mock gains `useMatch`.

## Risks
The app shell itself is desktop-first (sidebar fixed width): at 390px the page scrolls horizontally outside
the tab list; pre-existing, not touched here (notice backlog:app-shell-mobile).
