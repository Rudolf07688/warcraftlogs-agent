---

description: "Task list for feature 010 — Shared UI Component Adoption"
---

# Tasks: Shared UI Component Adoption

**Input**: Design documents from `/specs/010-shadcn-ui-adoption/`

**Prerequisites**: plan.md, spec.md, research.md (R1–R14), data-model.md, contracts/ui-components.md, quickstart.md

**Tests**: Not requested in the spec and the frontend has no test runner (research R14). Verification per story is `npx tsc -b`, `npm run build`, the grep audits in `contracts/ui-components.md` §5–§7 and the manual checks in `quickstart.md` §3. No test tasks are generated.

**Organization**: Tasks are grouped by user story (US1 forms/buttons → US2 dialogs/confirmations → US3 tabs → US4 tables/badges/alerts). Every story leaves the app building and usable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US4)
- All paths are relative to the repository root; frontend work lives under `frontend/`

## Standing rules (constitution VI, every task)

- Before editing a component, run `impact({target: "<Symbol>", direction: "upstream"})` (planning results: `ModelSelect`, `Composer`, `Sidebar`, `ClassGuidesTab`, `CharactersTab` LOW; `AdminUsersPage` UNKNOWN, confirmed route-only by grep).
- Before each commit, run `detect_changes({scope: "all"})`; after committing, `node .gitnexus/run.cjs analyze --index-only`.
- Never touch the FR-015 list: `MessageList.tsx`, `SpellCard.tsx`, `CastBar.tsx`, `RuneCircle.tsx`, `Ambient.tsx`, `BackendBootGate.tsx`, `PlotlyArtifact.tsx`, `StreamMarkdown.tsx`, `FollowUps.tsx`, `EncounterPicker.tsx`, the sidebar resizer and section toggles.

---

## Phase 1: Setup (install primitives, tokens)

**Purpose**: Get the generated components, their dependency and the theme tokens in place, with the three recorded local edits.

- [x] T001 Record the baseline per quickstart §0: from `frontend/` run `npm ci && npm run build`, note `gzip -c dist/assets/index-*.js | wc -c` as BEFORE_GZ, and the current native-control count from `grep -rnE '<(button|input|select|textarea)\b|confirm\(' src --include='*.tsx' | wc -l`; write both numbers into a new `## Measurements` section at the bottom of `specs/010-shadcn-ui-adoption/quickstart.md`
- [x] T002 (also produced `separator.tsx`, a dependency of `field`; the CLI mis-resolved the `cn` alias to an npm package and absolute `src/…` imports — both fixed in T003, see research R1) From `frontend/` run `npx shadcn@latest add button input textarea label field native-select dialog alert-dialog tabs table badge alert`; confirm `frontend/src/components/ui/` holds the 12 files listed in `contracts/ui-components.md` §1 and that `frontend/package.json` gained only `radix-ui` (plus lockfile changes)
- [x] T003 Verify `grep -rn "lucide-react" frontend/src/components/ui` is empty; if any file still imports lucide, replace the import with the same-named icon from `react-icons/lu` (e.g. `LuX`, `LuChevronDown`) in that file under `frontend/src/components/ui/` (FR-012, research R1)
- [x] T004 [P] Trim `buttonVariants` in `frontend/src/components/ui/button.tsx` to variants `default`, `secondary`, `ghost`, `destructive` and sizes `default`, `sm`, `icon` (delete `outline`, `link`, `lg`, `icon-sm`, `icon-lg`); keep `asChild` support (research R8)
- [x] T005 [P] Remove the `tw-animate-css` utility classes (`data-[state=open]:animate-in`, `data-[state=closed]:animate-out`, `fade-in-0`, `fade-out-0`, `zoom-in-95`, `zoom-out-95`, `slide-in-from-*`, `slide-out-to-*`, `duration-200`) from `frontend/src/components/ui/dialog.tsx` and `frontend/src/components/ui/alert-dialog.tsx` (research R3)
- [x] T006 [P] Add `success` and `warning` variants to `badgeVariants` in `frontend/src/components/ui/badge.tsx` using `border-success/40 bg-success/15 text-success` and `border-warning/40 bg-warning/15 text-warning` (research R10)
- [x] T007 Add the shared-component tokens to `frontend/src/index.css` per research R2 / contract §3: new `:root` variables (`--card-foreground`, `--popover`, `--popover-foreground`, `--primary-foreground`, `--secondary`, `--secondary-foreground`, `--surface-muted`, `--muted-foreground`, `--surface-accent`, `--accent-foreground`, `--destructive`, `--success`, `--warning`, `--input`, `--ring`, `--radius`) and in `@theme inline` map `--color-muted: var(--surface-muted)`, `--color-muted-foreground: var(--muted)`, `--color-accent: var(--surface-accent)`, plus `--color-<name>` for every other new token and `--radius-sm/md/lg/xl`; leave the legacy `--bg*/--text*/--accent/--danger/--wow-gold*` aliases unchanged
- [x] T008 Run `npx tsc -b` and `npm run build` from `frontend/` to confirm the generated files and tokens compile before any page is touched

**Checkpoint**: primitives installed and themed; nothing in the app uses them yet.

---

## Phase 2: Foundational (app wrappers used by several stories)

**Purpose**: The three shared wrappers from data-model.md §1–§3 that US1, US2 and US4 all import.

- [x] T009 [P] Create `frontend/src/components/StatusBadge.tsx`: export `Tone`, `TONE_VARIANT`, `GUIDE_TONE`, `USER_TONE`, `INVITE_TONE`, `GUIDE_LABEL_SHORT`, `GUIDE_LABEL_LIBRARY` and `StatusBadge({ tone, title, children })` rendering `Badge` with the mapped variant and `whitespace-nowrap` (contract §2, data-model §2)
- [x] T010 [P] Create `frontend/src/components/StatusAlert.tsx`: `StatusAlert({ tone, children, onDismiss, className })` rendering `Alert variant={tone === "error" ? "destructive" : "default"}` with `AlertDescription` and, when `onDismiss` is given, a `Button variant="ghost" size="icon" aria-label="Dismiss"` with a `react-icons/lu` `LuX` icon (contract §2)
- [x] T011 [P] Create `frontend/src/components/ConfirmDialog.tsx`: controlled `AlertDialog` with `AlertDialogTitle`, `AlertDialogDescription`, `AlertDialogCancel` ("Cancel") and `AlertDialogAction asChild` wrapping `Button variant="destructive"` labelled `confirmLabel`; `onOpenChange(false)` calls `onCancel` only when `!busy`; both buttons `disabled={busy}`; `onEscapeKeyDown` prevented while busy (contract §2, data-model §1)
- [x] T012 Run `npx tsc -b` from `frontend/` (wrappers compile unused)

**Checkpoint**: foundation ready; user stories can proceed.

---

## Phase 3: User Story 1 — Consistent forms and buttons everywhere (Priority: P1) 🎯 MVP

**Goal**: Every text input, dropdown, label, validation message and button on the auth, admin and profile pages and in the chat header, sidebar and composer is a shared component in the dark-gold palette; behaviour unchanged (FR-001–FR-004, FR-011–FR-013).

**Independent Test**: quickstart §3 US1 steps 1–5 plus `grep -rnE 'neutral-|indigo-|red-[0-9]' frontend/src` returning nothing for the six retired files.

- [x] T013 [P] [US1] Rebuild `frontend/src/pages/LoginPage.tsx` with `Field`/`FieldLabel`/`Input` (ids via `useId`, `autoComplete` kept), the native "Show password" checkbox inside a `Label`, form-level error as `FieldError`, submit as `Button type="submit" className="w-full"`; page shell `bg-background text-foreground`, card `rounded-2xl border border-border bg-card p-6` (research R12)
- [x] T014 [P] [US1] Rebuild `frontend/src/pages/AcceptInvitePage.tsx` the same way (two password `Input`s with `minLength={15}`, checkbox, `FieldError`, `Button` disabled while `submitting || !ready`); keep the `<meta name="referrer">` and token scrubbing untouched
- [x] T015 [P] [US1] Rebuild `frontend/src/pages/ResetPasswordPage.tsx` the same way, including the "Password updated" card whose "Go to sign in" becomes `Button className="w-full"`
- [x] T016 [P] [US1] Re-theme `frontend/src/pages/ForbiddenPage.tsx` (shell/text tokens, link `text-primary hover:text-glow`) and the loading state in `frontend/src/auth/RequireAuth.tsx` (`bg-background text-muted-foreground`)
- [x] T017 [US1] In `frontend/src/pages/AdminUsersPage.tsx` convert the page shell and section cards to theme tokens, the invite form to `Field`/`FieldLabel`/`Input`/`NativeSelect`, and every button to `Button` (Create invite `default`; Copy/Resend/Enable/Reset link `secondary size="sm"`; Revoke/Disable `destructive size="sm"`); "← Back to app" becomes `Button asChild variant="secondary"` around `Link`; leave the tables, status cells, error paragraph and `confirm()` call for US2/US4
- [x] T018 [P] [US1] Replace the `<select className="model-select">` in `frontend/src/components/ModelSelect.tsx` with `NativeSelect`/`NativeSelectOption` carrying `aria-label="Model"` and `title="Model"`, keeping `value`/`disabled`/`onChange`; keep the degraded span for now (US4 converts it)
- [x] T019 [P] [US1] Replace the textarea and Send button in `frontend/src/components/Composer.tsx` with `Textarea` (`rows={2}`, same placeholder, `aria-label="Message"`, same `onKeyDown`) and `Button` (`disabled={disabled || !text.trim()}`); keep the `.composer` wrapper
- [x] T020 [P] [US1] In `frontend/src/components/Sidebar.tsx` convert "+ New chat" to `Button`, "⚑ Profile" to `Button variant="secondary"` (keep `title`), and the conversation ✕ to `Button variant="ghost" size="icon" aria-label="Delete conversation" title="Delete"` keeping `e.stopPropagation()` and the hover-reveal class; do not touch the section toggles or raid items (FR-015)
- [x] T021 [US1] In `frontend/src/App.tsx` header convert the PDF button and Sign out to `Button variant="secondary" size="sm"` (keep `title`s and `disabled={streaming}` on PDF) and the Admin anchor to `Button asChild variant="secondary" size="sm"` around `<a href="/admin/users">`
- [x] T022 [P] [US1] In `frontend/src/components/profile/CharactersTab.tsx` convert `IdentityForm` inputs to `Input`, the region and raid-role selects to `NativeSelect` (keep `aria-label="Raid role"`), the submit to `Button size="sm"`, and the remove ✕ buttons to `Button variant="ghost" size="icon"` with `aria-label` matching their `title`; leave badges, error strip and the remove handlers' direct calls for US2/US4
- [x] T023 [P] [US1] In `frontend/src/components/profile/ClassGuidesTab.tsx` convert View/Generate/Retry to `Button size="sm"`, Refresh to `Button variant="secondary" size="sm"` (keep `title`), and the overlay close ✕ to `Button variant="ghost" size="icon"` (US2 replaces the overlay itself)
- [x] T024 [P] [US1] In `frontend/src/pages/ProfilePage.tsx` convert "← Back to chat" to `Button asChild variant="secondary"` around `Link`; leave the tab strip for US3
- [x] T025 [US1] Delete the now-dead rules from `frontend/src/styles.css`: `.new-chat`, `.conversation-delete` (keep the `.conversation-item:hover .conversation-delete` opacity rule only if still referenced by a class on the ghost button), `.model-select`, `.model-select-wrap`, `.download-pdf`, `.bg-toggle*`, `.composer-input`, `.composer-send`, `.profile-open`, `.profile-remove`, `.profile-form input/select/button`, `.profile-back`, `.guide-btn*`, and the transition/hover selectors listing them (research R13)
- [x] T026 [US1] Run `npx tsc -b && npm run build` from `frontend/`, then quickstart §3 US1 steps 1–5 in the browser; confirm `grep -rnE 'neutral-|indigo-|red-[0-9]' frontend/src` is empty

**Checkpoint**: US1 shippable — one look for every field and button, palette unified.

---

## Phase 4: User Story 2 — Accessible dialogs and in-app confirmations (Priority: P2)

**Goal**: The guide viewer is a real modal; disable user, delete conversation, remove friend and remove guild all go through `ConfirmDialog`; `window.confirm` is gone (FR-005, FR-006).

**Independent Test**: quickstart §3 US2 steps 1–9; `grep -rn 'confirm(' frontend/src --include='*.tsx'` is empty.

- [x] T027 [US2] In `frontend/src/components/profile/ClassGuidesTab.tsx` replace the `.profile-overlay`/`.guide-view-panel` markup with `Dialog open={viewing !== null} onOpenChange={(o) => !o && setViewing(null)}`, `DialogContent className="max-h-[86vh] overflow-y-auto sm:max-w-3xl" aria-describedby={undefined}`, `DialogHeader`/`DialogTitle` "{class} — {spec}"; keep `.guide-view-meta`, `.guide-view-body`, `.guide-sources` content inside (research R5)
- [x] T028 [P] [US2] In `frontend/src/pages/AdminUsersPage.tsx` add `pendingDisable: AdminUser | null` state; Disable sets it instead of calling `confirm()`; render one `ConfirmDialog` (title "Disable user?", description naming `pendingDisable.email`, confirmLabel "Disable", `busy`, onConfirm → `run(setUserStatus(id, "disabled"))` then clear, onCancel → clear); Revoke and Enable stay immediate
- [x] T029 [P] [US2] In `frontend/src/components/Sidebar.tsx` widen `onDelete` to `(id: string) => void | Promise<void>`, add `pendingDelete: Conversation | null` and `deleting` state; the ✕ sets `pendingDelete`; one `ConfirmDialog` (title "Delete conversation?", description naming `title || "Untitled"`, confirmLabel "Delete") awaits `onDelete(id)` with `busy={deleting}` before clearing (`App.removeConversation` is already async and needs no change)
- [x] T030 [P] [US2] In `frontend/src/components/profile/CharactersTab.tsx` add `pendingRemove` state (`{kind:"friend", friend} | {kind:"guild", guild} | null`); the two ✕ buttons set it; one `ConfirmDialog` (title "Remove friend?" / "Remove guild?", description with `Name-Server (Region)`, confirmLabel "Remove", `busy`) calls `run(deleteFriend(id))` / `run(deleteGuild())`
- [x] T031 [US2] Delete `.profile-overlay`, `.profile-panel`, `.profile-header`, `.profile-close`, `.guide-view-panel` from `frontend/src/styles.css` (research R13)
- [x] T032 [US2] Run `npx tsc -b && npm run build` from `frontend/`; walk quickstart §3 US2 steps 1–9 (focus trap, Escape, scroll lock, focus return, failure path, in-flight Escape); confirm `grep -rn 'confirm(' frontend/src --include='*.tsx'` is empty

**Checkpoint**: US1 + US2 shippable.

---

## Phase 5: User Story 3 — Keyboard-navigable profile tabs that keep their state (Priority: P3)

**Goal**: Arrow-key tabs with `aria-selected`, both panels stay mounted, guide fetch still deferred (FR-007, FR-008).

**Independent Test**: quickstart §3 US3 steps 1–3.

- [x] T033 [US3] In `frontend/src/pages/ProfilePage.tsx` replace the `nav role="tablist"` buttons with `Tabs value={tab} onValueChange={(v) => setTab(v as Tab)}`, `TabsList aria-label="Profile sections"`, two `TabsTrigger`s ("Characters", "Class Guides"), and two `TabsContent` panels with `forceMount` and `className="data-[state=inactive]:hidden"`; keep `ClassGuidesTab active={tab === "guides"}` (research R6)
- [x] T034 [US3] Delete `.profile-tabs`, `.profile-tab`, `.profile-tab:hover`, `.profile-tab.is-active` from `frontend/src/styles.css`; keep `.profile-tabpanel` and adjust its top-left radius only if the new `TabsList` no longer sits flush against it
- [x] T035 [US3] Run `npx tsc -b && npm run build` from `frontend/`; walk quickstart §3 US3 steps 1–3 (arrow keys, typed text survives switching, no `/api/guides` request before first selection)

**Checkpoint**: US1–US3 shippable.

---

## Phase 6: User Story 4 — Admin tables and status messaging (Priority: P4)

**Goal**: Shared tables, badges and alert strips on the admin page; the same badge/alert treatment for guide status pills and the header's fallback warning (FR-009, FR-010).

**Independent Test**: quickstart §3 US4 steps 1–4.

- [x] T036 [US4] In `frontend/src/pages/AdminUsersPage.tsx` convert both tables to `Table`/`TableHeader`/`TableRow`/`TableHead`/`TableBody`/`TableCell` inside an `overflow-x-auto` wrapper, render invitation and user status cells as `StatusBadge tone={INVITE_TONE[s] ?? "neutral"}` / `USER_TONE[s] ?? "neutral"`, and replace the error paragraph with `StatusAlert tone="error" onDismiss={() => setError(null)}` at the top of the content
- [x] T037 [P] [US4] In `frontend/src/components/profile/CharactersTab.tsx` replace the local `STATUS_LABEL` and `StatusBadge` with imports of `StatusBadge`, `GUIDE_TONE`, `GUIDE_LABEL_SHORT` from `../StatusBadge`, and `.profile-error` div with `StatusAlert tone="error"`
- [x] T038 [P] [US4] In `frontend/src/components/profile/ClassGuidesTab.tsx` replace `CHIP_LABEL` and the `guide-badge` spans with `StatusBadge` using `GUIDE_TONE`/`GUIDE_LABEL_LIBRARY`, the "May be out of date" span with `StatusBadge tone="warn"` keeping its freshness `title`, and the `.profile-error`/`.profile-notice` divs with `StatusAlert tone="error"` / `tone="notice"`
- [x] T039 [P] [US4] In `frontend/src/components/ModelSelect.tsx` replace the `.model-degraded` span with `StatusBadge tone="warn" title="Model discovery could not reach Vertex; showing a fallback list."` and the text "fallback list"
- [x] T040 [US4] Delete `.guide-badge`, `.guide-pending`, `.guide-ready`, `.guide-failed`, `.guide-stale`, `.guide-none`, `.profile-error`, `.profile-notice`, `.model-degraded` from `frontend/src/styles.css` (research R13)
- [x] T041 [US4] Run `npx tsc -b && npm run build` from `frontend/`; walk quickstart §3 US4 steps 1–4 (tables, badge tones, dismissible alert, narrow viewport, degraded model badge tooltip)

**Checkpoint**: all four stories shippable.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Audits, size gate, docs, graph hygiene.

- [x] T042 Run the native-control audit from contract §5 (`grep -rnE '<(button|input|select|textarea)\b|confirm\(' frontend/src --include='*.tsx' --exclude-dir=ui`); fix any match not on the allowlist, then paste the final match list into the `## Measurements` section of `specs/010-shadcn-ui-adoption/quickstart.md`
- [x] T043 [P] Run the palette and icon audits (`grep -rnE 'neutral-|indigo-|red-[0-9]' frontend/src`, `grep -rn "lucide-react" frontend/src`); both must be empty
- [x] T044 [P] Size gate: `npm run build` from `frontend/`, record AFTER_GZ via `gzip -c dist/assets/index-*.js | wc -c` next to BEFORE_GZ in `specs/010-shadcn-ui-adoption/quickstart.md` and confirm AFTER_GZ ≤ 1.10 × BEFORE_GZ (SC-006)
- [x] T045 [P] Run the backend suite `uv run pytest -q` from the repo root to confirm nothing outside `frontend/` changed behaviour
- [x] T046 [P] Add a short "Feature 010 — shared UI components" section to `README.md` (how to add another shadcn component, the three recorded local edits in `frontend/src/components/ui/`, the token block in `frontend/src/index.css`, the audit greps)
- [x] T047 (sweep found only pre-existing orphans: boot-step-* state classes built from template strings, chat-main-area, font-display, scroll-viewport, streaming-body, tool-activity, tool-chip — none introduced here, nothing removed) Final sweep of `frontend/src/styles.css` for selectors no longer referenced by any TSX (`for s in $(grep -oE '^\.[a-zA-Z0-9_-]+' frontend/src/styles.css | sort -u); do grep -rq "${s#.}" frontend/src --include='*.tsx' || echo "$s"; done`) and remove orphans introduced by this feature only
- [x] T048 (detect_changes clean; committed as c69b66e docs(010) + 4982bae feat(010); index refreshed) Run `detect_changes({scope: "all"})`, commit per story or as one feature commit, then `node .gitnexus/run.cjs analyze --index-only`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: T001 first (baseline before anything changes); T002 → T003 → {T004, T005, T006 in parallel} → T007 → T008
- **Foundational (Phase 2)**: after Phase 1; T009–T011 in parallel; T012 after
- **US1 (Phase 3)**: after Phase 2; T013–T016, T018–T020, T022–T024 are independent files; T017 and T021 are single-file; T025 after all component swaps in the phase; T026 last
- **US2 (Phase 4)**: after US1 (reuses the converted buttons); T027 then T028–T030 in parallel; T031 → T032
- **US3 (Phase 5)**: after US1 (T024 touched ProfilePage); independent of US2
- **US4 (Phase 6)**: after US1 and US2 (edits the same three files after their confirm/dialog changes); T036 then T037–T039 in parallel; T040 → T041
- **Polish (Phase 7)**: after all stories

### Same-file sequencing (do not parallelise across phases)

- `AdminUsersPage.tsx`: T017 → T028 → T036
- `CharactersTab.tsx`: T022 → T030 → T037
- `ClassGuidesTab.tsx`: T023 → T027 → T038
- `Sidebar.tsx`: T020 → T029
- `ModelSelect.tsx`: T018 → T039
- `ProfilePage.tsx`: T024 → T033
- `styles.css`: T025 → T031 → T034 → T040 → T047

### Parallel Opportunities

- Phase 1: T004, T005, T006 (three different generated files)
- Phase 2: T009, T010, T011
- Phase 3: T013, T014, T015, T016, T018, T019, T020, T022, T023, T024 (ten different files)
- Phase 4: T028, T029, T030
- Phase 6: T037, T038, T039
- Phase 7: T043, T044, T045, T046

---

## Parallel Example: User Story 1

```bash
# After T012, launch the independent page/component conversions together:
Task: "Rebuild frontend/src/pages/LoginPage.tsx with Field/Input/Button + theme tokens"
Task: "Rebuild frontend/src/pages/AcceptInvitePage.tsx the same way"
Task: "Rebuild frontend/src/pages/ResetPasswordPage.tsx the same way"
Task: "Re-theme frontend/src/pages/ForbiddenPage.tsx and frontend/src/auth/RequireAuth.tsx"
Task: "NativeSelect in frontend/src/components/ModelSelect.tsx"
Task: "Textarea + Button in frontend/src/components/Composer.tsx"
Task: "Buttons in frontend/src/components/Sidebar.tsx"
Task: "Inputs/selects/buttons in frontend/src/components/profile/CharactersTab.tsx"
Task: "Buttons in frontend/src/components/profile/ClassGuidesTab.tsx"
Task: "Back link Button in frontend/src/pages/ProfilePage.tsx"
# Then T017 (AdminUsersPage), T021 (App.tsx header), T025 (dead CSS), T026 (verify).
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 (install, tokens) and Phase 2 (wrappers) — about a dozen small tasks.
2. Phase 3: every field and button swapped, palette unified.
3. **STOP and VALIDATE** with quickstart §3 US1 and the palette grep; this alone removes most duplicated styling and is independently shippable.

### Incremental Delivery

1. US1 → shared look everywhere (MVP).
2. US2 → real modal + four confirmations; `window.confirm` gone.
3. US3 → keyboard tabs.
4. US4 → tables, badges, alerts.
5. Polish → audits, size gate, docs, commit.

Each story ends with `npx tsc -b`, `npm run build` and its quickstart section; commit at each checkpoint after `detect_changes`.

---

## Notes

- Generated files under `frontend/src/components/ui/` are edited only in T003–T006 (recorded in contract §1); everything else imports them.
- Keep the accessible-name register (contract §4) open while doing T017–T024, T027–T030 and T036–T039; every `title`/`aria-label` listed there must still exist afterwards (FR-013).
- The spec's FR-015 unchanged list is a hard boundary: if a task seems to need a change there, stop and re-read the spec.
