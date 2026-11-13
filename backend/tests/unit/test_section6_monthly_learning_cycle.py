"""
STUDIQS® SmartParent™ (v6.2 Complete) - Unit Tests for Section 6 Parent Pulse & Learning Cycle
=============================================================================
Tests all Section 6 requirements:
1. 3-Card Parent Pulse Digest: 1 Improvement + 1 Watch Area + 1 Next Action
2. Strict Rule: "No new evidence means no fabricated change"
3. Dynamic synthesis on confirmed new evidence
4. Max 3 Grounded Actions (Home screen rule) with "Ask a Subject Expert" alignment
5. Progress Since Last Update (What changed tracking)
6. Longitudinal Parent Pulse history
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
from src.smartparent.db.models.parent_pulse import ParentPulseRecord
from src.smartparent.services.parent_pulse_service import ParentPulseService


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
            ParentPulseRecord.__table__,
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
# 1. Parent Pulse 3-Card Triad Tests
# =============================================================================

def test_parent_pulse_3_card_triad_synthesis(db_session, setup_test_family):
    """
    Validates synthesis of the mandatory 3 cards:
    - 1 Green Improvement Area
    - 1 Amber Watch Area
    - 1 Blue Next Immediate Action
    """
    service = ParentPulseService()
    sub_a = setup_test_family["sub_a"]
    child_a = setup_test_family["child_a"]

    # Seed an assessment showing improvement
    er1 = EvidenceRecord(
        record_id=uuid.uuid4(),
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        evidence_type="QUICK_MARKS",
        subject="Mathematics",
        test_title="Midterm",
        test_date=date(2026, 9, 1),
        total_scored_marks=70.0,
        total_max_marks=100.0,
    )
    er2 = EvidenceRecord(
        record_id=uuid.uuid4(),
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        evidence_type="QUICK_MARKS",
        subject="Mathematics",
        test_title="Unit Test",
        test_date=date(2026, 10, 1),
        total_scored_marks=82.0,
        total_max_marks=100.0,
    )
    db_session.add_all([er1, er2])
    db_session.commit()

    pulse = service.get_or_synthesize_parent_pulse(
        db=db_session,
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        month_key="2026-10",
    )

    assert pulse.student_name == "Aarav"
    assert pulse.month_key == "2026-10"
    assert pulse.pulse_period == "October 2026"

    # Card 1: Green Improvement Area
    assert pulse.improvement_area.card_type == "IMPROVEMENT"
    assert pulse.improvement_area.color_theme == "GREEN"
    assert pulse.improvement_area.title is not None
    assert len(pulse.improvement_area.description) > 5

    # Card 2: Amber Watch Area
    assert pulse.watch_area.card_type == "WATCH_AREA"
    assert pulse.watch_area.color_theme == "AMBER"

    # Card 3: Blue Next Immediate Action
    assert pulse.next_immediate_action.card_type == "NEXT_ACTION"
    assert pulse.next_immediate_action.color_theme == "BLUE"


# =============================================================================
# 2. Strict Rule: "No New Evidence Means No Fabricated Change"
# =============================================================================

def test_parent_pulse_no_new_evidence_no_fabrication(db_session, setup_test_family):
    """
    Section 6 Core Principle:
    If no new evidence has been submitted, the platform must preserve the confirmed
    baseline without fabricating fake movement or artificial alerts.
    """
    service = ParentPulseService()
    sub_a = setup_test_family["sub_a"]
    child_a = setup_test_family["child_a"]

    # Initial evidence
    er = EvidenceRecord(
        record_id=uuid.uuid4(),
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        evidence_type="QUICK_MARKS",
        subject="Mathematics",
        test_title="Diagnostic Assessment",
        test_date=date(2026, 10, 1),
        total_scored_marks=75.0,
        total_max_marks=100.0,
    )
    db_session.add(er)
    db_session.commit()

    # 1. First pulse synthesis creates database record
    pulse_1 = service.get_or_synthesize_parent_pulse(
        db_session, sub_a.subscriber_id, child_a.child_id, "2026-10"
    )
    assert pulse_1.is_fabricated is False
    assert pulse_1.evidence_status == "CONFIRMED_EVIDENCE_PRESENT"

    # 2. Second request without any new evidence
    pulse_2 = service.get_or_synthesize_parent_pulse(
        db_session, sub_a.subscriber_id, child_a.child_id, "2026-10"
    )

    # Must return existing confirmed record
    assert pulse_2.pulse_id == pulse_1.pulse_id
    assert pulse_2.evidence_status == "CONFIRMED_BASELINE_PRESERVED"
    assert pulse_2.progress_since_last_update.has_meaningful_change is False
    assert "No new test evidence recorded" in pulse_2.progress_since_last_update.narrative_summary


# =============================================================================
# 3. Dynamic Synthesis on Confirmed New Evidence
# =============================================================================

def test_parent_pulse_new_evidence_triggers_synthesis(db_session, setup_test_family):
    """Submitting new test evidence triggers recalculation of deltas and pulse."""
    service = ParentPulseService()
    sub_a = setup_test_family["sub_a"]
    child_a = setup_test_family["child_a"]

    # 1. Baseline evidence in September (70%)
    er1 = EvidenceRecord(
        record_id=uuid.uuid4(),
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        evidence_type="QUICK_MARKS",
        subject="Mathematics",
        test_title="September Test",
        test_date=date(2026, 9, 15),
        total_scored_marks=70.0,
        total_max_marks=100.0,
    )
    db_session.add(er1)
    db_session.commit()

    pulse_sep = service.get_or_synthesize_parent_pulse(
        db_session, sub_a.subscriber_id, child_a.child_id, "2026-09"
    )
    assert pulse_sep.month_key == "2026-09"

    # 2. New evidence in October (85%) (+15% upward momentum)
    er2 = EvidenceRecord(
        record_id=uuid.uuid4(),
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        evidence_type="QUICK_MARKS",
        subject="Mathematics",
        test_title="October Test",
        test_date=date(2026, 10, 15),
        total_scored_marks=85.0,
        total_max_marks=100.0,
    )
    db_session.add(er2)
    db_session.commit()

    pulse_oct = service.get_or_synthesize_parent_pulse(
        db_session, sub_a.subscriber_id, child_a.child_id, "2026-10"
    )

    assert pulse_oct.month_key == "2026-10"
    assert pulse_oct.progress_since_last_update.overall_movement_delta == 15.0
    assert pulse_oct.progress_since_last_update.movement_direction == "IMPROVING"
    assert "+15.0%" in pulse_oct.progress_since_last_update.narrative_summary


# =============================================================================
# 4. Max 3 Grounded Actions & "Ask a Subject Expert" Alignment Tests
# =============================================================================

def test_parent_pulse_max_3_grounded_actions_and_expert_handoff(db_session, setup_test_family):
    """
    Home screen action list must:
    1. Contain strictly <= 3 actions.
    2. Suggest Practice & Recheck for unresolved gaps.
    3. Include 'Ask a Subject Expert' when a persistent weak subject (<50%) is detected.
    """
    service = ParentPulseService()
    sub_a = setup_test_family["sub_a"]
    child_a = setup_test_family["child_a"]

    # Seed a persistent weak subject (<50%)
    er = EvidenceRecord(
        record_id=uuid.uuid4(),
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        evidence_type="QUICK_MARKS",
        subject="Physics",
        test_title="Electricity Unit Test",
        test_date=date(2026, 10, 5),
        total_scored_marks=42.0,  # 42% (<50%)
        total_max_marks=100.0,
    )
    db_session.add(er)

    # Seed an active topic gap
    node = CurriculumNode(
        node_id="CBSE_G10_SCI_CH12_OHM",
        board="CBSE",
        standard_class="Class 10",
        subject="Physics",
        chapter_name="Electricity",
        topic_name="Ohm's Law",
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

    actions = service.get_grounded_actions(db_session, sub_a.subscriber_id, child_a.child_id)

    # Rule: Max 3 actions
    assert len(actions) <= 3
    action_types = [a.action_type for a in actions]

    # Action 1: PRACTICE
    assert "PRACTICE" in action_types
    # Action 2: DIAGNOSTIC_RECHECK
    assert "DIAGNOSTIC_RECHECK" in action_types
    # Action 3: Persistent weak subject (<50%) -> ASK_EXPERT
    assert "ASK_EXPERT" in action_types

    expert_act = next(a for a in actions if a.action_type == "ASK_EXPERT")
    assert expert_act.subject == "Physics"
    assert "/marketplace/experts" in expert_act.action_url


# =============================================================================
# 5. Longitudinal Pulse History Tests
# =============================================================================

def test_parent_pulse_history_retrieval(db_session, setup_test_family):
    """Retrieves longitudinal pulse history across multiple months."""
    service = ParentPulseService()
    sub_a = setup_test_family["sub_a"]
    child_a = setup_test_family["child_a"]

    # Seed 2 historical monthly pulses directly
    p1 = ParentPulseRecord(
        pulse_id=uuid.uuid4(),
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        month_key="2026-08",
        improvement_text="Steady Math foundations",
        watch_area_text="Algebra basics",
        next_action_text="15 min review",
        grounded_actions=[],
        movement_delta=2.0,
    )
    p2 = ParentPulseRecord(
        pulse_id=uuid.uuid4(),
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        month_key="2026-09",
        improvement_text="Significant Algebra jump",
        watch_area_text="Quadratic equations",
        next_action_text="Attempt 5 practice questions",
        grounded_actions=[],
        movement_delta=5.0,
    )
    db_session.add_all([p1, p2])
    db_session.commit()

    history = service.get_pulse_history(db_session, sub_a.subscriber_id, child_a.child_id)
    assert len(history) == 2
    month_keys = [h.month_key for h in history]
    assert "2026-08" in month_keys
    assert "2026-09" in month_keys


# =============================================================================
# 6. Non-Negotiable B2C Boundary Security Test
# =============================================================================

def test_parent_pulse_security_boundary(db_session, setup_test_family):
    """Subscriber B cannot access Subscriber A's child Parent Pulse."""
    service = ParentPulseService()
    sub_b = setup_test_family["sub_b"]
    child_a = setup_test_family["child_a"]

    with pytest.raises(PermissionError, match="Child profile not found or not authorized"):
        service.get_or_synthesize_parent_pulse(
            db=db_session,
            subscriber_id=sub_b.subscriber_id,
            child_id=child_a.child_id,
        )
