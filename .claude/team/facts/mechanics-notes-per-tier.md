---
id: mechanics-notes-per-tier
anchors: [file:backend/app/kb/mechanics/, sym:backend/app/agent_tools/mechanics.py::get_boss_mechanics]
by: dev-1 Ansel
verified: c0d587d 2026-11-20
---
Boss-mechanic notes are hand-curated JSON, one file per raid tier, loaded once at import (no
file opened per call). Ability names and spell ids come from Blizzard's Encounter Journal
(team-lead runs specs/081-boss-mechanics/live_pre.py); icy-veins blocks fetches, Method and
warcraft.wiki.gg work. test_081 requires each normalised name/alias/id to be unique within a
boss. A key shared across bosses makes a lookup without a boss a found_under miss: keep
aliases specific.
