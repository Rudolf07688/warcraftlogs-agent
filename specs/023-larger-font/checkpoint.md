# Checkpoint: 023 larger font

Commits: 9e30fe8 (36 font-size px to rem, exact), 0c62d18 (html root 106.25%).
Sidebar.tsx:154 now uses `text-[0.6875rem]` (8cd7d2f); nothing open.

## AC 2 layout check (throwaway Postgres/Redis/uvicorn/vite stack, logged in, seeded fixtures, headless Chrome via CDP)

Screenshots (scratchpad, not committed): /tmp/claude-1000/-home-rudolf-dev-warcraftlogs-agent/276b1986-87b3-4ee2-99ff-9c16b4e10bfa/scratchpad/b023/{welcome,chat}-{1280,390}.png after; /tmp/claude-1000/-home-rudolf-dev-warcraftlogs-agent/276b1986-87b3-4ee2-99ff-9c16b4e10bfa/scratchpad/b023/base/ before (root 16px).

- 1280px: no horizontal overflow (scrollWidth 1280). Sidebar rows and pin button, welcome raid and M+ cards (timed and depleted, long name truncated), composer, chat messages (long user bubble, table, inline code, scrolling code block) all fit, no clipped text.
- 390px: the page scrolls horizontally. This is PRE-EXISTING: the sidebar stays about 260px wide and squeezes the main column (header buttons, composer, welcome and chat columns overflow). scrollWidth before the change: 726 (welcome), 842 (chat); after: 750 and 873. The larger font adds about 24-31px on top of a layout that already overflowed. Fixing it needs a responsive layout (collapsing sidebar), which touches component files and is a separate story.
