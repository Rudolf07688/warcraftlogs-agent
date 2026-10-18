# Feature Specification: Grounded, Patch-Aware Class Guides

**Feature Branch**: `015-grounded-class-guides`

**Created**: 2026-10-18

**Status**: Draft (revised 2026-10-18: separate Raid and Mythic+ guides; agent coaching brief is the primary output)

**Input**: User description: "Here is a review of your plan with some added suggestions or questions. Please use this to ground the new spec" — grounding document: `documentation/wow_guide_grounding_plan_v2.md` (WoW Guide Generation: Grounding and Hallucination Plan v2). Originating todo: "Fix Class guides — hallucinations (better grounding; a reviewing agent that must fix the guide first; current datetime and exact patch version in the agent's context); Devourer DH spec not showing." Revision: "I would rather like to have the option to generate two different guides per spec -> Raid and M+. The UI change must be well-considered to still make it look good. Also consider that the guides in this context is the guidelines the agent sees when giving player feedback - good agent context is much more important here than the guide the user sees."

## Overview

The shared class/spec guide library (feature 008) and its freshness metadata (feature 009)
produce guides that often contain hallucinations: wrong cooldowns, invented or outdated
talents, guessed spell identifiers, and a guessed patch. The guides' most important reader
is not the person browsing the library but **the coaching agent**. When it gives a player
feedback, the agent treats the guide as its guidelines (feature 009 also uses the guide's
cooldowns to judge cooldown usage). A wrong guide makes the coaching wrong.

Today the agent gets the guide only as the opening part of the human-readable text, cut
off after a fixed length. This happens only for the user's own saved characters, and there
is a single guide per spec, even though raid and Mythic+ play differ. The guide author does
not know the real date (the assistant's "current time" is fixed when the service starts),
is never told the live patch, writes from second-hand search summaries in a single
unchecked pass, and is the general coaching assistant rather than an author working only
on guides. The class and spec roster is a fixed list, so the new Demon Hunter spec
**Devourer** never appears.

This feature rebuilds guide generation around one principle from the grounding plan:
**patch validity is access control for knowledge**. Evidence from the wrong game version
(test realms, Classic, an older patch, or something a later hotfix changed) must be
*unavailable* to the author, not just ranked lower.

Each spec can now have two guides, **Raid** and **Mythic+**, generated independently. Each
guide has two forms built from one set of verified claims:

- **The coaching brief** is the primary output. It is compact and structured for the
  agent, and every expectation in it can be checked against a log.
- **The readable guide** is for people. It never says anything the brief does not.

Before publication, a separate reviewer checks each guide claim by claim and either fixes it
or holds it back. Leaving a gap is a valid outcome: a shorter guide that says what it could
not confirm is better than a complete-looking guide with invented claims.

## Clarifications

### Session 2026-10-18

- Q: How may guide research use publisher pages (Wowhead, Icy Veins, etc.)? → A: Read full pages only to pull out facts; publish those facts paraphrased, with credit and links; never copy guide text.
- Q: When a guide is in "needs review", what do users see? → A: The previous ready guide if one exists; otherwise the draft with a prominent warning listing the unconfirmed areas.
- Q: What content does each spec guide cover? → A: ~~One guide per spec, raid-focused, plus a short Mythic+ section.~~ Superseded by the revision below.
- Q: Which guides regenerate automatically after a patch change or hotfix? → A: In-use guides (spec of a saved character, or opened in the last 14 days) regenerate immediately; all others are marked possibly stale and regenerate on next open or request.
- Revision (user): Two separate guides per spec, **Raid** and **Mythic+**, each generated independently. The library UI must be well designed for this. The agent-facing guidance (the coaching brief) matters more than the guide users read. PvP remains out of scope.
- Q: How should each spec row in the library show its two guides? → A: A Raid / Mythic+ switch in the toolbar sets which guide each row shows (and what the status filter and ready counts apply to). Each row also shows a small indicator of the other content type's status. The viewer has Raid / Mythic+ tabs.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Guides written for the real date and live patch (Priority: P1)

A player opens a guide. It states the patch it targets (and, for Mythic+, the season), and
that is the live patch on the live (Retail) game, not a guess, an older patch or a
test-realm build. Every guide is generated with an up-to-date briefing:

- the current date and time
- the live patch and the time of its latest hotfix
- the current raid tier and Mythic+ season
- the content type being written for
- the game environment (Retail, live, region)
- the full spec list for the class

The author works only on guides, has no coaching tools or coaching instructions loaded, and
is told to leave out anything it cannot confirm for that patch. The same date fix applies to
chat: the agent always knows the real current date, however long the service has been
running.

**Why this priority**: This is the cheapest change and removes a whole class of errors
(wrong patch, stale "current" season, content from an earlier expansion). It ships on its
own and every later story builds on the briefing.

**Independent Test**: Generate a guide for any spec, then compare the patch it states and
its metadata with the live patch. Keep the service running for more than a day, then ask
the agent and the guide author for today's date and check that both are correct.

**Acceptance Scenarios**:

1. **Given** the live patch is known, **When** a guide is generated, **Then** the guide
   states that patch near the top and its stored patch metadata equals it; a Mythic+ guide
   also states the current season.
2. **Given** the service has been running for several days, **When** a guide is generated
   or a chat question is answered, **Then** the date and time the author or agent works
   from is the real current date and time, not the service start time.
3. **Given** a guide is being generated, **When** the author cannot confirm a detail for the
   live patch, **Then** the detail is left out and the guide says which area is unconfirmed
   instead of filling it with a guess.
4. **Given** a guide is being generated, **When** the author runs, **Then** it has only the
   guide-writing instructions and the evidence for that guide; coaching tools and coaching
   instructions are not available to it.
5. **Given** the live patch cannot be determined (the game data is unavailable), **When** a
   guide is requested, **Then** generation is postponed and marked retryable with a clear
   reason, rather than publishing a guide for a guessed patch.

---

### User Story 2 - The agent coaches from a complete, content-matched brief (Priority: P1)

A player asks the agent "why was my damage low on this boss?" or "how did I play in that
+12?". The agent's guidelines for that player's spec are the **coaching brief** for the
matching content type: the Raid brief for a raid log or boss, the Mythic+ brief for a
dungeon run. The brief is given to the agent whole, never cut off part-way, and carries its
patch, freshness and confidence. Every expectation in it can be checked against a log: what
to look for, and which log data shows whether the player met it (casts, buff uptime,
cooldown usage, deaths). The agent can look up the brief for any spec and content type in
the conversation, not just the user's own characters, for example when coaching a friend or
a player in a shared report. When no verified brief exists for the spec and content type,
the agent says so plainly and does not apply the other content type's brief as if it fitted.

**Why this priority**: The user's stated top priority. Coaching quality depends far more on
what the agent sees than on how the library looks. Delivering the brief whole, matched to
the content, also fixes today's problem of cut-off guide text.

**Independent Test**: For a fixed set of raid and Mythic+ logs with ready briefs, ask
coaching questions and confirm the agent received the full brief for the right spec and
content type, that its advice uses only the brief's expectations and measured log data,
and that it says a brief is missing rather than borrowing the other one.

**Acceptance Scenarios**:

1. **Given** a ready Raid brief for a spec, **When** the user asks about that spec's
   performance in a raid log, **Then** the agent receives that brief whole, including its
   patch and freshness, and does not receive the Mythic+ brief as raid guidance.
2. **Given** a ready Mythic+ brief, **When** the user asks about a Mythic+ run, **Then** the
   agent receives the Mythic+ brief for that spec.
3. **Given** a question about a player whose spec is not among the user's saved characters,
   **When** a ready brief exists for that spec and content type, **Then** the agent can look
   it up during the conversation.
4. **Given** no ready brief exists for the spec and content type in question, **When** the
   agent coaches, **Then** it states that no verified guidance is available for that
   content, coaches only from measured log data, and does not present the other content
   type's brief as applying.
5. **Given** a brief is possibly stale or its spec's data was insufficient, **When** the
   agent uses it, **Then** that limitation is visible to the agent and is reflected in the
   confidence of its advice.
6. **Given** several characters' briefs would be relevant in one conversation, **When** they
   don't all fit the agent's guidance budget, **Then** whole briefs are left out (least
   relevant first), never truncated part-way, and the agent knows which ones it can still
   look up.

---

### User Story 3 - Every live spec is covered, including Devourer (Priority: P1)

A Devourer Demon Hunter adds their character or opens the class guides list. Devourer
appears next to Havoc and Vengeance, both of its guides can be generated, and the
character's guide links work. The class and spec roster comes from authoritative game data,
so any future new spec appears without a code change. A built-in roster is used only when
that data is unavailable.

**Why this priority**: This is a visible, reported gap: users of a whole spec currently get
nothing. It is small, independent and testable on its own.

**Independent Test**: Open the class guides list and confirm that every spec the game data
lists (including Devourer) appears exactly once. Add a Devourer character and confirm that
its spec is recognised and its guides can be generated.

**Acceptance Scenarios**:

1. **Given** the authoritative game data lists Devourer for Demon Hunter, **When** a user
   opens the class guides list, **Then** Devourer appears with the same statuses and
   actions as every other spec.
2. **Given** a character whose active spec resolves to Devourer, **When** the character is
   saved, **Then** its spec and role are recognised (damage dealer) and its guides are
   requested like any other spec's.
3. **Given** the authoritative game data is unavailable at startup, **When** the roster is
   built, **Then** the built-in roster is used, it includes Devourer, and the service still
   starts normally.
4. **Given** the game data adds a spec the built-in roster does not know, **When** the
   roster is next refreshed, **Then** the new spec appears without a code change.

---

### User Story 4 - Guide and coaching accuracy is measured before and after every change (Priority: P1)

The maintainer runs an accuracy check with two parts:

- **Guide facts:** a hand-checked test set of 5 to 10 known facts for each of 3 to 4 specs
  (one of them Devourer), covering both Raid and Mythic+, plus deliberately misleading
  cases.
- **Coaching:** a fixed set of raid and Mythic+ logs with expected coaching points, which
  checks whether the agent used the right brief and its expectations correctly.

The check reports patch accuracy, claim support rate, test-realm/Classic leakage, spec
coverage, abstention quality, source-link health and wrong-content-type brief use. It runs
once before any other story lands (the baseline) and again after each change.

**Why this priority**: Without a baseline, nobody can tell whether the later stories reduce
hallucinations or improve coaching. It has to exist before them, which makes it P1 even
though users don't see it.

**Independent Test**: Run the accuracy check against today's guides and coaching and record
the baseline report; it runs without any other story implemented.

**Acceptance Scenarios**:

1. **Given** the hand-checked test set, **When** the accuracy check runs, **Then** it
   reports, for each spec and content type, which test facts the guide confirms,
   contradicts or leaves out, plus the aggregate metrics.
2. **Given** the misleading cases (an older guide that looks very similar, a test-realm page
   newer than the live guide, conflicting guides, a hotfix after a guide was published, a
   brand-new spec with little data, and a raid question where only a Mythic+ brief exists),
   **When** the accuracy check runs, **Then** each case reports pass or fail with the
   reason.
3. **Given** the coaching test logs, **When** the check runs, **Then** it reports, for each
   expected coaching point, whether the agent raised it correctly, missed it, or
   contradicted it.
4. **Given** a candidate change, **When** it fails the release gate (any test-realm/Classic
   leakage, any wrong-content-type brief use, patch accuracy below 100%, or claim support
   below its target), **Then** the check fails, whatever the output's fluency or
   completeness.

---

### User Story 5 - Separate Raid and Mythic+ guides in a clean library (Priority: P2)

A player opens the class guides library. Each spec still appears once, on its class card,
and the library shows each spec's Raid and Mythic+ guides compactly. Each guide can be
generated, viewed, refreshed or retried on its own; generating one never requires the
other. Opening a spec shows its guides in one viewer, with a clear way to switch between
Raid and Mythic+, each showing its own patch or season, freshness and sources. A content
type that hasn't been generated offers a generate action in place. The layout keeps the
current look (class-coloured cards, the same status badges, search and status filter) and
works at phone width. A Raid / Mythic+ switch in the toolbar sets which guide each spec row shows and what the
status filter and ready counts apply to. Each row also carries a small indicator of the
other content type's status (e.g. a filled dot when that guide is ready, an empty one when
it isn't generated), so both are visible at a glance without doubling the rows. On the Characters tab, each character's guide indicator
summarises both guides, for example "Raid ready · M+ not generated".

**Why this priority**: This is the user's requested capability and makes Mythic+ coaching
possible. It needs the brief format (Story 2) to be defined first, and it doubles the
number of guides that must be generated, checked and kept fresh.

**Independent Test**: Generate only the Mythic+ guide for a spec and confirm the library
and the character indicator show Raid as not generated and Mythic+ as ready. Open the
viewer and switch between the two. Repeat at phone width and with keyboard only.

**Acceptance Scenarios**:

1. **Given** a spec with no guides, **When** a user generates only its Mythic+ guide,
   **Then** the Raid guide stays "not generated" and the Mythic+ guide goes through
   pending to ready (or needs review or failed) independently.
2. **Given** a spec with both guides ready, **When** the user opens it, **Then** one viewer
   shows the spec and lets the user switch between the Raid and Mythic+ guides, each with
   its own patch or season, generated date, freshness and sources.
3. **Given** the viewer is open on a content type that has no guide, **When** the user looks
   at it, **Then** it explains that the guide hasn't been generated and offers to generate
   it.
4. **Given** the toolbar switch is set to Mythic+, **When** the user applies the status
   filter (e.g. "Needs attention") or reads the ready counts, **Then** they apply to Mythic+
   guides only, every row shows its Mythic+ guide, and no spec appears twice.
5. **Given** a spec whose Raid guide is ready but whose Mythic+ guide is not generated,
   **When** the switch is on Raid, **Then** the row shows the Raid guide and an indicator
   that the Mythic+ guide is not generated, with an accessible label saying so.
6. **Given** the user switches content type, **When** they return to the library later on
   the same device, **Then** their last choice is remembered (Raid by default).
7. **Given** a phone-width screen or keyboard-only use, **When** the user browses, generates
   and views guides, **Then** every action is reachable, labelled and readable without
   horizontal scrolling.

---

### User Story 6 - Guides built on measured Warcraft Logs evidence (Priority: P2)

For each spec and content type, the system builds a data sheet from top-ranked logs of the
current raid tier (Raid) or the current Mythic+ season (Mythic+). It covers:

- the most common talent builds
- the observed spread of secondary stats
- how often each major ability is cast (casts per minute)
- the shortest gap between casts, which approximates the ability's cooldown
- uptime of key buffs and debuffs where measurable
- the real ability names and identifiers

The author uses the data sheet as primary evidence. Its measured values become the
benchmarks in the coaching brief, and the guide presents them as *observed* ("most top
players run…"), with the sample size, difficulty or key level and encounters behind them. It
does not present them as prescriptions.

**Why this priority**: These are measured facts the product already has privileged access
to. They remove the most damaging errors (guessed spell identifiers and cooldowns the
coaching relies on) and give the agent concrete benchmarks, but they need Stories 1 and 2
first.

**Independent Test**: Build the data sheet for a well-populated spec for both content types
and check its identifiers, cooldown estimates and talent builds against the logs. Generate
the briefs and confirm that every cooldown, identifier and benchmark in them comes from the
matching sheet.

**Acceptance Scenarios**:

1. **Given** enough top-ranked logs exist for a spec and content type, **When** its data
   sheet is built, **Then** it records talent builds, stat spread, cast rates, shortest
   cast gaps, measurable uptimes and real ability identifiers, each with sample size,
   difficulty or key level, and encounter scope.
2. **Given** a brief lists major cooldowns, **When** it is stored, **Then** each cooldown's
   ability identifier is either taken from the data sheet or left empty; it is never
   guessed.
3. **Given** a new or thinly played spec (e.g. Devourer early in a patch) is below the
   minimum sample size, **When** its data sheet is built, **Then** the low-sample data is
   marked as insufficient, and the brief relies on other evidence or says the area is
   unconfirmed.
4. **Given** data-sheet facts reach a guide, **When** a reader or the agent sees them,
   **Then** they are worded as observed behaviour among top players with their scope, not
   as the single correct choice for every player.
5. **Given** a Mythic+ guide, **When** it is written, **Then** it uses only Mythic+ data and
   Mythic+-valid sources, never raid-derived facts, and the same holds the other way round
   for a Raid guide.

---

### User Story 7 - Automatic checks stop inconsistent guides (Priority: P2)

Before a guide can be published, a set of rule-based checks run (no AI judgement involved):

- every ability named in the brief exists in that spec's observed ability list for that
  content type;
- stated cooldown lengths roughly match the shortest observed cast gap;
- the stated patch (and, for Mythic+, the season) equals the live one;
- every cited source is for the right game product, environment and content type (no test
  realm, beta or Classic);
- no source predates the latest hotfix affecting that spec unless it is flagged as possibly
  stale;
- every claim carries a reference to the evidence behind it;
- every coaching expectation in the brief names the log evidence that would show whether a
  player met it;
- the readable guide contains no claim that is missing from the brief.

A failed check blocks publication and records the reason.

**Why this priority**: These checks are cheap, repeatable and testable, and they are the
hard barrier behind the "patch validity is access control" principle. They depend on
Story 6's data sheet for some rules.

**Independent Test**: Feed hand-crafted guides with each kind of defect through the checks
and confirm each is caught with the right reason.

**Acceptance Scenarios**:

1. **Given** a draft guide with any of the defects listed above, **When** the checks run,
   **Then** the guide is not published and the failing check and the offending item are
   recorded.
2. **Given** a draft guide passes all checks, **When** the checks run, **Then** it proceeds
   to review (Story 9) or publication.
3. **Given** a guide is written as structured claims, **When** it is published, **Then**
   both the coaching brief and the readable guide are produced from those same claims.

---

### User Story 8 - Research limited to current, trustworthy sources (Priority: P3)

Before writing, the author gathers a fact sheet for the spec and content type, covering
talents, stat priority, cooldowns, rotation and content-specific advice (boss mechanics for
Raid, affixes and route-related play for Mythic+). Each fact records its source link, the
source's date, its trust tier and its product, environment, patch and content-type tags:

1. official game sources and game data
2. measured Warcraft Logs data
3. curated guide publishers
4. forums and video, which can lead to sources but are never the only basis for a fact

Hard filters run before the author sees anything: wrong product, test realm or beta,
incompatible patch or season, wrong class, spec or content type, and anything a later hotfix
superseded are all removed. Only then is the remaining evidence ordered by relevance, patch
match, authority and freshness. Freshness never overrides patch identity. The author may
only state facts on the sheet. Full source pages may be read, but only to pull out facts:
the guide states those facts in its own words with credit and links, and never reproduces a
publisher's guide text.

**Why this priority**: This gives the largest gain in completeness for areas the logs can't
measure (rotation intent, situational advice), but it depends on Stories 1, 6 and 7.

**Independent Test**: Run research for a spec while a test-realm page newer than the live
guide, a Classic page, and a page for the other content type all exist. Confirm that none of
them reach the fact sheet, and that every fact carries its source, date, tier and tags.

**Acceptance Scenarios**:

1. **Given** test-realm, beta or Classic material matches the search, **When** the fact
   sheet is built, **Then** that material is excluded before the author sees anything, even
   if it is newer or more relevant.
2. **Given** two current sources conflict on a fact, **When** the fact sheet is built,
   **Then** the higher-tier source wins, and if the tiers are equal the conflict is recorded
   and the fact is treated as unconfirmed.
3. **Given** a fact appears only in a tier-4 source, **When** the author writes, **Then**
   that fact is not stated as guidance.
4. **Given** the author writes, **When** a fact is not on the fact sheet or the data sheet
   for that content type, **Then** it does not appear in the guide.

---

### User Story 9 - Independent review and correction before publishing (Priority: P3)

After drafting, a separate reviewer, which is a different and stronger model than the
author, receives the same briefing, the data sheet and the fact sheet. It reviews the
**coaching brief first**, since that is what the agent coaches from. It breaks the guide
into individual claims and marks each as *confirmed*, *contradicted* or *unconfirmed* by
checking it against the evidence sheets, not against its own memory. Contradicted claims
are rewritten and unconfirmed claims removed, then the guide is checked again, for at most
3 rounds. A guide that passes is published as ready. A guide that still has open issues is
held in a new **needs review** state with those issues recorded. Users then see the previous
ready guide if one exists; if not, they see the draft with a prominent warning that lists
the unconfirmed areas. The agent never coaches from a draft.

**Why this priority**: This is the step that fixes the guide before anyone relies on it, as
asked in the originating todo. It works best once the evidence sheets (Stories 6 and 8)
exist for the reviewer to check against.

**Independent Test**: Give the reviewer a draft with seeded errors (a wrong cooldown, a
removed talent, a claim no evidence supports, a raid tip in a Mythic+ brief) and confirm
that each is caught, fixed or removed. Confirm that a draft whose problems can't be fixed
ends in needs review with its issues listed.

**Acceptance Scenarios**:

1. **Given** a draft guide and its evidence sheets, **When** review runs, **Then** every
   claim is marked confirmed, contradicted or unconfirmed with a reference to the evidence
   used.
2. **Given** contradicted or unconfirmed claims, **When** a review round completes, **Then**
   contradicted claims are corrected from the evidence, unconfirmed claims are removed, and
   the guide is checked again.
3. **Given** open issues remain after the final round, **When** review ends, **Then** the
   guide is stored as needs review with the open issues recorded and is not shown as ready.
4. **Given** review removes unsupported claims, **When** the guide is published, **Then** it
   states which areas were left out because they could not be confirmed.
5. **Given** a guide is in needs review, **When** a user opens it, **Then** they see the
   previous ready guide if one exists, otherwise the draft with a prominent warning listing
   the unconfirmed areas; the agent receives only the previous ready brief, or none.

---

### User Story 10 - Guides stay current and users can report errors (Priority: P3)

When the live patch or Mythic+ season changes, or a hotfix affecting a spec is released,
that spec's affected guides are marked possibly stale. Guides in use (the spec of at least
one saved character, or a guide opened in the last 14 days) regenerate automatically
through the full pipeline; all others regenerate the next time someone opens or requests
them. A user who spots a mistake can report it from the guide viewer with a short note.
Open reports are given to the next regeneration of that guide as items to check, and the
maintainer can see them.

**Why this priority**: This keeps accuracy from decaying after launch. It depends on the
pipeline from the earlier stories.

**Independent Test**: Simulate a patch change, a season change and a spec hotfix and confirm
that the affected guides are flagged and regenerated. Submit an inaccuracy report and
confirm the next regeneration checks it explicitly.

**Acceptance Scenarios**:

1. **Given** the live patch changes, **When** the system notices, **Then** every guide
   targeting the earlier patch is marked possibly stale, and those in use are queued for
   regeneration.
2. **Given** the Mythic+ season changes, **When** the system notices, **Then** every Mythic+
   guide for the earlier season is marked possibly stale, and those in use are queued.
3. **Given** a hotfix affecting a spec is released after its guides were generated, **When**
   the system notices, **Then** those guides are marked possibly stale and, if in use,
   queued for regeneration.
4. **Given** a possibly-stale guide that is not in use, **When** a user opens or requests
   it, **Then** its regeneration is queued and the user sees the existing guide marked
   possibly stale and being refreshed.
5. **Given** a signed-in user reports an inaccuracy on a guide, **When** the guide is next
   regenerated, **Then** the reported item is checked against the evidence and the report
   records whether it was confirmed and fixed or rejected.
6. **Given** a guide is being regenerated, **When** a user opens it or the agent uses it,
   **Then** the previous ready guide stays available, marked as being refreshed.

---

### Edge Cases

- **Thin data for a new spec** (Devourer early in a patch): the data sheet is marked
  insufficient, the brief relies on higher-tier written sources or leaves gaps, and the
  accuracy check's "brand-new spec" case covers this.
- **A test-realm page is newer than the live guide**: it is filtered out regardless of
  date. Freshness never overrides patch identity.
- **A hotfix lands after a guide is published**: the guide is flagged possibly stale and
  regenerated (Story 10). Sources older than the hotfix are excluded or flagged.
- **Only one content type has a guide**: the agent uses it only for that content type and
  says verified guidance is missing for the other; the library shows the missing one as
  not generated.
- **The conversation's content type is unclear** (no log, a general question): the agent
  uses the Raid brief by default, says so, and switches to the Mythic+ brief when the
  conversation turns to dungeons.
- **Early in a new Mythic+ season** (little data, few current sources): the Mythic+ brief
  says which areas are unconfirmed instead of borrowing last season's or raid advice.
- **Sources conflict**: the higher tier wins; if tiers are equal, the fact is treated as
  unconfirmed and left out.
- **The live patch is unknown** (game data unavailable): generation is postponed and
  retryable; no guide is published for a guessed patch.
- **The game data roster is unavailable**: the built-in roster (including Devourer) is used
  and the service starts normally.
- **A spec is removed from the game**: its existing guides are kept but no longer listed or
  regenerated.
- **Review never converges**: after the round limit the guide is held as needs review with
  its open issues. It is never published as ready; users see the previous ready guide, or
  the warned draft when there is none, and the agent gets the previous ready brief or none.
- **Generation fails partway** (model or data errors, rate limits): the guide becomes
  failed and retryable as today, and any previous ready guide stays available.
- **Retrieved content contains instructions** ("ignore previous rules…"): it is treated as
  untrusted evidence and never followed (consistent with feature 009's evidence contract).
- **The same evidence is needed by several guides in one patch**: lookups are reused within
  that patch, season and region, and discarded when the patch, season or a relevant hotfix
  changes.
- **Existing single guides from before this feature**: they are treated as Raid guides,
  marked possibly stale, and regenerated through the new pipeline under the in-use rule.

## Requirements *(mandatory)*

### Functional Requirements

**Briefing and authoring (Story 1)**

- **FR-001**: The agent's sense of the current date and time MUST be the real date and time
  at the moment of each request (chat and guide generation alike), never the moment the
  service started.
- **FR-002**: Every guide generation MUST receive a briefing containing:
  - the current date and time (UTC)
  - the live patch and the time of the latest hotfix when known
  - the current raid tier and Mythic+ season
  - the content type being written for
  - the game product (Retail), environment (live) and region
  - the full spec roster for the class
- **FR-003**: A guide MUST state the patch it targets (a Mythic+ guide also its season), and
  its stored metadata MUST equal the live values at generation time.
- **FR-004**: Guides MUST be written by a dedicated guide author with guide-writing
  instructions only; it MUST NOT have coaching tools or coaching instructions.
- **FR-005**: The guide author MUST leave out any detail it cannot confirm for the live
  patch and content type, and the guide MUST name the areas that were left unconfirmed.
- **FR-006**: When the live patch cannot be determined, generation MUST be postponed and
  marked retryable with a reason; a guide MUST NOT be published for a guessed patch.
- **FR-007**: The most precise patch available MUST be used. Where only major.minor is
  available, the guide MUST state only major.minor.

**Coaching brief and agent context (Story 2)**

- **FR-008**: Every guide MUST include a coaching brief: a compact, structured form for the
  agent. It MUST cover:
  - target patch, season (Mythic+) and content type
  - spec role
  - an ordered priority list (rotation and priorities)
  - major cooldowns, each with ability identifier, cooldown length, charges and expected
    usage pattern
  - key buffs, debuffs or procs to maintain, with expected uptime where measured
  - observed talent builds and stat priority, each with its scope
  - common mistakes
  - measured benchmarks with sample scope
  - an explicit list of areas not covered or unconfirmed
- **FR-009**: Every expectation and common mistake in a brief MUST name the log evidence
  that shows whether a player met it (e.g. cast count, buff uptime, cooldown usage, deaths),
  and every item MUST carry its evidence type (observed, benchmarked, guidance) and
  confidence.
- **FR-010**: A brief MUST fit within the agent's per-brief guidance budget so it is never
  truncated; a brief that doesn't fit MUST fail the automatic checks (Story 7) instead of
  being cut.
- **FR-011**: When coaching a player, the agent MUST receive the ready brief for that
  player's spec **and** the content type under discussion (Raid for raid logs or encounters,
  Mythic+ for dungeon runs). When the content type is unclear, it MUST default to the Raid
  brief and say so.
- **FR-012**: The agent MUST be able to look up the ready brief for any class, spec and
  content type during a conversation, including specs that are not among the user's saved
  characters.
- **FR-013**: When several briefs are relevant and they don't all fit the agent's total
  guidance budget, whole briefs MUST be left out in order of least relevance. A brief MUST
  NOT be truncated, and the agent MUST be told which briefs were left out and are available
  to look up.
- **FR-014**: When no ready brief exists for the spec and content type, the agent MUST say
  that verified guidance is unavailable, coach only from measured log data, and MUST NOT
  present another content type's brief as applying.
- **FR-015**: Each brief given to the agent MUST carry its patch or season, freshness and
  any insufficient-data flags; possibly stale or low-confidence briefs MUST lower the stated
  confidence of advice built on them.
- **FR-016**: Coaching that judges cooldown usage MUST use the cooldowns from the ready
  brief of the matching content type only; drafts (needs review, pending, failed) MUST never
  be given to the agent.
- **FR-017**: The readable guide MUST be produced from the same verified claims as the
  brief, MUST NOT contain any claim absent from the brief's verified claims, and MUST
  include a "What the coach looks for" section listing the brief's log-checkable
  expectations.

**Roster (Story 3)**

- **FR-018**: The class and spec roster MUST come from authoritative game data, with a
  built-in roster (including Devourer) used only when that data is unavailable.
- **FR-019**: Every spec in the roster MUST appear exactly once in the class guides list and
  MUST be supported for both guide types, character spec recognition and role inference
  (Devourer = damage dealer).
- **FR-020**: A spec added to the game data MUST appear after the next roster refresh with
  no code change; a spec no longer in the game data MUST stop being listed or regenerated,
  but its stored guides MUST be kept.

**Measurement (Story 4)**

- **FR-021**: The system MUST provide a repeatable accuracy check over a hand-checked test
  set of at least 5 facts each for at least 3 specs (including Devourer), covering both Raid
  and Mythic+, plus the misleading cases:
  - an older guide that looks very similar
  - a test-realm page newer than the live guide
  - conflicting guides
  - a hotfix after publication
  - a brand-new spec with little data
  - a raid question where only a Mythic+ brief exists
- **FR-022**: The accuracy check MUST include coaching tests: a fixed set of raid and
  Mythic+ logs with expected coaching points, scored as raised correctly, missed, or
  contradicted, plus whether the right brief was used.
- **FR-023**: The accuracy check MUST report the following, for each spec and content type
  and in total:
  - patch accuracy
  - claim support rate
  - test-realm/Classic leakage rate
  - current-source precision
  - spec coverage
  - abstention quality
  - source-link health
  - wrong-content-type brief use
  - coaching-point accuracy
- **FR-024**: A baseline accuracy report MUST be recorded against today's guides and coaching
  before any other story's changes are adopted.
- **FR-025**: The accuracy check MUST fail when any of these happens, regardless of other
  results:
  - any test-realm/Classic leakage
  - any wrong-content-type brief use
  - patch accuracy below 100%
  - claim support below its target

**Raid and Mythic+ guides and library (Story 5)**

- **FR-026**: Each spec MUST support two independent guides, Raid and Mythic+, each with its
  own status (none, pending, ready, needs review, failed), patch or season, generated date,
  freshness, sources and brief. PvP is out of scope.
- **FR-027**: Users MUST be able to generate, view, refresh and retry each content type's
  guide independently; generating one MUST NOT require or trigger the other.
- **FR-028**: The library MUST list each spec exactly once. A Raid / Mythic+ switch in the
  toolbar MUST set which content type's guide each row shows and acts on, and what the
  status filter and ready counts (overall and per class) apply to. Each row MUST also show
  a compact indicator of the other content type's status with an accessible label. The
  library MUST keep the class-coloured cards, status badges, search and status filter. The
  switch defaults to Raid and remembers the user's last choice on that device.
- **FR-029**: The guide viewer MUST show one spec at a time with a clear Raid / Mythic+
  switch. Each content type shows its own patch or season, generated date, freshness,
  sources and inaccuracy-report action; a content type without a guide offers to generate
  it in place.
- **FR-030**: The Characters tab MUST summarise both guides for each character in one compact
  indicator (e.g. "Raid ready · M+ not generated"). Saving a character MUST request the
  Raid guide for its spec; the Mythic+ guide MUST be requested too when the character has
  current-season Mythic+ activity in Warcraft Logs.
- **FR-031**: The library and viewer MUST work at phone width without horizontal scrolling,
  and every action MUST be keyboard reachable with an accessible label naming the spec and
  content type.

**Measured evidence (Story 6)**

- **FR-032**: For each spec and content type, the system MUST build a data sheet from
  top-ranked logs of the current raid tier (Raid) or current Mythic+ season (Mythic+),
  covering:
  - common talent builds
  - secondary-stat spread
  - casts per minute per major ability
  - shortest observed cast gap per major ability
  - measurable buff and debuff uptimes
  - real ability names and identifiers
- **FR-033**: Every data-sheet fact MUST record its sample size, difficulty or key level, and
  encounter scope; facts below a minimum sample size MUST be marked insufficient and MUST
  NOT be stated as guidance.
- **FR-034**: Ability identifiers in a brief MUST come from the data sheet or be left empty;
  they MUST NOT be generated by the model.
- **FR-035**: Data-sheet facts MUST be worded as observed behaviour among top players, with
  their scope, not as universal prescriptions; a guide MUST use only evidence for its own
  content type.

**Automatic checks (Story 7)**

- **FR-036**: Before publication, a guide MUST pass rule-based checks for:
  - abilities known to the spec for that content type
  - cooldown lengths consistent with observed cast gaps
  - stated patch or season equal to live
  - sources matching product, environment and content type
  - no source predating the latest hotfix affecting the spec, unless flagged possibly stale
  - an evidence reference on every claim
  - a log-evidence reference on every brief expectation
  - the brief fitting its budget
  - no claim in the readable guide that is absent from the brief
- **FR-037**: A failed check MUST block publication and record which check failed and on
  which item.
- **FR-038**: The guide author MUST produce the guide as structured claims from which the
  system builds both the brief and the readable guide.

**Research (Story 8)**

- **FR-039**: Research MUST produce a fact sheet in which every fact records:
  - its source link and source date
  - its trust tier (1 official, 2 measured log data, 3 curated publishers, 4 forums/video)
  - product, environment, patch or season, and content-type tags
- **FR-040**: Material for the wrong product, a test realm or beta, an incompatible patch or
  season, the wrong class, spec or content type, or material superseded by a later hotfix
  MUST be removed before the author receives any evidence. Remaining evidence is ordered by
  relevance, patch match, authority and freshness, with freshness never overriding patch
  identity.
- **FR-041**: A fact supported only by tier-4 sources MUST NOT be stated as guidance;
  conflicts between equal-tier current sources MUST be recorded and the fact treated as
  unconfirmed.
- **FR-042**: The guide author MUST state only facts present on the fact sheet or the data
  sheet for that content type.
- **FR-043**: Full source pages MAY be read for fact extraction only. Guides MUST state
  extracted facts in their own words with credit and a link to the source, and MUST NOT
  reproduce publisher guide text beyond a short quotation.
- **FR-044**: Retrieved content MUST be treated as untrusted evidence; instructions inside
  it MUST never be followed.

**Review (Story 9)**

- **FR-045**: Every draft guide MUST be reviewed, before publication, by a reviewer that is a
  different and stronger model than the author and that receives the same briefing and
  evidence sheets. The review covers the coaching brief first.
- **FR-046**: The reviewer MUST mark every claim confirmed, contradicted or unconfirmed with a
  reference to the evidence used, checking against the evidence sheets rather than its own
  memory.
- **FR-047**: Contradicted claims MUST be corrected from the evidence and unconfirmed claims
  removed, followed by re-review, for at most 3 rounds.
- **FR-048**: A guide MUST be published as ready only if review passes; otherwise it MUST be
  stored as "needs review" with its open issues recorded.
- **FR-049**: For a guide in needs review, users MUST see the previous ready guide when one
  exists; otherwise they MUST see the draft with a prominent warning listing its unconfirmed
  areas. A draft MUST never be presented as ready or given to the agent.

**Freshness and feedback (Story 10)**

- **FR-050**: A guide MUST be marked possibly stale when the live patch changes from the one
  it targets, when (for Mythic+) the season changes, or when a hotfix affecting its spec is
  released after it was generated.
- **FR-051**: A possibly-stale guide that is in use (its spec is the active spec of at least
  one saved character, or it was opened in the last 14 days) MUST be queued for regeneration
  through the full pipeline immediately; any other possibly-stale guide MUST be queued when
  it is next opened or requested.
- **FR-052**: Signed-in users MUST be able to report an inaccuracy on a guide with a short
  note; open reports MUST be given to that guide's next regeneration as items to verify, and
  each report MUST record its outcome (confirmed and fixed, or rejected with reason).
- **FR-053**: While a guide regenerates, the previous ready guide and brief MUST remain
  available to users and the agent, marked as being refreshed.
- **FR-054**: Evidence lookups MUST be reused within the same patch, season, product,
  environment and region, and MUST be discarded when the patch, season or a relevant hotfix
  changes.
- **FR-055**: Guides that existed before this feature MUST be treated as Raid guides, marked
  possibly stale, and regenerated under FR-051.

### Key Entities *(include if feature involves data)*

- **Content type**: Raid or Mythic+. Every guide, brief, data sheet, fact and accuracy test
  belongs to exactly one content type.
- **Generation briefing**: The per-run context given to the author and reviewer: current
  date and time, live patch (and precision), latest hotfix time, raid tier, Mythic+ season,
  content type, product, environment, region, and the class's spec roster.
- **Spec roster entry**: A class and spec pair as listed by authoritative game data, with
  display name, role and whether it came from game data or the built-in fallback.
- **Spec guide** (existing, extended): Identified by class, spec **and content type**. It
  holds:
  - status (none, pending, ready, needs review, failed)
  - patch or season, generated date, freshness and sources
  - its verified claims, coaching brief and readable guide
  - open review issues, the areas left unconfirmed, and the briefing it was generated under
- **Coaching brief**: The agent-facing form of a guide. It holds the structured priorities,
  cooldowns, uptimes, builds, mistakes and benchmarks, each with its log-evidence reference,
  evidence type and confidence, plus the unconfirmed-areas list. It is bounded in size.
- **Guide claim**: An individual verified statement with its evidence reference and review
  verdict (confirmed, contradicted, unconfirmed); both the brief and the readable guide are
  built from claims.
- **Spec data sheet**: Measured evidence for one spec, content type and patch or season:
  talent builds, stat spread, cast rates, shortest cast gaps, uptimes and ability
  identifiers, each with sample size, difficulty or key level, encounter scope and a
  sufficiency flag.
- **Evidence item / fact sheet**: A single researched fact with source link, source date,
  trust tier and tags; the fact sheet is the filtered set of these for one guide.
- **Inaccuracy report**: A user's note against a specific guide (spec and content type),
  with its status (open, confirmed and fixed, rejected) and the regeneration that resolved
  it.
- **Accuracy test case**: A hand-checked fact, misleading scenario, or coaching log with
  expected coaching points, for a spec and content type; accuracy reports are produced from
  runs over these.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of guides generated after this feature state a patch (and, for Mythic+, a
  season) that matches the live one at generation time.
- **SC-002**: 0 test-realm, beta or Classic sources are cited across all generated guides and
  all accuracy-check runs.
- **SC-003**: Across the hand-checked test set, no published guide contradicts a hand-checked
  fact. Every test fact is either stated correctly or explicitly left out.
- **SC-004**: At least 95% of claims in guides published as ready are confirmed by recorded
  evidence.
- **SC-005**: Spec coverage is 100%: every spec in the authoritative roster, including
  Devourer, appears in the library with both content types available.
- **SC-006**: 100% of ability identifiers in coaching briefs are either verified against
  measured data or left empty.
- **SC-007**: After the service has run for more than 24 hours, the date the agent and guide
  author work from equals the real current date in 100% of checks.
- **SC-008**: All six misleading cases in the accuracy check pass.
- **SC-009**: In 100% of coaching test conversations with a ready brief, the agent receives
  the full, untruncated brief for the correct spec and content type; wrong-content-type
  brief use is 0.
- **SC-010**: On the coaching test logs, at least 90% of expected coaching points are raised
  correctly and none are contradicted, and coaching-point accuracy improves on the recorded
  baseline.
- **SC-011**: Compared with the recorded baseline, the share of hand-checked facts that
  guides get wrong drops by at least 80%.
- **SC-012**: After a patch change, season change or spec hotfix, affected guides are
  flagged within one roster/patch refresh, and in-use guides are regenerated within 24
  hours.
- **SC-013**: 95% of guide generations, including review, finish within 10 minutes, and a
  previous ready guide is never hidden (from users or the agent) while a new one is
  generated.
- **SC-014**: In a usability check, users find, generate and open a specific spec's Mythic+
  guide in under 30 seconds on first try, at desktop and phone width, with each spec still
  listed once.
- **SC-015**: Every inaccuracy report on a guide has a recorded outcome after that guide's
  next regeneration.

## Assumptions

- Guides target the **Retail, live** game only. Classic, test realms, beta and PvP are out
  of scope. Guides are region-agnostic; region is recorded in the briefing for evidence
  filtering and caching.
- Warcraft Logs ranks Mythic+ runs per spec for the current season, so Mythic+ data sheets
  can be built from top-ranked keys. If a spec has too few ranked keys, its Mythic+ data is
  marked insufficient (FR-033).
- Warcraft Logs' live raid partition gives the patch as major.minor. A more precise build
  string from an official version source will be used if it proves reliable during
  planning; otherwise guides state major.minor (FR-007).
- The per-brief and total guidance budgets, the minimum sample size, and the claim-support
  target are set during planning and recorded in the accuracy check; SC-004's 95% and
  SC-010's 90% are the starting targets.
- The agent decides the content type from the conversation: the log or encounter being
  discussed, or the user's wording. This feature does not add a manual content-type control
  to chat.
- Hotfix detection relies on an official hotfix/patch-notes source being reachable; when it
  isn't, only patch and season changes trigger regeneration.
- The hand-checked test set and coaching test logs are written and maintained by the
  maintainer; this feature provides the format and the check, not an exhaustive fact base.
- Guides remain a single shared, global library (feature 008), now keyed by class, spec and
  content type; the existing statuses (none, pending, ready, failed) are kept and "needs
  review" is added.
- Reviewer and author model choices are configurable; "stronger" means the more capable
  model available to the deployment at the time.
- Generation stays a non-blocking background task with the existing concurrency cap and
  per-user request rate limit (each content type counts as one request). Two guides per
  spec plus research and review raise generation cost; that is accepted in exchange for
  accuracy and is limited by the in-use regeneration rule.
- Inaccuracy reports are visible to the maintainer only; no public moderation workflow is
  in scope.
- The frozen-date fix (FR-001) also changes chat behaviour, which is intended.
