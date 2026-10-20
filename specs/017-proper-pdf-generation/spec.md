# Feature Specification: Proper PDF Generation

**Feature Branch**: `017-proper-pdf-generation`

**Created**: 2026-10-19

**Status**: Draft

**Input**: User description: "Ok check `99, Proper PDF generation` and let's spec that one out" — Shortcut epic 99 ("PDF reports still look terrible with some html/markdown markers visible — need to use proper pdf generation"), stories 108 (adopt a real document renderer), 109 (clean Markdown conversion, no raw `**`, `#` or HTML tags), 110 (charts, headers, page breaks and themed styling).

## Context

Players download two kinds of PDF report today: a whole-conversation report and a per-message report. Since feature 007, both first rewrite the chat into a findings document (summary, key findings, results by encounter or player, recommendations) and then turn that document into a PDF. The findings step works. The output step does not: it only understands a narrow subset of the formatting the analyst writes, so stray formatting markers, raw tags and broken layouts end up on the page. This has been reported repeatedly (todo Phases 1, 3 and 5) and is still open.

This feature replaces the way reports are laid out and drawn. It does not change *what* a report says: the findings content, the two report scopes, the download buttons and the in-progress indicator stay as they are.

## Clarifications

### Session 2026-10-19

- Q: Where do charts go in the report? → A: In a separate "Charts" section after the findings, each chart numbered and captioned (the current structure, made to look good). Charts are not placed next to individual findings.
- Q: What should the report look like? → A: A clean, neutral analyst-report look with small tavern-colour accents (headings, table header rows, rules). There is one style only, with no theme option and no parchment or fantasy styling.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Clean, readable report text (Priority: P1)

A player who has finished analysing a raid downloads the conversation report. Every piece of formatting the analyst used comes out as real formatting: headings look like headings, bold is bold, lists (including nested ones) are indented lists, tables are tables, links are clickable, code and equations are set apart. No formatting syntax or markup is visible anywhere in the document.

**Why this priority**: This is the defect named in the ticket. A report full of `**`, `#`, `|---|` and `<br>` is unusable, whatever else is fixed.

**Independent Test**: Download a report from a conversation whose findings use every supported formatting element (see FR-002) and check the PDF: no syntax characters or tags are visible, and each element appears in its formatted form.

**Acceptance Scenarios**:

1. **Given** findings that contain headings, bold, italics, bullet and numbered lists, and a nested list, **When** the player downloads the report, **Then** each appears formatted, with nested items indented under their parent and no `#`, `*`, `-` or `1.` markers left over from the source formatting.
2. **Given** findings that contain a table with formatting inside its cells (bold names, links), **When** the report is generated, **Then** the table appears with a distinct header row and the cell contents are formatted, not shown as raw syntax.
3. **Given** findings that contain links to Warcraft Logs pages, **When** the player opens the PDF, **Then** the link text is shown and clicking it opens the right page.
4. **Given** findings that contain inline and block equations, **When** the report is generated, **Then** the equations appear typeset, and an equation that cannot be typeset appears as readable plain text rather than raw source.
5. **Given** findings that contain stray markup (for example `<br>`, `<b>` or an HTML comment), **When** the report is generated, **Then** none of that markup is visible, and harmless formatting tags are honoured or silently dropped.
6. **Given** prose that uses a dollar sign as currency ("costs $5 and $10"), **When** the report is generated, **Then** the text appears as written and is not treated as an equation.

---

### User Story 2 - A report that looks like a real document (Priority: P2)

The player opens the PDF, or prints it, and it reads like a professional analysis document: a clear title block, consistent typography, a running header and page numbers, sensible page breaks, and a clean neutral style with small accents in the app's tavern colours.

**Why this priority**: Clean text (P1) makes the report usable. Layout and styling make it something a player would share with their guild or raid lead. That value comes second.

**Independent Test**: Generate a report long enough to span several pages, with a wide table and several sections. Check it on screen and printed in black and white on A4.

**Acceptance Scenarios**:

1. **Given** any report, **When** it is opened, **Then** the first page shows a title block with the report title (the raid label or conversation title), the scope (whole conversation or single answer), the generation date and time, and, for a single-answer report, the question that prompted the answer.
2. **Given** a report that spans several pages, **When** it is viewed, **Then** every page after the first shows a running header with the report title and a footer with "page X of Y".
3. **Given** a section heading that would land at the bottom of a page, **When** the report is laid out, **Then** the heading moves to the next page together with its first lines of content.
4. **Given** a table that spans a page break, **When** it is laid out, **Then** its header row repeats on the new page and no row is split across pages.
5. **Given** a table with more columns or longer cell text than the page width allows, **When** it is laid out, **Then** it fits within the page margins (text wraps, columns size to their content) and nothing is cut off.
6. **Given** the report is printed in black and white, **When** it is read, **Then** all text, table banding and chart series stay distinguishable.

---

### User Story 3 - Charts that belong in the report (Priority: P3)

Charts from the conversation (Warcraft Logs graphs the analyst pulled and charts the analyst produced) appear in the PDF as sharp, captioned figures with labelled axes and a legend, styled to match the rest of the document.

**Why this priority**: Charts are already included today, just unstyled and dumped at the end. Improving them matters, but less than readable text and layout.

**Independent Test**: Download a report from a conversation with at least one captured graph and one analyst-produced chart. Check that each is crisp when zoomed to 200%, captioned, labelled and placed in the Charts section after the findings (FR-012).

**Acceptance Scenarios**:

1. **Given** a conversation with captured graphs and analyst-produced charts, **When** the report is generated, **Then** each chart appears as a figure with a numbered caption (for example "Figure 2 — Damage done, Fyrakk"), axis labels, a legend when there is more than one series, and a source link when one is known.
2. **Given** a chart, **When** the PDF is zoomed to 200%, **Then** its lines and text stay sharp.
3. **Given** a chart whose data cannot be drawn, **When** the report is generated, **Then** that chart is left out with a short "chart unavailable" note in its place, and the rest of the report is produced normally.
4. **Given** a single-answer report, **When** it is generated, **Then** only the charts tied to that answer are included (unchanged from today).

---

### Edge Cases

- **Very long reports** (the findings rewrite is already capped in length): the report is produced in full with correct page numbering and no truncated content.
- **Long unbroken text** (report codes, URLs, ability names with no spaces) wraps within the margins and never runs off the page.
- **Names with non-English characters** (for example "Ælfwyn", "Kâzzak", or Cyrillic and other non-Latin realm or character names) display correctly. Missing characters must not show as boxes or question marks.
- **Emoji or symbols** the analyst uses appear as written, or are left out silently. They never appear as broken boxes.
- **An empty or "no substantive findings" document** still produces a valid, styled one-to-two-page report.
- **A malformed table** (rows with more or fewer cells than the header) is padded or trimmed to the header width, not dropped and not shown as raw text.
- **Code blocks** (if the analyst writes one despite instructions) appear in a fixed-width, visually set-apart block, and long lines wrap.
- **An image link in the findings** that points to a remote address is not fetched while the PDF is built. It is shown as its alt text or link instead (in line with the open SEC-003 concern about remote images).
- **Generation failure** of any kind still fails closed: the player gets a clear error and never a partial or corrupt file (unchanged from feature 007).
- **A partial (interrupted) answer**, for the per-message report, is marked as partial in the document.

## Requirements *(mandatory)*

### Functional Requirements

**Text and formatting**

- **FR-001**: The system MUST produce reports in which no formatting syntax (for example `**`, `__`, `#`, `|---|`, backticks, `$$`) or markup tags are visible in the rendered text, except where the analyst wrote those characters as literal content (for example inside a code block).
- **FR-002**: The system MUST render at least these elements as formatted output: headings (levels 1 to 4), paragraphs, bold, italic, bold-italic, strikethrough, inline code, code blocks, bullet lists, numbered lists (keeping the authored numbering), nested lists at least three levels deep, task-list checkboxes, block quotes, horizontal rules, tables (including column alignment and formatting inside cells), links, inline equations and block equations.
- **FR-003**: Links MUST be clickable in the PDF and MUST show their link text, not the raw address syntax.
- **FR-004**: Equations MUST be typeset. Any equation that cannot be typeset MUST fall back to a readable plain-text form with the equation syntax removed.
- **FR-005**: Dollar signs used as currency or in ordinary prose MUST NOT be interpreted as equations (keeping the current behaviour).
- **FR-006**: Raw markup in the findings MUST NOT appear in the output. Basic formatting tags MAY be honoured. Anything else, including scripts and remote resources, MUST be dropped or neutralised and MUST NOT be fetched or executed while the report is built.
- **FR-007**: Text in Latin-extended, Cyrillic and other common non-Latin scripts used for WoW character and realm names MUST display correctly.

**Layout and styling**

- **FR-008**: Every report MUST start with a title block showing the title, the report scope, the generation date and time (with time zone) and, for a single-answer report, the originating question.
- **FR-009**: Every page MUST show a page number in the form "X of Y". Pages after the first MUST show a running header with the report title.
- **FR-010**: Headings MUST NOT be left alone at the bottom of a page. Table rows MUST NOT split across pages, and table header rows MUST repeat after a page break.
- **FR-011**: All content, including wide tables and long unbroken text, MUST stay within the page margins on A4 and US Letter paper.
- **FR-012**: Charts MUST be placed in a separate "Charts" section that follows the findings and starts on a new page. Charts MUST be numbered in order (Figure 1, Figure 2, …), with captured Warcraft Logs graphs first, then analyst-produced charts. When a report has no charts, the section MUST be left out.
- **FR-013**: The report MUST use a single, consistent visual style for typography, colours, tables, block quotes, code and charts. That style MUST be a clean, neutral analyst-report look: a readable serif or sans-serif body font, and the app's tavern colours used only as accents (headings, table header rows, rules and the title block). It MUST NOT use parchment textures, background tints or decorative fantasy fonts. There is exactly one style, so the player has no style choice. It MUST stay legible when printed in black and white.
- **FR-014**: Report pages MUST have a white or near-white background, so printing does not use excessive ink.

**Charts**

- **FR-015**: Every chart MUST appear as a vector figure, or at a resolution that stays sharp at 200% zoom. It MUST have a numbered caption, axis labels when the chart has axes, a legend when it has more than one series, and a source link when the chart carries one.
- **FR-016**: A chart that cannot be drawn MUST be replaced by a short "chart unavailable" note and MUST NOT stop the report from being generated.
- **FR-017**: Chart series MUST be distinguishable without colour (for example by line style or marker) so that black-and-white printing stays meaningful.

**Behaviour preserved from earlier features**

- **FR-018**: Both report scopes (whole conversation and single answer), their download entry points and file names, and the in-progress indicator from story 151 MUST keep working without change for the player.
- **FR-019**: Report content MUST still come from the existing findings rewrite (feature 007). This feature changes only how that content is laid out and drawn.
- **FR-020**: Any failure while generating a report MUST still give the player a clear error with no file, never a partial or corrupt PDF.
- **FR-021**: Single-answer reports MUST still include only that answer, its originating question and its own charts.
- **FR-022**: Report generation MUST NOT block other users' requests while it runs.

### Key Entities

- **Findings document**: The structured analysis text produced by the existing findings rewrite (summary, key findings, results, recommendations), using headings, lists, tables, links and equations. This is the report body.
- **Report**: The downloadable document. Attributes: title, scope (conversation or single answer), originating question (single answer only), generation timestamp, body, figures.
- **Figure**: A chart included in the report. Comes from a captured Warcraft Logs graph or an analyst-produced chart. Attributes: number, caption, source link (optional), the answer it belongs to.
- **Report style**: The single visual definition (fonts, colours, spacing, table/quote/code/chart styling, page header and footer) applied to every report.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Across a test set of at least 20 real findings documents covering every element in FR-002, zero formatting markers or markup tags are visible in the generated reports.
- **SC-002**: 100% of the elements in FR-002 appear formatted when they occur in the test set.
- **SC-003**: Every link in a generated report opens its target when clicked.
- **SC-004**: In a report of at least 5 pages with at least 2 tables that span a page break, no content is cut off at a margin, no heading is left alone at the bottom of a page, and every continued table repeats its header.
- **SC-005**: A typical report (one findings document plus up to 5 charts) is ready to download in no more time than today, and in under 30 seconds end to end, including the findings rewrite.
- **SC-006**: When asked to compare an old and a new report of the same conversation, the project owner prefers the new one, and judges it "something I'd share with my raid lead".
- **SC-007**: A report printed in black and white has every chart series and table row band distinguishable.
- **SC-008**: Error outcomes are unchanged: a forced generation failure gives a clear error and no file in 100% of attempts.

## Assumptions

- The findings rewrite (feature 007) and its output format stay as they are. Its prompt already limits the analyst to headings, lists, tables and equations, but the renderer must also handle anything outside that list gracefully (FR-002, FR-006), because the model does not always follow instructions.
- Reports stay generated on the server and downloaded as a file. Printing from the browser is not the delivery path.
- A4 is the default page size. US Letter must also lay out correctly, but choosing a page size in the UI is out of scope.
- Reports are generated on demand and not stored. Caching or a report history is out of scope.
- Interactive charts (hover, zoom) are out of scope. PDF charts are static figures.
- A light, print-friendly page background is acceptable even if the app's on-screen theme is dark.
- Embedding fonts that cover the needed character sets is acceptable, even though it makes the PDF file somewhat larger. Reports are expected to stay well under 5 MB.
- The extra runtime a better renderer may need inside the backend container is acceptable, provided start-up and request time stay within SC-005.
- Shortcut stories 108, 109 and 110 map to user stories 1 and 2 (108, 109) and user story 3 (110). No other tickets are in scope.
