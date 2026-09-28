# ==============================================================================
# Scheduler & Notification Worker
# ==============================================================================
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    curl \
    gcc \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 1000 appgroup \
    && useradd --uid 1000 --gid appgroup --shell /bin/bash --create-home appuser

WORKDIR /app

COPY BackgroundProcessingInstances/SchedulerNotificationWorker/requirements.txt .
COPY BackgroundProcessingInstances/SchedulerNotificationWorker/requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock

# Copy shared code from ApiServer
COPY --chown=appuser:appgroup CoreInstances/ApiServer/src/shared ./shared

# Copy worker source
COPY --chown=appuser:appgroup BackgroundProcessingInstances/SchedulerNotificationWorker/src ./src

USER appuser

CMD ["python", "-m", "src.scheduler"]
