# Feature Specification: Boss mechanics for the coach

**Feature Branch**: `081-boss-mechanics`
**Created**: 2026-11-20
**Status**: Draft
**Input**: sc-571 "Coach can explain boss mechanics (Gravebound, Ula'tek heart)", brief `sprints/2026-11-20/briefs/081-boss-mechanics.md`, board decision:571-design.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ask what a mechanic requires (Priority: P1)

A raider asks the coach "What does Gravebound require me to do, and how can I survive it?" after a Coiled Altar
pull. Today the coach says it can't look mechanics up. With this feature it answers what Gravebound does and what
the player must do (pick up their Soul Fragments before the debuff runs out), names the source and the patch, and
then ties it to the player's log.

**Why this priority**: "How do I survive X" is a core coaching question and the owner's own failing example.

**Independent Test**: Call the lookup with "Gravebound" (with and without "The Coiled Altar"); it returns the stored
note with what it does, what to do, a source link and a patch.

**Acceptance Scenarios**:

1. **Given** the current-tier notes, **When** the coach looks up "Gravebound" for "The Coiled Altar", **Then** it gets
   what removes the threat / what to do, a named source with URL, and the patch.
2. **Given** the owner types "The ulatek heart" (any apostrophe, any case), **When** the coach looks it up, **Then** it
   gets Ula'tek's Venomous Heart note.

---

### User Story 2 - No invented mechanics (Priority: P1)

A raider asks about an ability the notes don't cover. The coach says plainly it is not in its guides instead of
inventing a mechanic.

**Independent Test**: Look up an unknown ability; the result says it was not found, with no mechanic text.

**Acceptance Scenarios**:

1. **Given** an ability the notes lack, **When** it is looked up, **Then** the result is "Not in my mechanic guides."
2. **Given** an ability that exists under a different boss than the one named, **When** it is looked up with the
   wrong boss, **Then** the result is a miss that names the boss it belongs to, never the other boss's note presented
   as the named boss's.

---

### Edge Cases

- Arguments shaped like file paths (`../`, `\`, absolute paths) or URLs: never used to locate data; a plain miss.
- Very long arguments (10,000 characters), newlines, control characters: bounded, no crash, nothing echoed.
- Unicode compatibility lookalikes (full-width letters) and curly apostrophes match like their plain forms; letters
  from other scripts that only look alike do not match.
- A prompt-injection string as the ability: a plain miss; the text never comes back.
- Empty or whitespace-only ability: a short correctable error.
- The same ability name on two bosses with no boss named: a miss that names both bosses so the coach can ask again.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST keep curated mechanic notes for the current raid tier (The Venomous Abyss), one entry per
  ability: boss name and id, ability name and ids, alternative names, what it does, what to do, source name and URL,
  patch.
- **FR-002**: The coach MUST have a lookup that takes an ability (name, alternative name or ability id) and an optional
  boss, in the "Stored knowledge" tool group, available on every model provider.
- **FR-003**: A hit MUST return the boss, ability, what it does, what to do, source (name, URL) and patch, plus the
  ability's ids so the coach can find it in the log.
- **FR-004**: A miss MUST return found=false with "Not in my mechanic guides." and no mechanic text.
- **FR-005**: Matching MUST ignore case, apostrophe style (straight, curly, none), a leading "the", possessive "'s",
  punctuation and Unicode compatibility forms, and accept the boss name inside the ability text ("The Ula'tek heart").
- **FR-006**: When a boss is named, a hit MUST come only from that boss; an ability found only elsewhere gives a miss
  naming where it is (canonical names only).
- **FR-007**: The lookup MUST never build a file path or fetch from its arguments; the notes are a fixed set loaded
  from the app's own data directory.
- **FR-008**: Argument text MUST never be echoed back; over-long or empty arguments get a short fixed error.
- **FR-009**: The new tool's description MUST fit the prompt budget share (+400 tokens).

### Key Entities

- **Mechanic note**: one ability of one boss: name, ids, aliases, what it does, what to do, source, patch.
- **Encounter notes**: a boss (WCL encounter id, name, aliases such as the NPC names) with its mechanic notes.
- **Tier file**: the notes for one raid tier.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The owner's two questions ("What does Gravebound require me to do, and how can I survive it?", "The
  Ula'tek heart") each get an answer that states what to do and cites the note's source or patch (live check).
- **SC-002**: An ability not in the notes gets "not in my guides" in 100% of test lookups, with no mechanic text.
- **SC-003**: Every hostile input in the edge cases returns a bounded result with none of the input text in it.
- **SC-004**: Notes cover at least The Coiled Altar and Ula'tek, plus as many other current-tier bosses as good sources
  allow; each entry has a source URL and patch.

## Assumptions

- The current tier is The Venomous Abyss (WCL zone 53, patch 12.1.0, 12.1.5 live since 2026-10-13); notes are refreshed
  by hand per tier.
- Sources: Blizzard's Adventure Guide (ability names and ids), warcraft.wiki.gg, and Method guides for what to do;
  notes are written in our own words.
- Exact/alias lookup is enough for a few dozen entries; no vector search, no migration, no new dependency.
- Web search stays sc-380.

## Clarifications

### Session 2026-11-20 (answered by the developer, board `scope:081:*`)

- Q: Ability found under another boss than the one passed? → A: a miss naming the boss it is under (`found_under`,
  canonical names); two bosses and none passed: a miss listing both. (`scope:081:wrong-encounter`)
- Q: Invalid arguments? → A: standard error envelope with fixed text; hit/miss shapes unchanged. (`scope:081:bad-args`)
- Q: Extra hit fields? → A: `ability_ids` added; an unknown named boss is a miss; patch per note from its source date;
  Nymrissa Wavecaller out of scope. (`scope:081:result-fields`)
