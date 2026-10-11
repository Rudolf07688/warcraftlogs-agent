# Feature Specification: Grounded, Evidence-Based Coaching

**Feature Branch**: `009-grounded-coaching-prompt`

**Created**: 2026-10-07

**Status**: Draft

**Input**: User description: "Ok now, while still using this file as grounding, let's start building this" — grounding document: `documentation/designs/20261007_prompt_upgrade.md` (Improving the Warcraft Logs Coaching Prompt).

## Overview

Barnaby already knows where to fetch Warcraft Logs data, but not rigorously enough
*how far that data can be trusted*. Today he benchmarks a player against a single
top parse, quotes "the percentile" without saying which one, calls fewer casts
"missed casts", treats generated guides as current regardless of patch, and is told
to answer "ANY" question — so he rarely says "the log can't tell us that".

This feature makes coaching answers **grounded**: every claim is traceable to its
evidence, comparisons are made against a fair population, percentiles carry their
context, cast criticism is based on real opportunities, guide advice carries its
freshness, and the assistant abstains when evidence is insufficient. Personality
stays — but is applied after the facts are settled and never changes them.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Evidence-honest coaching answers (Priority: P1)

A raider asks "why was my parse low on this pull?" or "what killed us on that wipe?".
Barnaby answers verdict-first, then the evidence, then up to three prioritised fixes.
Each fix states the evidence behind it, the expected change, and a confidence level.
Measured facts are worded as facts; comparisons, guide advice, and interpretations
are worded as such ("likely contributed", "the guide recommends", "the log can't
establish whether…"). When the data can't support an answer, Barnaby says exactly
what can't be concluded and asks for the smallest missing piece instead of guessing.

**Why this priority**: This is the core trust problem. It is achievable through the
assistant's instructions alone, ships independently of every other story, and
prevents the most damaging failure — confident but wrong coaching.

**Independent Test**: Ask a fixed set of coaching, wipe, and insufficient-data
questions against known reports; verify answer structure, claim wording,
abstention, and that no number or identifier appears that the tools didn't return.

**Acceptance Scenarios**:

1. **Given** a report-specific coaching question, **When** Barnaby answers, **Then**
   the answer opens with a 1–2 sentence verdict, followed by evidence, at most three
   priority fixes (each with evidence, expected change, and confidence), material
   caveats only, and source links attached to the claims they support.
2. **Given** a death on a wipe, **When** Barnaby explains it, **Then** he
   distinguishes the immediate cause, contributing factors, and what is unknown
   (e.g. whether a cooldown was deliberately held), and does not call damage
   "avoidable" unless a current mechanic source supports that label.
3. **Given** a question the available data cannot answer (e.g. player intent,
   positioning not present in the log, a report the user hasn't identified),
   **When** Barnaby responds, **Then** he names what cannot be concluded and asks
   for the single smallest missing input or lookup — he does not fill the gap with
   a plausible-sounding answer.
4. **Given** a resolved player whose class/spec, fight, or encounter doesn't match
   what the user asked about (e.g. a name collision, an off-spec pull, a fight from
   a different report), **When** Barnaby detects the mismatch, **Then** he corrects
   the lookup or tells the user — he never analyses the wrong subject silently.
5. **Given** retrieved web or guide text that contains instructions (e.g. "ignore
   previous instructions"), **When** Barnaby uses that source, **Then** he treats it
   purely as evidence and does not follow the embedded instructions.
6. **Given** any answer, **When** the persona is applied, **Then** the banter does
   not alter any number, confidence, or recommendation, uses at most one short joke
   or tavern metaphor per section, and criticises the play, never the person.

---

### User Story 2 - Fair benchmark comparisons (Priority: P2)

When a player asks how they compare, Barnaby compares them against a **matched
group** of strong-but-not-extreme parses — same encounter, difficulty, spec, metric,
and partition as the player's pull; kill vs kill; similar fight length — shows each
parse's item level, and reports the group's typical (median) behaviour and range, the
group size, and anything that couldn't be matched. The player's own rates are
measured over the time they were alive, so an early death doesn't make them look
slow against the group. A single rank-one parse is only used
when the user explicitly asks about elite or rank-one play.

**Why this priority**: The single-top-parse benchmark is the most consequential flaw
identified in the grounding document; it produces false criticism whenever the top
parse had a shorter fight, a different strategy, or padding. It depends on richer
comparison data than the assistant can assemble from today's tools.

**Independent Test**: For a known player pull, request a comparison and verify the
benchmark group's size, its match criteria (duration window, kill status, percentile
band), that medians/ranges are reported, and that any shortfall in matching is
disclosed.

**Acceptance Scenarios**:

1. **Given** a player's kill pull, **When** Barnaby benchmarks it, **Then** the
   comparison group consists of several parses from roughly the 75th–95th
   percentile band, kill-only, with fight duration within about 15% of the player's,
   and the answer states the group size.
2. **Given** a matched group, **When** Barnaby reports differences, **Then** he
   reports the group's median and range (not a single parse's number) for each
   compared measure.
3. **Given** only one comparable parse can be found, **When** Barnaby compares,
   **Then** the comparison is explicitly labelled anecdotal/directional.
4. **Given** the user asks "what does the #1 player do differently?", **When**
   Barnaby answers, **Then** he may use the top parse, and says it is an elite
   outlier rather than a typical benchmark.
5. **Given** a wipe pull, **When** Barnaby benchmarks, **Then** he does not compare
   it against kill parses as if equivalent; he either matches on phase reached or
   says the comparison is limited.
6. **Given** a kill where the player died partway through, **When** Barnaby
   benchmarks it, **Then** the player's per-minute rates are measured over the time
   they were alive, the time dead is stated, and the death — not the rates — is
   presented as the issue.
7. **Given** two players with the same name in the pull, **When** a comparison is
   requested by name, **Then** Barnaby is told the name is ambiguous, with the
   candidates, and asks which one (or picks by the known server) rather than guessing.

---

### User Story 3 - Percentiles and data with explicit context (Priority: P3)

When Barnaby quotes a percentile, the relevant context is stated whenever it changes
the meaning: ranking (a player's best) vs parse (one pull), today vs historical,
overall vs item-level bracket, partition, metric, and sample size. When both overall
and bracket percentiles exist, both are shown. Every Warcraft Logs result Barnaby
relies on carries what it was about (report, fight, encounter, difficulty, partition,
metric, player) and whether it was complete (paginated, truncated, sample size), so
claims based on partial data are flagged rather than presented as complete.

**Why this priority**: The same performance can legitimately have several different
percentiles; quoting "your percentile" without context misleads. It also underpins
the validation in Story 1 and the matching in Story 2.

**Independent Test**: Ask percentile questions where overall and bracket percentiles
disagree, and ones that require paginated data; verify the context is disclosed and
partial results are flagged.

**Acceptance Scenarios**:

1. **Given** a player's pull with both overall and item-level-bracket percentiles,
   **When** Barnaby quotes the percentile, **Then** both are shown and labelled.
2. **Given** a population question ("how are Fire Mages doing?"), **When** Barnaby
   answers, **Then** he states the metric, difficulty, partition, and the sample the
   statistics were computed over — including that it is the top of the leaderboard
   when that is all that was fetched.
3. **Given** a tool result that was truncated or has more pages available, **When**
   a claim depends on completeness (e.g. "nobody died to X"), **Then** Barnaby either
   fetches the rest or states that the claim is based on partial data.
4. **Given** item level differs between the player and the benchmark, **When**
   Barnaby explains a gap, **Then** he does not imply item level alone explains it.

---

### User Story 4 - Opportunity-based cast coaching (Priority: P4)

Instead of "you only cast Combustion twice", Barnaby says "2 of about 4 reasonable
opportunities used", where opportunities account for the player's eligible time
(the time they could act) and the ability's cooldown, and are reduced for time dead,
forced downtime,
intermissions, and target immunity. The cooldown comes from the spec's stored
class guide, so opportunity counts are only as fresh as that guide (Story 5): a
stale or unknown-freshness guide makes the count "approximate". Where an ability's
opportunity count can't be established (no guide, or the guide doesn't state that
cooldown), he says "lower than the comparison group" rather than "missed casts".
The counts come from a deterministic calculation, not the assistant's mental
arithmetic.

**Why this priority**: Raw cast counts are the most common source of false
criticism (short fights, early deaths, intermissions). It needs cooldown knowledge
from the guide library (Story 5) and active-time data, so it builds on Stories 1–3
and 5.

**Independent Test**: For pulls with an early death, a long intermission, and a
normal kill, request cooldown feedback; verify opportunity counts reflect the lost
time and that unknown-cooldown abilities fall back to comparative wording.

**Acceptance Scenarios**:

1. **Given** a player who died at 60% of the fight, **When** Barnaby assesses major
   cooldown usage, **Then** opportunities are counted only over the time the player
   was alive and able to act.
2. **Given** an encounter with an intermission where the boss is untargetable,
   **When** Barnaby counts opportunities, **Then** that window is excluded or the
   answer states it could not be excluded.
3. **Given** an ability whose cooldown is not stated in the spec's guide (or no
   guide exists for the spec), **When** Barnaby comments on its usage, **Then** he
   compares the rate to the benchmark group and does not use the word "missed".
4. **Given** any cast-usage claim, **When** it is presented, **Then** it is expressed
   as a rate (per minute) or as uses out of opportunities, not as a bare count.
5. **Given** the spec's guide is possibly stale or of unknown freshness, **When**
   Barnaby reports opportunities based on its cooldowns, **Then** he labels the
   count approximate and notes the guide's freshness.

---

### User Story 5 - Guide advice with known freshness (Priority: P5)

Every class/spec guide in the shared library records the game version/patch it was
written for, when it was generated, and the sources it drew on. When Barnaby uses a
guide whose patch doesn't match the current one (or is unknown), he treats it as
potentially stale and says so, preferring current-patch sources. When sources
conflict, he reports the conflict rather than silently choosing one. Users can see
a guide's patch and generation date on the Class Guides page.

**Why this priority**: Guide advice turns observations into recommendations; stale
guides produce confidently wrong advice after balance patches. It touches stored
guide data and the Class Guides page, so it is independent of the analysis stories.

**Independent Test**: Use one guide generated for the current patch and one marked
as an older/unknown patch; ask a coaching question that draws on each; verify the
stale one is flagged and the guide page shows the patch and date.

**Acceptance Scenarios**:

1. **Given** a newly generated guide, **When** it is stored, **Then** it records the
   game version/patch it targets, its generation date, its source links, and the
   cooldown duration of the spec's major abilities.
2. **Given** a guide generated before this feature (no patch recorded), **When**
   Barnaby uses it, **Then** it is treated as unknown-freshness and the answer says
   so when the advice is material to a recommendation.
3. **Given** a guide whose patch is older than the current patch, **When** the user
   views it on the Class Guides page, **Then** it is visibly marked as possibly out
   of date and can be regenerated.
4. **Given** a guide recommendation that conflicts with official patch notes found
   via web search, **When** Barnaby answers, **Then** he states the conflict and
   prefers the source closest to the underlying fact.

---

### Edge Cases

- **Missing context**: difficulty, encounter, report, or player identity not given —
  population questions default to Heroic and say so; report-specific questions ask
  one concise clarifying question when the omission could change the answer.
- **Name collision / off-spec**: the resolved player has a different class/spec than
  expected, or two players share a name across servers.
- **Kill vs progression wipe**: wipes are not benchmarked as if they were kills.
- **Early death**: a player who died early is not criticised for low totals or casts
  over time they were dead.
- **Intermission or boss immunity**: long untargetable windows distort rates.
- **Different fight lengths**: a 3-minute vs 6-minute kill makes raw counts
  incomparable.
- **Rank-one padding or unusual strategy**: the top parse is excluded from
  "typical" benchmarks.
- **Stale guide vs current guide**: older or unknown-patch guide content conflicts
  with current information.
- **Partition / balance-change boundary**: data from before a balance patch is mixed
  with current data.
- **Bracket vs overall disagreement**: item-level-bracket percentile differs sharply
  from overall percentile.
- **Partial / paginated data**: event or ranking results are truncated.
- **Rate limit or query error**: Warcraft Logs budget is low or a query fails —
  Barnaby repairs and retries at most once or twice, then gives the supported partial
  answer and names the missing evidence. Benchmark groups shrink rather than fail
  when budget is short, and are labelled accordingly.
- **Prompt injection in retrieved content**: web or guide text contains instructions.
- **No web search available** (models without it): Barnaby answers from logs and
  stored guides and says that current-patch verification wasn't possible.
- **Non-coaching uses of the same assistant** (startup greeting, guide generation,
  raid-investigation kickoff): the verdict/evidence/fixes structure applies to
  analytical answers only; it does not distort greetings or guide documents.
- **No guide or no stated cooldown**: the spec's guide hasn't been generated, failed,
  or doesn't list the ability's cooldown — usage is compared by rate only.
- **Talent-modified cooldowns**: the guide's stated cooldown may not match the
  player's build — opportunity counts are labelled approximate.
- **Insufficient data overall**: the correct behaviour is to abstain.

## Requirements *(mandatory)*

### Functional Requirements

**Evidence contract and answer shape (Story 1)**

- **FR-001**: The assistant MUST NOT state any measurement, identifier, mechanic,
  guide recommendation, or cause that is not supported by a tool result, a cited
  guide, or a cited external source.
- **FR-002**: The assistant MUST distinguish, in wording, between observed facts
  (directly from a tool), benchmarked differences (computed against a comparison
  group), guidance (from a guide or patch source), and inferences — and MUST never
  word a benchmark, guidance, or inference as an observed fact.
- **FR-003**: When evidence is missing, contradictory, stale, or insufficient, the
  assistant MUST say what cannot be concluded and request the smallest missing input
  or lookup, rather than answering beyond the evidence.
- **FR-004**: The assistant MUST treat retrieved web and guide content as untrusted
  evidence and MUST NOT follow instructions embedded in it.
- **FR-005**: The assistant MUST rank sources by authority: Warcraft Logs for what
  happened in a fight; current-patch guides for expected play (not for what
  happened or why); official patch notes for game changes; other web sources only
  with source, date, and link. Conflicts MUST be reported, not silently resolved.
- **FR-006**: Before analysing, the assistant MUST confirm that the encounter,
  difficulty, fight, player, and player class/spec match the user's request and that
  timestamps, kill/wipe status, and filters are coherent; on mismatch it MUST
  correct the lookup or tell the user. Capabilities that look a player up by name
  MUST refuse an ambiguous match (more than one actor with that name in the fight)
  and list the candidates, rather than silently picking one.
- **FR-007**: Analytical answers MUST lead with a 1–2 sentence verdict, followed by
  evidence, at most three priority fixes ordered by expected impact (unless the user
  asks for a deep dive), material caveats, and source links attached to the claims
  they support.
- **FR-008**: Each priority fix MUST state its evidence, the expected change, and a
  confidence level (high / medium / low).
- **FR-009**: Coaching MUST prioritise mechanics, survival, major cooldowns, resource
  waste, buff/debuff uptime, and high-impact rotational gaps over minor throughput
  differences, and MUST NOT infer player intent.
- **FR-010**: For deaths and wipes, the assistant MUST separate immediate cause,
  contributing factors, and unknowns, and MUST NOT label damage "avoidable" without a
  current mechanic source or explicit rule.
- **FR-011**: The persona MUST be applied after the factual analysis: it MUST NOT
  change any fact, number, or confidence, MUST use at most one short joke or tavern
  metaphor per answer section, and MUST criticise the play, never the person. The
  existing blunt, mistake-first Barnaby voice is otherwise preserved.
- **FR-012**: On tool errors the assistant MUST attempt a clear repair at most twice,
  then give the supported partial answer and name the missing evidence; it MUST NOT
  loop indefinitely.
- **FR-013**: Existing behaviours MUST be preserved: Warcraft Logs source-link rules
  (links only from returned identifiers, one per distinct source, none on non-WCL
  claims), known-player context resolution, Heroic default for population questions,
  parallel independent lookups, charts from fetched data only, and graceful operation
  without web search.

**Fair benchmarks (Story 2)**

- **FR-014**: The system MUST be able to assemble a comparison group for a player's
  pull, matched on encounter, difficulty, spec, metric, the partition of the player's
  pull, kill status, and fight duration (within ~15% where enough parses exist),
  drawn from roughly the 75th–95th percentile band, and report each parse's item
  level where available (item level is reported, not matched).
- **FR-015**: Benchmark results MUST report the group size, the median and range of
  each compared measure, and which match criteria could not be met.
- **FR-015a**: The player's per-minute rates in a benchmark MUST be computed over the
  time the player was alive (the same death windows as FR-023), and the result MUST
  state the time dead, so an early death is never presented as low throughput or
  under-casting against the group.
- **FR-016**: The assistant MUST NOT treat a single maximum or rank-one parse as
  representative unless the user explicitly asks about elite/rank-one play, and MUST
  label any single-parse comparison as anecdotal.
- **FR-017**: Comparison group size MUST be bounded (default 3–5 parses) so a
  benchmark stays within the Warcraft Logs request budget; when budget is low the
  group MAY shrink and MUST be labelled accordingly.

**Percentile and data context (Story 3)**

- **FR-018**: Every percentile the assistant relies on MUST carry its context —
  rankings vs parses, today vs historical, overall vs item-level bracket, partition,
  metric, encounter, difficulty, and sample size (or "unknown") — and the assistant
  MUST state the parts that affect interpretation.
- **FR-019**: When both overall and item-level-bracket percentiles are available,
  the assistant MUST present both.
- **FR-020**: Warcraft Logs results used for analysis MUST indicate what they
  describe (report, fight, encounter, difficulty, partition, metric, player, as
  applicable) and whether they are complete (more pages available, truncated,
  sample size).
- **FR-021**: Population statistics MUST state the sample they were computed over,
  including when that sample is only the top of the leaderboard.
- **FR-022**: Claims that depend on completeness MUST NOT be made from partial
  results without saying so.

**Opportunity-based cast coaching (Story 4)**

- **FR-023**: The system MUST compute, deterministically, a player's **eligible time**
  in a fight — fight duration minus time dead and, where detectable, forced downtime,
  intermissions, and target immunity — and casts per minute per ability. (Eligible
  time is distinct from Warcraft Logs' own "active time", which measures time spent
  casting and is a performance measure, not an opportunity window.)
- **FR-024**: For major abilities whose cooldown duration is stated in the spec's
  stored class guide (FR-026), the system MUST compute approximate opportunities
  (eligible time ÷ cooldown) and the assistant MUST express usage as "uses of ~N
  opportunities", citing the guide as the cooldown's source.
- **FR-025**: When an ability's opportunities can't be established (no ready guide
  for the spec, or the guide doesn't state that cooldown), the assistant MUST compare
  its usage rate to the benchmark group and MUST NOT describe casts as "missed".
- **FR-025a**: When the guide supplying a cooldown is possibly stale or of unknown
  freshness (FR-027, FR-028), opportunity counts MUST be labelled approximate.

**Guide freshness (Story 5)**

- **FR-026**: Each stored class/spec guide MUST record the game version/patch it
  targets, its generation date, the source links used to produce it, and the
  cooldown durations of the spec's major abilities in a form the system can read
  reliably (not only as free prose).
- **FR-027**: Guides generated before this feature MUST be treated as unknown
  freshness until regenerated.
- **FR-028**: When a guide's patch is older than the current patch or unknown, the
  assistant MUST say so whenever that guide's advice drives a recommendation, and
  SHOULD prefer current-patch sources when available.
- **FR-029**: The Class Guides page MUST display each guide's patch and generation
  date and visibly mark guides that may be out of date.

### Key Entities

- **Evidence claim**: a statement in an answer, with its kind (observed,
  benchmarked, guidance, inferred, unknown) and the source(s) supporting it.
- **Percentile context**: the population (rankings/parses), timeframe
  (today/historical), bracket (overall/item level), partition, metric, encounter,
  difficulty, and sample size attached to a percentile value.
- **Result provenance & completeness**: what a Warcraft Logs result describes
  (report, fight, encounter, difficulty, partition, metric, player, time fetched)
  and whether it is complete (more pages, truncated, sample size).
- **Comparison group (matched cohort)**: the set of benchmark parses for a pull, its
  match criteria, unmet criteria, size, and per-measure median and range.
- **Ability opportunity**: for a player, ability, and fight — uses, eligible time,
  cooldown (from the spec guide), approximate opportunities, whether the count is
  approximate, and rate per minute.
- **Guide provenance**: patch/game version, generation date, source links, and
  major-ability cooldowns on a stored class/spec guide; freshness status (current,
  possibly stale, unknown).

## Success Criteria *(mandatory)*

### Measurable Outcomes

Unless stated otherwise, outcomes are checked by hand on a **review sample**: at
least 15 answers to questions chosen to cover every edge-case category above (an
automated evaluation set is deferred to a later feature).

- **SC-001**: Across the review sample, 100% of numbers and identifiers in answers
  match values returned by the tools (zero invented measurements or links).
- **SC-002**: Across the review sample, zero answers present an inference,
  benchmark difference, or guide recommendation as an observed fact.
- **SC-003**: 100% of insufficient-data cases end with an explicit statement of what
  can't be concluded plus a single smallest-next-step request, instead of a
  speculative answer.
- **SC-004**: At least 90% of benchmark comparisons use a matched group of 3 or more
  parses; 100% of the rest are labelled anecdotal or directional.
- **SC-005**: Zero benchmark comparisons treat a rank-one parse as typical when the
  user didn't ask about elite play.
- **SC-006**: 100% of percentiles quoted in cases where overall and bracket values
  differ show both, labelled.
- **SC-007**: Zero cast-usage criticisms use the word "missed" for an ability without
  an established opportunity count; 100% of cast-usage claims are expressed as rates
  or uses-out-of-opportunities.
- **SC-008**: 100% of coaching answers contain at most three priority fixes (unless
  a deep dive was requested), each with evidence, expected change, and confidence.
- **SC-009**: Zero cases where instructions embedded in retrieved content change the
  assistant's behaviour.
- **SC-010**: 100% of guides generated after release show a patch and generation
  date on the Class Guides page; pre-existing guides are shown as unknown freshness.
- **SC-011**: A typical report coaching answer that includes a benchmark completes
  within roughly the same time as today's answer plus no more than 50% (i.e. the
  fairer benchmark doesn't make answers feel slow), and never exhausts the Warcraft
  Logs request budget on its own.
- **SC-012**: In a blind side-by-side review of at least 10 coaching answers, the
  maintainer judges the new answers more trustworthy and at least as actionable as
  the old ones in at least 8 of 10.

## Assumptions

- The grounding document `documentation/designs/20261007_prompt_upgrade.md` is the
  source of intent; its recommended replacement prompt is a starting point, not a
  verbatim requirement, and is adapted to the tools that actually exist in this app
  (including charts, rate-limit checks, and the optional web search).
- Barnaby's blunt, mistake-first innkeeper voice (requested earlier) is kept; this
  feature only constrains joke density and forbids banter that changes facts or
  targets the person.
- Evidence kinds (observed / benchmarked / guidance / inferred) shape the wording of
  answers; they are not shown to users as explicit tags. Confidence is shown per
  priority fix.
- The "75th–95th percentile band" refers to Warcraft Logs' own percentile ranking for
  the encounter/spec, not percentiles of whatever top-of-leaderboard sample was
  fetched.
- Kill-status and fight-duration matching use data Warcraft Logs already exposes on
  ranking entries and reports; positioning and player intent are not available and
  are always treated as unknown.
- The current patch/game version can be determined at runtime (from Warcraft Logs
  zone/partition data or a web lookup); if it can't, guides are treated as unknown
  freshness rather than current.
- Existing guides are not bulk-regenerated automatically; they are flagged and
  regenerated on demand through the existing Class Guides flow.
- An internal per-answer analysis trace (resolved context, tool calls, evidence,
  confidence) is out of scope for this feature and is a candidate follow-up.
- An automated regression evaluation set (the grounding document's 25–50 scored
  cases) is deferred to its own feature; this feature is verified by manual review
  of a fixed sample (see Success Criteria).
- Ability cooldowns come from the spec's stored class guide, not a separately
  maintained cooldown list. Guides therefore become the single source for both
  expected play and major-ability cooldowns, and guide freshness (Story 5) directly
  bounds the reliability of opportunity counts (Story 4). Story 4 is delivered after
  Story 5.
- Replacing broad report tools wholesale is out of scope; new focused capabilities
  (matched comparison group, eligible time and cast opportunities) are added alongside
  the existing tools, which remain available.
