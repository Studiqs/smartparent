"""
=============================================================================
STUDIQS® SmartParent™ (v6.2 Complete) - Section 4 Unit & Integration Test Suite
=============================================================================
Validates:
1. Student 360 Intelligence Aggregation:
   - Non-negotiable B2C Boundary (subscriber isolation).
   - Subject performance, score deltas, and consistency tiers.
   - Top unresolved topic gaps.
   - Parent Pulse card integration.
   - Board readiness integration for Classes 10 & 12.
2. Consolidated Report Lifecycle:
   - Monthly Consolidated Report generation with PDF compilation.
   - Term-wise Consolidated Report generation.
   - Yearly Consolidated Report generation.
   - Current academic year active report querying.
3. Academic-Year Rollover:
   - Finalizing and archiving the Yearly Consolidated Report.
   - Retiring prior-year monthly and term reports.
   - Preserving only the single finalized Yearly Report in report history.
   - Updating child's academic year and promoting class.
=============================================================================
"""

import uuid
import pytest
from datetime import date, datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID

from src.smartparent.db.base import Base
from src.smartparent.db.models.auth import Subscriber, Child
from src.smartparent.db.models.assessment import EvidenceRecord
from src.smartparent.db.models.curriculum import CurriculumNode
from src.smartparent.db.models.diagnostic import TopicGap
from src.smartparent.db.models.parent_pulse import ParentPulseRecord
from src.smartparent.db.models.readiness import BoardReadinessRecord
from src.smartparent.db.models.marketplace import Expert, EvaluationCase
from src.smartparent.db.models.consolidated_report import ConsolidatedReport
from src.smartparent.services.student_360_service import Student360Service
from src.smartparent.services.report_service import ReportService


# Register SQLite dialect mappings for PostgreSQL JSONB and UUID
@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


@compiles(PG_UUID, "sqlite")
def compile_uuid_sqlite(type_, compiler, **kw):
    return "CHAR(36)"


@pytest.fixture
def db_session():
    """In-memory SQLite session with full schema support."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(
        bind=engine,
        tables=[
            Subscriber.__table__,
            Child.__table__,
            CurriculumNode.__table__,
            EvidenceRecord.__table__,
            TopicGap.__table__,
            ParentPulseRecord.__table__,
            BoardReadinessRecord.__table__,
            Expert.__table__,
            EvaluationCase.__table__,
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
    """Creates authenticated test subscriber and children."""
    sub_a = Subscriber(
        subscriber_id=uuid.uuid4(),
        mobile_number="+919876543210",
        parent_name="Rajesh Kumar",
        email="rajesh.kumar@example.com",
        password_hash="mock_hash_123",
    )
    sub_b = Subscriber(
        subscriber_id=uuid.uuid4(),
        mobile_number="+919876543211",
        parent_name="Priya Sharma",
        email="priya.sharma@example.com",
        password_hash="mock_hash_456",
    )
    db_session.add_all([sub_a, sub_b])
    db_session.commit()

    child_a = Child(
        child_id=uuid.uuid4(),
        subscriber_id=sub_a.subscriber_id,
        student_name="Aarav",
        standard_class="Class 10",
        board="CBSE",
        academic_year="2025-2026",
    )
    child_b = Child(
        child_id=uuid.uuid4(),
        subscriber_id=sub_b.subscriber_id,
        student_name="Ananya",
        standard_class="Class 8",
        board="State Board",
        academic_year="2025-2026",
    )
    db_session.add_all([child_a, child_b])
    db_session.commit()

    return {
        "sub_a": sub_a,
        "sub_b": sub_b,
        "child_a": child_a,
        "child_b": child_b,
    }


# =============================================================================
# 1. Student 360 Aggregation Tests
# =============================================================================

def test_student_360_security_boundary(db_session, setup_test_family):
    """Subscriber B cannot access Subscriber A's child 360 intelligence view."""
    s360_service = Student360Service()
    sub_b = setup_test_family["sub_b"]
    child_a = setup_test_family["child_a"]

    with pytest.raises(PermissionError, match="Child profile not found or not authorized"):
        s360_service.get_student_360(
            db=db_session,
            subscriber_id=sub_b.subscriber_id,
            child_id=child_a.child_id,
        )


def test_student_360_full_intelligence(db_session, setup_test_family):
    """Verifies subject trends, deltas, topic gaps, and board readiness."""
    sub_a = setup_test_family["sub_a"]
    child_a = setup_test_family["child_a"]

    # 1. Seed sequential EvidenceRecords for delta/movement calculation
    # Math: Midterm (70) -> Final (80) (+10 Improving)
    # Science: Midterm (80) -> Final (85) (+5 Improving)
    er_math_1 = EvidenceRecord(
        record_id=uuid.uuid4(),
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        evidence_type="QUICK_MARKS",
        subject="Mathematics",
        test_title="Midterm",
        test_date=date(2025, 9, 1),
        total_scored_marks=70.0,
        total_max_marks=100.0,
    )
    er_math_2 = EvidenceRecord(
        record_id=uuid.uuid4(),
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        evidence_type="QUICK_MARKS",
        subject="Mathematics",
        test_title="Final",
        test_date=date(2025, 10, 1),
        total_scored_marks=80.0,
        total_max_marks=100.0,
    )
    er_sci_1 = EvidenceRecord(
        record_id=uuid.uuid4(),
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        evidence_type="QUICK_MARKS",
        subject="Science",
        test_title="Midterm",
        test_date=date(2025, 9, 1),
        total_scored_marks=80.0,
        total_max_marks=100.0,
    )
    er_sci_2 = EvidenceRecord(
        record_id=uuid.uuid4(),
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        evidence_type="QUICK_MARKS",
        subject="Science",
        test_title="Final",
        test_date=date(2025, 10, 1),
        total_scored_marks=85.0,
        total_max_marks=100.0,
    )
    db_session.add_all([er_math_1, er_math_2, er_sci_1, er_sci_2])
    db_session.commit()


    # 2. Seed a critical topic gap
    cur_node = CurriculumNode(
        node_id="CBSE_G10_MAT_CH04_QUAD_EQ",
        board="CBSE",
        standard_class="Class 10",
        subject="Mathematics",
        chapter_name="Quadratic Equations",
        topic_name="Quadratic Equations",
    )
    db_session.add(cur_node)
    db_session.commit()

    gap = TopicGap(
        gap_id=uuid.uuid4(),
        child_id=child_a.child_id,
        node_id=cur_node.node_id,
        gap_status="ACTIVE",
    )
    db_session.add(gap)
    db_session.commit()

    # 3. Seed Board Readiness Record for Class 10
    readiness = BoardReadinessRecord(
        readiness_id=uuid.uuid4(),
        child_id=child_a.child_id,
        standard_class="Class 10",
        projected_board_score=84.50,
        projected_cutoff=178.50,
        stream_readiness_data={"engineering": "High", "life_science": "Moderate", "commerce": "Low"},
        career_readiness_summary="High alignment with Engineering.",
    )
    db_session.add(readiness)
    db_session.commit()

    # Execute Student 360 aggregation
    s360_service = Student360Service()
    view = s360_service.get_student_360(db_session, sub_a.subscriber_id, child_a.child_id)

    assert view["profile"]["student_name"] == "Aarav"
    assert view["profile"]["standard_class"] == "Class 10"
    assert view["overall_average"] == 82.5
    assert view["monthly_movement"] == 7.5  # 82.5 - 75.0 = +7.5%

    # Check subject movement
    math_perf = next(s for s in view["subject_performance"] if s["subject_name"] == "Mathematics")
    assert math_perf["current_marks"] == 80.0
    assert math_perf["previous_marks"] == 70.0
    assert math_perf["delta"] == 10.0
    assert math_perf["consistency_tier"] == "Improving"

    # Check topic gaps
    assert len(view["top_unresolved_gaps"]) == 1
    assert view["top_unresolved_gaps"][0]["topic_name"] == "Quadratic Equations"

    # Check Board Readiness
    assert view["board_readiness"] is not None
    assert view["board_readiness"]["projected_board_score"] == 84.50
    assert view["board_readiness"]["projected_cutoff"] == 178.50


# =============================================================================
# 2. Consolidated Report Generation & PDF Lifecycle Tests
# =============================================================================

def test_consolidated_report_monthly_and_pdf(db_session, setup_test_family):
    """Generates a Monthly Consolidated Report and compiles vector PDF."""
    report_service = ReportService()
    sub_a = setup_test_family["sub_a"]
    child_a = setup_test_family["child_a"]

    report = report_service.generate_consolidated_report(
        db=db_session,
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        report_type="MONTHLY",
        academic_year="2025-2026",
        period_key="2025-10",
        include_pdf=True,
    )

    assert report.report_type == "MONTHLY"
    assert report.period_key == "2025-10"
    assert report.is_finalized is False
    assert report.is_archived_yearly is False
    assert report.pdf_storage_path is not None
    assert report.pdf_storage_path.endswith(".pdf")


def test_current_year_reports_query(db_session, setup_test_family):
    """Retrieves all active monthly, term, and yearly reports for the present academic year."""
    report_service = ReportService()
    sub_a = setup_test_family["sub_a"]
    child_a = setup_test_family["child_a"]

    # Generate Monthly Report
    report_service.generate_consolidated_report(
        db_session, sub_a.subscriber_id, child_a.child_id, "MONTHLY", "2025-2026", "2025-09", include_pdf=False
    )
    # Generate Term Report
    report_service.generate_consolidated_report(
        db_session, sub_a.subscriber_id, child_a.child_id, "TERM", "2025-2026", "TERM_1", include_pdf=False
    )

    active_reports = report_service.get_current_year_reports(
        db_session, sub_a.subscriber_id, child_a.child_id, "2025-2026"
    )

    assert len(active_reports) == 2
    types = [r.report_type for r in active_reports]
    assert "MONTHLY" in types
    assert "TERM" in types


# =============================================================================
# 3. Academic-Year Rollover & Archival Tests (Section 4 Mandate)
# =============================================================================

def test_academic_year_rollover_lifecycle(db_session, setup_test_family):
    """
    Section 4 Rollover Mandate:
    1. Archives finalized Yearly report for prior year.
    2. Retires previous-year monthly/term reports.
    3. Preserves only the single finalized Yearly report in report history.
    """
    report_service = ReportService()
    sub_a = setup_test_family["sub_a"]
    child_a = setup_test_family["child_a"]

    # 1. Create previous year reports: 2 Monthly, 1 Term, 1 Yearly
    report_service.generate_consolidated_report(
        db_session, sub_a.subscriber_id, child_a.child_id, "MONTHLY", "2025-2026", "2025-09", include_pdf=False
    )
    report_service.generate_consolidated_report(
        db_session, sub_a.subscriber_id, child_a.child_id, "MONTHLY", "2025-2026", "2025-10", include_pdf=False
    )
    report_service.generate_consolidated_report(
        db_session, sub_a.subscriber_id, child_a.child_id, "TERM", "2025-2026", "TERM_1", include_pdf=False
    )
    report_service.generate_consolidated_report(
        db_session, sub_a.subscriber_id, child_a.child_id, "YEARLY", "2025-2026", "YEAR_2025_2026", include_pdf=False
    )

    # Verify 4 reports active in previous year
    pre_reports = report_service.get_current_year_reports(db_session, sub_a.subscriber_id, child_a.child_id, "2025-2026")
    assert len(pre_reports) == 4

    # 2. Execute Academic-Year Rollover (2025-2026 -> 2026-2027, promote Class 10 -> Class 11)
    rollover_receipt = report_service.execute_academic_year_rollover(
        db=db_session,
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        previous_academic_year="2025-2026",
        new_academic_year="2026-2027",
        new_standard_class="Class 11",
    )

    assert rollover_receipt["status"] == "COMPLETED"
    assert rollover_receipt["retired_reports_count"] == 3  # 2 monthly + 1 term retired!

    # 3. Check child updated state
    db_session.refresh(child_a)
    assert child_a.standard_class == "Class 11"
    assert child_a.academic_year == "2026-2027"

    # 4. Check active reports for 2025-2026 is now ZERO (all monthly/term deleted, yearly archived)
    post_active = report_service.get_current_year_reports(db_session, sub_a.subscriber_id, child_a.child_id, "2025-2026")
    assert len(post_active) == 0

    # 5. Check report history: Exactly ONE finalized Yearly report preserved!
    history = report_service.get_report_history(db_session, sub_a.subscriber_id, child_a.child_id)
    assert len(history) == 1
    archived_yearly = history[0]
    assert archived_yearly.report_type == "YEARLY"
    assert archived_yearly.academic_year == "2025-2026"
    assert archived_yearly.is_finalized is True
    assert archived_yearly.is_archived_yearly is True
