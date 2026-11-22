---
id: mechanics-notes-per-tier
anchors: [file:backend/app/kb/mechanics/, sym:backend/app/agent_tools/mechanics.py::get_boss_mechanics]
by: dev-1 Ansel
verified: 8986855 2026-11-20
---
Boss-mechanic notes are hand-curated JSON, one file per raid tier, loaded once at import (no
file opened per call). Ability names and spell ids come from Blizzard's Encounter Journal
(team-lead runs specs/081-boss-mechanics/live_pre.py); icy-veins blocks fetches, Method and
warcraft.wiki.gg work. The models lint every file at load (086): source URLs only on
SOURCE_HOSTS, no markup or instruction-like text, length caps; a new host or wording fails start-up.
Each normalised name/alias/id must be unique within a boss; keep aliases specific across bosses.
