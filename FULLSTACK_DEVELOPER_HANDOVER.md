# 🚀 STUDIQS® SmartParent™ - Full-Stack Developer Handover Guide

> **Welcome to STUDIQS SmartParent™!**  
> **Lead & Chief Reviewer**: [@MaheshM-01](https://github.com/MaheshM-01)  
> **Developer**: [@Dora1HasiniR](https://github.com/Dora1HasiniR)  
> This document guides you through setting up the backend, connecting Supabase PostgreSQL, and building the Frontend Mobile PWA.

---

## 🏛️ Architecture at a Glance
- **Backend**: FastAPI (Python 3.11), SQLAlchemy 2.0, Alembic, PostgreSQL 16 with Row-Level Security (RLS).
- **AI & RAG Engine**: Ask Studiqs Neuro-Symbolic NLU (INT8 ONNX Model, zero-hallucination 5D NLG).
- **Payments**: Razorpay Subscriptions (Basic ₹200, Advanced ₹400, Pro ₹600 with 1/3/6/12m durations) + 18% GST.
- **Frontend Target**: Mobile-first Progressive Web App (PWA) under `/frontend`.
- **Database**: Supabase PostgreSQL.

---

## 🛠️ Step 1: Local Backend Setup (5 Minutes)

### Prerequisites:
- Python 3.11+
- Tesseract OCR (`tesseract-ocr`)
- Git

### Commands:
```bash
# 1. Navigate to backend directory
cd backend

# 2. Create virtual environment
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/Mac:
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy environment configuration
cp .env.example .env

# 5. Run local development server
uvicorn src.smartparent.main:app --reload --port 8000
```
API Documentation & Interactive Swagger UI is live at:
👉 **`http://localhost:8000/docs`**

---

## 🗄️ Step 2: Supabase Database Connection & Auto-Migration

Supabase is a managed PostgreSQL database. You do NOT need to write manual SQL table scripts!

1. Go to your **Supabase Project Settings** $\rightarrow$ **Database** $\rightarrow$ **Connection URI**.
2. Copy the Connection String and set it in `backend/.env`:
   ```env
   DATABASE_URL=postgresql://postgres:[YOUR-PASSWORD]@db.[YOUR-PROJECT-REF].supabase.co:5432/postgres
   ```
3. Run Alembic migrations to automatically create all 41 tables and PostgreSQL Row-Level Security (RLS) policies:
   ```bash
   cd backend
   alembic upgrade head
   ```
4. Seed the 8,034 Curriculum Topics into Supabase:
   ```bash
   python scripts/seed_curriculum.py
   ```
5. Seed the Demo Parent Sandbox (Parent + 2 Children + Diagnostic Scores):
   ```bash
   python scripts/seed_demo_parent.py
   ```

---

## 🧪 Step 3: Developer Sandboxes (Zero Money & Mock Testing)

We have built dedicated Sandbox APIs under `/api/v1/sandbox/*` so you can build the frontend without waiting for external accounts:

### 1. Payment Sandbox (No Real Money Needed)
- **Endpoint**: `POST /api/v1/sandbox/payments/mock-checkout`
- **Request Body**:
  ```json
  {
    "plan": "PRO",
    "duration_months": 12,
    "payment_method": "mock_upi",
    "simulate_failure": false
  }
  ```
- **Returns**: Real 18% GST calculation, `order_sandbox_...`, instant `INV-SBX-...` invoice, and activates subscription!

### 2. Ask Studiqs Voice Assistant Sandbox
- **Endpoint**: `POST /api/v1/sandbox/voice/ask-studiqs`
- **Request Body**:
  ```json
  {
    "query_text": "En paiyan maths la entha topic la weak?",
    "language_hint": "ta-IN"
  }
  ```
- **Returns**: Intent detection, resolved student name, 5D UI narrative card, audio speech transcript, and recommended drill. Strictly read-only safe!

---

## 📱 Step 4: Frontend Development Guidelines (`/frontend`)

- Place all frontend code inside the `/frontend` directory.
- The PWA app shell assets are already available at `backend/static/`:
  - `manifest.webmanifest` (Theme: `#2563EB`, Display: `standalone`)
  - `sw.js` (Service Worker with DPDP Act 2023 zero-cache rule for private `/api/v1/*` routes)
  - `pwa_installer.js` (Native install-to-home-screen trigger)
  - `offline.html` (Branded offline fallback)

---

## 🛡️ Step 5: Git Branching & Lead Review Protocol

You **CANNOT push directly to `main` or `staging`**. All work is submitted via Pull Requests to the Lead (**@MaheshM-01**).

### Developer Git Workflow:
```bash
# 1. Pull latest staging before starting a new feature
git checkout staging
git pull origin staging

# 2. Create feature branch
git checkout -b feat/mobile-login-ui

# 3. Code, build, and test locally
npm run build     # (in frontend)
python -m pytest  # (in backend)

# 4. Commit with semantic messages
git add .
git commit -m "feat(auth): implement mobile OTP login screen with cooldown timer"

# 5. Push feature branch
git push origin feat/mobile-login-ui

# 6. Open a Pull Request targeting: staging
```

### Lead Review & Acceptance Gate:
1. Automated CI (`.github/workflows/ci.yml`) will run and must be 100% green.
2. The Lead (**@MaheshM-01**) reviews your code diff, tests the UI, and approves the PR.
3. Once approved, the Lead merges your PR into `staging`.
4. Staging build is live-tested by the QA team before final release to `main`.

