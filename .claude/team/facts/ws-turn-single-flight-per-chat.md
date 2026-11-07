---
id: ws-turn-single-flight-per-chat
anchors: [sym:backend/app/api/ws.py::_ChatTurn, sym:backend/app/api/ws.py::_start_turn]
by: dev-4 Vera
verified: 20d4197 2026-11-07
---
One turn at a time per chat, across sockets (sc-511): _ChatTurn.turns is keyed (tenant,
conversation), claimed after the ownership check, released in _handle_turn's finally. A newer
turn cancels the old one only in setup or streaming (not while it saves), waits
SUPERSEDE_WAIT_S, then writes. Each turn is its own task under _start_turn, so a cancel never
closes the socket. Tests running two turns on one chat at once will supersede each other.
