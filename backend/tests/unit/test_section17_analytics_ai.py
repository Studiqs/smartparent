"""
STUDIQS® SmartParent™ (v6.2 Complete) - Unit Tests for Section 17 Analytics, AI & Topic-Repository Rules
=============================================================================
Tests all Section 17 requirements:
1. BaseEngine health & circuit state
2. Deterministic calculations (strictly server-owned math, zero LLM hallucination)
3. Trajectory movement deltas & mathematical mastery tiers (STRONG, AVERAGE, WEAK, CRITICAL)
4. Grounded AI explanations ("No new evidence means no fabricated change")
5. Multi-lingual grounded explanations (English & Tamil)
6. Feedback origin visual badging ("Subject Expert Feedback" vs "AI Learning Summary")
7. Immutable source provenance generation with cryptographic SHA256 audit hash
8. Topic-Repository taxonomy & canonical node ID validation
9. Gate 2 Zero-Fake-Mastery enforcement (aggregate-only vs granular evidence)
10. Database mapping of Expert Evaluation into Student 360 TopicScore & Gap resolution
11. Non-negotiable B2C multi-tenant security boundary
12. FastAPI REST API endpoints via TestClient
=============================================================================
"""

import uuid
from datetime import date, datetime, timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.pool import StaticPool
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.smartparent.db.base import Base
from src.smartparent.db.models.auth import Subscriber, Child
from src.smartparent.db.models.assessment import EvidenceRecord
from src.smartparent.db.models.curriculum import CurriculumNode
from src.smartparent.db.models.diagnostic import TopicScore, TopicGap
from src.smartparent.engines.section_17_analytics_ai.analytics_ai_engine import AnalyticsAiEngine
from src.smartparent.services.analytics_ai_service import AnalyticsAiService
from src.smartparent.schemas.analytics_ai_rules import (
    FeedbackOriginEnum,
    MasteryTierEnum,
    MovementDirectionEnum,
    DeterministicScorePoint,
    DeterministicCalculationRequest,
    GroundedAiExplanationRequest,
    TopicNodeValidationRequest,
    Gate2TopicIntelligenceCheckRequest,
    MapExpertEvaluationToIntelligenceRequest,
)
from src.smartparent.api.v1.analytics_ai import (
    router as analytics_router,
    get_db,
    get_current_subscriber_id,
)


# SQLite dialect compatibility for Postgres JSONB and UUID
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
            TopicScore.__table__,
            TopicGap.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def setup_analytics_data(db_session):
    """Seed authenticated subscriber, child, curriculum nodes, and active gap."""
    sub_a = Subscriber(
        subscriber_id=uuid.uuid4(),
        mobile_number="+919876543210",
        parent_name="Sundaram R.",
        email="sundaram.r@example.com",
        password_hash="mock_hash_sundar",
    )
    child_a = Child(
        child_id=uuid.uuid4(),
        subscriber_id=sub_a.subscriber_id,
        student_name="Pranav Sundaram",
        standard_class="Class 10",
        board="CBSE",
        academic_year="2026-2027",
    )

    sub_b = Subscriber(
        subscriber_id=uuid.uuid4(),
        mobile_number="+919123456789",
        parent_name="Meenakshi S.",
        email="meena.s@example.com",
        password_hash="mock_hash_meena",
    )
    child_b = Child(
        child_id=uuid.uuid4(),
        subscriber_id=sub_b.subscriber_id,
        student_name="Divya Meenakshi",
        standard_class="Class 8",
        board="ICSE",
        academic_year="2026-2027",
    )

    node_quad = CurriculumNode(
        node_id="CBSE_10_MATH_QUADRATIC",
        board="CBSE",
        standard_class="Class 10",
        subject="Mathematics",
        chapter_name="Quadratic Equations",
        topic_name="Quadratic Formula & Discriminant",
    )
    node_trig = CurriculumNode(
        node_id="CBSE_10_MATH_TRIGONOMETRY",
        board="CBSE",
        standard_class="Class 10",
        subject="Mathematics",
        chapter_name="Trigonometry",
        topic_name="Trigonometric Ratios",
    )

    # Active gap in Quadratic Equations
    gap_quad = TopicGap(
        gap_id=uuid.uuid4(),
        child_id=child_a.child_id,
        node_id=node_quad.node_id,
        gap_status="ACTIVE",
    )

    db_session.add_all([sub_a, child_a, sub_b, child_b, node_quad, node_trig, gap_quad])
    db_session.commit()

    return {
        "sub_a": sub_a,
        "child_a": child_a,
        "sub_b": sub_b,
        "child_b": child_b,
        "node_quad": node_quad,
        "node_trig": node_trig,
        "gap_quad": gap_quad,
    }


# =============================================================================
# 1. BaseEngine Health & Lifecycle
# =============================================================================

def test_analytics_ai_engine_health():
    engine = AnalyticsAiEngine()
    health = engine.health_check()
    assert health["status"] == "healthy"
    assert health["circuit_state"] == "CLOSED"


# =============================================================================
# 2. Deterministic Server-Owned Calculations
# =============================================================================

def test_deterministic_calculation_math_precision():
    engine = AnalyticsAiEngine()
    scores = [
        DeterministicScorePoint(score=45.0, max_marks=100.0),
        DeterministicScorePoint(score=60.0, max_marks=100.0),
        DeterministicScorePoint(score=75.0, max_marks=100.0),
    ]
    res = engine.calculate_deterministic_metrics("Mathematics", scores)

    assert res.subject == "Mathematics"
    assert res.latest_score_pct == 75.0
    assert res.prior_score_pct == 60.0
    assert res.movement_delta == 15.0
    assert res.movement_direction == MovementDirectionEnum.IMPROVING
    assert res.rolling_average_pct == 60.0  # (45+60+75)/3
    assert res.mastery_tier == MasteryTierEnum.AVERAGE  # 75% is in [60, 80)
    assert res.is_server_deterministic is True


def test_deterministic_calculation_direction_and_mastery_tiers():
    engine = AnalyticsAiEngine()

    # Drop: 85% -> 50%
    scores_drop = [
        DeterministicScorePoint(score=85.0, max_marks=100.0),
        DeterministicScorePoint(score=50.0, max_marks=100.0),
    ]
    res_drop = engine.calculate_deterministic_metrics("Science", scores_drop)
    assert res_drop.movement_delta == -35.0
    assert res_drop.movement_direction == MovementDirectionEnum.DECLINING
    assert res_drop.mastery_tier == MasteryTierEnum.WEAK

    # Critical tier (< 40%)
    scores_crit = [DeterministicScorePoint(score=32.0, max_marks=100.0)]
    res_crit = engine.calculate_deterministic_metrics("Physics", scores_crit)
    assert res_crit.mastery_tier == MasteryTierEnum.CRITICAL
    assert res_crit.movement_direction == MovementDirectionEnum.STABLE  # No prior

    # Strong tier (>= 80%)
    scores_strong = [DeterministicScorePoint(score=92.0, max_marks=100.0)]
    res_strong = engine.calculate_deterministic_metrics("English", scores_strong)
    assert res_strong.mastery_tier == MasteryTierEnum.STRONG

    # Stable range (-1.5 to +1.5)
    scores_stable = [
        DeterministicScorePoint(score=70.0, max_marks=100.0),
        DeterministicScorePoint(score=71.0, max_marks=100.0),
    ]
    res_stable = engine.calculate_deterministic_metrics("Chemistry", scores_stable)
    assert res_stable.movement_delta == 1.0
    assert res_stable.movement_direction == MovementDirectionEnum.STABLE


# =============================================================================
# 3. Grounded AI Explanations ("No new evidence = No fabricated change")
# =============================================================================

def test_grounded_ai_no_evidence_no_fabricated_change():
    engine = AnalyticsAiEngine()
    req = GroundedAiExplanationRequest(
        student_name="Ananya",
        subject="Mathematics",
        latest_score_pct=72.0,
        prior_score_pct=72.0,
        movement_delta=0.0,
        movement_direction=MovementDirectionEnum.STABLE,
        has_new_evidence=False,  # No new evidence uploaded
        language="en",
    )
    res = engine.generate_grounded_ai_explanation(req)

    assert res.has_fabricated_change is False
    assert "No New Assessments" in res.headline
    assert "without fabricated changes" in res.narrative_explanation
    assert res.feedback_badge == "AI Learning Summary"
    assert res.feedback_origin == FeedbackOriginEnum.AUTOMATED_AI_NARRATIVE


def test_grounded_ai_improving_and_declining_narratives():
    engine = AnalyticsAiEngine()

    # Improving
    req_imp = GroundedAiExplanationRequest(
        student_name="Pranav",
        subject="Mathematics",
        latest_score_pct=82.0,
        prior_score_pct=74.0,
        movement_delta=8.0,
        movement_direction=MovementDirectionEnum.IMPROVING,
        has_new_evidence=True,
    )
    res_imp = engine.generate_grounded_ai_explanation(req_imp)
    assert "+8.0%" in res_imp.headline
    assert "Pranav achieved +8.0% upward momentum" in res_imp.narrative_explanation

    # Declining
    req_dec = GroundedAiExplanationRequest(
        student_name="Pranav",
        subject="Physics",
        latest_score_pct=48.0,
        prior_score_pct=60.0,
        movement_delta=-12.0,
        movement_direction=MovementDirectionEnum.DECLINING,
        active_gaps=["Ohm's Law", "Ray Optics"],
        has_new_evidence=True,
    )
    res_dec = engine.generate_grounded_ai_explanation(req_dec)
    assert "-12.0%" in res_dec.headline
    assert "Ohm's Law" in res_dec.narrative_explanation


def test_grounded_ai_tamil_language():
    engine = AnalyticsAiEngine()
    req = GroundedAiExplanationRequest(
        student_name="கார்த்திக்",
        subject="கணிதம்",
        latest_score_pct=85.0,
        prior_score_pct=75.0,
        movement_delta=10.0,
        movement_direction=MovementDirectionEnum.IMPROVING,
        has_new_evidence=True,
        language="ta",
    )
    res = engine.generate_grounded_ai_explanation(req)
    assert "முன்னேற்றம்" in res.headline
    assert "கார்த்திக்" in res.narrative_explanation


# =============================================================================
# 4. Visual Badging & Origin Separation
# =============================================================================

def test_feedback_origin_visual_badging():
    engine = AnalyticsAiEngine()

    # Human Expert
    expert_badge = engine.badge_feedback(
        text="Step marks deducted in question 4 due to missing discriminant formula.",
        origin=FeedbackOriginEnum.HUMAN_EXPERT,
        author_name="Dr. Raghavan",
    )
    assert expert_badge["badge_title"] == "Subject Expert Feedback"
    assert "Dr. Raghavan" in expert_badge["author_label"]
    assert "Verified Human Examiner" in expert_badge["disclaimer"]
    assert expert_badge["origin"] == "HUMAN_EXPERT"

    # AI Narrative
    ai_badge = engine.badge_feedback(
        text="Consistent trajectory maintained across algebra concepts.",
        origin=FeedbackOriginEnum.AUTOMATED_AI_NARRATIVE,
    )
    assert ai_badge["badge_title"] == "AI Learning Summary"
    assert "Studiqs Interpretive Engine" in ai_badge["author_label"]
    assert ai_badge["origin"] == "AUTOMATED_AI_NARRATIVE"

    # Deterministic Rule
    det_badge = engine.badge_feedback(
        text="75.0% score established as baseline.",
        origin=FeedbackOriginEnum.DETERMINISTIC_RULE,
    )
    assert det_badge["badge_title"] == "Diagnostic Metric"
    assert det_badge["origin"] == "DETERMINISTIC_RULE"


# =============================================================================
# 5. Immutable Source Provenance Generator
# =============================================================================

def test_immutable_expert_provenance_generation():
    engine = AnalyticsAiEngine()
    exp_id = str(uuid.uuid4())
    eval_id = str(uuid.uuid4())
    date_iso = "2026-10-30T10:00:00Z"
    nodes = ["CBSE_10_MATH_QUADRATIC", "CBSE_10_MATH_REAL_NUMBERS"]

    prov = engine.generate_expert_provenance(
        expert_id=exp_id,
        evaluation_id=eval_id,
        completion_date=date_iso,
        marks_awarded=85.0,
        total_max_marks=100.0,
        topic_node_ids=nodes,
    )
    assert prov.expert_id == exp_id
    assert prov.evaluation_id == eval_id
    assert prov.evidence_type == "EXPERT_EVALUATION"
    assert prov.percentage == 85.0
    assert len(prov.audit_hash) == 64  # SHA256 hex length

    # Altering nodes changes audit hash
    tampered_prov = engine.generate_expert_provenance(
        expert_id=exp_id,
        evaluation_id=eval_id,
        completion_date=date_iso,
        marks_awarded=85.0,
        total_max_marks=100.0,
        topic_node_ids=["CBSE_10_MATH_QUADRATIC", "TAMPERED_NODE"],
    )
    assert prov.audit_hash != tampered_prov.audit_hash


# =============================================================================
# 6. Topic-Repository Taxonomy & Gate 2 Validation
# =============================================================================

def test_topic_repository_node_validation():
    engine = AnalyticsAiEngine()

    # Valid node
    req_valid = TopicNodeValidationRequest(
        node_id="CBSE_10_MATH_QUAD",
        board="CBSE",
        standard_class="Class 10",
        subject="Mathematics",
        chapter_name="Quadratic Equations",
        topic_name="Quadratic Formula",
    )
    res_valid = engine.validate_topic_repository_node(req_valid)
    assert res_valid.is_valid is True
    assert "CBSE > Class 10 > Mathematics" in res_valid.hierarchy_path

    # Invalid board & class
    req_invalid = TopicNodeValidationRequest(
        node_id="CUSTOM_NODE",
        board="OXFORD_BOARD",
        standard_class="Class 15",
        subject="Math",
        chapter_name="Ch1",
        topic_name="T1",
    )
    res_invalid = engine.validate_topic_repository_node(req_invalid)
    assert res_invalid.is_valid is False
    assert len(res_invalid.validation_errors) == 2


def test_gate2_topic_intelligence_boundary_enforcement():
    engine = AnalyticsAiEngine()

    # Aggregate evidence attempting to update topic mastery -> BLOCKED
    check_agg = engine.assert_gate2_topic_intelligence_boundary(
        evidence_type="QUICK_MARKS",
        requested_topic_mastery=True,
    )
    assert check_agg.is_topic_intelligence_eligible is False
    assert check_agg.status_code == "LOCKED_AGGREGATE_ONLY"
    assert "Gate 2 Locked" in check_agg.enforcement_message

    check_ocr = engine.assert_gate2_topic_intelligence_boundary(
        evidence_type="RESULT_CARD_OCR",
        requested_topic_mastery=True,
    )
    assert check_ocr.is_topic_intelligence_eligible is False
    assert check_ocr.status_code == "LOCKED_AGGREGATE_ONLY"

    # Granular evidence -> ALLOWED
    check_qp = engine.assert_gate2_topic_intelligence_boundary(
        evidence_type="QUESTION_PAPER",
        requested_topic_mastery=True,
    )
    assert check_qp.is_topic_intelligence_eligible is True
    assert check_qp.status_code == "ELIGIBLE_GRANULAR"

    check_exp = engine.assert_gate2_topic_intelligence_boundary(
        evidence_type="EXPERT_EVALUATION",
        requested_topic_mastery=True,
    )
    assert check_exp.is_topic_intelligence_eligible is True
    assert check_exp.status_code == "ELIGIBLE_GRANULAR"


# =============================================================================
# 7. Service Layer Integration (Mapping Expert Evaluation with Provenance)
# =============================================================================

def test_service_map_expert_evaluation_with_provenance(db_session, setup_analytics_data):
    data = setup_analytics_data
    service = AnalyticsAiService()

    eval_uuid = str(uuid.uuid4())
    expert_uuid = str(uuid.uuid4())

    req = MapExpertEvaluationToIntelligenceRequest(
        child_id=str(data["child_a"].child_id),
        evaluation_id=eval_uuid,
        expert_id=expert_uuid,
        subject="Mathematics",
        marks_awarded=88.0,
        total_max_marks=100.0,
        topic_ratings={
            "CBSE_10_MATH_QUADRATIC": 85.0,  # Resolves the active gap!
            "CBSE_10_MATH_TRIGONOMETRY": 90.0,
        },
        expert_feedback_text="Excellent algebraic execution in factoring.",
    )

    resp = service.map_expert_evaluation_to_intelligence(
        db=db_session,
        subscriber_id=data["sub_a"].subscriber_id,
        request=req,
    )

    assert resp.success is True
    assert resp.updated_topic_scores_count == 2
    assert resp.resolved_gaps_count == 1  # Quadratic gap resolved!
    assert resp.feedback_badge == "Subject Expert Feedback"
    assert resp.feedback_origin == FeedbackOriginEnum.HUMAN_EXPERT
    assert resp.provenance.expert_id == expert_uuid

    # Check database state
    gap = db_session.query(TopicGap).filter(TopicGap.gap_id == data["gap_quad"].gap_id).first()
    assert gap.gap_status == "RESOLVED"

    ts = (
        db_session.query(TopicScore)
        .filter(TopicScore.child_id == data["child_a"].child_id, TopicScore.node_id == "CBSE_10_MATH_QUADRATIC")
        .first()
    )
    assert float(ts.percentage) == 85.0

    # Check evidence record created with provenance
    ev = (
        db_session.query(EvidenceRecord)
        .filter(EvidenceRecord.child_id == data["child_a"].child_id, EvidenceRecord.evidence_type == "EXPERT_EVALUATION")
        .first()
    )
    assert ev is not None
    assert expert_uuid in ev.storage_file_path
    assert eval_uuid in ev.storage_file_path


def test_service_map_expert_evaluation_b2c_isolation(db_session, setup_analytics_data):
    data = setup_analytics_data
    service = AnalyticsAiService()

    req = MapExpertEvaluationToIntelligenceRequest(
        child_id=str(data["child_a"].child_id),
        evaluation_id=str(uuid.uuid4()),
        expert_id=str(uuid.uuid4()),
        subject="Mathematics",
        marks_awarded=70.0,
        topic_ratings={"CBSE_10_MATH_QUADRATIC": 70.0},
        expert_feedback_text="Need more practice.",
    )

    # Foreign subscriber B attempting to map to Child A -> Forbidden
    with pytest.raises(PermissionError, match="not authorized"):
        service.map_expert_evaluation_to_intelligence(
            db=db_session,
            subscriber_id=data["sub_b"].subscriber_id,
            request=req,
        )


# =============================================================================
# 8. FastAPI Router Endpoints via TestClient
# =============================================================================

@pytest.fixture
def test_app(db_session, setup_analytics_data):
    data = setup_analytics_data
    app = FastAPI()
    app.include_router(analytics_router)

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_subscriber_id] = lambda: data["sub_a"].subscriber_id

    return app


def test_api_deterministic_calculate(test_app):
    client = TestClient(test_app)
    payload = {
        "subject": "Mathematics",
        "scores": [
            {"score": 50.0, "max_marks": 100.0},
            {"score": 70.0, "max_marks": 100.0},
        ],
    }
    resp = client.post("/analytics/deterministic-calculate", json=payload)
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["latest_score_pct"] == 70.0
    assert res_data["prior_score_pct"] == 50.0
    assert res_data["movement_delta"] == 20.0
    assert res_data["movement_direction"] == "IMPROVING"
    assert res_data["is_server_deterministic"] is True


def test_api_grounded_explain(test_app):
    client = TestClient(test_app)
    payload = {
        "student_name": "Naveen",
        "subject": "Science",
        "latest_score_pct": 80.0,
        "prior_score_pct": 72.0,
        "movement_delta": 8.0,
        "movement_direction": "IMPROVING",
        "has_new_evidence": True,
        "language": "en",
    }
    resp = client.post("/analytics/grounded-explain", json=payload)
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["feedback_badge"] == "AI Learning Summary"
    assert res_data["has_fabricated_change"] is False
    assert "+8.0%" in res_data["headline"]


def test_api_gate2_check(test_app):
    client = TestClient(test_app)
    payload = {
        "evidence_type": "QUICK_MARKS",
        "requested_topic_mastery": True,
    }
    resp = client.post("/analytics/gate2-check", json=payload)
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["is_topic_intelligence_eligible"] is False
    assert res_data["status_code"] == "LOCKED_AGGREGATE_ONLY"
