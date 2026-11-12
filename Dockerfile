# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Stage 1: build Python dependencies in an isolated layer
# ---------------------------------------------------------------------------
FROM python:3.13-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r requirements.txt

# ---------------------------------------------------------------------------
# Stage 2: lean runtime image
# ---------------------------------------------------------------------------
FROM python:3.13-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    STORAGE_PATH=/app/storage \
    HOST=0.0.0.0 \
    PORT=8000

WORKDIR /app

# Runtime OS packages: OCR (eng + Amharic), image libs, curl for healthchecks
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-amh \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN groupadd --system --gid 1000 appuser \
    && useradd --system --uid 1000 --gid appuser --create-home --shell /usr/sbin/nologin appuser

COPY --from=builder /opt/venv /opt/venv

COPY --chown=appuser:appuser alembic.ini .
COPY --chown=appuser:appuser alembic ./alembic
COPY --chown=appuser:appuser app ./app
COPY --chown=appuser:appuser main.py .
COPY --chown=appuser:appuser docker/entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh \
    && mkdir -p /app/storage/books /app/storage/raw /app/storage/extracted \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/health" || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
