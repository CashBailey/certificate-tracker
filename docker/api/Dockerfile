# ==============================================================================
# FastAPI API Server - Production Multi-Stage Build
# ==============================================================================

# Stage 1: Builder
FROM python:3.12-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY CoreInstances/ApiServer/requirements.txt .
COPY CoreInstances/ApiServer/requirements.lock .
RUN pip install --no-cache-dir --prefix=/install -r requirements.lock

# Stage 2: Runtime
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 appgroup \
    && useradd --uid 1000 --gid appgroup --shell /bin/bash --create-home appuser

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY --chown=appuser:appgroup CoreInstances/ApiServer/src ./src

USER appuser

EXPOSE 8000

# Production: Use gunicorn with uvicorn workers
CMD ["gunicorn", "src.main:app", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000", "--forwarded-allow-ips", "*", "--access-logfile", "-", "--error-logfile", "-"]
