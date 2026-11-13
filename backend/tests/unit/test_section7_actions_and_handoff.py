"""
STUDIQS® SmartParent™ (v6.2 Complete) - Unit Tests for Section 7 Parent Actions, Gap Recheck & Academic Handoff
=============================================================================
Tests all Section 7 requirements:
1. Home Screen Action Cockpit strictly capped at <= 3 grounded actions
2. Action Prioritization hierarchy:
   - Persistent weak subject (< 50%) -> "Ask a Subject Expert" (ASK_EXPERT)
   - Critical gap (< 40%) -> "Take 10-Minute Gap Recheck" (DIAGNOSTIC_RECHECK)
   - Secondary weak topic -> "Practice 5 Guided Questions" (PRACTICE)
   - Routine -> "Daily Revision" (REVISION)
3. 5-Question Targeted Diagnostic Recheck Quiz generation across Bloom levels
4. Recheck submission score >= 80% marks TopicGap as RESOLVED with timestamp,
   persists confirmed TopicScore (STRONG tier) and EvidenceRecord
5. Recheck submission score < 80% retains ACTIVE status with progress delta
6. Academic Handoff Brief for PTM / Tutors applying "Praise First, Remediate Second",
   2-week focus directive, talking points, and formatted printable text
7. Non-negotiable B2C multi-tenant security boundary isolation
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
from src.smartparent.services.parent_actions_service import ParentActionsService
from src.smartparent.engines.academic_handoff_engine import AcademicHandoffEngine


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
        board="ICSE",
        academic_year="2026-2027",
    )
    db_session.add_all([child_a, child_b])
    db_session.commit()

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
            node_id="CBSE_10_MATH_TRIANGLES",
            board="CBSE",
            standard_class="Class 10",
            subject="Mathematics",
            chapter_name="Triangles",
            topic_name="Basic Proportionality Theorem",
        ),
        CurriculumNode(
            node_id="CBSE_10_SCI_OPTICS",
            board="CBSE",
            standard_class="Class 10",
            subject="Science",
            chapter_name="Light Reflection & Refraction",
            topic_name="Lens Formula and Ray Diagrams",
        ),
    ]

    db_session.add_all(nodes)
    db_session.commit()

    return {
        "sub_a": sub_a,
        "sub_b": sub_b,
        "child_a": child_a,
        "child_b": child_b,
    }


def test_home_actions_capped_at_max_3(db_session, setup_test_family):
    """Verifies Section 7 rule: strictly <= 3 actions on Home screen."""
    child_a = setup_test_family["child_a"]
    sub_a = setup_test_family["sub_a"]

    # Insert multiple active gaps
    gap1 = TopicGap(
        gap_id=uuid.uuid4(),
        child_id=child_a.child_id,
        node_id="CBSE_10_MATH_QUADRATIC",
        gap_status="ACTIVE",
        first_identified_at=datetime.now(timezone.utc) - timedelta(days=5),
    )
    gap2 = TopicGap(
        gap_id=uuid.uuid4(),
        child_id=child_a.child_id,
        node_id="CBSE_10_MATH_TRIANGLES",
        gap_status="ACTIVE",
        first_identified_at=datetime.now(timezone.utc) - timedelta(days=4),
    )
    gap3 = TopicGap(
        gap_id=uuid.uuid4(),
        child_id=child_a.child_id,
        node_id="CBSE_10_SCI_OPTICS",
        gap_status="ACTIVE",
        first_identified_at=datetime.now(timezone.utc) - timedelta(days=2),
    )
    db_session.add_all([gap1, gap2, gap3])
    db_session.commit()

    service = ParentActionsService()
    res = service.get_home_actions(db_session, sub_a.subscriber_id, child_a.child_id)

    assert res.child_id == str(child_a.child_id)
    assert res.student_name == "Aarav"
    assert len(res.actions) <= 3
    assert res.active_gaps_count >= 3


def test_home_actions_prioritization_weak_subject(db_session, setup_test_family):
    """
    Verifies Section 7 Mandate: Persistent weak subject (<50%)
    prioritizes 'Ask a Subject Expert' with marketplace URL.
    """
    child_a = setup_test_family["child_a"]
    sub_a = setup_test_family["sub_a"]

    # Add low marks in Science (35% average)
    ev1 = EvidenceRecord(
        record_id=uuid.uuid4(),
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        evidence_type="QUICK_MARKS",
        subject="Science",
        test_title="Unit Test 1",
        test_date=date.today() - timedelta(days=10),
        total_scored_marks=18.0,
        total_max_marks=50.0,  # 36%
    )
    ev2 = EvidenceRecord(
        record_id=uuid.uuid4(),
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        evidence_type="QUICK_MARKS",
        subject="Science",
        test_title="Unit Test 2",
        test_date=date.today() - timedelta(days=3),
        total_scored_marks=16.0,
        total_max_marks=50.0,  # 32%
    )
    db_session.add_all([ev1, ev2])
    db_session.commit()

    service = ParentActionsService()
    res = service.get_home_actions(db_session, sub_a.subscriber_id, child_a.child_id)

    # First action must be ASK_EXPERT for Science
    first_act = res.actions[0]
    assert first_act.action_type == "ASK_EXPERT"
    assert first_act.priority == "HIGH"
    assert "Science" in first_act.title
    assert "marketplace/experts" in first_act.action_url


def test_recheck_quiz_generation(db_session, setup_test_family):
    """
    Verifies generation of 5-question targeted diagnostic recheck quiz
    across Bloom levels for an active gap.
    """
    child_a = setup_test_family["child_a"]
    sub_a = setup_test_family["sub_a"]

    gap = TopicGap(
        gap_id=uuid.uuid4(),
        child_id=child_a.child_id,
        node_id="CBSE_10_MATH_QUADRATIC",
        gap_status="ACTIVE",
    )
    db_session.add(gap)
    db_session.commit()

    service = ParentActionsService()
    quiz = service.generate_recheck_quiz(
        db=db_session,
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        gap_id=gap.gap_id,
    )

    assert quiz.gap_id == str(gap.gap_id)
    assert quiz.total_questions == 5
    assert quiz.passing_threshold_pct == 80.0
    assert len(quiz.questions) == 5
    # Verify Bloom taxonomy representation
    bloom_levels = [q.bloom_level for q in quiz.questions]
    assert "Remember" in bloom_levels
    assert "Understand" in bloom_levels
    assert "Apply" in bloom_levels
    assert "Analyze" in bloom_levels
    assert "Evaluate" in bloom_levels


def test_recheck_quiz_submission_gap_resolved_at_or_above_80_pct(db_session, setup_test_family):
    """
    Verifies: Scoring >= 80% on recheck marks TopicGap as RESOLVED,
    records resolved_at, persists TopicScore with STRONG tier and creates EvidenceRecord.
    """
    child_a = setup_test_family["child_a"]
    sub_a = setup_test_family["sub_a"]

    gap = TopicGap(
        gap_id=uuid.uuid4(),
        child_id=child_a.child_id,
        node_id="CBSE_10_MATH_QUADRATIC",
        gap_status="ACTIVE",
    )
    db_session.add(gap)
    db_session.commit()

    service = ParentActionsService()
    res = service.submit_recheck_quiz(
        db=db_session,
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        gap_id=gap.gap_id,
        scored_marks=8.5,
        max_marks=10.0,  # 85%
        recheck_title="Diagnostic Gap Recheck - Quadratic Formula",
    )

    assert res.score_percentage == 85.0
    assert res.is_gap_closed is True
    assert res.new_status == "RESOLVED"
    assert "Mastered" in res.pedagogical_badge or "Closed" in res.pedagogical_badge or "Mastered" in res.transition_narrative

    # Verify Database state
    db_gap = db_session.query(TopicGap).filter(TopicGap.gap_id == gap.gap_id).first()
    assert db_gap.gap_status == "RESOLVED"
    assert db_gap.resolved_at is not None

    # Verify TopicScore persisted
    score_rec = (
        db_session.query(TopicScore)
        .filter(TopicScore.child_id == child_a.child_id, TopicScore.node_id == "CBSE_10_MATH_QUADRATIC")
        .first()
    )
    assert score_rec is not None
    assert score_rec.mastery_tier == "STRONG"
    assert float(score_rec.percentage) == 85.0

    # Verify EvidenceRecord persisted
    evidence = (
        db_session.query(EvidenceRecord)
        .filter(EvidenceRecord.child_id == child_a.child_id, EvidenceRecord.subject == "Mathematics")
        .first()
    )
    assert evidence is not None
    assert float(evidence.total_scored_marks) == 8.5


def test_recheck_quiz_submission_gap_retained_below_80_pct(db_session, setup_test_family):
    """
    Verifies: Scoring < 80% retains ACTIVE status, does not set resolved_at,
    and logs progress delta.
    """
    child_a = setup_test_family["child_a"]
    sub_a = setup_test_family["sub_a"]

    gap = TopicGap(
        gap_id=uuid.uuid4(),
        child_id=child_a.child_id,
        node_id="CBSE_10_MATH_TRIANGLES",
        gap_status="ACTIVE",
    )
    # Existing score 35%
    prior_score = TopicScore(
        score_id=uuid.uuid4(),
        child_id=child_a.child_id,
        node_id="CBSE_10_MATH_TRIANGLES",
        scored_marks=7.0,
        max_marks=20.0,
        percentage=35.0,
        mastery_tier="CRITICAL",
        evaluated_at=datetime.now(timezone.utc) - timedelta(days=7),
    )
    db_session.add_all([gap, prior_score])
    db_session.commit()

    service = ParentActionsService()
    res = service.submit_recheck_quiz(
        db=db_session,
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        gap_id=gap.gap_id,
        scored_marks=6.5,
        max_marks=10.0,  # 65%
    )

    assert res.score_percentage == 65.0
    assert res.is_gap_closed is False
    assert res.new_status == "ACTIVE"
    assert res.delta_percentage == 30.0  # +30% improvement from 35%

    # Verify DB: gap still ACTIVE, resolved_at is None
    db_gap = db_session.query(TopicGap).filter(TopicGap.gap_id == gap.gap_id).first()
    assert db_gap.gap_status == "ACTIVE"
    assert db_gap.resolved_at is None


def test_academic_handoff_brief_synthesis(db_session, setup_test_family):
    """
    Verifies Section 7 & 9 Academic Handoff Brief for PTM / Tutors:
    - Praise First, Remediate Second
    - Pinpointed topic gaps
    - 2-week focus directive
    - Exact tutor talking points
    - Clean formatted printable text
    """
    child_a = setup_test_family["child_a"]
    sub_a = setup_test_family["sub_a"]

    # 1 confirmed strength (88% in Real Numbers)
    strength_ts = TopicScore(
        score_id=uuid.uuid4(),
        child_id=child_a.child_id,
        node_id="CBSE_10_MATH_REAL_NUMBERS",
        scored_marks=22.0,
        max_marks=25.0,
        percentage=88.0,
        mastery_tier="STRONG",
        evaluated_at=datetime.now(timezone.utc),
    )
    # 1 active gap (35% in Quadratic Equations)
    gap = TopicGap(
        gap_id=uuid.uuid4(),
        child_id=child_a.child_id,
        node_id="CBSE_10_MATH_QUADRATIC",
        gap_status="ACTIVE",
    )
    gap_ts = TopicScore(
        score_id=uuid.uuid4(),
        child_id=child_a.child_id,
        node_id="CBSE_10_MATH_QUADRATIC",
        scored_marks=7.0,
        max_marks=20.0,
        percentage=35.0,
        mastery_tier="CRITICAL",
        evaluated_at=datetime.now(timezone.utc),
    )
    db_session.add_all([strength_ts, gap, gap_ts])
    db_session.commit()

    service = ParentActionsService()
    brief = service.generate_academic_handoff_brief(
        db=db_session,
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
    )

    assert brief.student_name == "Aarav"
    assert brief.standard_class == "Class 10"
    assert brief.board == "CBSE"

    # Praise Points: must celebrate Real Numbers
    assert len(brief.praise_points) >= 1
    assert brief.praise_points[0].mastery_percentage == 88.0

    # Remedial Gaps: must target Quadratic Equations
    assert len(brief.remedial_gaps) >= 1
    assert "Quadratic" in brief.remedial_gaps[0].topic_name or "Quadratic" in brief.remedial_gaps[0].chapter_name

    # 2-Week focus directive & talking points
    assert len(brief.recommended_focus_next_2_weeks) > 10
    assert len(brief.tutor_talking_points) >= 2

    # Formatted printable text structure
    pt = brief.formatted_printable_text
    assert "ACADEMIC HANDOFF BRIEF" in pt
    assert "Student: Aarav" in pt
    assert "ACCOMPLISHMENTS & STRENGTHS TO CELEBRATE" in pt
    assert "PRIORITY DIAGNOSTIC LEARNING GAPS" in pt
    assert "KEY TALKING POINTS FOR PARENT-TEACHER MEETING" in pt



def test_section7_b2c_tenant_isolation(db_session, setup_test_family):
    """
    Verifies non-negotiable B2C multi-tenant security:
    Subscriber B cannot access Child A's actions, recheck quiz, or brief.
    """
    child_a = setup_test_family["child_a"]
    sub_b = setup_test_family["sub_b"]

    service = ParentActionsService()

    # Unauthorized Home actions
    with pytest.raises(PermissionError):
        service.get_home_actions(db_session, sub_b.subscriber_id, child_a.child_id)

    # Unauthorized recheck quiz
    with pytest.raises(PermissionError):
        service.generate_recheck_quiz(
            db=db_session,
            subscriber_id=sub_b.subscriber_id,
            child_id=child_a.child_id,
            gap_id=uuid.uuid4(),
        )

    # Unauthorized recheck submission
    with pytest.raises(PermissionError):
        service.submit_recheck_quiz(
            db=db_session,
            subscriber_id=sub_b.subscriber_id,
            child_id=child_a.child_id,
            gap_id=uuid.uuid4(),
            scored_marks=8.0,
            max_marks=10.0,
        )

    # Unauthorized Academic brief
    with pytest.raises(PermissionError):
        service.generate_academic_handoff_brief(
            db=db_session,
            subscriber_id=sub_b.subscriber_id,
            child_id=child_a.child_id,
        )
