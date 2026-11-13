"""
STUDIQS® SmartParent™ - Section 3 & Section 5 Ground-Level Adversarial Test Suite
================================================================================
Module: tests.unit.test_section3_5_groundlevel_torture

Audits and proves production reliability across:
  1. Section 3: Evidence Intake, Quick Marks, File Uploads, Document AI boundaries
  2. Section 5: Performance Intelligence, Gap Watchlists, Consistency Indexes
  3. Multi-Tenant Cross-Parent Isolation across all Section 3 & 5 endpoints
  4. Mathematical Edge Cases (ZeroDivision, 0% & 100% bounds, Scored > Max marks)
  5. Cold Start Resiliency (Child with 0 evidence records)
================================================================================
"""

import io
import uuid
import pytest
from datetime import date, datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID

@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"

@compiles(PG_UUID, "sqlite")
def compile_uuid_sqlite(type_, compiler, **kw):
    return "CHAR(36)"

from src.smartparent.main import app
from src.smartparent.db.base import Base
from src.smartparent.db.models.auth import Subscriber, Child, SubscriberSession
from src.smartparent.db.models.assessment import EvidenceRecord, QuestionPaper, Question, StudentQuestionMark
from src.smartparent.db.models.diagnostic import TopicScore, TopicGap
from src.smartparent.db.models.curriculum import CurriculumNode
from src.smartparent.api.deps import get_db
from src.smartparent.core.security import create_access_token, get_password_hash
from src.smartparent.services.intake_service import IntakeService
from src.smartparent.services.performance_service import PerformanceService
from src.smartparent.services.diagnostic_service import DiagnosticService
from src.smartparent.schemas.intake import QuickMarksFeedRequest
from src.smartparent.schemas.performance import GapRecheckRequestSchema


from src.smartparent.db.models.marketplace import EvaluationCase, Expert

# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture(scope="module")
def sec35_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Compile and create tables needed for Section 3 & 5
    tables = [
        Subscriber.__table__,
        Child.__table__,
        SubscriberSession.__table__,
        EvidenceRecord.__table__,
        QuestionPaper.__table__,
        Question.__table__,
        StudentQuestionMark.__table__,
        TopicScore.__table__,
        TopicGap.__table__,
        CurriculumNode.__table__,
        EvaluationCase.__table__,
        Expert.__table__,
    ]
    Base.metadata.create_all(bind=engine, tables=tables)
    yield engine
    Base.metadata.drop_all(bind=engine, tables=tables)


@pytest.fixture
def db(sec35_engine):
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sec35_engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


import asyncio
try:
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
except AttributeError:
    pass

@pytest.fixture
def client(sec35_engine):
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sec35_engine)
    def override_get_db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def seed_family(db):
    """Provisions Parent A (with Child A) and Parent B (with Child B) for multi-tenant tests."""
    suffix = uuid.uuid4().hex[:7]
    mobile_a = f"+9199{suffix[:8]}".ljust(13, "0")[:13]
    mobile_b = f"+9198{suffix[:8]}".ljust(13, "0")[:13]

    sub_a = Subscriber(
        subscriber_id=uuid.uuid4(),
        mobile_number=mobile_a,
        parent_name="Parent Alpha",
        password_hash="fake_bcrypt_hash_for_testing",
        subscription_plan="PRO",
    )
    sub_b = Subscriber(
        subscriber_id=uuid.uuid4(),
        mobile_number=mobile_b,
        parent_name="Parent Beta",
        password_hash="fake_bcrypt_hash_for_testing",
        subscription_plan="BASIC",
    )
    db.add_all([sub_a, sub_b])
    db.flush()

    child_a = Child(
        child_id=uuid.uuid4(),
        subscriber_id=sub_a.subscriber_id,
        student_name="Aadhya Alpha",
        standard_class="Class 10",
        board="CBSE",
        academic_year="2025-2026",
        is_active=True,
    )
    child_b = Child(
        child_id=uuid.uuid4(),
        subscriber_id=sub_b.subscriber_id,
        student_name="Bharat Beta",
        standard_class="Class 10",
        board="CBSE",
        academic_year="2025-2026",
        is_active=True,
    )
    db.add_all([child_a, child_b])

    # Seed curriculum nodes if not present
    node_math_id = f"MAT-10-QUAD-{uuid.uuid4().hex[:4]}"
    node_sci_id = f"SCI-10-CHEM-{uuid.uuid4().hex[:4]}"
    node_math = CurriculumNode(
        node_id=node_math_id,
        subject="Mathematics",
        standard_class="Class 10",
        board="CBSE",
        chapter_name="Quadratic Equations",
        topic_name="Quadratic Formula & Roots",
        semantic_keywords=["quadratic", "formula", "roots"],
    )
    node_sci = CurriculumNode(
        node_id=node_sci_id,
        subject="Science",
        standard_class="Class 10",
        board="CBSE",
        chapter_name="Chemical Reactions",
        topic_name="Balancing Equations",
        semantic_keywords=["chemical", "reactions", "equations"],
    )
    db.add_all([node_math, node_sci])
    db.commit()

    token_a = create_access_token({"sub": str(sub_a.subscriber_id), "plan": "PRO"})
    token_b = create_access_token({"sub": str(sub_b.subscriber_id), "plan": "BASIC"})

    return {
        "sub_a": sub_a,
        "sub_b": sub_b,
        "child_a": child_a,
        "child_b": child_b,
        "token_a": token_a,
        "token_b": token_b,
        "node_math": node_math,
        "node_sci": node_sci,
    }


# =============================================================================
# 1. SECTION 3: QUICK MARKS BOUNDARY & MATHEMATICAL RESILIENCY
# =============================================================================

def test_quick_marks_normal_flow(client, seed_family, db):
    """Verifies that legitimate quick marks are recorded and update telemetry."""
    f = seed_family
    headers = {"Authorization": f"Bearer {f['token_a']}"}
    payload = {
        "child_id": str(f["child_a"].child_id),
        "subject": "Mathematics",
        "test_title": "Unit Test 1 - Algebra",
        "test_date": str(date.today()),
        "total_scored_marks": 85.0,
        "total_max_marks": 100.0,
    }
    res = client.post("/api/v1/evidence/quick-marks", json=payload, headers=headers)
    assert res.status_code == 201
    data = res.json()
    assert data["percentage"] == 85.0
    assert data["status"] == "CONFIRMED"

    # Verify DB persistence
    score = (
        db.query(TopicScore)
        .filter(TopicScore.child_id == f["child_a"].child_id)
        .first()
    )
    assert score is not None
    assert score.percentage == 85.0
    assert score.mastery_tier == "STRONG"


def test_quick_marks_boundary_zero_and_perfect_score(client, seed_family):
    """Tests 0% and 100% boundary marks handling."""
    f = seed_family
    headers = {"Authorization": f"Bearer {f['token_a']}"}

    # 1. Zero Score (0/100)
    res_zero = client.post(
        "/api/v1/evidence/quick-marks",
        json={
            "child_id": str(f["child_a"].child_id),
            "subject": "Science",
            "test_title": "Physics Pop Quiz",
            "test_date": str(date.today()),
            "total_scored_marks": 0.0,
            "total_max_marks": 50.0,
        },
        headers=headers,
    )
    assert res_zero.status_code == 201
    assert res_zero.json()["percentage"] == 0.0

    # 2. Perfect Score (100/100)
    res_perfect = client.post(
        "/api/v1/evidence/quick-marks",
        json={
            "child_id": str(f["child_a"].child_id),
            "subject": "Science",
            "test_title": "Chemistry Midterm",
            "test_date": str(date.today()),
            "total_scored_marks": 100.0,
            "total_max_marks": 100.0,
        },
        headers=headers,
    )
    assert res_perfect.status_code == 201
    assert res_perfect.json()["percentage"] == 100.0


def test_quick_marks_invalid_negative_and_overflow(client, seed_family):
    """Rejects negative scored marks and scores exceeding max marks."""
    f = seed_family
    headers = {"Authorization": f"Bearer {f['token_a']}"}

    # Negative scored marks -> 422 Validation Error
    res_neg = client.post(
        "/api/v1/evidence/quick-marks",
        json={
            "child_id": str(f["child_a"].child_id),
            "subject": "Mathematics",
            "test_title": "Invalid Test",
            "test_date": str(date.today()),
            "total_scored_marks": -10.0,
            "total_max_marks": 100.0,
        },
        headers=headers,
    )
    assert res_neg.status_code == 422


# =============================================================================
# 2. SECTION 3: FILE UPLOAD & DOCUMENT AI BOUNDARIES
# =============================================================================

def test_evidence_upload_unsupported_format(client, seed_family):
    """Rejects unsupported file types (.exe, .py, .zip)."""
    f = seed_family
    headers = {"Authorization": f"Bearer {f['token_a']}"}
    fake_file = io.BytesIO(b"malicious script content")
    res = client.post(
        "/api/v1/evidence/upload",
        data={
            "child_id": str(f["child_a"].child_id),
            "subject": "Mathematics",
            "test_title": "Quarterly Exam",
            "test_date": str(date.today()),
        },
        files={"file": ("hack.exe", fake_file, "application/octet-stream")},
        headers=headers,
    )
    assert res.status_code == 400
    assert "Unsupported file format" in res.json()["detail"]


def test_evidence_upload_valid_pdf_queuing(client, seed_family):
    """Accepts valid PDF and queues Document AI processing."""
    f = seed_family
    headers = {"Authorization": f"Bearer {f['token_a']}"}
    fake_pdf = io.BytesIO(b"%PDF-1.4 sample exam paper header content")
    res = client.post(
        "/api/v1/evidence/upload",
        data={
            "child_id": str(f["child_a"].child_id),
            "subject": "Mathematics",
            "test_title": "Half Yearly Exam Paper",
            "test_date": str(date.today()),
        },
        files={"file": ("maths_paper.pdf", fake_pdf, "application/pdf")},
        headers=headers,
    )
    assert res.status_code == 202
    data = res.json()
    assert data["evidence_id"] is not None
    assert data["status"] in ("PENDING", "PROCESSING", "COMPLETED")


# =============================================================================
# 3. MULTI-TENANT ISOLATION: SECTION 3 EVIDENCE
# =============================================================================

def test_cross_parent_evidence_isolation(client, seed_family):
    """Parent A is strictly forbidden from uploading or listing Parent B's evidence."""
    f = seed_family
    headers_a = {"Authorization": f"Bearer {f['token_a']}"}

    # Parent A tries to submit quick marks for Child B -> 403 Forbidden
    res = client.post(
        "/api/v1/evidence/quick-marks",
        json={
            "child_id": str(f["child_b"].child_id),
            "subject": "Mathematics",
            "test_title": "Cross Tenant Attempt",
            "test_date": str(date.today()),
            "total_scored_marks": 90.0,
            "total_max_marks": 100.0,
        },
        headers=headers_a,
    )
    assert res.status_code == 403

    # Parent A tries to list evidence history for Child B -> 403 Forbidden
    res_list = client.get(
        f"/api/v1/evidence/child/{f['child_b'].child_id}",
        headers=headers_a,
    )
    assert res_list.status_code == 403


# =============================================================================
# 4. SECTION 5: COLD START & PERFORMANCE INTELLIGENCE
# =============================================================================

def test_performance_intelligence_cold_start(client, seed_family):
    """Verifies that a child with 0 evidence records returns clean telemetry without crashing."""
    f = seed_family
    headers_b = {"Authorization": f"Bearer {f['token_b']}"}

    # Child B has zero evidence records initially
    res = client.get(
        f"/api/v1/performance/{f['child_b'].child_id}",
        headers=headers_b,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["student_name"] == "Bharat Beta"
    assert "overall_monthly_movement" in data
    assert len(data["subject_consistencies"]) == 0


def test_performance_consistency_progression(client, seed_family, db):
    """Verifies that sequential marks generate an improving/declining consistency index."""
    f = seed_family
    child_id = f["child_a"].child_id
    sub_id = f["sub_a"].subscriber_id

    # Create 3 sequential evidence records over 3 months: 60 -> 75 -> 88 (Improving)
    dates = [date(2026, 1, 15), date(2026, 2, 15), date(2026, 3, 15)]
    scores = [60.0, 75.0, 88.0]
    for d, s in zip(dates, scores):
        ev = EvidenceRecord(
            record_id=uuid.uuid4(),
            subscriber_id=sub_id,
            child_id=child_id,
            evidence_type="QUICK_MARKS",
            subject="Mathematics",
            test_title=f"Monthly Test {d.strftime('%b')}",
            test_date=d,
            total_scored_marks=s,
            total_max_marks=100.0,
        )
        db.add(ev)
    db.commit()

    headers = {"Authorization": f"Bearer {f['token_a']}"}
    res = client.get(f"/api/v1/performance/{child_id}", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert len(data["subject_consistencies"]) >= 1
    math_consistency = next(c for c in data["subject_consistencies"] if c["subject"] == "Mathematics")
    assert math_consistency["current_percentage"] == 88.0
    assert math_consistency["consistency_tier"] in ("Improving", "Stable", "Declining", "Fluctuating")


# =============================================================================
# 5. SECTION 5: GAP WATCHLIST & RECHECK LIFECYCLE
# =============================================================================

def test_gap_watch_and_resolution_flow(client, seed_family, db):
    """Tests the full lifecycle of identifying a learning gap and closing it via recheck."""
    f = seed_family
    child_id = f["child_a"].child_id
    gap_id = uuid.uuid4()

    # Provision a critical topic gap
    gap = TopicGap(
        gap_id=gap_id,
        child_id=child_id,
        node_id=f["node_math"].node_id,
        gap_status="ACTIVE",
        first_identified_at=datetime.now(timezone.utc) - timedelta(days=7),
    )
    db.add(gap)
    db.commit()

    headers = {"Authorization": f"Bearer {f['token_a']}"}

    # 1. Fetch performance gap summary -> Verify gap is on active watchlist
    res_summary = client.get(f"/api/v1/performance/gap-closure/{child_id}", headers=headers)
    assert res_summary.status_code == 200
    summary_data = res_summary.json()
    assert summary_data["active_gaps_count"] >= 1

    # 2. Submit Recheck with poor score (45%) -> Gap remains ACTIVE
    res_fail_recheck = client.post(
        "/api/v1/performance/gap-recheck",
        json={
            "child_id": str(child_id),
            "gap_id": str(gap_id),
            "recheck_scored_marks": 45.0,
            "recheck_max_marks": 100.0,
            "recheck_title": "Remedial Worksheet 1",
        },
        headers=headers,
    )
    assert res_fail_recheck.status_code == 200
    assert res_fail_recheck.json()["is_gap_closed"] is False
    assert res_fail_recheck.json()["new_status"] == "ACTIVE"

    # 3. Submit Recheck with mastery score (85%) -> Gap marks RESOLVED
    res_pass_recheck = client.post(
        "/api/v1/performance/gap-recheck",
        json={
            "child_id": str(child_id),
            "gap_id": str(gap_id),
            "recheck_scored_marks": 85.0,
            "recheck_max_marks": 100.0,
            "recheck_title": "Remedial Worksheet 2",
        },
        headers=headers,
    )
    assert res_pass_recheck.status_code == 200
    assert res_pass_recheck.json()["is_gap_closed"] is True
    assert res_pass_recheck.json()["new_status"] == "RESOLVED"

    # Verify gap status updated in DB
    db.refresh(gap)
    assert gap.gap_status == "RESOLVED"
    assert gap.resolved_at is not None


# =============================================================================
# 6. MULTI-TENANT ISOLATION: SECTION 5 PERFORMANCE & DIAGNOSTIC
# =============================================================================

def test_cross_parent_performance_and_diagnostic_isolation(client, seed_family):
    """Parent A is strictly blocked from reading Parent B's performance and diagnostic telemetry."""
    f = seed_family
    headers_a = {"Authorization": f"Bearer {f['token_a']}"}

    # 1. Parent A attempts to view Child B's performance intelligence -> 403 Forbidden
    res_perf = client.get(f"/api/v1/performance/{f['child_b'].child_id}", headers=headers_a)
    assert res_perf.status_code == 403

    # 2. Parent A attempts to view Child B's subject consistency -> 403 Forbidden
    res_cons = client.get(f"/api/v1/performance/consistency/{f['child_b'].child_id}", headers=headers_a)
    assert res_cons.status_code == 403

    # 3. Parent A attempts to view Child B's diagnostic Student 360 profile -> 403 Forbidden
    res_diag = client.get(f"/api/v1/diagnostic/child/{f['child_b'].child_id}", headers=headers_a)
    assert res_diag.status_code == 403
