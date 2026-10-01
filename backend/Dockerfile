# Backend: FastAPI + ADK agent (Python 3.14)
FROM python:3.14-slim

# Runtime libs for matplotlib/reportlab chart rendering on the slim base
# (fonts + freetype/png). manylinux wheels mostly bundle these, but installing
# them keeps PDF/graph rendering robust across base-image changes.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libfreetype6 libpng16-16 fonts-dejavu-core \
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
