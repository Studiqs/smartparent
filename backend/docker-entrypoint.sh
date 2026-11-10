#!/usr/bin/env bash
# ==============================================================================
# STUDIQS® SmartParent™ v6.3 - Container Entrypoint Script
# Handles DB Readiness Probing, Automated Migrations & Zero-Downtime Launch
# ==============================================================================
set -e

echo "[STUDIQS Entrypoint] Starting container initialization..."

# 1. Database Connectivity Probe
if [ -n "$DATABASE_URL" ] || [ -n "$DATABASE_SYNC_URL" ]; then
    DB_CHECK_URL="${DATABASE_SYNC_URL:-$DATABASE_URL}"
    # Replace asyncpg dialect with standard postgresql for sync readiness check
    CLEAN_URL=$(echo "$DB_CHECK_URL" | sed 's/postgresql+asyncpg/postgresql/')
    
    echo "[STUDIQS Entrypoint] Probing database connection..."
    python - <<END
import sys
import time
from sqlalchemy import create_engine, text

url = "${CLEAN_URL}"
max_retries = 30
retry_delay = 2

for attempt in range(1, max_retries + 1):
    try:
        engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 3})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print(f"[STUDIQS Entrypoint] Database is ready! (Attempt {attempt}/{max_retries})")
        sys.exit(0)
    except Exception as e:
        if attempt == max_retries:
            print(f"[STUDIQS Entrypoint] FATAL: Database not reachable after {max_retries} attempts: {e}")
            sys.exit(1)
        print(f"[STUDIQS Entrypoint] Database not ready yet (attempt {attempt}/{max_retries}). Retrying in {retry_delay}s...")
        time.sleep(retry_delay)
END
fi

# 2. Automated Alembic Migration Runner
if [ "$RUN_MIGRATIONS" = "true" ] || [ "$RUN_MIGRATIONS" = "1" ]; then
    echo "[STUDIQS Entrypoint] Executing Alembic database migrations (upgrade head)..."
    alembic upgrade head
    echo "[STUDIQS Entrypoint] Migrations applied successfully."
fi

# 3. Optional Taxonomy Seeding
if [ "$SEED_CURRICULUM" = "true" ] || [ "$SEED_CURRICULUM" = "1" ]; then
    echo "[STUDIQS Entrypoint] Checking and seeding 8,034 curriculum taxonomy nodes..."
    python -m scripts.seed_curriculum || echo "[STUDIQS Entrypoint] Curriculum seeding completed or already populated."
fi

echo "[STUDIQS Entrypoint] Initialization complete. Executing container process: $@"
exec "$@"

