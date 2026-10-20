# Quickstart: Proper PDF Generation

How to check the feature end to end. Commands run from the repo root.

## 0. Prerequisites (local, outside Docker)

WeasyPrint needs Pango and HarfBuzz from the system. The Ubuntu dev host already has them. On a fresh Debian or Ubuntu machine, run:

```bash
sudo apt-get install -y libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 \
  fonts-dejavu-core fonts-noto-cjk fonts-noto-color-emoji
uv sync --extra test
```

## 1. Automated tests (no network)

```bash
uv run --extra test pytest -q backend/tests/test_pdf_report.py backend/tests/test_charts.py \
  backend/tests/test_reports.py backend/tests/test_message_report.py
uv run --extra test pytest -q          # full suite
```

What they cover:

- **Fixture corpus** (`backend/tests/fixtures/findings/*.md`, 20 or more documents): each one renders to `%PDF`. The extracted text contains none of `**`, `__`, `##`, `|---`, `` ` ``, `$$`, `](`, `<br`, `<b>`, `&lt;` or `&gt;`. Every Markdown link appears as a URI annotation. Page 1 shows "Page 1 of N" (SC-001 to SC-003).
- **`findings_to_html` unit tests**:
  - nested lists three levels deep;
  - task lists;
  - table alignment, plus ragged rows padded or trimmed;
  - "$5 and $10" stays as text, and `$a^2$` becomes a maths image;
  - `$$\badcommand{x}$$` falls back to plain italics with no `\`;
  - `<script>` is dropped with its content;
  - `<br>` and `<b>` are honoured;
  - a remote `img` turns into alt text.
- **Fetch lockdown**: a document with `<img src="file:///etc/hostname">` and `<img src="http://127.0.0.1:9/x.png">` renders, and neither file contents nor a connection attempt appear (monkeypatched socket or open).
- **Charts**: `chart_spec_to_svg` returns SVG for every `CHART_KINDS` value. Series get different line styles and markers. `graph_to_svg` returns `None` for a payload with nothing to plot.
- **Endpoints**: unchanged `%PDF` output, file names, 404s and fail-closed 500s. A partial message gives a PDF containing "partial answer".

## 2. Live check (Docker)

```bash
docker compose up --build backend frontend
```

1. Open a conversation with a raid analysis that includes at least one fetched graph or analyst chart and a table. Click **Download PDF** on the conversation, then on a single answer.
2. Expect a backend log line like:
   ```text
   INFO: backend.app.services.pdf_report: pdf rendered scope=conversation pages=4 figures=2 ms=380
   ```
3. Check the conversation PDF:
   - the title block shows the title, "Whole conversation" and the UTC timestamp;
   - pages 2 and later have the running title header, and every page has "Page X of Y";
   - no `**`, `#`, `|`, `$$` or tags anywhere; links open Warcraft Logs;
   - a table that runs past a page break repeats its header, and no row is split;
   - no heading is left alone at the bottom of a page;
   - the Charts section starts on a new page with "Figure 1 — …" captions, and the charts stay sharp at 200% zoom.
4. Check the single-answer PDF: the title block shows "Single answer" and the question. Only that answer's charts appear.
5. **Black-and-white print** (SC-007): print to PDF in greyscale, or print on paper. Chart series and table banding must still be distinguishable.
6. **Old vs new** (SC-006): generate the same conversation's report on `main` and on this branch. The owner judges the new one shareable.

## 3. Image check

```bash
docker compose exec backend python -c "import weasyprint; print(weasyprint.__version__)"
docker compose exec backend fc-list | grep -E "DejaVu Sans|Noto Sans CJK|Noto Color Emoji" | head
docker image ls | grep backend     # expect roughly +120 MB vs main (R7)
```
