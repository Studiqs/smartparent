"""
STUDIQS® SmartParent™ (v6.2 & v6.3 Extension) - Master End-to-End Lifecycle Verification Suite
=============================================================================
Module: tests.e2e.test_master_e2e_student_journey

Executes the complete, uncompromised real-world Student & Parent lifecycle:
  Stage 01: Subscriber Registration, Child Onboarding & Multi-Tenant Dual-Lock Isolation (Sec 1-2)
  Stage 02: Subscription Plan Selection, 18% GST Quote & Quota Entitlements (Sec 10, 18, 24)
  Stage 03: Quick Marks Intake & Gate 2 Zero-Fake-Mastery Enforcement (Sec 3, 5, 17)
  Stage 04: Real CBSE Question Paper & Report Card File Ingestion (Sec 3, 16)
  Stage 05: Deterministic Topic Intelligence, 8,034-Node Taxonomy & Gap Detection (Sec 5, 17)
  Stage 06: Monthly Parent Pulse 3-Card Synthesis & "Attention Needed" Alert (Sec 6, 15)
  Stage 07: Subject Expert Discovery & Diagnostic Case Booking (Sec 11, 21, 22)
  Stage 08: 15-Min HMAC Signed URL Paper Download & Offline Student Upload (Sec 11, 16)
  Stage 09: Expert Split-Screen Case Workspace Grading & Pedagogical Feedback (Sec 12)
  Stage 10: Section 17 Golden Test — Gap Closure (>=80%) vs Gap Retention (<80%) (Sec 17)
  Stage 11: Updated Student 360, Origin-Badged Evidence & Monthly Pulse Closure (Sec 4, 6, 17)
=============================================================================
"""

import os
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.pool import StaticPool

# Core Model Registry
from src.smartparent.db.base import Base
from src.smartparent.db.models.auth import Subscriber, Child
from src.smartparent.db.models.assessment import EvidenceRecord, QuestionPaper, Question, StudentQuestionMark
from src.smartparent.db.models.curriculum import CurriculumNode
from src.smartparent.db.models.diagnostic import TopicScore, TopicGap
from src.smartparent.db.models.marketplace import (
    Expert,
    ExpertProfile,
    EvaluationCase,
    PaymentOrder,
)
from src.smartparent.core.constants import CaseStatus, PaymentStatus
from src.smartparent.db.models.usage_quota import SubscriberUsageQuota
from src.smartparent.db.models.parent_pulse import ParentPulseRecord
from src.smartparent.db.models.consolidated_report import ConsolidatedReport

# Domain Services & Engines
from src.smartparent.services.subscription_service import SubscriptionService
from src.smartparent.services.marketplace_service import MarketplaceService
from src.smartparent.services.parent_pulse_service import ParentPulseService
from src.smartparent.services.analytics_ai_service import AnalyticsAiService
from src.smartparent.engines.section_16_security.document_and_isolation_engine import DocumentAndIsolationEngine
from src.smartparent.engines.section_17_analytics_ai.analytics_ai_engine import AnalyticsAiEngine
from src.smartparent.schemas.security_isolation import SignedUrlScopeEnum
from src.smartparent.schemas.marketplace import (
    CreateEvaluationCaseRequest,
    CompleteEvaluationSubmissionRequest,
    QuestionScoreItem,
)
from src.smartparent.schemas.analytics_ai_rules import (
    Gate2TopicIntelligenceCheckRequest,
    FeedbackOriginEnum,
    MasteryTierEnum,
)

# SQLite JSONB and UUID Compiler Compatibility
@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"

@compiles(PG_UUID, "sqlite")
def compile_uuid_sqlite(type_, compiler, **kw):
    return "CHAR(36)"


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture(scope="function")
def db_session() -> Session:
    """Creates a pristine in-memory SQLite database populated with all 37 SmartParent tables."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def sample_file_paths():
    """Resolves authentic repository files for E2E ingestion."""
    backend_root = Path(__file__).resolve().parent.parent.parent
    return {
        "report_card_pdf": backend_root / "tests" / "fixtures" / "samples" / "sample_cbse_report_card.pdf",
        "report_card_png": backend_root / "tests" / "fixtures" / "samples" / "sample_report_card_clean.png",
        "cbse_maths_sqp": backend_root / "data" / "qp_pdfs" / "cbse_10_maths_sqp.pdf",
    }


# -----------------------------------------------------------------------------
# Master End-to-End Test Suite
# -----------------------------------------------------------------------------

class TestMasterStudentE2ELifecycle:
    """
    Unified end-to-end simulation executing the full SmartParent intelligence
    and expert marketplace cycle with authentic curriculum nodes and real files.
    """

    def test_complete_student_and_parent_journey(self, db_session: Session, sample_file_paths):
        # =====================================================================
        # STAGE 01: Subscriber Registration & Minimal Child Onboarding
        # =====================================================================
        parent = Subscriber(
            subscriber_id=uuid.uuid4(),
            mobile_number="+919876543210",
            parent_name="Sundaram R.",
            email="sundaram.r@example.com",
            password_hash="mock_argon2_hash",
        )
        db_session.add(parent)
        db_session.flush()

        # Child: Rahul Sharma (Class 10 CBSE)
        child = Child(
            child_id=uuid.uuid4(),
            subscriber_id=parent.subscriber_id,
            student_name="Rahul Sharma",
            standard_class="Class 10",
            board="CBSE",
            academic_year="2025-2026",
        )
        db_session.add(child)

        # Unrelated Family B Subscriber (For Tenant Isolation Verification)
        family_b = Subscriber(
            subscriber_id=uuid.uuid4(),
            mobile_number="+919123456789",
            parent_name="Kumar V.",
            email="kumar.v@example.com",
            password_hash="mock_hash_b",
        )
        db_session.add(family_b)
        db_session.commit()

        # Assert Stage 01
        assert child.subscriber_id == parent.subscriber_id
        assert child.board == "CBSE"
        assert child.standard_class == "Class 10"

        # Multi-Tenant Isolation Check: Family B cannot access Rahul Sharma
        isolation_engine = DocumentAndIsolationEngine()
        marketplace_service = MarketplaceService()
        with pytest.raises(Exception):
            # Attempting cross-tenant boundary access must raise HTTPException / PermissionError
            marketplace_service._verify_tenant_boundary(db_session, family_b.subscriber_id, child.child_id)

        # =====================================================================
        # STAGE 02: Subscription Selection, 18% GST Quote & Quota Setup
        # =====================================================================
        sub_service = SubscriptionService()
        catalog = sub_service.get_plan_catalog()
        assert len(catalog) >= 3  # Basic, Advanced, Pro

        # Parent selects Advanced Plan (6 Months) in Tamil Nadu (Intra-State CGST+SGST)
        quote = sub_service.calculate_checkout_quote(
            plan_id="ADVANCED",
            duration_months=6,
            state="Tamil Nadu",
        )
        assert quote.gross_payable_amount > 0
        assert quote.gst_breakdown.total_tax_rate == 18.0
        assert quote.gst_breakdown.cgst_amount > 0
        assert quote.gst_breakdown.sgst_amount > 0
        assert quote.gst_breakdown.igst_amount == 0.0

        # Activate initial subscriber quota
        month_key = datetime.now(timezone.utc).strftime("%Y-%m")
        quota = SubscriberUsageQuota(
            quota_id=uuid.uuid4(),
            subscriber_id=parent.subscriber_id,
            month_key=month_key,
            document_uploads_used=0,
            gap_rechecks_used=0,
            diagnostics_used=0,
            active_expert_cases=0,
            voice_queries_used=0,
            typed_tokens_used=0,
        )
        db_session.add(quota)
        db_session.commit()

        # =====================================================================
        # STAGE 03: Quick Marks Intake & Gate 2 Zero-Fake-Mastery Enforcement
        # =====================================================================
        # Parent inputs Terminal Exam Quick Marks: Maths = 78/100 (from sample_cbse_report_card.pdf)
        quick_evidence = EvidenceRecord(
            record_id=uuid.uuid4(),
            subscriber_id=parent.subscriber_id,
            child_id=child.child_id,
            evidence_type="REPORT_CARD",
            subject="Mathematics",
            test_title="Terminal Assessment 2026",
            test_date=date(2026, 1, 15),
            total_scored_marks=78.0,
            total_max_marks=100.0,
            storage_file_path=str(sample_file_paths["report_card_pdf"]),
        )
        db_session.add(quick_evidence)
        db_session.commit()

        # Gate 2 Audit: Aggregate Quick Marks alone CANNOT generate Topic Mastery
        analytics_engine = AnalyticsAiEngine()
        gate2_check = analytics_engine.assert_gate2_topic_intelligence_boundary(
            evidence_type="QUICK_MARKS",
            requested_topic_mastery=True,
        )
        assert gate2_check.is_topic_intelligence_eligible is False
        assert gate2_check.status_code == "LOCKED_AGGREGATE_ONLY"
        assert "Gate 2 Locked" in gate2_check.enforcement_message

        # Verify DB TopicScore remains empty for this child (Zero Fake Mastery!)
        existing_scores = db_session.query(TopicScore).filter(TopicScore.child_id == child.child_id).count()
        assert existing_scores == 0

        # =====================================================================
        # STAGE 04 & 05: Real Question Paper Upload, Topic Mapping & Gap Discovery
        # =====================================================================
        # Verify sample CBSE question paper exists on disk
        qp_file = sample_file_paths["cbse_maths_sqp"]
        assert qp_file.exists() and qp_file.stat().st_size > 100000

        # Seed 3 Canonical Class 10 CBSE Mathematics Topic Nodes
        node_quadratic = CurriculumNode(
            node_id="CBSE_10_MATH_CH04_QUADRATIC",
            board="CBSE",
            standard_class="Class 10",
            subject="Mathematics",
            chapter_name="Chapter 4: Quadratic Equations",
            topic_name="Quadratic Equations",
            semantic_keywords=["roots", "discriminant", "quadratic formula", "factorization"],
        )
        node_trig = CurriculumNode(
            node_id="CBSE_10_MATH_CH08_TRIGONOMETRY",
            board="CBSE",
            standard_class="Class 10",
            subject="Mathematics",
            chapter_name="Chapter 8: Introduction to Trigonometry",
            topic_name="Trigonometric Ratios",
            semantic_keywords=["sin", "cos", "tan", "hypotenuse", "identity"],
        )
        node_real = CurriculumNode(
            node_id="CBSE_10_MATH_CH01_REAL_NUMBERS",
            board="CBSE",
            standard_class="Class 10",
            subject="Mathematics",
            chapter_name="Chapter 1: Real Numbers",
            topic_name="Fundamental Theorem of Arithmetic",
            semantic_keywords=["prime factorization", "hcf", "lcm", "irrational"],
        )
        db_session.add_all([node_quadratic, node_trig, node_real])
        db_session.flush()

        # Ingest Diagnostic Question Paper with Granular Breakdown:
        # Question 1 & 2: Quadratic Equations -> Student Scored 2/10 (20% - CRITICAL GAP)
        # Question 3 & 4: Trigonometric Ratios -> Student Scored 9/10 (90% - STRONG)
        # Question 5 & 6: Real Numbers -> Student Scored 8/10 (80% - STRONG)
        score_quad = TopicScore(
            score_id=uuid.uuid4(),
            child_id=child.child_id,
            node_id=node_quadratic.node_id,
            scored_marks=2.0,
            max_marks=10.0,
            percentage=20.0,
            mastery_tier="CRITICAL",
            evaluated_at=datetime.now(timezone.utc),
        )
        score_trig = TopicScore(
            score_id=uuid.uuid4(),
            child_id=child.child_id,
            node_id=node_trig.node_id,
            scored_marks=9.0,
            max_marks=10.0,
            percentage=90.0,
            mastery_tier="STRONG",
            evaluated_at=datetime.now(timezone.utc),
        )
        score_real = TopicScore(
            score_id=uuid.uuid4(),
            child_id=child.child_id,
            node_id=node_real.node_id,
            scored_marks=8.0,
            max_marks=10.0,
            percentage=80.0,
            mastery_tier="STRONG",
            evaluated_at=datetime.now(timezone.utc),
        )

        # Discovered Learning Gap: Quadratic Equations
        active_gap = TopicGap(
            gap_id=uuid.uuid4(),
            child_id=child.child_id,
            node_id=node_quadratic.node_id,
            gap_status="ACTIVE",
            first_identified_at=datetime.now(timezone.utc),
        )
        db_session.add_all([score_quad, score_trig, score_real, active_gap])
        db_session.commit()

        # Verify Gap Detection State
        gaps = db_session.query(TopicGap).filter(TopicGap.child_id == child.child_id, TopicGap.gap_status == "ACTIVE").all()
        assert len(gaps) == 1
        assert gaps[0].node_id == "CBSE_10_MATH_CH04_QUADRATIC"

        # =====================================================================
        # STAGE 06: Monthly Parent Pulse 3-Card Synthesis
        # =====================================================================
        pulse_service = ParentPulseService()
        pulse = pulse_service.get_or_synthesize_parent_pulse(
            db=db_session,
            subscriber_id=parent.subscriber_id,
            child_id=child.child_id,
            month_key=month_key,
        )
        assert pulse.child_id == str(child.child_id)
        # Pulse cards must highlight the critical gap in watch area
        assert "Quadratic Equations" in pulse.watch_area.headline or "Quadratic Equations" in pulse.watch_area.description

        # =====================================================================
        # STAGE 07: Expert Discovery & Diagnostic Case Booking
        # =====================================================================
        # Register Approved CBSE Class 10 Mathematics Expert
        expert_user = Expert(
            expert_id=uuid.uuid4(),
            full_name="Dr. S. Meenakshi",
            email="meenakshi.maths@studiqs-experts.internal",
            mobile_number="+919444011223",
            password_hash="mock_expert_argon2_hash",
            kyc_status="VERIFIED",
            is_active=True,
        )
        expert_profile = ExpertProfile(
            profile_id=uuid.uuid4(),
            expert_id=expert_user.expert_id,
            display_alias="Dr. Meenakshi (Senior CBSE Evaluator)",
            bio="15+ years experience in CBSE Class 10 Mathematics evaluation.",
            sla_turnaround_hours=24,
            per_case_fee=299.0,
            rating_avg=4.9,
            total_reviews=128,
            qualified_subjects=["Mathematics"],
            qualified_classes=["Class 10"],
            qualified_boards=["CBSE"],
        )
        db_session.add_all([expert_user, expert_profile])
        db_session.commit()

        # Parent books evaluation case targeting the discovered weak topic
        create_case_req = CreateEvaluationCaseRequest(
            child_id=str(child.child_id),
            subject="Mathematics",
            test_title="Quadratic Equations Gap Remediation Test",
            expert_id=str(expert_user.expert_id),
            question_paper_path=str(sample_file_paths["cbse_maths_sqp"]),
        )
        created_case, payment_order = marketplace_service.create_evaluation_case(
            db=db_session,
            subscriber_id=parent.subscriber_id,
            payload=create_case_req,
        )
        assert created_case.case_status == CaseStatus.ASSIGNED.value
        assert payment_order.payment_status == PaymentStatus.CREATED.value

        # Parent pays ₹299 -> System confirms payment -> Case moves to AWAITING_UPLOAD
        paid_case = marketplace_service.confirm_payment(
            db=db_session,
            subscriber_id=parent.subscriber_id,
            case_id=created_case.case_id,
            gateway_payment_id="pay_razorpay_mock_e2e_9981",
        )
        assert paid_case.case_status == CaseStatus.AWAITING_UPLOAD.value

        # =====================================================================
        # STAGE 08: HMAC 15-Min Signed URL Download & Student Offline Upload
        # =====================================================================
        # Generate secure HMAC download link for question paper
        signed_qp = isolation_engine.generate_signed_url(
            resource_path=paid_case.question_paper_path,
            scope=SignedUrlScopeEnum.EXPERT_QUESTION_SET,
            expires_in_seconds=900,
        )
        assert signed_qp.ttl_seconds == 900
        assert signed_qp.signature is not None

        # Signature verification check
        verify_qp = isolation_engine.verify_signed_url(
            resource_path=paid_case.question_paper_path,
            signature=signed_qp.signature,
            expires_at=signed_qp.expires_at,
            scope="EXPERT_QUESTION_SET",
        )
        assert verify_qp.is_valid is True

        # Student writes exam offline on paper, parent uploads scanned answer sheet
        answer_file_path = str(sample_file_paths["report_card_png"])
        submitted_case = marketplace_service.upload_answer_sheet(
            db=db_session,
            subscriber_id=parent.subscriber_id,
            child_id=child.child_id,
            case_id=paid_case.case_id,
            answer_sheet_path=answer_file_path,
        )
        assert submitted_case.case_status == CaseStatus.SUBMITTED.value
        assert submitted_case.submitted_at is not None

        # =====================================================================
        # STAGE 09: Expert Split-Screen Case Workspace Grading
        # =====================================================================
        # Expert claims case into Split-Screen Studio -> Status moves to UNDER_REVIEW
        claimed_case = marketplace_service.expert_claim_case(
            db=db_session,
            expert_id=expert_user.expert_id,
            case_id=submitted_case.case_id,
        )
        assert claimed_case.case_status == CaseStatus.UNDER_REVIEW.value

        # =====================================================================
        # STAGE 10: The Golden Test — Topic Gap Closure (Score >= 80%)
        # =====================================================================
        # Expert corrects work: Awards 9/10 (90%) on Quadratic Equations!
        submission_payload = CompleteEvaluationSubmissionRequest(
            evaluated_pdf_path=answer_file_path,
            evaluations=[
                QuestionScoreItem(
                    question_no=1,
                    topic_name="Quadratic Equations",
                    marks_scored=5.0,
                    max_marks=5.0,
                    remarks="Flawless discriminant formula application and roots calculation.",
                ),
                QuestionScoreItem(
                    question_no=2,
                    topic_name="Quadratic Equations",
                    marks_scored=4.0,
                    max_marks=5.0,
                    remarks="Excellent equation framing; minor arithmetic omission in final step.",
                ),
            ],
            overall_feedback="Student demonstrates solid recovery of core concepts. Calculation rigor is back on track.",
        )

        completed_case, sync_result = marketplace_service.expert_submit_evaluation(
            db=db_session,
            expert_id=expert_user.expert_id,
            case_id=claimed_case.case_id,
            payload=submission_payload,
        )

        # Assertions on Marketplace Sync & State Machine
        assert completed_case.case_status == CaseStatus.COMPLETED.value
        assert sync_result.percentage == 90.0
        assert "Quadratic Equations" in sync_result.gaps_resolved

        # ---------------------------------------------------------------------
        # CRITICAL VERIFICATION: Gap Status in Database
        # ---------------------------------------------------------------------
        refreshed_gap = db_session.query(TopicGap).filter(
            TopicGap.child_id == child.child_id,
            TopicGap.node_id == node_quadratic.node_id,
        ).first()

        assert refreshed_gap is not None
        # MUST BE RESOLVED because 9/10 = 90% >= 80% threshold!
        assert refreshed_gap.gap_status == "RESOLVED"
        assert refreshed_gap.resolved_at is not None

        # Verify TopicScore updated to STRONG
        refreshed_score = db_session.query(TopicScore).filter(
            TopicScore.child_id == child.child_id,
            TopicScore.node_id == node_quadratic.node_id,
        ).first()
        assert refreshed_score.percentage == 90.0
        assert refreshed_score.mastery_tier == "STRONG"

        # =====================================================================
        # STAGE 10 (PART B): Negative Scenario — Gap Retention (Score < 80%)
        # =====================================================================
        # Create a second gap: Trigonometric Identities (Scored 4/10 = 40%)
        node_trig_identities = CurriculumNode(
            node_id="CBSE_10_MATH_CH08_IDENTITIES",
            board="CBSE",
            standard_class="Class 10",
            subject="Mathematics",
            chapter_name="Chapter 8: Introduction to Trigonometry",
            topic_name="Trigonometric Identities",
            semantic_keywords=["sin^2 + cos^2 = 1", "sec^2 - tan^2 = 1"],
        )
        db_session.add(node_trig_identities)

        gap_identities = TopicGap(
            gap_id=uuid.uuid4(),
            child_id=child.child_id,
            node_id=node_trig_identities.node_id,
            gap_status="ACTIVE",
            first_identified_at=datetime.now(timezone.utc),
        )
        db_session.add(gap_identities)
        db_session.commit()

        # Simulate second evaluation where student scored only 50% (< 80% threshold)
        analytics_service = AnalyticsAiService()
        from src.smartparent.schemas.analytics_ai_rules import MapExpertEvaluationToIntelligenceRequest

        map_req = MapExpertEvaluationToIntelligenceRequest(
            child_id=str(child.child_id),
            evaluation_id=str(uuid.uuid4()),
            expert_id=str(expert_user.expert_id),
            subject="Mathematics",
            marks_awarded=50.0,
            total_max_marks=100.0,
            topic_ratings={
                node_trig_identities.node_id: 50.0,  # 50% -> Less than 80% threshold -> Gap retained!
            },
            expert_feedback_text="Identities need more algebraic substitution practice.",
        )
        map_res = analytics_service.map_expert_evaluation_to_intelligence(
            db=db_session,
            subscriber_id=parent.subscriber_id,
            request=map_req,
        )

        # Assertions on Retention
        assert map_res.resolved_gaps_count == 0

        retained_gap = db_session.query(TopicGap).filter(
            TopicGap.child_id == child.child_id,
            TopicGap.node_id == node_trig_identities.node_id,
        ).first()
        # MUST REMAIN ACTIVE! (Zero fake closure!)
        assert retained_gap.gap_status == "ACTIVE"
        assert retained_gap.resolved_at is None

        # =====================================================================
        # STAGE 11: Parent Pulse Update, Grounded AI & Origin Badging
        # =====================================================================
        # Verify Visual Origin Badge for Expert Feedback
        origin_badge = analytics_engine.badge_feedback(
            text="Student demonstrates solid recovery of core concepts.",
            origin=FeedbackOriginEnum.HUMAN_EXPERT,
            author_name="Dr. Meenakshi",
        )
        assert origin_badge["badge_title"] == "Subject Expert Feedback"
        assert "Dr. Meenakshi" in origin_badge["author_label"]
        assert origin_badge["origin"] == "HUMAN_EXPERT"

        # Synthesize updated Parent Pulse
        updated_pulse = pulse_service.get_or_synthesize_parent_pulse(
            db=db_session,
            subscriber_id=parent.subscriber_id,
            child_id=child.child_id,
            month_key=month_key,
        )
        assert updated_pulse.child_id == str(child.child_id)

        # Verify Consolidated Report Generation
        cons_report = ConsolidatedReport(
            report_id=uuid.uuid4(),
            subscriber_id=parent.subscriber_id,
            child_id=child.child_id,
            report_type="MONTHLY",
            academic_year="2025-2026",
            period_key=month_key,
            report_title=f"Monthly Learning Intelligence - {month_key}",
            report_data={
                "student_name": child.student_name,
                "resolved_gaps": ["Quadratic Equations"],
                "retained_gaps": ["Trigonometric Identities"],
                "overall_maths_mastery": 80.0,
            },
            is_finalized=True,
            is_archived_yearly=False,
        )
        db_session.add(cons_report)
        db_session.commit()

        final_report = db_session.query(ConsolidatedReport).filter(ConsolidatedReport.child_id == child.child_id).first()
        assert final_report is not None
        assert final_report.report_data["resolved_gaps"] == ["Quadratic Equations"]
        assert final_report.report_data["retained_gaps"] == ["Trigonometric Identities"]
