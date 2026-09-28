# ==============================================================================
# OCR Engine Worker - Tesseract-based
# ==============================================================================
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

# Install Tesseract OCR and language packs
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-spa \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd --gid 1000 appgroup \
    && useradd --uid 1000 --gid appgroup --shell /bin/bash --create-home appuser

WORKDIR /app

# Install Python dependencies
COPY BackgroundProcessingInstances/OcrEngine/requirements.txt .
COPY BackgroundProcessingInstances/OcrEngine/requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock

# Copy shared code (minimal subset for OCR - models only)
COPY --chown=appuser:appgroup CoreInstances/ApiServer/src/shared ./shared

# Copy application
COPY --chown=appuser:appgroup BackgroundProcessingInstances/OcrEngine/src ./src

USER appuser

CMD ["python", "-m", "src.worker"]
