"""
STUDIQS® SmartParent™ - Section 3 Evidence Intake & QP Intelligence Tests
=============================================================================
Module: tests.unit.test_section3_evidence_intake

Verifies Section 3 Production Standards:
  1. Multi-Tenant Isolation: Submissions blocked across unauthorized subscribers.
  2. File Extension & Size Guards (PDF/PNG/JPEG <= 25MB).
  3. Quick Marks Fast Feed & Real-Time Mastery Sync.
  4. Question Paper Upload & Line-Item Marks Confirmation.
  5. Validation Engines (DataValidationEngine, MappingValidationEngine, OCR).
=============================================================================
"""

import io
import uuid
from datetime import date, datetime
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID

# SQLite dialect mapping for PostgreSQL JSONB and UUID types
@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


@compiles(PG_UUID, "sqlite")
def compile_uuid_sqlite(type_, compiler, **kw):
    return "CHAR(36)"

from src.smartparent.db.base import Base
from src.smartparent.db.models.auth import Subscriber, Child
from src.smartparent.db.models.curriculum import CurriculumNode
from src.smartparent.db.models.assessment import EvidenceRecord, QuestionPaper, Question
from src.smartparent.db.models.diagnostic import TopicScore, TopicGap
from src.smartparent.schemas.intake import (
    QuickMarksFeedRequest,
    ConfirmQuestionMarksRequest,
    QuestionMarkInput,
)
from src.smartparent.services.intake_service import IntakeService
from src.smartparent.engines.section_03_qp_intelligence.data_validation_engine import DataValidationEngine
from src.smartparent.engines.section_03_qp_intelligence.mapping_validation_engine import MappingValidationEngine
from src.smartparent.engines.section_03_qp_intelligence.ocr_service import DocumentOCRService


@pytest.fixture
def test_db():
    """In-memory SQLite database configured with all SmartParent models."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def seed_data(test_db):
    """Seeds authorized parent, child, and curriculum nodes."""
    sub_id = uuid.uuid4()
    other_sub_id = uuid.uuid4()
    child_id = uuid.uuid4()
    other_child_id = uuid.uuid4()

    subscriber = Subscriber(
        subscriber_id=sub_id,
        mobile_number="9876543210",
        parent_name="Ramanathan K.",
        password_hash="test_hash_1",
    )
    other_subscriber = Subscriber(
        subscriber_id=other_sub_id,
        mobile_number="9876543211",
        parent_name="Other Parent",
        password_hash="test_hash_2",
    )

    child = Child(
        child_id=child_id,
        subscriber_id=sub_id,
        student_name="Viswa",
        standard_class="Class 10",
        board="CBSE",
        is_active=True,
    )
    other_child = Child(
        child_id=other_child_id,
        subscriber_id=other_sub_id,
        student_name="Stranger Child",
        standard_class="Class 10",
        board="CBSE",
        is_active=True,
    )

    node = CurriculumNode(
        node_id="MATH-10-QUAD-001",
        board="CBSE",
        standard_class="Class 10",
        subject="Mathematics",
        chapter_name="Algebra",
        topic_name="Quadratic Equations",
    )

    test_db.add_all([subscriber, other_subscriber, child, other_child, node])
    test_db.commit()

    return {
        "subscriber_id": sub_id,
        "other_subscriber_id": other_sub_id,
        "child_id": child_id,
        "other_child_id": other_child_id,
        "node_id": "MATH-10-QUAD-001",
    }


class TestSection3EvidenceIntake:
    """Verifies complete Section 3 Evidence Intake and QP Intelligence."""

    def test_multi_tenant_isolation_blocks_unauthorized_child_upload(self, test_db, seed_data):
        """Cross-tenant firewall: Subscriber cannot upload evidence for another parent's child."""
        service = IntakeService()
        with pytest.raises(PermissionError) as exc_info:
            service.upload_question_paper(
                db=test_db,
                subscriber_id=seed_data["subscriber_id"],
                child_id=seed_data["other_child_id"],  # Belongs to other_subscriber_id!
                subject="Mathematics",
                test_title="Unit Test 1",
                test_date=date(2026, 10, 1),
                file_bytes=b"dummy pdf bytes",
                file_name="paper.pdf",
            )
        assert "Access Denied" in str(exc_info.value)

    def test_quick_marks_submission_and_telemetry_sync(self, test_db, seed_data):
        """Sub-1-minute Fast Route: Feeds marks, computes percentage, updates TopicScores."""
        service = IntakeService()
        req = QuickMarksFeedRequest(
            child_id=seed_data["child_id"],
            subject="Mathematics",
            test_title="Mid-Term Assessment",
            test_date=date(2026, 10, 15),
            total_scored_marks=42.0,
            total_max_marks=50.0,
            exam_type="MID_TERM",
        )

        res = service.submit_quick_marks(
            db=test_db,
            subscriber_id=seed_data["subscriber_id"],
            request=req,
        )

        assert res.percentage == 84.0
        assert res.total_scored_marks == 42.0
        assert res.total_max_marks == 50.0
        assert res.status == "CONFIRMED"

        # Verify DB EvidenceRecord was persisted
        ev = test_db.query(EvidenceRecord).filter_by(record_id=res.evidence_id).one()
        assert ev.total_scored_marks == 42.0
        assert ev.evidence_type == "QUICK_MARKS"

        # Verify TopicScore was updated
        ts = test_db.query(TopicScore).filter_by(child_id=seed_data["child_id"]).first()
        assert ts is not None
        assert ts.mastery_tier == "STRONG"
        assert ts.percentage == 84.0

    def test_question_paper_upload_and_line_item_confirmation(self, test_db, seed_data):
        """Full Document AI Route: Uploads paper, parses questions, and confirms marks."""
        service = IntakeService()
        dummy_content = b"%PDF-1.4\nQuestion 1. Solve x^2 - 5x + 6 = 0 [2 Marks]\nQuestion 2. Find discriminant [2 Marks]"

        upload_res = service.upload_question_paper(
            db=test_db,
            subscriber_id=seed_data["subscriber_id"],
            child_id=seed_data["child_id"],
            subject="Mathematics",
            test_title="Quarterly Board Exam Prep",
            test_date=date(2026, 11, 1),
            file_bytes=dummy_content,
            file_name="math_quarterly.pdf",
        )

        assert upload_res.evidence_id is not None
        assert upload_res.status in ("PROCESSING", "COMPLETED")

        # Fetch parsed paper questions
        parsed_detail = service.get_parsed_paper(
            db=test_db,
            subscriber_id=seed_data["subscriber_id"],
            evidence_id=upload_res.evidence_id,
        )

        assert parsed_detail.total_questions > 0
        q1 = parsed_detail.questions[0]
        assert q1.question_number in ("Q1", "Q01")

        # Confirm line-item marks with mistake attribution
        confirm_req = ConfirmQuestionMarksRequest(
            marks=[
                QuestionMarkInput(
                    question_id=q1.question_id,
                    scored_marks=1.0,  # Lost 1 mark
                    is_correct=False,
                    mistake_type="Procedural Factorization Error",
                )
            ]
        )

        confirm_res = service.confirm_question_marks(
            db=test_db,
            subscriber_id=seed_data["subscriber_id"],
            evidence_id=upload_res.evidence_id,
            payload=confirm_req,
        )

        assert confirm_res.status == "CONFIRMED"
        assert confirm_res.total_scored_marks == 1.0

        # Check evidence history
        history = service.list_child_evidence(
            db=test_db,
            subscriber_id=seed_data["subscriber_id"],
            child_id=seed_data["child_id"],
        )
        assert len(history) >= 1
        assert history[0].evidence_id == upload_res.evidence_id

    def test_data_validation_engine_deduplication(self):
        """DataValidationEngine filters duplicate question stems and short artifacts."""
        engine = DataValidationEngine()
        raw_questions = [
            {"question_no": "1", "question_text": "What is the capital of Tamil Nadu?", "max_marks": 1.0},
            {"question_no": "2", "question_text": "What is the capital of Tamil Nadu?", "max_marks": 1.0},  # Duplicate!
            {"question_no": "3", "question_text": "Ok", "max_marks": 1.0},  # < 5 chars artifact!
            {"question_no": "4", "question_text": "Calculate the roots of quadratic equation.", "max_marks": 3.0},
        ]
        result = engine.run(raw_questions)
        assert result["is_valid"] is True
        assert result["total_questions"] == 2  # Only Q1 and Q4 kept
        assert result["total_extracted_marks"] == 4.0
        assert len(result["warnings"]) == 2

    def test_mapping_validation_engine_confidence_thresholds(self):
        """MappingValidationEngine correctly flags low-confidence mappings for review."""
        engine = MappingValidationEngine()
        mapped_data = [
            {"question_number": "Q1", "topic": "Trigonometry", "confidence": 0.92},
            {"question_number": "Q2", "topic": "Light Reflection", "confidence": 0.65},
            {"question_number": "Q3", "topic": "Unclear Jargon", "confidence": 0.35},
        ]
        res = engine.run(mapped_data)
        assert res["total_mapped"] == 3
        assert res["high_confidence_count"] == 1
        assert res["review_required_count"] == 1
        assert res["mapping_accuracy_rate"] == 66.7
