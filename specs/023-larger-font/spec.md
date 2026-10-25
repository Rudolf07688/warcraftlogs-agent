# Feature Specification: Slightly larger default font

**Feature Branch**: `023-larger-font`
**Created**: 2026-10-25
**Status**: Draft
**Input**: sc-152, "Slightly increase the default font size"; product owner decision 30.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Text is a step easier to read (Priority: P1)

A user opens the app and finds all text (sidebar, composer, welcome panel, chat messages) one step larger than before, with no broken layout.

**Why this priority**: it is the whole feature.

**Independent Test**: load the app at 1280px and 390px wide; text is visibly larger and nothing overflows or is clipped.

**Acceptance Scenarios**:

1. **Given** the app at 1280px, **When** the sidebar (with pin buttons), composer, welcome panel (raid and M+ cards) and chat messages render, **Then** there is no horizontal overflow or clipped text.
2. **Given** the same views at 390px, **Then** no regression beyond the existing 390px horizontal overflow (decision 31; the sidebar already overflowed there).
3. **Given** the font size is changed in the future, **Then** it is changed in one place (the root size) and all text follows.

### User Story 2 - Fixed-pixel text sizes scale with the root (Priority: P1)

Font sizes declared in fixed pixels are converted to relative units so one root change reaches them. Before the root change, rendering is identical.

**Independent Test**: computed font sizes of sampled elements are the same before and after the conversion, at the current root.

**Acceptance Scenarios**:

1. **Given** the conversion only, **When** computed font sizes are compared with the previous build, **Then** they are identical.

## Requirements *(mandatory)*

- **FR-001**: Every hard-coded pixel font size in `styles.css` and `index.css` MUST become a relative size (px/16 rem) with identical rendering at the current root.
- **FR-002**: The root font size MUST be raised one step (16px to 17px) in one place, as `html { font-size: 106.25% }` (decision 32).
- **FR-003**: Spacing, borders and layout pixel values MUST NOT change.
- **FR-004**: No per-component font overrides are added.

## Success Criteria *(mandatory)*

- **SC-001**: Text is about 6% larger across the app.
- **SC-002**: No horizontal overflow or clipped text at 1280px (and no regression at 390px, decision 31) in the sidebar, composer, welcome panel and chat messages.
- **SC-003**: The frontend build passes.

## Assumptions

- "One step" is 16px to 17px (about 6%); the product owner pre-answered the conversion approach (decision 30).
- Tailwind `text-*` utilities are already rem-based and follow the root.
