"""
STUDIQS® SmartParent™ - Diagnostic Intelligence & Topic Scoring Unit Tests
=============================================================================
Module: tests.unit.test_topic_scoring

Verifies:
  1. Multi-Tenant Isolation for Student 360 telemetry.
  2. Topic Mastery tier aggregation (STRONG, AVERAGE, WEAK, CRITICAL).
  3. Learning gap status transitions and resolution timestamps.
  4. Curriculum taxonomy search and Tamil script exclusion filter.
=============================================================================
"""

import uuid
from datetime import datetime, timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID

@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"

@compiles(PG_UUID, "sqlite")
def compile_uuid_sqlite(type_, compiler, **kw):
    return "CHAR(36)"

from src.smartparent.db.base import Base
from src.smartparent.db.models.auth import Subscriber, Child
from src.smartparent.db.models.curriculum import CurriculumNode
from src.smartparent.db.models.diagnostic import TopicScore, TopicGap
from src.smartparent.schemas.diagnostic import ResolveGapRequest
from src.smartparent.services.diagnostic_service import DiagnosticService
from src.smartparent.utils.text_cleaner import contains_tamil_script


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def seed_diagnostic_data(test_db):
    sub_id = uuid.uuid4()
    other_sub_id = uuid.uuid4()
    child_id = uuid.uuid4()
    other_child_id = uuid.uuid4()

    sub = Subscriber(
        subscriber_id=sub_id,
        mobile_number="9876543201",
        parent_name="Kavitha R.",
        password_hash="hash_pw",
    )
    other_sub = Subscriber(
        subscriber_id=other_sub_id,
        mobile_number="9876543202",
        parent_name="Other Parent",
        password_hash="hash_pw",
    )

    child = Child(
        child_id=child_id,
        subscriber_id=sub_id,
        student_name="Surya",
        standard_class="Class 10",
        board="CBSE",
        academic_year="2025-2026",
    )
    other_child = Child(
        child_id=other_child_id,
        subscriber_id=other_sub_id,
        student_name="Aravind",
        standard_class="Class 10",
        board="CBSE",
        academic_year="2025-2026",
    )

    node1 = CurriculumNode(
        node_id="MATH-G10-001",
        board="CBSE",
        standard_class="Class 10",
        subject="Mathematics",
        chapter_name="Trigonometry",
        topic_name="Trigonometric Identities",
    )
    node2 = CurriculumNode(
        node_id="MATH-G10-002",
        board="CBSE",
        standard_class="Class 10",
        subject="Mathematics",
        chapter_name="Statistics",
        topic_name="Mean and Median",
    )

    test_db.add_all([sub, other_sub, child, other_child, node1, node2])
    test_db.commit()

    # Add TopicScores for child: 1 STRONG (85%), 1 WEAK (45%)
    ts1 = TopicScore(
        score_id=uuid.uuid4(),
        child_id=child_id,
        node_id="MATH-G10-001",
        scored_marks=17.0,
        max_marks=20.0,
        percentage=85.0,
        mastery_tier="STRONG",
        evaluated_at=datetime.now(timezone.utc),
    )
    ts2 = TopicScore(
        score_id=uuid.uuid4(),
        child_id=child_id,
        node_id="MATH-G10-002",
        scored_marks=9.0,
        max_marks=20.0,
        percentage=45.0,
        mastery_tier="WEAK",
        evaluated_at=datetime.now(timezone.utc),
    )

    # Add active learning gap for weak topic
    gap = TopicGap(
        gap_id=uuid.uuid4(),
        child_id=child_id,
        node_id="MATH-G10-002",
        gap_status="ACTIVE",
        first_identified_at=datetime.now(timezone.utc),
    )

    test_db.add_all([ts1, ts2, gap])
    test_db.commit()

    return {
        "subscriber_id": sub_id,
        "other_subscriber_id": other_sub_id,
        "child_id": child_id,
        "other_child_id": other_child_id,
        "gap_id": gap.gap_id,
    }


class TestDiagnosticService:

    def test_summary_telemetry_aggregation(self, test_db, seed_diagnostic_data):
        """Verifies Student 360 mastery tiers, total evaluated topics, and overall percentage."""
        service = DiagnosticService()
        res = service.get_child_diagnostic_summary(
            db=test_db,
            subscriber_id=seed_diagnostic_data["subscriber_id"],
            child_id=seed_diagnostic_data["child_id"],
        )

        assert res.student_name == "Surya"
        assert res.total_evaluated_topics == 2
        assert res.strong_topics_count == 1
        assert res.weak_topics_count == 1
        assert res.average_topics_count == 0
        assert res.critical_topics_count == 0
        assert res.active_gaps_count == 1
        # Total scored = 26 / 40 = 65%
        assert res.overall_mastery_percentage == 65.0

    def test_multi_tenant_isolation_on_diagnostic_data(self, test_db, seed_diagnostic_data):
        """Cross-tenant firewall blocks unauthorized subscribers from reading student telemetry."""
        service = DiagnosticService()
        with pytest.raises(PermissionError) as exc_info:
            service.get_child_diagnostic_summary(
                db=test_db,
                subscriber_id=seed_diagnostic_data["other_subscriber_id"],  # Unauthorized!
                child_id=seed_diagnostic_data["child_id"],
            )
        assert "Access Denied" in str(exc_info.value)

    def test_learning_gap_resolution_lifecycle(self, test_db, seed_diagnostic_data):
        """Resolving a gap marks it RESOLVED and sets a UTC resolved_at timestamp."""
        service = DiagnosticService()
        req = ResolveGapRequest(gap_status="RESOLVED", notes="Remediated through diagnostic practice set")
        res = service.resolve_gap(
            db=test_db,
            subscriber_id=seed_diagnostic_data["subscriber_id"],
            gap_id=seed_diagnostic_data["gap_id"],
            payload=req,
        )

        assert res.new_status == "RESOLVED"
        assert res.resolved_at is not None

        # Verify DB persistence
        gap = test_db.query(TopicGap).filter_by(gap_id=seed_diagnostic_data["gap_id"]).one()
        assert gap.gap_status == "RESOLVED"
        assert gap.resolved_at is not None

    def test_tamil_script_exclusion_filter(self):
        """Enforces Tamil language exclusion across curriculum topics."""
        tamil_sample = "தமிழ் பாடம் இயல் 1"
        english_sample = "Physics: Reflection and Refraction"
        assert contains_tamil_script(tamil_sample) is True
        assert contains_tamil_script(english_sample) is False

