"""
STUDIQS® SmartParent™ (v6.2 Complete) - Unit Tests for Section 9 PTM Prep Pack & Academic Handoff
=============================================================================
Tests all Section 9 requirements:
1. PTM Prep Pack generation (Praise First, Remediate Second)
2. Subject-Specific dynamic filtering (e.g. Mathematics PTM vs Class Teacher)
3. Multi-Audience customization (TEACHER, TUTOR, COMPREHENSIVE)
4. Concrete Misconception patterns & struggling question stems
5. Longitudinal Subject score trajectories & exam history
6. 1-Click WhatsApp Quick-Share text formatting & URL generation
7. Cold-start student fallback handling (zero test data)
8. Non-negotiable B2C multi-tenant security boundary isolation
9. FastAPI REST API endpoints via TestClient
=============================================================================
"""

import uuid
from datetime import date, datetime, timedelta, timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.smartparent.db.base import Base
from src.smartparent.db.models.auth import Subscriber, Child
from src.smartparent.db.models.assessment import EvidenceRecord
from src.smartparent.db.models.curriculum import CurriculumNode
from src.smartparent.db.models.diagnostic import TopicGap, TopicScore
from src.smartparent.db.models.parent_pulse import ParentPulseRecord
from src.smartparent.db.models.consolidated_report import ConsolidatedReport
from src.smartparent.services.academic_handoff_service import AcademicHandoffService
from src.smartparent.schemas.handoff import (
    PtmAudienceEnum,
    ParentValueMomentEnum,
    AfterEachTestSnapshotSchema,
    DeeperHelpDiagnosticSchema,
    MonthEndDigestSchema,
    TermEndReviewSchema,
    YearEndConsolidatedSchema,
    NextAcademicYearRolloverStatusSchema,
    PtmPackResponse,
    WhatsAppShareResponse,
    Section9MasterValueLifecycleResponse,
)
from src.smartparent.api.v1.handoff import router as handoff_router, get_db, get_current_subscriber_id


# Register SQLite dialect mappings for PostgreSQL JSONB and UUID
@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


@compiles(PG_UUID, "sqlite")
def compile_uuid_sqlite(type_, compiler, **kw):
    return "CHAR(36)"
from sqlalchemy.pool import StaticPool


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
            ParentPulseRecord.__table__,
            ConsolidatedReport.__table__,
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
    """Creates authenticated test subscribers, children, and curriculum nodes."""
    # Subscriber A
    sub_a = Subscriber(
        subscriber_id=uuid.uuid4(),
        mobile_number="+919876543210",
        parent_name="Karthik R.",
        email="karthik.r@example.com",
        password_hash="mock_hash_123",
    )
    child_a = Child(
        child_id=uuid.uuid4(),
        subscriber_id=sub_a.subscriber_id,
        student_name="Arun",
        standard_class="Class 10",
        board="CBSE",
        academic_year="2026-2027",
    )

    # Subscriber B (Foreign Family for isolation testing)
    sub_b = Subscriber(
        subscriber_id=uuid.uuid4(),
        mobile_number="+919123456789",
        parent_name="Meena S.",
        email="meena.s@example.com",
        password_hash="mock_hash_456",
    )
    child_b = Child(
        child_id=uuid.uuid4(),
        subscriber_id=sub_b.subscriber_id,
        student_name="Pooja",
        standard_class="Class 8",
        board="CBSE",
        academic_year="2026-2027",
    )

    # Curriculum Nodes
    nodes = [
        CurriculumNode(
            node_id="CBSE_10_MATH_REAL_NUMBERS",
            board="CBSE",
            standard_class="Class 10",
            subject="Mathematics",
            chapter_name="Real Numbers",
            topic_name="Fundamental Theorem of Arithmetic",
        ),
        CurriculumNode(
            node_id="CBSE_10_MATH_QUADRATIC",
            board="CBSE",
            standard_class="Class 10",
            subject="Mathematics",
            chapter_name="Quadratic Equations",
            topic_name="Quadratic Formula & Discriminant",
        ),
        CurriculumNode(
            node_id="CBSE_10_SCI_ELECTRICITY",
            board="CBSE",
            standard_class="Class 10",
            subject="Science",
            chapter_name="Electricity",
            topic_name="Ohm's Law & Resistance",
        ),
        CurriculumNode(
            node_id="CBSE_10_SCI_CHEMICAL",
            board="CBSE",
            standard_class="Class 10",
            subject="Science",
            chapter_name="Chemical Reactions",
            topic_name="Balancing Chemical Equations",
        ),
    ]

    db_session.add_all([sub_a, child_a, sub_b, child_b] + nodes)
    db_session.commit()

    return {
        "sub_a": sub_a,
        "child_a": child_a,
        "sub_b": sub_b,
        "child_b": child_b,
    }


def test_ptm_pack_comprehensive_generation(db_session, setup_test_family):
    """
    Verifies full PTM Prep Pack generation across all subjects:
    - Praise First: Confirmed strength in Real Numbers (88%)
    - Remediate Second: Pinpointed gaps in Quadratic Equations (35%) and Electricity (38%)
    - Trajectories & Trends
    - Constructive Teacher talking points
    - Formatted printable text and WhatsApp share text
    """
    child_a = setup_test_family["child_a"]
    sub_a = setup_test_family["sub_a"]

    # 1. Strengths (Math Real Numbers: 88%, Science Chemical Reactions: 82%)
    s1 = TopicScore(
        score_id=uuid.uuid4(),
        child_id=child_a.child_id,
        node_id="CBSE_10_MATH_REAL_NUMBERS",
        scored_marks=22.0,
        max_marks=25.0,
        percentage=88.0,
        mastery_tier="STRONG",
        evaluated_at=datetime.now(timezone.utc),
    )
    s2 = TopicScore(
        score_id=uuid.uuid4(),
        child_id=child_a.child_id,
        node_id="CBSE_10_SCI_CHEMICAL",
        scored_marks=41.0,
        max_marks=50.0,
        percentage=82.0,
        mastery_tier="STRONG",
        evaluated_at=datetime.now(timezone.utc),
    )

    # 2. Gaps (Math Quadratic: 35%, Science Electricity: 38%)
    g1 = TopicGap(
        gap_id=uuid.uuid4(),
        child_id=child_a.child_id,
        node_id="CBSE_10_MATH_QUADRATIC",
        gap_status="ACTIVE",
    )
    g1_score = TopicScore(
        score_id=uuid.uuid4(),
        child_id=child_a.child_id,
        node_id="CBSE_10_MATH_QUADRATIC",
        scored_marks=7.0,
        max_marks=20.0,
        percentage=35.0,
        mastery_tier="CRITICAL",
        evaluated_at=datetime.now(timezone.utc),
    )
    g2 = TopicGap(
        gap_id=uuid.uuid4(),
        child_id=child_a.child_id,
        node_id="CBSE_10_SCI_ELECTRICITY",
        gap_status="ACTIVE",
    )
    g2_score = TopicScore(
        score_id=uuid.uuid4(),
        child_id=child_a.child_id,
        node_id="CBSE_10_SCI_ELECTRICITY",
        scored_marks=19.0,
        max_marks=50.0,
        percentage=38.0,
        mastery_tier="CRITICAL",
        evaluated_at=datetime.now(timezone.utc),
    )

    # 3. Evidence Records (Exam Trajectory)
    e1 = EvidenceRecord(
        record_id=uuid.uuid4(),
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        evidence_type="QUICK_MARKS",
        subject="Mathematics",
        test_title="Unit Test 1",
        test_date=date(2026, 8, 15),
        total_scored_marks=35.0,
        total_max_marks=50.0,
    )
    e2 = EvidenceRecord(
        record_id=uuid.uuid4(),
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        evidence_type="QUICK_MARKS",
        subject="Mathematics",
        test_title="Midterm Exam",
        test_date=date(2026, 9, 20),
        total_scored_marks=42.0,
        total_max_marks=50.0,
    )
    db_session.add_all([s1, s2, g1, g1_score, g2, g2_score, e1, e2])
    db_session.commit()

    service = AcademicHandoffService()
    pack = service.generate_ptm_pack(
        db=db_session,
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        subject=None,  # All subjects
        audience=PtmAudienceEnum.TEACHER,
    )

    assert isinstance(pack, PtmPackResponse)
    assert pack.student_name == "Arun"
    assert pack.standard_class == "Class 10"
    assert pack.target_audience == PtmAudienceEnum.TEACHER

    # Strengths check
    assert len(pack.praise_points) >= 2
    assert pack.praise_points[0].mastery_percentage == 88.0

    # Gaps check
    assert len(pack.priority_gaps) >= 2
    quad_gap = next((g for g in pack.priority_gaps if "Quadratic" in g.topic_name), None)
    assert quad_gap is not None
    assert quad_gap.current_percentage == 35.0
    assert len(quad_gap.misconception_type) > 10
    assert len(quad_gap.struggling_question_example) > 10

    # Trends check
    math_trend = next((t for t in pack.trends if t.subject == "Mathematics"), None)
    assert math_trend is not None
    assert math_trend.current_percentage == 84.0  # 42/50
    assert math_trend.prior_percentage == 70.0    # 35/50
    assert math_trend.delta_percentage == 14.0
    assert math_trend.direction == "IMPROVING"

    # Talking points & WhatsApp text
    assert len(pack.talking_points) >= 3
    assert "Praise & Foundation" in pack.talking_points[0]
    assert "📋 *STUDIQS® SmartParent™ — PTM Diagnostic Brief*" in pack.whatsapp_share_text
    assert "ACCOMPLISHMENTS & STRENGTHS TO CELEBRATE" in pack.formatted_printable_text


def test_ptm_pack_subject_specific_filter(db_session, setup_test_family):
    """
    Verifies dynamic single-subject filtering for a Mathematics Subject Teacher meeting:
    Only Mathematics telemetry is included; Science topics are excluded.
    """
    child_a = setup_test_family["child_a"]
    sub_a = setup_test_family["sub_a"]

    # Math strength
    s_math = TopicScore(
        score_id=uuid.uuid4(),
        child_id=child_a.child_id,
        node_id="CBSE_10_MATH_REAL_NUMBERS",
        scored_marks=22.0,
        max_marks=25.0,
        percentage=88.0,
        mastery_tier="STRONG",
        evaluated_at=datetime.now(timezone.utc),
    )
    # Science strength (should be filtered out)
    s_sci = TopicScore(
        score_id=uuid.uuid4(),
        child_id=child_a.child_id,
        node_id="CBSE_10_SCI_CHEMICAL",
        scored_marks=45.0,
        max_marks=50.0,
        percentage=90.0,
        mastery_tier="STRONG",
        evaluated_at=datetime.now(timezone.utc),
    )
    # Math gap
    g_math = TopicGap(
        gap_id=uuid.uuid4(),
        child_id=child_a.child_id,
        node_id="CBSE_10_MATH_QUADRATIC",
        gap_status="ACTIVE",
    )
    db_session.add_all([s_math, s_sci, g_math])
    db_session.commit()

    service = AcademicHandoffService()
    pack = service.generate_ptm_pack(
        db=db_session,
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        subject="Mathematics",
        audience=PtmAudienceEnum.TEACHER,
    )

    assert pack.selected_subject == "Mathematics"
    # All praise points must be Mathematics
    for p in pack.praise_points:
        assert p.subject == "Mathematics"
    # All gaps must be Mathematics
    for g in pack.priority_gaps:
        assert g.subject == "Mathematics"


def test_ptm_pack_home_tutor_audience(db_session, setup_test_family):
    """
    Verifies customization for Home Private Tutors:
    - Operational directives
    - Immediate homework drill problems
    - Diagnostic gap recheck SLA reminder
    """
    child_a = setup_test_family["child_a"]
    sub_a = setup_test_family["sub_a"]

    g_math = TopicGap(
        gap_id=uuid.uuid4(),
        child_id=child_a.child_id,
        node_id="CBSE_10_MATH_QUADRATIC",
        gap_status="ACTIVE",
    )
    db_session.add(g_math)
    db_session.commit()

    service = AcademicHandoffService()
    pack = service.generate_ptm_pack(
        db=db_session,
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        subject="Mathematics",
        audience=PtmAudienceEnum.TUTOR,
    )

    assert pack.target_audience == PtmAudienceEnum.TUTOR
    # Tutor talking points check
    assert any("Operational Priority" in tp for tp in pack.talking_points)
    assert any("Immediate Homework Drill" in tp for tp in pack.talking_points)
    assert any("SLA Recheck" in tp for tp in pack.talking_points)


def test_ptm_pack_whatsapp_share_payload(db_session, setup_test_family):
    """
    Verifies 1-click WhatsApp share payload and deep-link generation.
    """
    child_a = setup_test_family["child_a"]
    sub_a = setup_test_family["sub_a"]

    service = AcademicHandoffService()
    wa_resp = service.get_whatsapp_share_payload(
        db=db_session,
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        subject="Mathematics",
        audience=PtmAudienceEnum.TEACHER,
    )

    assert isinstance(wa_resp, WhatsAppShareResponse)
    assert wa_resp.student_name == "Arun"
    assert wa_resp.target_audience == PtmAudienceEnum.TEACHER
    assert "https://api.whatsapp.com/send?text=" in wa_resp.direct_whatsapp_url
    assert "📋 *STUDIQS® SmartParent™" in wa_resp.whatsapp_text


def test_ptm_pack_cold_start_fallback(db_session, setup_test_family):
    """
    Verifies that a student with zero exams/marks generates a graceful
    diagnostic baseline brief rather than crashing.
    """
    child_b = setup_test_family["child_b"]
    sub_b = setup_test_family["sub_b"]

    service = AcademicHandoffService()
    pack = service.generate_ptm_pack(
        db=db_session,
        subscriber_id=sub_b.subscriber_id,
        child_id=child_b.child_id,
    )

    assert pack.student_name == "Pooja"
    assert len(pack.praise_points) >= 1
    assert "Diligent Exam Participation" in pack.praise_points[0].topic_name
    assert len(pack.priority_gaps) == 0


def test_section9_b2c_tenant_isolation(db_session, setup_test_family):
    """
    Verifies non-negotiable B2C multi-tenant security:
    Subscriber B cannot access Child A's PTM Prep Pack.
    """
    child_a = setup_test_family["child_a"]
    sub_b = setup_test_family["sub_b"]

    service = AcademicHandoffService()
    with pytest.raises(PermissionError) as exc_info:
        service.generate_ptm_pack(
            db=db_session,
            subscriber_id=sub_b.subscriber_id,
            child_id=child_a.child_id,
        )
    assert "not authorized" in str(exc_info.value).lower()


def test_api_v1_handoff_endpoints(db_session, setup_test_family):
    """
    Verifies FastAPI REST endpoints for Section 9 via TestClient.
    """
    child_a = setup_test_family["child_a"]
    sub_a = setup_test_family["sub_a"]
    sub_b = setup_test_family["sub_b"]
    child_a_id = child_a.child_id
    sub_a_id = sub_a.subscriber_id
    sub_b_id = sub_b.subscriber_id

    app = FastAPI()
    app.include_router(handoff_router, prefix="/api/v1")

    # Override dependencies
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_subscriber_id] = lambda: sub_a_id

    client = TestClient(app)

    # 1. GET /api/v1/handoff/ptm-pack/{child_id} (All subjects, TEACHER)
    res1 = client.get(f"/api/v1/handoff/ptm-pack/{child_a_id}")
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["student_name"] == "Arun"
    assert data1["target_audience"] == "TEACHER"

    # 2. GET /api/v1/handoff/ptm-pack/{child_id}?subject=Mathematics&audience=TUTOR
    res2 = client.get(f"/api/v1/handoff/ptm-pack/{child_a_id}?subject=Mathematics&audience=TUTOR")
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["selected_subject"] == "Mathematics"
    assert data2["target_audience"] == "TUTOR"

    # 3. GET /api/v1/handoff/whatsapp-text/{child_id}
    res3 = client.get(f"/api/v1/handoff/whatsapp-text/{child_a_id}")
    assert res3.status_code == 200
    data3 = res3.json()
    assert "https://api.whatsapp.com/send?text=" in data3["direct_whatsapp_url"]

    # 4. Unauthorized Access (Switch to Subscriber B)
    app.dependency_overrides[get_current_subscriber_id] = lambda: sub_b_id
    res4 = client.get(f"/api/v1/handoff/ptm-pack/{child_a_id}")
    assert res4.status_code == 403


def test_moment1_after_each_test(db_session, setup_test_family):
    """
    Verifies Moment 1: 'After each test'
    - Quick marks/result upload updates intelligence immediately.
    - Computes delta %, movement badge, and immediate next step.
    """
    child_a = setup_test_family["child_a"]
    sub_a = setup_test_family["sub_a"]

    e1 = EvidenceRecord(
        record_id=uuid.uuid4(),
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        evidence_type="QUICK_MARKS",
        subject="Mathematics",
        test_title="Unit Test 1",
        test_date=date(2026, 8, 10),
        total_scored_marks=30.0,
        total_max_marks=50.0,  # 60%
    )
    e2 = EvidenceRecord(
        record_id=uuid.uuid4(),
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        evidence_type="QUICK_MARKS",
        subject="Mathematics",
        test_title="Unit Test 2",
        test_date=date(2026, 8, 28),
        total_scored_marks=38.0,
        total_max_marks=50.0,  # 76%
    )
    db_session.add_all([e1, e2])
    db_session.commit()

    service = AcademicHandoffService()
    snap = service.get_after_each_test_value(
        db=db_session,
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
    )

    assert isinstance(snap, AfterEachTestSnapshotSchema)
    assert snap.subject == "Mathematics"
    assert snap.score_percentage == 76.0
    assert snap.prior_score_percentage == 60.0
    assert snap.delta_percentage == 16.0
    assert "Improving" in snap.movement_badge
    assert len(snap.immediate_next_step) > 10


def test_moment2_when_subject_needs_deeper_help(db_session, setup_test_family):
    """
    Verifies Moment 2: 'When a subject needs deeper help'
    - Identifies persistent weak subject (<50%).
    - Generates targeted specialist evaluation recommendation & intake brief.
    """
    child_a = setup_test_family["child_a"]
    sub_a = setup_test_family["sub_a"]

    # Low score test (35%)
    e_low = EvidenceRecord(
        record_id=uuid.uuid4(),
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        evidence_type="QUICK_MARKS",
        subject="Mathematics",
        test_title="Midterm Exam",
        test_date=date(2026, 9, 15),
        total_scored_marks=17.5,
        total_max_marks=50.0,
    )
    # Critical gap
    gap = TopicGap(
        gap_id=uuid.uuid4(),
        child_id=child_a.child_id,
        node_id="CBSE_10_MATH_QUADRATIC",
        gap_status="ACTIVE",
    )
    db_session.add_all([e_low, gap])
    db_session.commit()

    service = AcademicHandoffService()
    deeper = service.get_deeper_help_value(
        db=db_session,
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        subject="Mathematics",
    )

    assert isinstance(deeper, DeeperHelpDiagnosticSchema)
    assert deeper.subject == "Mathematics"
    assert deeper.rolling_average_percentage == 35.0
    assert deeper.is_persistent_weak is True
    assert deeper.status_alert == "PERSISTENT_WEAKNESS_FLAGGED"
    assert "/marketplace/experts?subject=Mathematics" in deeper.expert_marketplace_url
    assert "Quadratic Equations" in deeper.identified_weak_chapters or "Quadratic Formula & Discriminant" in deeper.critical_topic_gaps
    assert "Arun" in deeper.expert_intake_brief


def test_moment3_month_end_digest(db_session, setup_test_family):
    """
    Verifies Moment 3: 'Month end'
    - Monthly Parent Pulse (1 improvement + 1 watch area + 1 next action).
    - Monthly Consolidated Report access link.
    """
    child_a = setup_test_family["child_a"]
    sub_a = setup_test_family["sub_a"]
    target_month = "2026-10"

    pulse = ParentPulseRecord(
        pulse_id=uuid.uuid4(),
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        month_key=target_month,
        improvement_text="Strong Foundation in Real Numbers",
        watch_area_text="Quadratic Equations needs attention",
        next_action_text="Practice 5 factoring problems",
        movement_delta=4.5,
    )
    report = ConsolidatedReport(
        report_id=uuid.uuid4(),
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        report_type="MONTHLY",
        academic_year="2026-2027",
        period_key=target_month,
        report_title="Monthly Report October 2026",
        report_data={},
        pdf_storage_path="https://storage.studiqs.com/reports/arun_oct_2026.pdf",
    )
    db_session.add_all([pulse, report])
    db_session.commit()

    service = AcademicHandoffService()
    month_val = service.get_month_end_value(
        db=db_session,
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        month_key=target_month,
    )

    assert isinstance(month_val, MonthEndDigestSchema)
    assert month_val.month_key == target_month
    assert month_val.has_parent_pulse is True
    assert "IMPROVEMENT" in month_val.pulse_summary
    assert month_val.monthly_report_available is True
    assert "arun_oct_2026.pdf" in month_val.monthly_report_pdf_url


def test_moment4_term_end_review(db_session, setup_test_family):
    """
    Verifies Moment 4: 'Term end'
    - Term-wise Consolidated Report & Consistency Rating.
    """
    child_a = setup_test_family["child_a"]
    sub_a = setup_test_family["sub_a"]

    term_rep = ConsolidatedReport(
        report_id=uuid.uuid4(),
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        report_type="TERM",
        academic_year="2026-2027",
        period_key="TERM_1",
        report_title="Term 1 Report",
        report_data={},
        pdf_storage_path="https://storage.studiqs.com/reports/arun_term_1.pdf",
    )
    db_session.add(term_rep)
    db_session.commit()

    service = AcademicHandoffService()
    term_val = service.get_term_end_value(
        db=db_session,
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        term_name="Term 1",
    )

    assert isinstance(term_val, TermEndReviewSchema)
    assert term_val.term_name == "Term 1"
    assert term_val.term_consistency_rating in ["STABLE", "FLUCTUATING"]
    assert "arun_term_1.pdf" in term_val.term_report_pdf_url


def test_moment5_year_end_consolidated(db_session, setup_test_family):
    """
    Verifies Moment 5: 'Year end'
    - Final Yearly Consolidated Report & permanent annual archive.
    """
    child_a = setup_test_family["child_a"]
    sub_a = setup_test_family["sub_a"]

    year_rep = ConsolidatedReport(
        report_id=uuid.uuid4(),
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        report_type="YEARLY",
        academic_year="2025-2026",
        period_key="2025-2026",
        report_title="Annual Report 2025-2026",
        report_data={},
        pdf_storage_path="https://storage.studiqs.com/reports/arun_final_2025_2026.pdf",
    )
    db_session.add(year_rep)
    db_session.commit()

    service = AcademicHandoffService()
    year_val = service.get_year_end_value(
        db=db_session,
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        academic_year="2025-2026",
    )

    assert isinstance(year_val, YearEndConsolidatedSchema)
    assert year_val.academic_year == "2025-2026"
    assert year_val.is_permanently_archived is True
    assert "arun_final_2025_2026.pdf" in year_val.yearly_report_pdf_url


def test_moment6_next_academic_year_rollover(db_session, setup_test_family):
    """
    Verifies Moment 6: 'Next academic year'
    - Strict Section 9 rule: Only prior Yearly Consolidated Report remains in report history.
    """
    child_a = setup_test_family["child_a"]
    sub_a = setup_test_family["sub_a"]

    service = AcademicHandoffService()
    rollover = service.get_next_academic_year_value(
        db=db_session,
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
    )

    assert isinstance(rollover, NextAcademicYearRolloverStatusSchema)
    assert rollover.prior_yearly_report_retained_in_history is True
    assert rollover.intermediate_drafts_retired is True
    assert rollover.fresh_diagnostic_baseline_ready is True
    assert rollover.promoted_to_class == "Class 10"


def test_master_7_moments_api_endpoints(db_session, setup_test_family):
    """
    Verifies REST API endpoints for all Section 9 moments:
    - Master lifecycle aggregator: GET /api/v1/handoff/moments/{child_id}
    - Moment 1: /after-each-test
    - Moment 2: /deeper-help
    - Moment 3: /month-end
    - Moment 4: /term-end
    - Moment 5: /year-end
    - Moment 6: /next-year-rollover
    """
    child_a = setup_test_family["child_a"]
    sub_a = setup_test_family["sub_a"]
    child_a_id = child_a.child_id
    sub_a_id = sub_a.subscriber_id

    app = FastAPI()
    app.include_router(handoff_router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_subscriber_id] = lambda: sub_a_id

    client = TestClient(app)

    # 1. Master 7 moments aggregator
    res = client.get(f"/api/v1/handoff/moments/{child_a_id}")
    assert res.status_code == 200
    master_data = res.json()
    assert master_data["student_name"] == "Arun"
    assert "AFTER_EACH_TEST" in master_data["moments_summary"]
    assert "WHEN_SUBJECT_NEEDS_DEEPER_HELP" in master_data["moments_summary"]
    assert "MONTH_END" in master_data["moments_summary"]
    assert "TERM_END" in master_data["moments_summary"]
    assert "YEAR_END" in master_data["moments_summary"]
    assert "NEXT_ACADEMIC_YEAR" in master_data["moments_summary"]
    assert "PTM_TUITION" in master_data["moments_summary"]

    # 2. Moment 1 endpoint
    r1 = client.get(f"/api/v1/handoff/moments/{child_a_id}/after-each-test")
    assert r1.status_code == 200

    # 3. Moment 2 endpoint
    r2 = client.get(f"/api/v1/handoff/moments/{child_a_id}/deeper-help?subject=Mathematics")
    assert r2.status_code == 200

    # 4. Moment 3 endpoint
    r3 = client.get(f"/api/v1/handoff/moments/{child_a_id}/month-end")
    assert r3.status_code == 200

    # 5. Moment 4 endpoint
    r4 = client.get(f"/api/v1/handoff/moments/{child_a_id}/term-end")
    assert r4.status_code == 200

    # 6. Moment 5 endpoint
    r5 = client.get(f"/api/v1/handoff/moments/{child_a_id}/year-end")
    assert r5.status_code == 200

    # 7. Moment 6 endpoint
    r6 = client.get(f"/api/v1/handoff/moments/{child_a_id}/next-year-rollover")
    assert r6.status_code == 200
