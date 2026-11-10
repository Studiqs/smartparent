# ==============================================================================
# STUDIQS® SmartParent™ v6.3 - Production Multi-Stage Dockerfile
# Optimized for High Concurrency, Fast Cold Starts & Enterprise Security
# ==============================================================================

# ------------------------------------------------------------------------------
# Stage 1: Dependency Builder
# ------------------------------------------------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies for C-extensions (psycopg2, cryptography, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Build wheels in an isolated directory
RUN pip install --no-cache-dir --upgrade pip && \
    pip wheel --no-cache-dir --no-deps --wheel-dir /build/wheels -r requirements.txt


# ------------------------------------------------------------------------------
# Stage 2: Final Minimal Runtime Image
# ------------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

# Prevent Python from writing .pyc files & enable unbuffered standard streams
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# Install minimal runtime dependencies:
# - libpq5: PostgreSQL database connectivity
# - curl: Container health checks
# - tesseract-ocr, tesseract-ocr-eng: Section 3 OCR Question Paper & Marks extraction
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    tesseract-ocr \
    tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

# Copy pre-compiled wheels from builder stage & install
COPY --from=builder /build/wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt && \
    rm -rf /wheels requirements.txt

# Create non-privileged system user and group for security compliance (CIS benchmark)
RUN groupadd --system --gid 1001 appgroup && \
    useradd --system --uid 1001 --gid appgroup --shell /bin/false appuser

# Create persistent storage directories with appropriate permissions
RUN mkdir -p /app/uploads/cases \
             /app/uploads/evidence \
             /app/uploads/reports \
             /app/uploads/temp \
             /app/storage/reports \
             /app/data \
             /app/static \
    && chown -R appuser:appgroup /app

# Copy application source code, taxonomy models, static PWA assets, and entrypoint
COPY --chown=appuser:appgroup alembic.ini /app/
COPY --chown=appuser:appgroup alembic /app/alembic/
COPY --chown=appuser:appgroup src /app/src/
COPY --chown=appuser:appgroup data /app/data/
COPY --chown=appuser:appgroup static /app/static/
COPY --chown=appuser:appgroup scripts /app/scripts/
COPY --chown=appuser:appgroup studiqs_production_bundle /app/studiqs_production_bundle/
COPY --chown=appuser:appgroup docker-entrypoint.sh /app/docker-entrypoint.sh

# Make entrypoint script executable
RUN chmod +x /app/docker-entrypoint.sh

# Switch to non-privileged user
USER appuser

# Expose standard FastAPI ASGI port
EXPOSE 8000

# Container liveness & readiness healthcheck probe
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Configure automated migration and initialization entrypoint
ENTRYPOINT ["/app/docker-entrypoint.sh"]

# Default launch command: 4-worker Uvicorn ASGI cluster
CMD ["uvicorn", "src.smartparent.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--access-log"]
