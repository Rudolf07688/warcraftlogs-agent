# Contract: Class Guides UI — Raid / Mythic+ (feature 015)

Supersedes the library parts of `specs/008-profile-class-pages/contracts/profile-page-ui.md`.
Visual language unchanged: class-coloured cards, `StatusBadge` tones, search + status filter,
font-display titles. Works at 360 px width with no horizontal scroll; keyboard-complete.

## Components (Constitution VII — UI reuse check, 2026-10-18)

| Need | Component | Source |
|---|---|---|
| Raid / Mythic+ switch | `ToggleGroup` (type single, variant outline, size sm) | existing `ui/toggle-group.tsx` (same style as the status filter) |
| Other-type indicator dot | `Tooltip` + a `span` dot with `aria-label` | **add** `@shadcn/tooltip` via MCP (`npx shadcn@latest add @shadcn/tooltip`), then run the MCP audit checklist |
| Viewer Raid / Mythic+ switch | `Tabs` | existing `ui/tabs.tsx` |
| Viewer | `Dialog` | existing |
| Report inaccuracy | `Dialog` + `Field` + `Textarea` + `Button` | existing |
| Status badges | `StatusBadge` (+ new tones/labels) | existing wrapper |
| Unverified-draft / held-update notice | `Alert` (warning) via `StatusAlert` | existing |

No hand-built component except the 8 px status dot inside the tooltip trigger (a styled
`span`; no registry item is a bare status dot).

## Library (`ClassGuidesTab`)

Toolbar (left → right, wraps on mobile): search · **content switch `Raid | Mythic+`** ·
status filter `All | Ready | Not generated | Needs attention` · count
`N of M <raid|Mythic+> guides ready`.

- The switch selects `contentType` (`"raid" | "mplus"`); default `raid`; persisted per device
  via `uiPrefs.getGuideContentType()/setGuideContentType()` (key `wcl.ui.guideContentType`,
  defensive read like `getSidebarWidth`).
- Each class card lists each spec **once**. A row shows the selected content type's
  `GuideSummary`: badge, provenance (`Patch 12.1 · 18 Oct` for raid; `Season 3 · 18 Oct` for
  M+), actions (View / ⟳ refresh / Generate / Retry / spinner), exactly as today but keyed by
  `(class, spec, contentType)`.
- To the right of the spec name: **other-type dot** — filled (ok tone) when the other type has
  a published guide, hollow when `none`, warn-tone when `needs_review`/`failed` without a
  published version, pulsing muted when pending. Tooltip + `aria-label`, e.g.
  "Mythic+ guide: ready" / "Mythic+ guide: not generated". Clicking the dot switches the
  toolbar to that content type (keeps scroll position).
- Card description and the toolbar count: ready = `has_published` for the selected type.
- "Needs attention" = selected type `failed` | `needs_review` | published-and-stale.
- Polling: while any row has either type `pending` and the tab is active (unchanged 4 s).

States per row (selected type) — see `guides-api.md` status table for wording.

## Viewer (`GuideViewerDialog`, extracted from `ClassGuidesTab`)

- Title: spec + class (class colour). Under it `Tabs`: **Raid | Mythic+**; opens on the
  content type the user clicked; switching tabs fetches that guide once (cached in component
  state). Each tab shows its own provenance line, freshness badge, refreshing indicator.
- `display == "published"` → markdown (incl. "What the coach looks for" section) + Sources
  (title, tier label "Official"/"Warcraft Logs"/"Guide site", date) + footer
  "Report an inaccuracy" button.
- `status == needs_review` with a published version → small warn notice "An update was held
  for review; showing the last verified guide."
- `display == "draft"` → warning `Alert`: "Unverified draft — these areas could not be
  confirmed:" + `review_issues` list, then the markdown. No report button.
- `display == "none"` → empty state "No Mythic+ guide yet" + Generate button (inline), or the
  pending spinner text "Researching the latest sources…".
- `unconfirmed` areas (published) render as a muted "Not covered" list at the end.

## Report inaccuracy dialog

Textarea (5–500 chars, counter), Submit (CSRF POST), success toast-style `StatusAlert`
"Thanks — this will be checked on the next update.", 429 → "slow down" notice. Focus returns
to the button.

## Characters tab

`GuideBadge` becomes `GuideIndicators`: two compact items `Raid ✓` `M+ –` using the
status-to-glyph mapping in `guides-api.md`, each with `aria-label` "Raid guide: ready".
Shown only when the character's spec is resolved.

## Types (`frontend/src/types.ts`)

`ContentType`, `GuideStatus` (+`needs_review`), `GuideSummary`, `GuideListItem`
(`raid`/`mplus` nested), `Guide` (= `GuideOut`), `CharacterGuides`; `Character.guides`
replaces `guide_status`/`guide_updated_at`. `restClient`: `getGuide(cls, spec, ct)`,
`generateGuide(cls, spec, ct, force)`, `reportGuide(cls, spec, ct, note)`.

## Acceptance (manual, quickstart §UI)

Desktop 3-column and 360 px: no horizontal scroll; tab order toolbar → cards → rows →
actions; switch announces its state; dot tooltip readable by screen readers; SC-014 timing
check (find + open a spec's Mythic+ guide < 30 s).
