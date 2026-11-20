---
id: profile-context-class-from-known-player
anchors: [sym:backend/app/services/profile_context.py::build_preamble]
by: dev-3 Nils
verified: 9cbc701 2026-11-20
---
A profile character can have active_spec but class_name None (class resolved later); the KNOWN
PLAYER CONTEXT line then read only 'Frost' and the agent asked Frost Mage or DK. build_preamble
fills a missing class from the known_players entry with the same name+server+region (never name
alone) and lists the workspace's main_class/main_spec (ProfileSettings) when passed.
ws._build_turn_preamble passes the main (082b).
