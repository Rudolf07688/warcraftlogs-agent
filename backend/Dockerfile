# Backend: FastAPI + ADK agent (Python 3.14)
FROM python:3.14-slim

# Runtime libs for PDF reports on the slim base: Pango/HarfBuzz for WeasyPrint,
# freetype/png for matplotlib charts and maths. Fonts: DejaVu (Latin, Greek,
# Cyrillic), Noto CJK (KR/TW/CN character and realm names) and Noto Color Emoji,
# so no glyph renders as a box.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 \
        libfreetype6 libpng16-16 \
        fonts-dejavu-core fonts-noto-cjk fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

# uv for fast, locked installs
RUN pip install --no-cache-dir uv

WORKDIR /app

# Install deps first (better layer caching)
COPY pyproject.toml uv.lock README.md ./
# Source needed for the editable package build
COPY wcl_agent ./wcl_agent
COPY backend ./backend
RUN uv sync --frozen --no-dev

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
