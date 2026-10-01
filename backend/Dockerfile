# Backend: FastAPI + ADK agent (Python 3.14)
FROM python:3.14-slim

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
