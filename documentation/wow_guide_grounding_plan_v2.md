# WoW Guide Generation: Grounding and Hallucination Plan (v2)

Merges the repo audit (problems and fixes grounded in the current code) with external research on patch-aware retrieval. Items marked **[NEW]** come from the research and were missing from the repo plan. Items marked **[REPO]** are unchanged from the audit.

## 1. Problems in the code today [REPO]

1. **Frozen "current time".** `wcl_agent/agent.py:71` evaluates `dt.now()` inside the module-level `INSTRUCTION` f-string, so it runs once at import. The agent's date is the backend start time and drifts as uptime grows. This affects chat as well as guides.
2. **Guide prompt has no date or patch.** `_GUIDE_PROMPT` only receives `{cls}` and `{spec}`. The model guesses the patch and writes it into `guide-meta`. `current_patch()` in `wcl_agent/patch.py` already returns the live patch but is only used afterwards for freshness display.
3. **Guides are written by the coaching agent.** `_generate_text -> stream_response -> build_agent` makes the author "Barnaby", with ~20 WCL coaching tools and coaching instructions loaded. `web_search` is a sub-agent returning a summary, so the writer works from second-hand text. It is a single pass on a flash model with no verification.
4. **Devourer missing.** `CLASS_SPECS` in `wcl_agent/constants.py:11` hardcodes `["Havoc", "Vengeance"]` for Demon Hunter, and `build_guide_roster` reads from it. Quick fix: add "Devourer" after confirming the slug with `gameData { classes { name slug specs { name slug } } }`. Lasting fix: build from that query at startup, cache in Redis, keep the static map as fallback.
5. **[NEW] No hard separation of game environment.** Nothing stops PTR/beta or Classic material from reaching the writer. Wowhead currently publishes live 12.1.5 and 12.1.7 PTR content side by side, and Blizzard ships Retail and several Classic products in the same hotfix feed, so version is a filter, not a ranking hint.
6. **[NEW] Patch treated as a single label.** Live state is base patch plus later hotfixes. A guide can be correct for 12.1.5 on release day and wrong after a hotfix.

## 2. Principle [NEW]

**Patch validity is access control for knowledge.** Evidence from the wrong version (PTR, Classic, older patch, superseded by hotfix) must be unavailable to the writer, not merely ranked lower. Every other mechanism below supports this.

## 3. Source hierarchy [NEW]

| Tier | Source | Role |
|---|---|---|
| 1 | Blizzard patch notes, hotfix feed, Game Data API, WCL game data | Patch identity, spell IDs, class/spec lists, tuning |
| 2 | Warcraft Logs / Archon measured data | Empirical: what top players actually do (labelled as observed, not prescriptive) |
| 3 | Icy Veins, Wowhead (curated guide publishers) | Editorial interpretation, rotations, priorities |
| 4 | Forums, Reddit, video | Discovery only, never sole basis |

## 4. Approach

### A. Context block up front (cheap, do first) [REPO + NEW]

Build for every run:
- current date/time (UTC), computed per request
- live patch from `current_patch()`, plus **latest hotfix timestamp** [NEW]
- current raid tier and season from the already-loaded zone list
- full spec list for the class
- **environment fields: product=retail, environment=live, region** [NEW]

Prompt rule: "If you cannot confirm X for patch {patch}, leave it out." Exact build: WCL partitions give only major.minor. Blizzard's version endpoint (`us.version.battle.net/v2/products/wow/versions`) reportedly returns the full build string; it has not been verified, so test before relying on it.

### B. Dedicated guide agent: research, then write [REPO + NEW]

- Small agent with guide-writing instructions and no coaching tools, on a stronger model.
- Step 1 (research): collect a fact sheet (talents, stat priority, cooldowns, rotation), each fact with source URL, page date, source tier, and patch/environment tags.
- **Hard filters before the writer sees anything** [NEW]: product, live vs PTR, compatible patch, class/spec, non-superseded. Then rerank by relevance, patch match, authority, freshness (freshness never overrides patch identity).
- Step 2 (writing): only facts on the sheet may appear. Missing facts are omitted, and the guide states what is unconfirmed.
- **Decision to make: page access.** The repo plan fetches full pages (e.g. Gemini URL-context). The earlier requirement was links/snippets only. Full-page extraction gives far better facts but raises content-reuse and terms-of-use questions. Options: (1) snippets and links only, writer limited to a briefing with links; (2) fetch pages for internal fact extraction only, publish paraphrased facts with attribution and links, never reproduce guide text; (3) licensed access. Check each site's terms; `robots.txt` governs crawling, not reuse rights.

### C. Real Warcraft Logs data as evidence (the app's advantage) [REPO]

Top parses for the spec in the current raid provide measured facts:
- Talents: most common build among the top N (`combatantInfo`).
- Stats: stat spread from top players' gear.
- Cooldowns and casts: casts per minute per ability; shortest cast gap approximates cooldown length (`benchmark.py` already does this for cohorts).
- Spell IDs and names from report master data (today `guide-meta.spell_id` is model-guessed and `get_cooldown_usage` depends on it).

Cautions [NEW]: top-parse builds reflect what is popular at the top of a ranking, which is not always what is best for the typical player or for other content (Mythic+ vs raid, single target vs AoE). Record sample size, difficulty and encounter scope with each datum, and present it as "observed". Minimum-sample thresholds are needed for new specs such as Devourer, where data will be thin early in a patch.

### D. Reviewer agent [REPO + NEW]

- Receives the same context block, the WCL data sheet, and the fact sheet.
- Splits the guide into atomic claims and marks each confirmed, contradicted, or unconfirmed (claim-level grounding check).
- Contradicted claims are rewritten, unconfirmed ones removed; up to 2-3 rounds via ADK `LoopAgent` with an exit check.
- Use a different, stronger model than the writer.
- Status `ready` only if review passes; else `needs_review` with stored open issues.
- [NEW] **Abstention is a valid outcome.** A shorter guide with explicit gaps beats a complete-looking guide with unsupported claims.
- [NEW] Reviewer must verify against the evidence sheets, not its own memory; otherwise it shares the writer's blind spots.

### E. Deterministic code checks [REPO + NEW]

- Every ability name in `guide-meta` and the cooldown section exists in that spec's WCL ability list.
- Cooldown seconds roughly match the shortest observed cast gap.
- `meta.patch` equals the live patch.
- Sources exist and are dated after the season started.
- [NEW] Every source has matching product and environment; no PTR/beta/Classic source is cited.
- [NEW] No source is older than the latest hotfix touching the cited spec, unless flagged as possibly stale.
- [NEW] Every claim in the output carries a source ID or WCL-data ID.

Prefer structured JSON sections from the writer, rendered to markdown by code, so these checks are mechanical.

### F. Measure it and keep it fresh [REPO + NEW]

- Test set of 5-10 hand-checked facts for 3-4 specs, run before and after each change to get a baseline.
- Regenerate automatically on patch change (`guide_freshness` already detects `possibly_stale`; nothing acts on it yet) **and on new hotfix** [NEW].
- "Report inaccuracy" button feeding the next regeneration.
- [NEW] Metrics:

| Metric | Meaning |
|---|---|
| Patch accuracy | Guide metadata matches live patch/environment |
| Claim support rate | Share of claims confirmed by evidence |
| PTR/Classic leakage rate | Must be zero |
| Current-source precision | Retrieved sources valid for active patch |
| Spec coverage | All live specs present (catches Devourer-type gaps) |
| Abstention quality | Unsupported detail withheld rather than invented |
| Source-link health | Cited pages resolve and are relevant |

Release gate: patch accuracy, claim support and zero leakage outrank fluency. Include adversarial cases: an old guide with high semantic similarity, a PTR page newer than the live guide, conflicting guides, a hotfix after guide publication, and a brand-new spec with little data.

## 5. Caching [NEW]

Cache normalized source/search results in Redis keyed by `query_hash + product + environment + patch + region`; short TTL for hotfix and patch queries, longer for guide-page discovery. Cache the WCL spec list and per-spec data sheets with a patch-based key so a patch change invalidates them. This follows the existing cache-aside pattern.

## 6. Suggested order

1. **Quick wins (about a day):** fix the frozen time; add the context block (date, patch, hotfix time, environment, season, spec list); build the spec list from WCL `gameData` with static fallback (adds Devourer); move to a dedicated guide agent on a stronger model; start the test set for a baseline.
2. **Grounding:** WCL data sheet (C) and code checks (E), including environment and patch filters.
3. **Research and review:** source tiering, hard filters and fact sheet (B), then reviewer loop and `needs_review` status (D). Resolve the page-access decision before building B.
4. **Feedback loop:** auto-regeneration on patch/hotfix, inaccuracy button, metrics dashboard (F).

## 7. Open questions

- Which page-access option (snippets, internal extraction, licensed) is acceptable?
- Is the full build string from the version endpoint reliable? Verify.
- Are guides per region/product or Retail only? (Assumed Retail live.)
- Does the model's guide output need to be per content type (raid, Mythic+, PvP) rather than one guide per spec?
