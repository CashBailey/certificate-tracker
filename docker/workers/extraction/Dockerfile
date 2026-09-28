# ==============================================================================
# Extraction Worker
# ==============================================================================
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app:/app/src

# Install dependencies for PDF/document processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    libmagic1 \
    poppler-utils \
    curl \
    gcc \
    python3-opencv \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 1000 appgroup \
    && useradd --uid 1000 --gid appgroup --shell /bin/bash --create-home appuser

WORKDIR /app

COPY BackgroundProcessingInstances/ExtractionWorker/requirements.txt .
COPY BackgroundProcessingInstances/ExtractionWorker/requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock

# Copy shared code from ApiServer
COPY --chown=appuser:appgroup CoreInstances/ApiServer/src/shared ./shared

# Copy templates
COPY --chown=appuser:appgroup CoreInstances/ApiServer/templates ./templates

# Copy worker source
COPY --chown=appuser:appgroup BackgroundProcessingInstances/ExtractionWorker/src ./src

RUN mkdir -p /tmp/worker && chown -R appuser:appgroup /tmp/worker

USER appuser

ENV TEMPLATES_DIR=/app/templates

CMD ["python", "-m", "src.worker"]
