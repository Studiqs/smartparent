"""
STUDIQS® SmartParent™ (v6.2 Complete) - Unit Tests for Section 5 Performance & Consistency
=============================================================================
Tests all Section 5 requirements:
1. Subject Monthly Consistency: (Maths 72 → 78 → 81 | Improving)
2. Overall Monthly Movement: (+4% vs last comparable result - strict compatibility protection)
3. Term Consistency: (Term 1 → Term 2 direction with sufficiency rule)
4. Topic Movement: (Needs Attention → Needs Practice → Mastered)
5. Gap Closure & Recheck Lifecycle: (2 of 3 gaps improved / closed)
6. Expert Feedback Status: (Submitted → Under Review → Completed with 48h SLA)
7. Non-negotiable B2C multi-tenant security boundary
=============================================================================
"""

import uuid
from datetime import date, datetime, timedelta, timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID

from src.smartparent.db.base import Base
from src.smartparent.db.models.auth import Subscriber, Child
from src.smartparent.db.models.assessment import EvidenceRecord
from src.smartparent.db.models.curriculum import CurriculumNode
from src.smartparent.db.models.diagnostic import TopicGap, TopicScore
from src.smartparent.db.models.marketplace import Expert, EvaluationCase
from src.smartparent.services.performance_service import PerformanceService
from src.smartparent.engines.performance_consistency_engine import PerformanceConsistencyEngine
from src.smartparent.engines.gap_recheck_engine import GapRecheckEngine


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
            TopicScore.__table__,
            Expert.__table__,
            EvaluationCase.__table__,
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
    """Creates authenticated test subscribers and children."""
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
        academic_year="2026-2027",
    )
    child_b = Child(
        child_id=uuid.uuid4(),
        subscriber_id=sub_b.subscriber_id,
        student_name="Ananya",
        standard_class="Class 8",
        board="State Board",
        academic_year="2026-2027",
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
# 1. Subject Monthly Consistency Tests
# =============================================================================

def test_subject_monthly_consistency_calculation():
    """
    Validates: Maths 72 → 78 → 81 | Improving
    Computes chronological progression array, delta, and directional narrative.
    """
    engine = PerformanceConsistencyEngine()
    assessments = [
        {"subject": "Mathematics", "test_date": "2026-08-15", "total_scored_marks": 72.0, "total_max_marks": 100.0},
        {"subject": "Mathematics", "test_date": "2026-09-15", "total_scored_marks": 78.0, "total_max_marks": 100.0},
        {"subject": "Mathematics", "test_date": "2026-10-15", "total_scored_marks": 81.0, "total_max_marks": 100.0},
    ]

    results = engine.evaluate_subject_monthly_consistency(assessments)
    assert len(results) == 1
    math_res = results[0]

    assert math_res.subject == "Mathematics"
    assert math_res.progression == [72.0, 78.0, 81.0]
    assert math_res.current_percentage == 81.0
    assert math_res.previous_percentage == 78.0
    assert math_res.delta == 3.0
    assert math_res.trend_direction == "IMPROVING"
    assert math_res.directional_symbol == "↗"
    assert math_res.consistency_tier == "Improving"
    assert math_res.display_narrative == "Mathematics 72 → 78 → 81 | Improving"


def test_subject_monthly_consistency_fluctuating():
    """Validates fluctuating trend detection on alternate score swings."""
    engine = PerformanceConsistencyEngine()
    assessments = [
        {"subject": "Science", "test_date": "2026-08-10", "total_scored_marks": 80.0, "total_max_marks": 100.0},
        {"subject": "Science", "test_date": "2026-09-10", "total_scored_marks": 55.0, "total_max_marks": 100.0},
        {"subject": "Science", "test_date": "2026-10-10", "total_scored_marks": 82.0, "total_max_marks": 100.0},
    ]

    results = engine.evaluate_subject_monthly_consistency(assessments)
    assert len(results) == 1
    sci_res = results[0]

    assert sci_res.trend_direction == "FLUCTUATING"
    assert sci_res.directional_symbol == "∿"
    assert "Fluctuating" in sci_res.display_narrative


# =============================================================================
# 2. Overall Monthly Movement & Incompatible Evidence Protection Tests
# =============================================================================

def test_overall_monthly_movement_compatible():
    """Validates +4% vs last comparable result on compatible evidence."""
    engine = PerformanceConsistencyEngine()
    assessments = [
        # Prior Month (September): Average = (70 + 80) / 2 = 75.0%
        {"subject": "Mathematics", "test_date": "2026-09-10", "total_scored_marks": 70.0, "total_max_marks": 100.0},
        {"subject": "Science", "test_date": "2026-09-20", "total_scored_marks": 80.0, "total_max_marks": 100.0},
        # Current Month (October): Average = (76 + 82) / 2 = 79.0%
        {"subject": "Mathematics", "test_date": "2026-10-05", "total_scored_marks": 76.0, "total_max_marks": 100.0},
        {"subject": "Science", "test_date": "2026-10-18", "total_scored_marks": 82.0, "total_max_marks": 100.0},
    ]

    res = engine.evaluate_overall_monthly_movement(assessments)
    assert res.is_comparable is True
    assert res.current_mean == 79.0
    assert res.prior_mean == 75.0
    assert res.movement_percentage == 4.0
    assert res.display_badge == "+4.0% vs last comparable result"


def test_overall_monthly_movement_incompatible_evidence_protection():
    """
    Strict Rule (Section 5): Never silently compare incompatible evidence!
    Disjoint subjects across months must be flagged rather than producing fake movement.
    """
    engine = PerformanceConsistencyEngine()
    assessments = [
        # Prior Month: Only Social Science
        {"subject": "Social Science", "test_date": "2026-09-10", "total_scored_marks": 90.0, "total_max_marks": 100.0},
        # Current Month: Only Mathematics
        {"subject": "Mathematics", "test_date": "2026-10-10", "total_scored_marks": 60.0, "total_max_marks": 100.0},
    ]

    res = engine.evaluate_overall_monthly_movement(assessments)
    assert res.is_comparable is False
    assert res.display_badge == "Incompatible evidence comparison avoided"
    assert "No overlapping subjects" in res.compatibility_note


# =============================================================================
# 3. Term Consistency & Sufficiency Tests
# =============================================================================

def test_term_consistency_insufficient_evidence():
    """Rule: Only with sufficient evidence (>= 2 assessments per term)."""
    engine = PerformanceConsistencyEngine()
    assessments = [
        # Only 1 test in Term 1 (August)
        {"subject": "Mathematics", "test_title": "August Unit Test", "test_date": "2026-08-15", "total_scored_marks": 70.0, "total_max_marks": 100.0},
        # Only 1 test in Term 2 (November)
        {"subject": "Mathematics", "test_title": "November Midterm", "test_date": "2026-11-15", "total_scored_marks": 80.0, "total_max_marks": 100.0},
    ]

    res = engine.evaluate_term_consistency(assessments)
    assert res.has_sufficient_evidence is False
    assert res.term_direction == "INSUFFICIENT_EVIDENCE"
    assert "Insufficient evidence" in res.display_narrative


def test_term_consistency_sufficient_evidence():
    """Validates Term 1 (74%) → Term 2 (80%) | Improving with >= 2 tests per term."""
    engine = PerformanceConsistencyEngine()
    assessments = [
        # Term 1: 2 tests (70% and 78% -> mean 74.0%)
        {"subject": "Mathematics", "test_title": "Term 1 Unit Test", "test_date": "2026-08-15", "total_scored_marks": 70.0, "total_max_marks": 100.0},
        {"subject": "Science", "test_title": "Term 1 Quarterly", "test_date": "2026-09-20", "total_scored_marks": 78.0, "total_max_marks": 100.0},
        # Term 2: 2 tests (80% and 80% -> mean 80.0%)
        {"subject": "Mathematics", "test_title": "Term 2 Midterm", "test_date": "2026-10-15", "total_scored_marks": 80.0, "total_max_marks": 100.0},
        {"subject": "Science", "test_title": "Term 2 Half Yearly", "test_date": "2026-11-25", "total_scored_marks": 80.0, "total_max_marks": 100.0},
    ]

    res = engine.evaluate_term_consistency(assessments)
    assert res.has_sufficient_evidence is True
    assert res.term_direction == "IMPROVING"
    assert res.term_scores["Term 1"] == 74.0
    assert res.term_scores["Term 2"] == 80.0
    assert res.display_narrative == "Term 1 (74%) → Term 2 (80%) | Improving"


# =============================================================================
# 4. Topic Movement Tracking Tests
# =============================================================================

def test_topic_movement_transitions():
    """Validates topic-level movement across pedagogical tiers."""
    engine = PerformanceConsistencyEngine()
    topic_history = [
        {
            "node_id": "CBSE_G10_MAT_CH04_QUAD_EQ",
            "topic_name": "Quadratic Equations",
            "subject": "Mathematics",
            "current_score": 55.0,  # Weak -> Needs Practice
            "previous_score": 35.0, # Critical -> Needs Attention
        },
        {
            "node_id": "CBSE_G10_SCI_CH12_ELEC",
            "topic_name": "Ohm's Law",
            "subject": "Science",
            "current_score": 85.0,  # Strong -> Mastered
            "previous_score": 65.0, # Average -> Foundational
        },
    ]

    movements = engine.evaluate_topic_movement(topic_history)
    assert len(movements) == 2

    m1 = movements[0]
    assert m1.previous_tier == "Needs Attention"
    assert m1.current_tier == "Needs Practice"
    assert m1.movement_label == "Needs Attention → Needs Practice"
    assert m1.is_improved is True

    m2 = movements[1]
    assert m2.previous_tier == "Foundational"
    assert m2.current_tier == "Mastered"
    assert m2.movement_label == "Foundational → Mastered"
    assert m2.is_improved is True


# =============================================================================
# 5. Gap Closure & Recheck Lifecycle Tests
# =============================================================================

def test_gap_closure_summary_statistics():
    """Validates 2 of 3 gaps improved / closed calculation."""
    engine = PerformanceConsistencyEngine()
    gaps_data = [
        {"gap_id": "gap-1", "gap_status": "RESOLVED"},
        {"gap_id": "gap-2", "gap_status": "RESOLVED"},
        {"gap_id": "gap-3", "gap_status": "ACTIVE"},
    ]

    summary = engine.evaluate_gap_closure(gaps_data)
    assert summary.total_identified_gaps == 3
    assert summary.resolved_gaps_count == 2
    assert summary.active_gaps_count == 1
    assert summary.closure_rate_percent == 66.7
    assert summary.display_badge == "2 of 3 gaps improved / closed (66.7%)"


def test_gap_recheck_execution_and_closure(db_session, setup_test_family):
    """
    Submits a diagnostic recheck for a topic gap:
    - If score >= 80%: Resolves the gap, records confirmed TopicScore and EvidenceRecord.
    - If score < 80%: Remains ACTIVE with updated score.
    """
    service = PerformanceService()
    sub_a = setup_test_family["sub_a"]
    child_a = setup_test_family["child_a"]

    # 1. Seed CurriculumNode and active TopicGap
    node = CurriculumNode(
        node_id="CBSE_G10_MAT_CH04_QUAD_EQ",
        board="CBSE",
        standard_class="Class 10",
        subject="Mathematics",
        chapter_name="Quadratic Equations",
        topic_name="Quadratic Equations",
    )
    db_session.add(node)
    db_session.commit()

    gap = TopicGap(
        gap_id=uuid.uuid4(),
        child_id=child_a.child_id,
        node_id=node.node_id,
        gap_status="ACTIVE",
    )
    db_session.add(gap)
    db_session.commit()

    # Verify initial summary
    initial_intel = service.get_performance_intelligence(db_session, sub_a.subscriber_id, child_a.child_id)
    assert initial_intel.gap_closure_summary.resolved_gaps_count == 0
    assert initial_intel.gap_closure_summary.active_gaps_count == 1

    # 2. Execute Gap Recheck with score 85% (>= 80% threshold -> RESOLVED)
    recheck_res = service.execute_gap_recheck(
        db=db_session,
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        gap_id=gap.gap_id,
        scored_marks=17.0,
        max_marks=20.0,  # 85.0%
        recheck_title="Quadratic Equations Quick Check",
    )

    assert recheck_res.is_gap_closed is True
    assert recheck_res.new_status == "RESOLVED"
    assert recheck_res.recheck_score == 85.0
    assert "Closed" in recheck_res.transition_narrative

    # Check database state: gap status is now RESOLVED
    db_session.refresh(gap)
    assert gap.gap_status == "RESOLVED"
    assert gap.resolved_at is not None

    # Check that confirmed TopicScore and EvidenceRecord were persisted
    ts = db_session.query(TopicScore).filter(TopicScore.node_id == node.node_id).first()
    assert ts is not None
    assert ts.percentage == 85.0
    assert ts.mastery_tier == "STRONG"

    ev = db_session.query(EvidenceRecord).filter(EvidenceRecord.subject == "Mathematics").first()
    assert ev is not None
    assert ev.total_scored_marks == 17.0

    # 3. Check updated Performance Intelligence
    updated_intel = service.get_performance_intelligence(db_session, sub_a.subscriber_id, child_a.child_id)
    assert updated_intel.gap_closure_summary.resolved_gaps_count == 1
    assert updated_intel.gap_closure_summary.active_gaps_count == 0
    assert updated_intel.gap_closure_summary.closure_rate_percent == 100.0


# =============================================================================
# 6. Expert Feedback Status & 48h SLA Tests
# =============================================================================

def test_expert_feedback_status_and_sla_tracking():
    """Validates 48h SLA turnaround calculation and state progression."""
    engine = PerformanceConsistencyEngine()
    now = datetime.now(timezone.utc)

    expert_cases = [
        # Case 1: SUBMITTED 10 hours ago -> ~38h remaining, not breached
        {
            "case_id": "case-001",
            "subject": "Mathematics",
            "test_title": "Quadratic Equations Diagnostic Sheet",
            "expert_name": "Dr. Ananya Roy",
            "case_status": "SUBMITTED",
            "submitted_at": (now - timedelta(hours=10)).isoformat(),
            "completed_at": None,
        },
        # Case 2: SUBMITTED 50 hours ago -> SLA breached
        {
            "case_id": "case-002",
            "subject": "Physics",
            "test_title": "Electricity Numerical Evaluation",
            "expert_name": "Prof. S. Sharma",
            "case_status": "UNDER_REVIEW",
            "submitted_at": (now - timedelta(hours=50)).isoformat(),
            "completed_at": None,
        },
        # Case 3: COMPLETED -> confirmed evidence
        {
            "case_id": "case-003",
            "subject": "Chemistry",
            "test_title": "Chemical Bonding Paper",
            "expert_name": "Dr. K. Verma",
            "case_status": "COMPLETED",
            "submitted_at": (now - timedelta(hours=30)).isoformat(),
            "completed_at": (now - timedelta(hours=5)).isoformat(),
            "evaluated_pdf_path": "/storage/evaluations/case-003.pdf",
            "expert_feedback": "Strong in ionic bonding; practice coordinate covalent mechanisms.",
        },
    ]

    results = engine.evaluate_expert_feedback_status(expert_cases)
    assert len(results) == 3

    c1 = results[0]
    assert c1.case_status == "SUBMITTED"
    assert c1.sla_hours_remaining is not None
    assert 37.0 <= c1.sla_hours_remaining <= 39.0
    assert c1.is_sla_breached is False
    assert c1.is_confirmed_evidence is False

    c2 = results[1]
    assert c2.case_status == "UNDER_REVIEW"
    assert c2.sla_hours_remaining == 0.0
    assert c2.is_sla_breached is True

    c3 = results[2]
    assert c3.case_status == "COMPLETED"
    assert c3.is_confirmed_evidence is True
    assert c3.evaluated_pdf_path == "/storage/evaluations/case-003.pdf"
    assert "ionic bonding" in c3.expert_feedback_summary


# =============================================================================
# 7. Non-Negotiable B2C Boundary Security Test
# =============================================================================

def test_performance_security_boundary(db_session, setup_test_family):
    """Subscriber B cannot access Subscriber A's child performance intelligence."""
    service = PerformanceService()
    sub_b = setup_test_family["sub_b"]
    child_a = setup_test_family["child_a"]

    with pytest.raises(PermissionError, match="Child profile not found or not authorized"):
        service.get_performance_intelligence(
            db=db_session,
            subscriber_id=sub_b.subscriber_id,
            child_id=child_a.child_id,
        )
