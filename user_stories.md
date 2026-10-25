# User Stories — open `todo.md` items

Derived from the "To Do" section of `todo.md` (struck-through items skipped).
Points use the Shortcut workspace scale **0, 1, 2, 4, 8** (old estimates mapped 3→2, 5→4).
Every original item of 8+ points became an **epic** that keeps the original title, with its work split into stories of 4 points or less.

**Areas:** Backend (FastAPI / `backend/app`), Agent (`wcl_agent`, prompts, tools), Frontend (React / `frontend/src`), Data (Postgres / Redis), Infra (Docker / hosting), Reports (PDF).

## Overview

| Epic | Stories | Pts |
|------|---------|-----|
| E1 Proper PDF generation | 3 | 8 |
| E2 Semantic search vector store | 5 | 14 |
| E3 Spin up sub-agent tool (incl. REPL) | 7 | 20 |
| E4 Upload a Warcraft Logs file directly | 4 | 10 |
| E5 Every fetch stored in the DB | 6 | 18 |
| E6 Fix class guides | 4 | 9 |
| E7 Chat interface redesign | 4 | 9 |
| E8 Rework Raids page *(grouped todo item, 7 pts)* | 3 | 7 |
| E9 Per-chat character filter *(grouped todo item, 8 pts)* | 2 | 8 |
| Standalone stories | 14 | 33 |
| **Total** | **52** | **~136** |

Breaking items down pushed the estimates for E2–E5 above the original single-story guesses; the old 13s were underestimates.

---

## E1 — Proper PDF generation
*Todo: "PDF reports still look terrible with some html/markdown markers visible — need to use proper pdf generation"*

| Story | Pts | Area |
|-------|-----|------|
| **E1.1 Adopt a real HTML→PDF renderer.** As a user, I want reports rendered by a proper engine (e.g. WeasyPrint or headless Chromium) from an HTML template, so the output looks like a real document. | 4 | Reports, Backend |
| **E1.2 Clean Markdown→HTML conversion.** As a user, I want Markdown, tables, LaTeX and code converted fully, with no raw `**`, `#` or HTML tags left in the PDF. | 2 | Reports, Backend |
| **E1.3 Charts and page styling.** As a user, I want charts embedded as images, plus headers, page breaks and themed styling, so reports are readable when printed. | 2 | Reports |

## E2 — Semantic search vector store
*Todo: "Add semantic search vector store — search data related to the query, used as a cache, parallel search terms"*
*Depends on E5.1/E5.2 (stored fetches are what gets embedded).*

| Story | Pts | Area |
|-------|-----|------|
| **E2.1 Vector store setup.** As a developer, I want a vector store (pgvector in the existing Postgres) with a schema and migration, so embeddings live next to the app data. | 2 | Data |
| **E2.2 Embed on write.** As a user, I want fetched WCL data and tool outputs chunked and embedded (Vertex embeddings) as they are stored, so they become searchable. | 4 | Backend, Data |
| **E2.3 Backfill.** As a user, I want existing cached and stored data embedded too, so search is useful from day one. | 2 | Data |
| **E2.4 Parallel search tool.** As a user, I want the agent to have a search tool that takes several queries and runs them in parallel, so it can find related data in one step. | 4 | Agent |
| **E2.5 Search-first prompting + eval.** As a user, I want the agent to search stored data before calling the API, with hit rate and latency measured, so answers come back faster. | 2 | Agent |

## E3 — Spin up sub-agent tool
*Todo: "Add a 'spin up sub-agent' tool call — agent creates an agent with a prompt (all tools available). Long term: give sub-agent a REPL environment"*

| Story | Pts | Area |
|-------|-----|------|
| **E3.1 Sub-agent tool.** As a user, I want the agent to start a sub-agent with its own prompt and the full tool set, which returns a result, so big questions can be split up. | 4 | Agent |
| **E3.2 Guardrails.** As an operator, I want limits on recursion depth, tokens and time, and sub-agents to share the LLM rate limiter, so sub-agents can't run away. | 2 | Agent |
| **E3.3 Sub-agent progress in the UI.** As a user, I want to see sub-agent activity in the chat's tool-call display, so I know what's happening while I wait. | 2 | Frontend, Backend |
| **E3.4 Sandboxed execution service** *(long term)*. As an operator, I want an isolated runtime (container, no network, CPU/memory/time limits) for running agent-written code. | 4 | Infra |
| **E3.5 REPL tool** *(long term)*. As a power user, I want sub-agents to have a REPL tool that keeps state across calls, so they can compute ad-hoc statistics. | 4 | Agent |
| **E3.6 Log data in the REPL** *(long term)*. As a power user, I want fetched or stored fight data loadable into the REPL as data frames, so analysis needs no further API calls. | 2 | Agent, Data |
| **E3.7 Sandbox security review** *(long term)*. As an operator, I want the sandbox reviewed for escapes and data exposure before it ships. | 2 | Infra |

## E4 — Upload a Warcraft Logs file directly
*Todo: "Upload warcraftlogs file directly"*

| Story | Pts | Area |
|-------|-----|------|
| **E4.1 Spike: upload scope.** As a developer, I want to decide what an upload means (raw `WoWCombatLog.txt` parsed by us, or a WCL export) and how we'd parse it, so the remaining stories can be sized properly. | 2 | Backend |
| **E4.2 Upload endpoint and storage.** As a user, I want an authenticated upload endpoint with size limits and streaming storage, so large logs upload reliably. | 2 | Backend |
| **E4.3 Upload UI.** As a user, I want to upload a file from the app and see progress, so I know it worked. | 2 | Frontend |
| **E4.4 Ingest for the agent.** As a user, I want an uploaded log parsed into the same shape as fetched WCL data, so the agent can analyze it. *(Re-estimate after E4.1.)* | 4 | Backend, Agent |

## E5 — Every fetch stored in the DB
*Todo: "Every single fetch must be stored in the db — build up a massive database; 80% of questions shouldn't need external API calls"*

| Story | Pts | Area |
|-------|-----|------|
| **E5.1 Raw fetch schema.** As a developer, I want a table for raw WCL responses (query key, params, report code, fetched_at, JSONB payload) with a migration. | 2 | Data |
| **E5.2 Write-through persistence.** As a user, I want every WCL client fetch saved to the DB automatically, so no fetched data is lost. | 2 | Backend |
| **E5.3 DB-first reads.** As a user, I want fetches served from the DB when fresh enough (finished reports never change; live data expires), layered with Redis, so repeat questions are fast. | 4 | Backend, Data |
| **E5.4 Normalized entities.** As a developer, I want key entities (reports, fights, players, rankings) extracted into queryable tables, so local data can be searched and joined. | 4 | Data |
| **E5.5 Local query tools.** As a user, I want the agent to have tools that query stored data directly, so it can answer without the API. | 4 | Agent |
| **E5.6 Local hit-rate metric.** As the app owner, I want to track the share of questions answered without external calls, so I can measure progress toward 80%. | 2 | Backend |

## E6 — Fix class guides
*Todo: "Fix Class guides — hallucinations (better grounding, review agent must fix it first, current datetime + exact patch version in context); Devourer DH spec not showing"*
*Feature 015 already added grounding and patch awareness. Check what is still missing first.*

| Story | Pts | Area |
|-------|-----|------|
| **E6.1 Date + patch in context.** As a player, I want the current date and exact patch version in the guide generator's context, so advice matches the live game. *(Check whether 015 already covers this.)* | 1 | Agent |
| **E6.2 Reviewer agent.** As a player, I want a reviewer agent to check each generated guide against its grounding sources and flag hallucinations. | 4 | Agent |
| **E6.3 Fix loop before save.** As a player, I want the generator to address review findings (up to N rounds) before a guide is saved, so I never see an unreviewed guide. | 2 | Agent, Backend |
| **E6.4 Devourer DH spec missing.** As a Demon Hunter player, I want the Devourer spec to show up in class guides. *(Roster tests already cover it, so the problem is likely in the UI or guide list.)* | 2 | Backend, Frontend |

## E7 — Chat interface redesign
*Todo: "Chat interface redesign — maybe single-lane chat; scroll to top of the question-message once answer is fully complete"*

| Story | Pts | Area |
|-------|-----|------|
| **E7.1 Single-lane design.** As a user, I want a mockup of a single-lane chat layout to review before it's built. | 2 | Frontend (design) |
| **E7.2 Implement single-lane layout.** As a user, I want the chat rebuilt in the new layout, so conversations are easier to read. | 4 | Frontend |
| **E7.3 Message actions in new layout.** As a user, I want follow-up buttons, per-message PDF, boss filters and tool-call displays to work in the new layout. | 2 | Frontend |
| **E7.4 Scroll to question on completion.** As a user, I want the view to scroll to the top of my question when the answer finishes, so I read from the start. | 1 | Frontend |

## E8 — Rework Raids page
*Todo: "Rework Raids page — tabs instead of dropdown; show previously pulled data; button to start a new chat with 'analyze this raid'"*

| Story | Pts | Area |
|-------|-----|------|
| **E8.1 Tabs instead of dropdown.** As a user, I want to switch raids with tabs instead of a dropdown, so it's quicker. | 2 | Frontend |
| **E8.2 Show previously pulled raid data.** As a user, I want each raid to show stored data (participants, duration, my character's parse), so I can review it without a chat. | 4 | Frontend, Backend, Data |
| **E8.3 "Analyze this raid" button.** As a user, I want a button that starts a new chat with the analyze prompt. | 1 | Frontend |

## E9 — Per-chat character filter
*Todo: "Select which character this chat is about ('filter') with checkboxes on every chat; bonus: AI can change the UI filter"*

| Story | Pts | Area |
|-------|-----|------|
| **E9.1 Character filter checkboxes.** As a user with several characters, I want checkboxes on each chat to choose which characters it's about (default: all), so answers focus on the right character. | 4 | Frontend, Backend, Agent |
| **E9.2 Agent sets the filter (stretch).** As a user, when I ask a targeted question ("How did my mage do on …"), I want the agent to switch the UI filter itself. | 4 | Agent, Frontend |

---

## Standalone stories

| # | Story | Pts | Area |
|---|-------|-----|------|
| S1 | **Deployment / hosting plan.** As the app owner, I want a documented plan (hosting, Postgres/Redis, secrets, Vertex credentials, cost), so the app can run outside my machine. | 4 | Infra |
| S2 | **Confirm browser cache usage.** As a user, I want repeat views served from the browser cache where safe, on top of Redis (014). | 2 | Frontend, Data |
| S3 | **Smoother rendering.** As a user, I want streamed responses to render without jank or layout jumps. | 4 | Frontend |
| S4 | **Performance-assessment agent skills.** As a player, I want the agent to have reference skills for judging WoW numbers (DPS/HPS, parses, uptime, deaths, M+ timing), so its verdicts are reliable. | 4 | Agent |
| S5 | **Restructure `wcl_agent/*.py`.** As a developer, I want the flat module split into sub-packages, so the code is easier to navigate. | 4 | Agent (refactor) |
| S6 | **Report progress indicator.** As a user, I want to see that a report is generating or downloading, so I know the button worked. | 2 | Frontend |
| S7 | **Larger default font.** As a user, I want a slightly larger default font size. | 1 | Frontend |
| S8 | **Welcome chat: 6 raids + 6 M+ runs.** As a user, I want at most 6 recent raids and 6 recent M+ runs, most recent first. | 2 | Frontend, Backend |
| S9 | **Sidebar: conversations above Raids.** As a user, I want previous conversations listed above the Raids section. | 1 | Frontend |
| S10 | **Auto-generated conversation names.** As a user, I want conversations named from their messages, so I can find old chats. | 2 | Backend, Agent, Frontend |
| S11 | **QA PERF-001.** As a user, I want the app to start serving right away, with model discovery in the background. | 2 | Backend |
| S12 | **QA SEC-003.** As a user, I want remote images in model output blocked or proxied, so a crafted response can't leak data. | 2 | Frontend |
| S13 | **QA SEC-004.** As a user, I want the login rate limit keyed on the real client IP (trusted forwarded headers), so one user behind the proxy can't lock everyone out. | 2 | Backend, Infra |
| S14 | **QA SPEC-002/004.** As an operator, I want the specified startup log line, and a catalog response with no models treated as an error rather than an empty list. | 1 | Backend |
