# Sprint 2026-11-07b plan (PO Maren)

Board `sprint-2026-11-07b`. Branch `sprint-2026-11-07b`, base 516aa0d, prep commit de66bdd
(restClient `send` exported so streams keep endpoints in their own api modules).
Every stream branches from **de66bdd**. Iteration "2026-11-07b" (id 553), stories in Shortlist.

Goal: the Raids page becomes a place to review a raid (tabs, stored data, one-click analysis);
new accounts land in profile setup with a main class/spec and content; characters get their
Battle.net portraits; a dropped chat turn can no longer run alongside the next one.

Planned: **23 pts**. Dropped from the steer: inline coaching briefs (sc-515, 2; its AC is a
live A/B measure of two turns, a spike for later) and background guides for the chosen spec
(sc-168, 2; next onboarding slice). Reserves (P15, team tooling): browse/stack hardening
(sc-538 + sc-540, 3, Ansel) and small team-tool CLI bugs (sc-541, 2, Tomas).

| Feat | Stream | Type | Stories (pts) | Tier | Seat | Model | Sec-core |
|---|---|---|---|---|---|---|---|
| 072 | raid-summary-api | app backend | Raids page: show previously pulled raid data, backend half (sc-142: 3 of 5) | M | dev-3 Nils | opus high | yes (tenant visibility) |
| 073 | raids-page | app frontend | tabs instead of dropdown (sc-141: 2), Analyze this raid button (sc-143: 1), raid data UI half (sc-142: 2 of 5) | M | dev-2 Tomas | sonnet high | no |
| 074 | onboarding-profile-setup | app full-stack | new accounts to profile setup (sc-166: 2), main class/spec + content selector (sc-167: 3), schema dev notes out of prompt (sc-514: 1) | M | dev-5 (new) | opus high | no (yes if new RLS table) |
| 075 | character-portraits | app full-stack | fetch and cache portraits (sc-363: 3), show portraits (sc-364: 3) | M | dev-1 Ansel | opus high | yes (secret, Redis key, untrusted URL) |
| 076 | turn-serialization | app backend | new turn alongside a dropped turn (sc-511: 3) | S | dev-4 Vera | opus high | yes (per-chat single-flight) |

## Acceptance criteria (copied from the tickets)

- sc-141 (2): As a user, I want to switch raids with tabs instead of a dropdown, so it's quicker.
- sc-142 (5): As a user, I want each raid to show stored data (participants, duration, my
  character's parse), so I can review it without a chat.
- sc-143 (1): As a user, I want a button that starts a new chat with the analyze prompt.
- sc-166 (2): As a new player, I want to land on the profile page right after creating my
  account, with a prompt to add at least one character that I can skip, so the app knows who
  I am without forcing me.
- sc-167 (3): As a new player, I want a simple selector for my main class (and spec) and my
  main content (Raid, M+ or both), saved to my profile, so the app can tailor guides and
  answers to what I play.
- sc-514 (1): `ProfileChangeIn` docstring developer notes move to a comment. Acceptance:
  `test_064_prompt_budget` budget lowered by the saved amount; the schema description no
  longer contains the notes.
- sc-363 (3): portraits from the Blizzard Profile API character-media endpoint
  (client-credentials token; region/realm/name from the stored character); cache the URL per
  character with a sensible TTL, no Blizzard call per page load; graceful fallback (class
  icon or initials) when not found, private or API down; served to the frontend
  (changed AC: own endpoint, comment on the ticket).
- sc-364 (3): one shared avatar component (portrait, class-icon/initials fallback) on the
  profile page, welcome chat, chat character mentions where there is room; lazy-load, no
  layout shift, all themes (changed AC: raids page portrait is a follow-up; sidebar shows no
  characters).
- sc-511 (3): a test where T1 is mid tool round, the socket closes, and T2 starts on a new
  socket for the same chat: T1 is cancelled (or finishes) before T2 writes; message order is
  Q1, partial-A1, Q2, A2; T2's charts link to A2.

## Order, dependencies, contracts
- All five run in parallel. 073 consumes 072's endpoint through `contract:raid-summary`
  (mocked until merge). 073 may use `ClassAvatar`; 075 keeps its props (`contract:class-avatar`).
- Shared files are granted once: `schemas.py`, `types.ts`, `restClient.ts`, `api/profile.py`,
  `db/repository.py`, `db/models.py` belong to 074. Others put new types and calls in their
  own new modules.
- Migration: 074 only, `0023_profile_main_spec`, down_revision `0022_pg_stat_statements`.
- Merge order: as they hand off; 072 before 073 is preferred but not required.

## Drop first
sc-514 (trivial), then sc-143's button polish, then 364's welcome-page placement.
