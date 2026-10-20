"""Colour tokens of the app's "Tavern Hearth" theme, as used by the PDF report.

The chat defines them as ``oklch()`` in ``frontend/src/index.css``; they are converted
to hex once here so the PDF renderer doesn't depend on CSS Color 4 support. Keep them in
step with the frontend tokens (owner's choice 2026-10-20: the PDF looks like the chat).
"""

from __future__ import annotations

OAK = "#110904"  # --background        oklch(0.15 0.02 60): the page
CARD = "#23140a"  # --card             oklch(0.21 0.03 55): agent bubble, cards, tables
RAISED = "#2a1c11"  # --surface-muted  oklch(0.24 0.03 58): table header row
ZEBRA = "#2c1d14"  # 4% white over CARD: even table rows
BORDER = "#543a1e"  # --border-token  oklch(0.52 0.08 70 / 0.5) over CARD
CREAM = "#ece4d2"  # --foreground     oklch(0.92 0.025 85): body text
TAN = "#af9b80"  # --muted            oklch(0.7 0.045 75): secondary text
GOLD = "#e8a127"  # --primary         oklch(0.76 0.15 75): headings, accents
GLOW = "#febf32"  # --glow            oklch(0.84 0.16 82): title, links, KPI values
ON_GOLD = "#190c03"  # --primary-foreground: text on a gold fill
EMBER = "#ed4a49"  # --destructive    oklch(0.64 0.2 25): warnings
GREEN = "#3fc168"  # --success        oklch(0.72 0.17 150)
BLUE = "#6fa7ee"  # oklch(0.72 0.12 255): a cool contrast series for charts
