# STUDIQS® SmartParent™ Backend (v6.3 Production Release)

> High-Concurrency B2C Family Intelligence, Learning Diagnostics, Razorpay Invoicing & Expert Marketplace Platform.

[![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115.0-009688.svg)](https://fastapi.tiangolo.com/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0.35-red.svg)](https://www.sqlalchemy.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791.svg)](https://www.postgresql.org/)
[![Celery](https://img.shields.io/badge/Celery-5.6.2-brightgreen.svg)](https://docs.celeryq.dev/)
[![Redis](https://img.shields.io/badge/Redis-7-red.svg)](https://redis.io/)
[![Tests](https://img.shields.io/badge/Tests-360%20Passed%20(100%25)-success.svg)]()

---

## 📌 Executive Architecture Overview

```
                      +---------------------------------------+
                      |       Next.js / React Frontend        |
                      +---------------------------------------+
                                          |
                                          | (HTTPS / TLS 1.3)
                                          v
                      +---------------------------------------+
                      |         Nginx Reverse Proxy           |
                      |   (Rate Limiting & 25MB Body Size)    |
                      +---------------------------------------+
                                          |
                                          | (Reverse Proxy :8000)
                                          v
                      +---------------------------------------+
                      |        FastAPI ASGI Application       |
                      |          (102 Mounted Endpoints)       |
                      +---------------------------------------+
                         |                 |               |
                         | (Asyncpg Pool)  | (Enqueues)    | (Redis Cache)
                         v                 v               v
            +--------------------+  +---------------+  +--------------+
            | Supabase / PG 16   |  | Celery Queue  |  | Redis 7      |
            | (37 Tables / RLS)  |  | (Evidence &   |  | (Taxonomy,   |
            +--------------------+  |  Scheduled)   |  |  OTP limits, |
                                    +---------------+  |  Token Rev.) |
                                           |           +--------------+
                                           v
                             +--------------------------+
                             |   Celery Background &    |
                             |      Beat Workers        |
                             |  * OCR QP Ingestion      |
                             |  * 12-Page Vector PDF    |
                             |  * 48h SLA Watchdog      |
                             |  * Monthly Parent Pulse  |
                             +--------------------------+
```

---

## 🚀 Quickstart & Local Setup

### 1. Prerequisites
- Python 3.11+
- Redis 7+ (`redis-server`)
- PostgreSQL 16+ or Supabase Project Credentials

### 2. Virtual Environment Setup
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Environment Variables Configuration
Copy `.env.example` to `.env` and fill in your database credentials:
```bash
cp .env.example .env
```
Ensure `DATABASE_URL` (async) and `DATABASE_SYNC_URL` (sync) point to your Supabase/PostgreSQL instance:
```env
DATABASE_URL=postgresql+asyncpg://postgres:[YOUR-PASSWORD]@db.[YOUR-PROJECT-REF].supabase.co:5432/postgres
DATABASE_SYNC_URL=postgresql://postgres:[YOUR-PASSWORD]@db.[YOUR-PROJECT-REF].supabase.co:5432/postgres
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=generate_using_openssl_rand_hex_32
```

### 4. Apply Database Migrations (All 37 Tables)
```bash
alembic upgrade head
```

### 5. Launch Services
**A. Start FastAPI Backend:**
```bash
uvicorn src.smartparent.main:app --reload --host 0.0.0.0 --port 8000
```
Open interactive Swagger API docs at `http://localhost:8000/docs`.

**B. Start Celery Background Worker (in a separate terminal):**
```bash
celery -A src.smartparent.core.celery_app worker -l info -Q evidence_queue,scheduled_queue -c 4
```

**C. Start Celery Beat Scheduler (in a separate terminal):**
```bash
celery -A src.smartparent.core.celery_app beat -l info
```

---

## 🐳 Docker Deployment

To launch the full microservices stack (API + Celery Worker + Celery Beat + Redis + Local Postgres) with a single command:
```bash
docker-compose up --build -d
```
Inspect container health:
```bash
docker-compose ps
```

---

## 🧪 Comprehensive Verification Suite

Run the full testing battery (360 tests covering unit, integration, end-to-end, and hypothesis property testing):

```bash
# Run all tests
pytest tests/unit tests/integration tests/e2e -q

# Run hypothesis property tests & statistical validation
pytest tests/unit/test_hypothesis_and_statistical_suite.py -v

# Run production deliverable suite (Invoices, Webhooks, MRR, Onboarding)
pytest tests/unit/test_production_backend_deliverables.py -v
```

---

## 📂 Key Architecture Modules

| Module Directory | Functionality & Domain Responsibility |
| :--- | :--- |
| `src/smartparent/api/v1/` | 102 REST endpoints: Auth, Evidence, Taxonomy, Diagnostic, Pulse, Marketplace, Invoicing, Support, Admin. |
| `src/smartparent/db/models/` | 37 SQLAlchemy models covering subscriber, students, evidence, diagnostic gap, marketplace, invoices, tickets. |
| `src/smartparent/services/` | Core domain engines: `billing_service.py` (ReportLab GST Invoicing), `onboarding_service.py` (Sub-3-min wizard). |
| `src/smartparent/tasks/` | Celery async workers: `evidence_tasks.py` (OCR & vector PDF generator), `sla_watchdog_tasks.py` (48h watchdog & pulse). |
| `src/smartparent/utils/` | `redis_cache.py` (Sliding window OTP rate limiter, 24h taxonomy cache, JWT revocation blacklist). |
| `alembic/versions/` | Migration `001_initial_production_schema.py` provisioning all tables and indexes. |

---

## 📄 Fullstack Developer Handoff

For the detailed fullstack developer implementation blueprint, schema definitions, endpoint catalog, and UI integration guides, refer to:
👉 [FULLSTACK_DEVELOPER_HANDOFF_BLUEPRINT.md](docs/FULLSTACK_DEVELOPER_HANDOFF_BLUEPRINT.md)

