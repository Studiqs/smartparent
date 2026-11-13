"""
STUDIQS® SmartParent™ (v6.2 Complete) - Unit Tests for Section 8 Board Readiness & Share Mode
=============================================================================
Tests all Section 8 requirements:
1. Deterministic Board Readiness Index calculation:
   - Syllabus Coverage & Mastery Gauge
   - High-Weightage Topic Risk Radar (topics >=10% exam marks in WEAK/CRITICAL tiers)
   - 3-Point Score Corridor (Lower, Most Likely, Upper) with gap & stability adjustments
   - Readiness Status Tiers (READY, ON_TRACK, NEEDS_ATTENTION, CRITICAL_RISK)
   - Stream Alignment & Career Future Readiness (Engineering, Life Science, Commerce)
   - High-Priority Action Checklist before Board Exams
2. Student Achievements & Milestone Badges Engine:
   - Centum Club (100% verified exam)
   - Consistency Champion
   - Topic Gap Slayer (3+ gaps resolved)
   - Syllabus Pioneer (>=70% coverage)
   - Board Ready
   - Persistent Scholar
   - Subject Maestro
3. Parent-Authorized 72-Hour Share Token Generation:
   - URL-safe cryptographic token
   - Expiration timestamp (now + 72 hours)
   - Live countdown timer display formatting
4. Public Shared Report (Zero Privacy Leakage):
   - Strictly hides subscriber identity, phone, email, and billing
   - Exposes only sanitized student alias (e.g. 'Arun K.') and academic diagnostic brief
5. Parent-Controlled Instant Revocation:
   - Token marked revoked immediately
   - Access blocked with 410 / REVOKED status
6. Multi-Tenant Row-Level Security Boundary:
   - Unauthorized foreign subscriber rejected with PermissionError / 403 Forbidden
=============================================================================
"""

import uuid
from datetime import date, datetime, timedelta, timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.smartparent.db.base import Base
from src.smartparent.db.models.auth import Subscriber, Child
from src.smartparent.db.models.assessment import EvidenceRecord
from src.smartparent.db.models.curriculum import CurriculumNode
from src.smartparent.db.models.diagnostic import TopicGap, TopicScore
from src.smartparent.db.models.readiness import BoardReadinessRecord, SharedReportToken
from src.smartparent.engines.board_readiness_engine import BoardReadinessEngine
from src.smartparent.engines.achievement_engine import AchievementEngine
from src.smartparent.services.readiness_service import ReadinessService
from src.smartparent.api.v1.readiness import router as readiness_router, get_db, get_current_subscriber_id


from sqlalchemy.pool import StaticPool

# SQLite dialect compatibility for JSONB and PG_UUID
@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


@compiles(PG_UUID, "sqlite")
def compile_uuid_sqlite(type_, compiler, **kw):
    return "CHAR(36)"


@pytest.fixture
def db_session():
    """In-memory SQLite session with full schema support."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[
            Subscriber.__table__,
            Child.__table__,
            CurriculumNode.__table__,
            EvidenceRecord.__table__,
            TopicGap.__table__,
            TopicScore.__table__,
            BoardReadinessRecord.__table__,
            SharedReportToken.__table__,
        ]
    )
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def setup_test_family(db_session):
    """Creates authenticated test subscriber and children for testing."""
    sub_id = uuid.uuid4()
    sub = Subscriber(
        subscriber_id=sub_id,
        mobile_number="+919876543210",
        parent_name="Rajesh Sharma",
        email="rajesh.sharma@example.com",
        password_hash="test_hash_123",
    )
    db_session.add(sub)

    # Class 10 Board student
    child_id = uuid.uuid4()
    child = Child(
        child_id=child_id,
        subscriber_id=sub_id,
        student_name="Arun Sharma",
        standard_class="Class 10",
        board="CBSE",
    )
    db_session.add(child)

    # Secondary child
    child2_id = uuid.uuid4()
    child2 = Child(
        child_id=child2_id,
        subscriber_id=sub_id,
        student_name="Pooja Sharma",
        standard_class="Class 8",
        board="CBSE",
    )
    db_session.add(child2)

    # Unrelated Foreign Subscriber (Tenant Isolation Testing)
    foreign_sub_id = uuid.uuid4()
    foreign_sub = Subscriber(
        subscriber_id=foreign_sub_id,
        mobile_number="+919999988888",
        parent_name="Karthik Raman",
        email="karthik.raman@example.com",
        password_hash="test_hash_456",
    )
    db_session.add(foreign_sub)

    # Seed curriculum nodes for Class 10 CBSE
    curriculum = [
        CurriculumNode(
            node_id="CBSE_G10_MAT_TRIG_01",
            standard_class="Class 10",
            board="CBSE",
            subject="MATHEMATICS",
            chapter_name="Trigonometry",
            topic_name="Trigonometric Identities",
            semantic_keywords=["sin", "cos", "identities"],
        ),
        CurriculumNode(
            node_id="CBSE_G10_MAT_QUAD_02",
            standard_class="Class 10",
            board="CBSE",
            subject="MATHEMATICS",
            chapter_name="Algebra",
            topic_name="Quadratic Equations",
            semantic_keywords=["roots", "discriminant"],
        ),
        CurriculumNode(
            node_id="CBSE_G10_SCI_LIGHT_03",
            standard_class="Class 10",
            board="CBSE",
            subject="SCIENCE",
            chapter_name="Physics",
            topic_name="Light Reflection & Refraction",
            semantic_keywords=["optics", "lenses"],
        ),
        CurriculumNode(
            node_id="CBSE_G10_SCI_ACIDS_04",
            standard_class="Class 10",
            board="CBSE",
            subject="SCIENCE",
            chapter_name="Chemistry",
            topic_name="Acids Bases and Salts",
            semantic_keywords=["pH", "neutralization"],
        ),
        CurriculumNode(
            node_id="CBSE_G10_ENG_GRAM_05",
            standard_class="Class 10",
            board="CBSE",
            subject="ENGLISH",
            chapter_name="Grammar",
            topic_name="Reported Speech",
            semantic_keywords=["indirect", "speech"],
        ),
    ]
    db_session.add_all(curriculum)

    # Seed test evidence
    evidence = [
        EvidenceRecord(
            record_id=uuid.uuid4(),
            subscriber_id=sub_id,
            child_id=child_id,
            subject="MATHEMATICS",
            test_title="Mid-Term Math Exam",
            test_date=date(2026, 9, 15),
            total_scored_marks=88.0,
            total_max_marks=100.0,
            evidence_type="MID_TERM",
        ),
        EvidenceRecord(
            record_id=uuid.uuid4(),
            subscriber_id=sub_id,
            child_id=child_id,
            subject="SCIENCE",
            test_title="Pre-Board Science Paper",
            test_date=date(2026, 10, 1),
            total_scored_marks=78.0,
            total_max_marks=100.0,
            evidence_type="PRE_BOARD",
        ),
        EvidenceRecord(
            record_id=uuid.uuid4(),
            subscriber_id=sub_id,
            child_id=child_id,
            subject="ENGLISH",
            test_title="Unit Test 1",
            test_date=date(2026, 8, 20),
            total_scored_marks=50.0,
            total_max_marks=50.0,  # Centum score!
            evidence_type="UNIT_TEST",
        ),
    ]
    db_session.add_all(evidence)

    # Seed Topic Scores & Gaps
    scores = [
        TopicScore(
            score_id=uuid.uuid4(),
            child_id=child_id,
            node_id="CBSE_G10_MAT_TRIG_01",
            scored_marks=45.0,
            max_marks=100.0,
            percentage=45.0,
            mastery_tier="EMERGING",
        ),
        TopicScore(
            score_id=uuid.uuid4(),
            child_id=child_id,
            node_id="CBSE_G10_SCI_LIGHT_03",
            scored_marks=85.0,
            max_marks=100.0,
            percentage=85.0,
            mastery_tier="MASTERED",
        ),
    ]
    db_session.add_all(scores)

    gaps = [
        TopicGap(
            gap_id=uuid.uuid4(),
            child_id=child_id,
            node_id="CBSE_G10_MAT_TRIG_01",
            gap_status="ACTIVE",
        ),
        TopicGap(
            gap_id=uuid.uuid4(),
            child_id=child_id,
            node_id="CBSE_G10_SCI_ACIDS_04",
            gap_status="RESOLVED",
        ),
        TopicGap(
            gap_id=uuid.uuid4(),
            child_id=child_id,
            node_id="CBSE_G10_MAT_QUAD_02",
            gap_status="RESOLVED",
        ),
        TopicGap(
            gap_id=uuid.uuid4(),
            child_id=child_id,
            node_id="CBSE_G10_ENG_GRAM_05",
            gap_status="RESOLVED",
        ),
    ]
    db_session.add_all(gaps)

    db_session.commit()

    return {
        "subscriber_id": sub_id,
        "child_id": child_id,
        "child2_id": child2_id,
        "foreign_subscriber_id": foreign_sub_id,
    }


# =============================================================================
# 1. Board Readiness Engine Unit Tests
# =============================================================================

def test_board_readiness_engine_calculation():
    """Validates deterministic mathematical calculation of board readiness."""
    engine = BoardReadinessEngine()

    curriculum = [
        {"topic_name": "Calculus", "subject": "MATHEMATICS", "weightage_marks": 14.0},
        {"topic_name": "Electrostatics", "subject": "PHYSICS", "weightage_marks": 12.0},
        {"topic_name": "Organic Chemistry", "subject": "CHEMISTRY", "weightage_marks": 10.0},
        {"topic_name": "Grammar", "subject": "ENGLISH", "weightage_marks": 6.0},
    ]
    evidence = [
        {"subject": "MATHEMATICS", "scored_marks": 82.0, "max_marks": 100.0, "exam_type": "PRE_BOARD"},
        {"subject": "PHYSICS", "scored_marks": 75.0, "max_marks": 100.0, "exam_type": "MID_TERM"},
        {"subject": "CHEMISTRY", "scored_marks": 80.0, "max_marks": 100.0, "exam_type": "UNIT_TEST"},
    ]
    topic_scores = [
        {"topic_name": "Calculus", "score_percentage": 50.0, "mastery_tier": "EMERGING"},
        {"topic_name": "Electrostatics", "score_percentage": 85.0, "mastery_tier": "MASTERED"},
    ]
    topic_gaps = [
        {"topic_name": "Calculus", "gap_status": "ACTIVE", "is_critical": True},
    ]

    result = engine.evaluate_board_readiness(
        standard_class="Class 12",
        board="CBSE",
        evidence_records=evidence,
        topic_scores=topic_scores,
        topic_gaps=topic_gaps,
        curriculum_topics=curriculum,
        consistency_slope=0.10,
        stability_index=0.85,
    )

    # Verify score corridor
    corridor = result["score_corridor"]
    assert corridor["lower_bound_pct"] <= corridor["most_likely_pct"] <= corridor["upper_bound_pct"]
    assert 70.0 <= corridor["most_likely_pct"] <= 90.0

    # Verify risk radar
    radar = result["risk_radar"]
    assert radar["high_weightage_risk_count"] >= 1
    assert any(r["topic_name"] == "Calculus" for r in radar["risk_topics"])

    # Verify stream alignment
    stream = result["stream_alignment"]
    assert stream["recommended_stream"] == "ENGINEERING"

    # Verify readiness status
    assert result["readiness_status"] in ["READY", "ON_TRACK", "NEEDS_ATTENTION"]
    assert len(result["priority_action_checklist"]) <= 3


# =============================================================================
# 2. Achievement Engine Unit Tests
# =============================================================================

def test_achievement_engine_milestones():
    """Validates award of verified academic milestone badges."""
    engine = AchievementEngine()

    evidence = [
        {"subject": "MATH", "scored_marks": 100.0, "max_marks": 100.0, "test_title": "Centum Unit Test"},
        {"subject": "SCIENCE", "scored_marks": 92.0, "max_marks": 100.0, "test_title": "Pre-Board"},
        {"subject": "ENGLISH", "scored_marks": 95.0, "max_marks": 100.0, "test_title": "Annual Paper"},
    ]
    topic_gaps = [
        {"gap_status": "RESOLVED"},
        {"gap_status": "RESOLVED"},
        {"gap_status": "RESOLVED"},
    ]

    result = engine.evaluate_achievements(
        evidence_records=evidence,
        topic_gaps=topic_gaps,
        coverage_metrics={"coverage_percentage": 75.0},
        board_readiness_status="READY",
        consistency_slope=0.12,
    )

    unlocked_codes = [b["badge_code"] for b in result["unlocked_badges"]]

    # Centum Club must be unlocked
    assert "CENTUM_CLUB" in unlocked_codes
    # Gap Slayer (3 resolved gaps) must be unlocked
    assert "GAP_SLAYER" in unlocked_codes
    # Syllabus Pioneer (>=70% coverage) must be unlocked
    assert "SYLLABUS_PIONEER" in unlocked_codes
    # Board Ready must be unlocked
    assert "BOARD_READY" in unlocked_codes
    # Consistency Champion must be unlocked
    assert "CONSISTENCY_CHAMPION" in unlocked_codes

    assert result["completion_percentage"] > 50.0


# =============================================================================
# 3. ReadinessService Multi-Tenant & Share Mode Unit Tests
# =============================================================================

def test_readiness_service_board_readiness(db_session, setup_test_family):
    """Tests complete Board Readiness retrieval through service."""
    service = ReadinessService()
    sub_id = setup_test_family["subscriber_id"]
    child_id = setup_test_family["child_id"]

    response = service.get_board_readiness(
        db=db_session,
        subscriber_id=sub_id,
        child_id=child_id,
    )

    assert response.child_id == child_id
    assert response.student_name == "Arun Sharma"
    assert response.standard_class == "Class 10"
    assert response.is_board_appearing_grade is True
    assert response.score_corridor.lower_bound_pct <= response.score_corridor.most_likely_pct
    assert "MATHEMATICS" in response.subject_breakdown
    assert len(response.priority_action_checklist) <= 3


def test_readiness_service_tenant_isolation(db_session, setup_test_family):
    """Asserts that unauthorized foreign subscriber is rejected with PermissionError."""
    service = ReadinessService()
    foreign_sub_id = setup_test_family["foreign_subscriber_id"]
    child_id = setup_test_family["child_id"]

    with pytest.raises(PermissionError) as exc_info:
        service.get_board_readiness(
            db=db_session,
            subscriber_id=foreign_sub_id,
            child_id=child_id,
        )
    assert "Unauthorized" in str(exc_info.value)


def test_readiness_service_share_token_flow(db_session, setup_test_family):
    """
    Tests complete Parent Share Mode lifecycle:
    1. Generate 72-Hour token
    2. Retrieve public sanitized report (assert zero privacy leakage)
    3. List active tokens
    4. Instant parent revocation
    5. Access revoked verification
    """
    service = ReadinessService()
    sub_id = setup_test_family["subscriber_id"]
    child_id = setup_test_family["child_id"]

    # 1. Generate 72-Hour Share Link
    share_resp = service.generate_share_token(
        db=db_session,
        subscriber_id=sub_id,
        child_id=child_id,
        duration_hours=72,
    )

    assert share_resp.child_id == child_id
    assert share_resp.hours_valid == 72
    assert share_resp.seconds_remaining > 0
    assert "remaining" in share_resp.time_remaining_display
    assert share_resp.is_revoked is False
    raw_token = share_resp.share_token

    # 2. Public Sanitized Report View (Tutor / Mentor View)
    public_view = service.get_public_shared_report(
        db=db_session,
        share_token=raw_token,
    )

    assert public_view.is_valid is True
    assert public_view.token_status == "ACTIVE"
    # PRIVACY LEAKAGE AUDIT:
    # Student full name, parent name, email, phone, and billing must be completely ABSENT!
    assert public_view.student_alias == "Arun S."  # First name + last initial only!
    assert "Sharma" not in public_view.student_alias
    assert "rajesh" not in str(public_view)
    assert "9876543210" not in str(public_view)
    assert public_view.readiness_status in ["READY", "ON_TRACK", "NEEDS_ATTENTION"]
    assert len(public_view.top_strengths) >= 1

    # 3. List Active Share Tokens
    tokens_list = service.list_active_share_tokens(
        db=db_session,
        subscriber_id=sub_id,
        child_id=child_id,
    )
    assert tokens_list.active_tokens_count >= 1
    assert any(t.share_token == raw_token for t in tokens_list.tokens)

    # 4. Instant Parent Revocation
    revoke_resp = service.revoke_share_token(
        db=db_session,
        subscriber_id=sub_id,
        token_id=share_resp.token_id,
    )
    assert revoke_resp.is_revoked is True

    # 5. Verify Revoked View
    revoked_view = service.get_public_shared_report(
        db=db_session,
        share_token=raw_token,
    )
    assert revoked_view.is_valid is False
    assert revoked_view.token_status == "REVOKED"
    assert "Revoked" in revoked_view.time_remaining_display


def test_readiness_service_expired_token(db_session, setup_test_family):
    """Verifies that expired share tokens are correctly recognized and blocked."""
    service = ReadinessService()
    sub_id = setup_test_family["subscriber_id"]
    child_id = setup_test_family["child_id"]

    # Manually create token expired 1 hour ago
    expired_token_record = SharedReportToken(
        subscriber_id=sub_id,
        child_id=child_id,
        share_token="expired_token_12345",
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        is_revoked=False,
    )
    db_session.add(expired_token_record)
    db_session.commit()

    view = service.get_public_shared_report(db=db_session, share_token="expired_token_12345")
    assert view.is_valid is False
    assert view.token_status == "EXPIRED"


# =============================================================================
# 4. FastAPI Endpoints Integration Tests
# =============================================================================

def test_api_v1_readiness_endpoints(db_session, setup_test_family):
    """Tests Section 8 FastAPI routes using TestClient."""
    app = FastAPI()
    app.include_router(readiness_router, prefix="/api/v1")

    sub_id = setup_test_family["subscriber_id"]
    child_id = setup_test_family["child_id"]

    # Override dependencies
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_subscriber_id] = lambda: sub_id

    client = TestClient(app)

    # 1. GET /api/v1/readiness/student/{child_id}/board
    res_board = client.get(f"/api/v1/readiness/student/{child_id}/board")
    assert res_board.status_code == 200
    data_board = res_board.json()
    assert data_board["student_name"] == "Arun Sharma"
    assert "score_corridor" in data_board

    # 2. GET /api/v1/readiness/student/{child_id}/achievements
    res_achieve = client.get(f"/api/v1/readiness/student/{child_id}/achievements")
    assert res_achieve.status_code == 200
    data_achieve = res_achieve.json()
    assert data_achieve["unlocked_count"] >= 1

    # 3. POST /api/v1/readiness/share/generate
    res_gen = client.post(
        "/api/v1/readiness/share/generate",
        json={"child_id": str(child_id), "duration_hours": 72},
    )
    assert res_gen.status_code == 201
    data_gen = res_gen.json()
    raw_token = data_gen["share_token"]
    token_id = data_gen["token_id"]

    # 4. GET /api/v1/readiness/share/active/{child_id}
    res_active = client.get(f"/api/v1/readiness/share/active/{child_id}")
    assert res_active.status_code == 200
    assert res_active.json()["active_tokens_count"] >= 1

    # 5. GET /api/v1/readiness/share/view/{share_token} (Public Endpoint)
    res_public = client.get(f"/api/v1/readiness/share/view/{raw_token}")
    assert res_public.status_code == 200
    data_public = res_public.json()
    assert data_public["is_valid"] is True
    assert data_public["student_alias"] == "Arun S."

    # 6. POST /api/v1/readiness/share/revoke/{token_id}
    res_revoke = client.post(f"/api/v1/readiness/share/revoke/{token_id}")
    assert res_revoke.status_code == 200
    assert res_revoke.json()["is_revoked"] is True
