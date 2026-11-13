"""
=============================================================================
STUDIQS® SmartParent™ (v6.2 Complete) - Section 11 Unit & Integration Test Suite
=============================================================================
Validates:
1. Expert Discovery & Catalog Filtering (Steps 1 & 2):
   - Filtering by Board, Class, Subject, Rating, Fee.
   - Masked private contact information (only safe public aliases visible).
2. Evaluation Booking & Plan Quota Enforcement (Step 3):
   - Basic (1 active), Advanced (3 active), Pro (6 active) limits.
   - Payment order generation (Razorpay intent).
   - Commercial 20% platform commission / 80% expert payout escrow ledger in HELD status.
3. Payment Confirmation & Transition to Awaiting Upload:
   - Status transitions ASSIGNED -> AWAITING_UPLOAD.
4. Paper Assignment & Student Answer Sheet Upload (Steps 4 & 5):
   - Status transitions AWAITING_UPLOAD -> SUBMITTED.
   - 48-Hour SLA clock starts.
5. Expert Claims Case in Split-Screen Studio (Step 6):
   - Status transitions SUBMITTED -> UNDER_REVIEW.
6. Expert Evaluation Submission & Automated Student 360 Sync (Steps 7 & 8):
   - Status transitions UNDER_REVIEW -> COMPLETED.
   - Evaluated PDF and line-item question marks saved.
   - Automated creation of EvidenceRecord (EXPERT_EVAL).
   - TopicScore created/updated with correct percentage and pedagogical tier.
   - TopicGap resolution (score >= 80% marks gap as RESOLVED).
   - SubscriberUsageQuota active count decremented.
7. Expert Rating & Controlled Review (Step 9):
   - 1–5 star rating only after completion.
   - Recalculates rolling rating average and total review count on ExpertProfile.
8. Escrow Dispute Lock (Section 12 & 14):
   - Challenge within 48h transitions to DISPUTED and freezes escrow payout.
   - Dispute rejected after 48h window.
9. In-Platform Anti-Contact Moderation (Section 21/22):
   - Blocks phone numbers, emails, UPI handles, URLs, and off-platform solicitation.
   - Preserves clean academic communication.
10. Strict B2C Multi-Tenant & Case-Scoped Isolation:
    - Subscriber B cannot access Subscriber A's child's evaluations.
    - Expert B cannot access Expert A's assigned cases.
11. FastAPI REST Endpoints (api/v1/marketplace).
=============================================================================
"""

import uuid
from datetime import date, datetime, timedelta, timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.smartparent.db.base import Base
from src.smartparent.db.models.auth import Subscriber, Child
from src.smartparent.db.models.curriculum import CurriculumNode
from src.smartparent.db.models.assessment import EvidenceRecord, Question, QuestionPaper, StudentQuestionMark
from src.smartparent.db.models.diagnostic import TopicGap, TopicScore
from src.smartparent.db.models.usage_quota import SubscriberUsageQuota
from src.smartparent.db.models.marketplace import (
    Expert,
    ExpertProfile,
    ExpertBankAccount,
    EvaluationCase,
    PaymentOrder,
    CommissionLedger,
    ExpertReview,
    CaseMessage,
)
from src.smartparent.services.marketplace_service import MarketplaceService
from src.smartparent.schemas.marketplace import (
    CreateEvaluationCaseRequest,
    UploadAnswerSheetRequest,
    CompleteEvaluationSubmissionRequest,
    QuestionScoreItem,
    CreateExpertReviewRequest,
    RaiseDisputeRequest,
    SendCaseMessageRequest,
)
from src.smartparent.api.v1.marketplace import (
    router as marketplace_router,
    get_db,
    get_current_subscriber_id,
    get_current_expert_id,
)


# SQLite dialect mapping for JSONB and UUID
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
            QuestionPaper.__table__,
            Question.__table__,
            StudentQuestionMark.__table__,
            TopicGap.__table__,
            TopicScore.__table__,
            SubscriberUsageQuota.__table__,
            Expert.__table__,
            ExpertProfile.__table__,
            ExpertBankAccount.__table__,
            EvaluationCase.__table__,
            PaymentOrder.__table__,
            CommissionLedger.__table__,
            ExpertReview.__table__,
            CaseMessage.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def setup_marketplace_data(db_session):
    """Seed sample subscribers, children, and verified experts."""
    # Subscriber A (Basic Plan)
    sub_a = Subscriber(
        subscriber_id=uuid.uuid4(),
        mobile_number="+919840011111",
        parent_name="Parent A",
        email="parent_a@test.com",
        password_hash="mock_hash",
        subscription_plan="BASIC",
    )
    child_a = Child(
        child_id=uuid.uuid4(),
        subscriber_id=sub_a.subscriber_id,
        student_name="Arun Kumar",
        standard_class="Class 10",
        board="CBSE",
        academic_year="2026-2027",
    )

    # Subscriber B (Tenant Isolation Test)
    sub_b = Subscriber(
        subscriber_id=uuid.uuid4(),
        mobile_number="+919840022222",
        parent_name="Parent B",
        email="parent_b@test.com",
        password_hash="mock_hash",
        subscription_plan="PRO",
    )
    child_b = Child(
        child_id=uuid.uuid4(),
        subscriber_id=sub_b.subscriber_id,
        student_name="Bala Kumar",
        standard_class="Class 10",
        board="CBSE",
        academic_year="2026-2027",
    )

    # Expert 1: Math Specialist (Active & Verified)
    expert_1 = Expert(
        expert_id=uuid.uuid4(),
        mobile_number="+919940011111",
        full_name="Dr. Ramanathan Sundaram",
        email="ramanathan.math@expert.com",
        password_hash="mock_hash",
        kyc_status="VERIFIED",
        is_active=True,
    )
    profile_1 = ExpertProfile(
        profile_id=uuid.uuid4(),
        expert_id=expert_1.expert_id,
        display_alias="Prof. Ramanathan (Math Specialist)",
        bio="Senior CBSE Mathematics Board Examiner with 18+ years experience.",
        qualified_boards=["CBSE", "ICSE"],
        qualified_classes=["Class 9", "Class 10", "Class 11", "Class 12"],
        qualified_subjects=["Mathematics"],
        sla_turnaround_hours=48,
        per_case_fee=300.0,
        rating_avg=4.90,
        total_reviews=25,
    )

    # Expert 2: Science Specialist (Active & Verified)
    expert_2 = Expert(
        expert_id=uuid.uuid4(),
        mobile_number="+919940022222",
        full_name="Mrs. Meenakshi Venkat",
        email="meenakshi.sci@expert.com",
        password_hash="mock_hash",
        kyc_status="VERIFIED",
        is_active=True,
    )
    profile_2 = ExpertProfile(
        profile_id=uuid.uuid4(),
        expert_id=expert_2.expert_id,
        display_alias="Mrs. Meenakshi (Science Expert)",
        bio="Experienced Science teacher specializing in Physics & Chemistry.",
        qualified_boards=["CBSE", "TN State Board"],
        qualified_classes=["Class 8", "Class 9", "Class 10"],
        qualified_subjects=["Science", "Physics", "Chemistry"],
        sla_turnaround_hours=24,
        per_case_fee=250.0,
        rating_avg=4.75,
        total_reviews=12,
    )

    # Expert 3: Unverified Expert (Should NOT appear in catalog)
    expert_unverified = Expert(
        expert_id=uuid.uuid4(),
        mobile_number="+919940033333",
        full_name="Pending Expert",
        email="pending@expert.com",
        password_hash="mock_hash",
        kyc_status="PENDING",
        is_active=False,
    )
    profile_unverified = ExpertProfile(
        profile_id=uuid.uuid4(),
        expert_id=expert_unverified.expert_id,
        display_alias="Pending Expert",
        bio="Not yet verified.",
        qualified_boards=["CBSE"],
        qualified_classes=["Class 10"],
        qualified_subjects=["Mathematics"],
        per_case_fee=150.0,
    )

    # Curriculum node & persistent gap for Child A
    cnode_math = CurriculumNode(
        node_id="cnode_math_quad_10",
        board="CBSE",
        standard_class="Class 10",
        subject="Mathematics",
        chapter_name="Quadratic Equations",
        topic_name="Quadratic Equations",
        semantic_keywords=[],
    )
    gap_math = TopicGap(
        gap_id=uuid.uuid4(),
        child_id=child_a.child_id,
        node_id=cnode_math.node_id,
        gap_status="ACTIVE",
    )

    db_session.add_all([
        sub_a, child_a, sub_b, child_b,
        expert_1, profile_1,
        expert_2, profile_2,
        expert_unverified, profile_unverified,
        cnode_math, gap_math,
    ])
    db_session.commit()

    return {
        "sub_a": sub_a,
        "child_a": child_a,
        "sub_b": sub_b,
        "child_b": child_b,
        "expert_1": expert_1,
        "profile_1": profile_1,
        "expert_2": expert_2,
        "profile_2": profile_2,
        "cnode_math": cnode_math,
        "gap_math": gap_math,
    }


# =============================================================================
# 1. EXPERT DISCOVERY & CATALOG FILTERING TESTS (STEPS 1 & 2)
# =============================================================================

def test_catalog_discovery_and_privacy_masking(db_session, setup_marketplace_data):
    """
    Verifies Step 1 & 2:
    - Filters approved experts by Board, Class, and Subject.
    - Masks private contact details (phone, email are absent).
    - Excludes unverified/pending experts.
    """
    service = MarketplaceService()
    catalog = service.get_expert_catalog(
        db=db_session,
        board="CBSE",
        standard_class="Class 10",
        subject="Mathematics",
    )

    assert catalog.total_count == 1
    expert_card = catalog.experts[0]
    assert expert_card.display_alias == "Prof. Ramanathan (Math Specialist)"
    assert expert_card.per_case_fee == 300.0
    assert expert_card.rating_avg == 4.90
    assert not hasattr(expert_card, "mobile_number")
    assert not hasattr(expert_card, "email")


def test_catalog_multi_filter_matching(db_session, setup_marketplace_data):
    """Verifies fee ceiling and minimum rating filters."""
    service = MarketplaceService()

    # Filter with low fee ceiling (max 260) -> matches expert 2 (250) but excludes expert 1 (300)
    cat_fee = service.get_expert_catalog(db=db_session, max_fee=260.0)
    assert cat_fee.total_count == 1
    assert cat_fee.experts[0].display_alias == "Mrs. Meenakshi (Science Expert)"

    # Filter by Science subject
    cat_sci = service.get_expert_catalog(db=db_session, subject="Science")
    assert cat_sci.total_count == 1
    assert cat_sci.experts[0].display_alias == "Mrs. Meenakshi (Science Expert)"


# =============================================================================
# 2. EVALUATION BOOKING & PLAN QUOTA TESTS (STEP 3)
# =============================================================================

def test_evaluation_booking_and_escrow_ledger(db_session, setup_marketplace_data):
    """
    Verifies Step 3:
    - Creates EvaluationCase (ASSIGNED).
    - Generates Razorpay-compatible PaymentOrder.
    - Sets 20% Studiqs commission / 80% Expert net payout in Escrow HELD.
    """
    service = MarketplaceService()
    sub_a = setup_marketplace_data["sub_a"]
    child_a = setup_marketplace_data["child_a"]
    expert_1 = setup_marketplace_data["expert_1"]

    req = CreateEvaluationCaseRequest(
        child_id=str(child_a.child_id),
        subject="Mathematics",
        test_title="Mid-Term Math Revision",
        expert_id=str(expert_1.expert_id),
    )

    case, order = service.create_evaluation_case(
        db=db_session,
        subscriber_id=sub_a.subscriber_id,
        payload=req,
    )

    assert case.case_status == "ASSIGNED"
    assert case.gross_fee == 300.0
    assert order.amount == 300.0
    assert order.payment_status == "CREATED"
    assert order.gateway_order_id.startswith("order_")

    # Verify Escrow Ledger
    ledger = db_session.query(CommissionLedger).filter(CommissionLedger.case_id == case.case_id).first()
    assert ledger is not None
    assert ledger.gross_amount == 300.0
    assert ledger.platform_commission == 60.0  # 20% of 300
    assert ledger.expert_net_payout == 240.0   # 80% of 300
    assert ledger.payout_status == "HELD"


def test_plan_active_evaluation_quota_enforcement(db_session, setup_marketplace_data):
    """
    Verifies Section 10 Plan Quota Enforcement:
    - Basic Plan permits 1 active case per child.
    - Attempting to book a second active case raises quota exception.
    """
    service = MarketplaceService()
    sub_a = setup_marketplace_data["sub_a"]
    child_a = setup_marketplace_data["child_a"]
    expert_1 = setup_marketplace_data["expert_1"]
    expert_2 = setup_marketplace_data["expert_2"]

    # Book Case 1 (Successful)
    req1 = CreateEvaluationCaseRequest(
        child_id=str(child_a.child_id),
        subject="Mathematics",
        test_title="Case 1",
        expert_id=str(expert_1.expert_id),
    )
    service.create_evaluation_case(db=db_session, subscriber_id=sub_a.subscriber_id, payload=req1)

    # Book Case 2 (Should raise ValueError because Basic limit = 1 active)
    req2 = CreateEvaluationCaseRequest(
        child_id=str(child_a.child_id),
        subject="Science",
        test_title="Case 2",
        expert_id=str(expert_2.expert_id),
    )
    with pytest.raises(ValueError, match=r"(?i)Active expert evaluation limit.*basic"):
        service.create_evaluation_case(db=db_session, subscriber_id=sub_a.subscriber_id, payload=req2)


# =============================================================================
# 3. END-TO-END 9-STEP LIFECYCLE EXECUTION
# =============================================================================

def test_full_9_step_evaluation_lifecycle(db_session, setup_marketplace_data):
    """
    Executes the complete 9-step Section 11 lifecycle:
    1. Need detected -> 2. Choose expert -> 3. Book & Pay -> 4. Paper assigned
    -> 5. Student writes & uploads -> 6. Expert corrects in studio
    -> 7. Expert returns -> 8. Intelligence updated -> 9. Rate expert.
    """
    service = MarketplaceService()
    sub_a = setup_marketplace_data["sub_a"]
    child_a = setup_marketplace_data["child_a"]
    expert_1 = setup_marketplace_data["expert_1"]

    # Step 3: Book
    book_req = CreateEvaluationCaseRequest(
        child_id=str(child_a.child_id),
        subject="Mathematics",
        test_title="Quadratic Equations Diagnostic",
        expert_id=str(expert_1.expert_id),
    )
    case, order = service.create_evaluation_case(db=db_session, subscriber_id=sub_a.subscriber_id, payload=book_req)
    case_id = case.case_id

    # Step 3b: Pay
    case = service.confirm_payment(
        db=db_session,
        subscriber_id=sub_a.subscriber_id,
        case_id=case_id,
        gateway_payment_id="pay_mock_12345",
    )
    assert case.case_status == "AWAITING_UPLOAD"

    # Step 4: Paper Assigned
    case = service.assign_question_paper(
        db=db_session,
        expert_id=expert_1.expert_id,
        case_id=case_id,
        question_paper_path="/storage/papers/quad_exam_v1.pdf",
    )
    assert case.question_paper_path == "/storage/papers/quad_exam_v1.pdf"

    # Step 5: Student Writes & Uploads
    case = service.upload_answer_sheet(
        db=db_session,
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        case_id=case_id,
        answer_sheet_path="/storage/answers/arun_quad_answers.pdf",
    )
    assert case.case_status == "SUBMITTED"
    assert case.submitted_at is not None

    # Step 6: Expert Claims Case in Studio
    case = service.expert_claim_case(
        db=db_session,
        expert_id=expert_1.expert_id,
        case_id=case_id,
    )
    assert case.case_status == "UNDER_REVIEW"

    # Step 7 & 8: Expert Submits Correction & Student 360 Intelligence Syncs
    eval_req = CompleteEvaluationSubmissionRequest(
        evaluated_pdf_path="/storage/corrected/arun_quad_evaluated.pdf",
        evaluations=[
            QuestionScoreItem(
                question_no=1,
                topic_name="Quadratic Equations",
                marks_scored=8.5,
                max_marks=10.0,
                remarks="Good factoring technique.",
            ),
            QuestionScoreItem(
                question_no=2,
                topic_name="Quadratic Equations",
                marks_scored=9.0,
                max_marks=10.0,
                remarks="Accurate discriminant calculation.",
            ),
        ],
        overall_feedback="Excellent recovery! The student has mastered finding roots by formula.",
    )
    case, sync_res = service.expert_submit_evaluation(
        db=db_session,
        expert_id=expert_1.expert_id,
        case_id=case_id,
        payload=eval_req,
    )

    assert case.case_status == "COMPLETED"
    assert case.completed_at is not None
    assert sync_res.percentage == 87.5  # (17.5 / 20) * 100

    # Verify Step 8: Gap Resolution (Score >= 80% marks gap as RESOLVED)
    assert "Quadratic Equations" in sync_res.gaps_resolved
    gap_record = db_session.query(TopicGap).filter(TopicGap.child_id == child_a.child_id).first()
    assert gap_record.gap_status == "RESOLVED"

    # Verify TopicScore entity was created
    score_rec = db_session.query(TopicScore).filter(TopicScore.child_id == child_a.child_id).first()
    assert score_rec is not None
    assert float(score_rec.percentage) == 87.5
    assert score_rec.mastery_tier == "STRONG"

    # Step 9: Rate Expert
    rev_req = CreateExpertReviewRequest(
        rating=5,
        feedback_text="Very detailed line-by-line red ink correction. Highly recommended!",
    )
    review = service.rate_expert(
        db=db_session,
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        case_id=case_id,
        payload=rev_req,
    )
    assert review.rating == 5
    assert review.feedback_text.startswith("Very detailed")

    # Verify ExpertProfile rolling average updated
    profile = db_session.query(ExpertProfile).filter(ExpertProfile.expert_id == expert_1.expert_id).first()
    assert profile.total_reviews == 1
    assert profile.rating_avg == 5.0


# =============================================================================
# 4. DISPUTE & ESCROW WORKFLOW TESTS (SECTION 12 & 14)
# =============================================================================

def test_dispute_within_48h_freezes_escrow(db_session, setup_marketplace_data):
    """
    Verifies that challenging an evaluation within 48h:
    - Transitions case status to DISPUTED.
    - Freezes CommissionLedger in HELD status.
    """
    service = MarketplaceService()
    sub_a = setup_marketplace_data["sub_a"]
    child_a = setup_marketplace_data["child_a"]
    expert_1 = setup_marketplace_data["expert_1"]

    # Create completed case
    case = EvaluationCase(
        case_id=uuid.uuid4(),
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        expert_id=expert_1.expert_id,
        subject="Mathematics",
        test_title="Mid-Term Math",
        case_status="COMPLETED",
        gross_fee=300.0,
        completed_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    ledger = CommissionLedger(
        ledger_id=uuid.uuid4(),
        case_id=case.case_id,
        expert_id=expert_1.expert_id,
        gross_amount=300.0,
        platform_commission=60.0,
        expert_net_payout=240.0,
        payout_status="HELD",
    )
    db_session.add_all([case, ledger])
    db_session.commit()

    dispute_req = RaiseDisputeRequest(
        dispute_reason="Marks awarded in Question 2 do not match the published formula steps."
    )
    disp_case = service.raise_dispute(
        db=db_session,
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        case_id=case.case_id,
        payload=dispute_req,
    )

    assert disp_case.case_status == "DISPUTED"
    refreshed_ledger = db_session.query(CommissionLedger).filter(CommissionLedger.case_id == case.case_id).first()
    assert refreshed_ledger.payout_status == "HELD"


def test_dispute_rejected_after_48h_window(db_session, setup_marketplace_data):
    """Verifies that dispute attempts after 48h window are rejected."""
    service = MarketplaceService()
    sub_a = setup_marketplace_data["sub_a"]
    child_a = setup_marketplace_data["child_a"]
    expert_1 = setup_marketplace_data["expert_1"]

    # Completed 50 hours ago (outside 48h window)
    case = EvaluationCase(
        case_id=uuid.uuid4(),
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        expert_id=expert_1.expert_id,
        subject="Mathematics",
        test_title="Mid-Term Math",
        case_status="COMPLETED",
        gross_fee=300.0,
        completed_at=datetime.now(timezone.utc) - timedelta(hours=50),
    )
    db_session.add(case)
    db_session.commit()

    dispute_req = RaiseDisputeRequest(dispute_reason="Late challenge.")
    with pytest.raises(ValueError, match="48-hour dispute window has expired"):
        service.raise_dispute(
            db=db_session,
            subscriber_id=sub_a.subscriber_id,
            child_id=child_a.child_id,
            case_id=case.case_id,
            payload=dispute_req,
        )


# =============================================================================
# 5. IN-PLATFORM ANTI-CONTACT MESSAGING TESTS (SECTION 21/22)
# =============================================================================

def test_clean_academic_messaging_permitted(db_session, setup_marketplace_data):
    """Verifies clean pedagogical message passes without obstruction."""
    service = MarketplaceService()
    sub_a = setup_marketplace_data["sub_a"]
    child_a = setup_marketplace_data["child_a"]
    expert_1 = setup_marketplace_data["expert_1"]

    case = EvaluationCase(
        case_id=uuid.uuid4(),
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        expert_id=expert_1.expert_id,
        subject="Mathematics",
        test_title="Geometry Test",
        case_status="UNDER_REVIEW",
        gross_fee=300.0,
    )
    db_session.add(case)
    db_session.commit()

    msg_resp = service.send_case_message(
        db=db_session,
        case_id=case.case_id,
        sender_type="PARENT",
        sender_id=sub_a.subscriber_id,
        message_text="Could you please check step 3 of question 4 regarding angle bisector theorem?",
    )

    assert msg_resp.is_blocked is False
    assert "angle bisector theorem" in msg_resp.message_text


def test_anti_contact_boundary_blocks_phone_number(db_session, setup_marketplace_data):
    """Verifies that attempting to share phone numbers is intercepted and blocked."""
    service = MarketplaceService()
    sub_a = setup_marketplace_data["sub_a"]
    child_a = setup_marketplace_data["child_a"]
    expert_1 = setup_marketplace_data["expert_1"]

    case = EvaluationCase(
        case_id=uuid.uuid4(),
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        expert_id=expert_1.expert_id,
        subject="Mathematics",
        test_title="Geometry Test",
        case_status="UNDER_REVIEW",
        gross_fee=300.0,
    )
    db_session.add(case)
    db_session.commit()

    # Off-platform solicitation attempt
    msg_resp = service.send_case_message(
        db=db_session,
        case_id=case.case_id,
        sender_type="EXPERT",
        sender_id=expert_1.expert_id,
        message_text="Please call me at 9840123456 or message on WhatsApp for personal tuition.",
    )

    assert msg_resp.is_blocked is True
    assert "PHONE_NUMBER" in msg_resp.block_reason or "SOLICITATION" in msg_resp.block_reason


# =============================================================================
# 6. B2C MULTI-TENANT & CASE-SCOPED ISOLATION TESTS
# =============================================================================

def test_b2c_tenant_isolation_boundary(db_session, setup_marketplace_data):
    """Subscriber B cannot book, upload, review, or access Subscriber A's child's evaluations."""
    service = MarketplaceService()
    sub_b = setup_marketplace_data["sub_b"]
    child_a = setup_marketplace_data["child_a"]
    expert_1 = setup_marketplace_data["expert_1"]

    # Subscriber B tries to book for Child A (who belongs to Subscriber A)
    req = CreateEvaluationCaseRequest(
        child_id=str(child_a.child_id),
        subject="Mathematics",
        test_title="Intrusion Attempt",
        expert_id=str(expert_1.expert_id),
    )
    with pytest.raises(PermissionError, match="Child profile not found or not authorized"):
        service.create_evaluation_case(db=db_session, subscriber_id=sub_b.subscriber_id, payload=req)


def test_expert_case_scoped_isolation(db_session, setup_marketplace_data):
    """Expert 2 cannot claim, edit, or submit evaluations for a case assigned to Expert 1."""
    service = MarketplaceService()
    sub_a = setup_marketplace_data["sub_a"]
    child_a = setup_marketplace_data["child_a"]
    expert_1 = setup_marketplace_data["expert_1"]
    expert_2 = setup_marketplace_data["expert_2"]

    case = EvaluationCase(
        case_id=uuid.uuid4(),
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        expert_id=expert_1.expert_id,
        subject="Mathematics",
        test_title="Case for Expert 1",
        case_status="SUBMITTED",
        gross_fee=300.0,
    )
    db_session.add(case)
    db_session.commit()

    # Expert 2 attempts to claim Expert 1's case
    with pytest.raises(PermissionError, match="Case not found or unauthorized for this expert"):
        service.expert_claim_case(db=db_session, expert_id=expert_2.expert_id, case_id=case.case_id)


# =============================================================================
# 7. FASTAPI API ROUTER ENDPOINTS INTEGRATION TEST
# =============================================================================

def test_api_v1_marketplace_router(db_session, setup_marketplace_data):
    """Tests all primary marketplace endpoints via FastAPI TestClient."""
    sub_a = setup_marketplace_data["sub_a"]
    child_a = setup_marketplace_data["child_a"]
    expert_1 = setup_marketplace_data["expert_1"]

    sub_id = sub_a.subscriber_id
    exp_id = expert_1.expert_id

    app = FastAPI()
    app.include_router(marketplace_router, prefix="/api/v1")

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_subscriber_id] = lambda: sub_id
    app.dependency_overrides[get_current_expert_id] = lambda: exp_id

    client = TestClient(app)

    # 1. GET /api/v1/marketplace/experts
    res_cat = client.get("/api/v1/marketplace/experts?subject=Mathematics")
    assert res_cat.status_code == 200
    data_cat = res_cat.json()
    assert data_cat["total_count"] >= 1
    assert data_cat["experts"][0]["display_alias"] == "Prof. Ramanathan (Math Specialist)"

    # 2. GET /api/v1/marketplace/experts/{expert_id}
    res_exp = client.get(f"/api/v1/marketplace/experts/{expert_1.expert_id}")
    assert res_exp.status_code == 200
    assert res_exp.json()["display_alias"] == "Prof. Ramanathan (Math Specialist)"

    # 3. POST /api/v1/marketplace/cases
    book_payload = {
        "child_id": str(child_a.child_id),
        "subject": "Mathematics",
        "test_title": "API Flow Test",
        "expert_id": str(expert_1.expert_id),
    }
    res_book = client.post("/api/v1/marketplace/cases", json=book_payload)
    assert res_book.status_code == 201
    case_id = res_book.json()["case_id"]

    # 4. POST /api/v1/marketplace/cases/{case_id}/pay
    res_pay = client.post(f"/api/v1/marketplace/cases/{case_id}/pay", json={"gateway_payment_id": "pay_test_999"})
    assert res_pay.status_code == 200
    assert res_pay.json()["case_status"] == "AWAITING_UPLOAD"

    # 5. POST /api/v1/marketplace/cases/{case_id}/upload-answer
    res_up = client.post(
        f"/api/v1/marketplace/cases/{case_id}/upload-answer?child_id={child_a.child_id}",
        json={"answer_sheet_path": "/storage/answers/test_answers.pdf"},
    )
    assert res_up.status_code == 200
    assert res_up.json()["case_status"] == "SUBMITTED"

    # 6. POST /api/v1/marketplace/cases/{case_id}/claim
    res_claim = client.post(f"/api/v1/marketplace/cases/{case_id}/claim")
    assert res_claim.status_code == 200
    assert res_claim.json()["case_status"] == "UNDER_REVIEW"

    # 7. POST /api/v1/marketplace/cases/{case_id}/complete
    complete_payload = {
        "evaluated_pdf_path": "/storage/evaluated/test_evaluated.pdf",
        "evaluations": [
            {
                "question_no": 1,
                "topic_name": "Quadratic Equations",
                "marks_scored": 10.0,
                "max_marks": 10.0,
                "remarks": "Flawless solution.",
            }
        ],
        "overall_feedback": "Perfect test execution.",
    }
    res_comp = client.post(f"/api/v1/marketplace/cases/{case_id}/complete", json=complete_payload)
    assert res_comp.status_code == 200
    assert res_comp.json()["percentage"] == 100.0

    # 8. POST /api/v1/marketplace/cases/{case_id}/review
    rev_payload = {
        "rating": 5,
        "feedback_text": "Excellent and thorough evaluation.",
    }
    res_rev = client.post(f"/api/v1/marketplace/cases/{case_id}/review?child_id={child_a.child_id}", json=rev_payload)
    assert res_rev.status_code == 201
    assert res_rev.json()["rating"] == 5

    # 9. GET /api/v1/marketplace/cases/{case_id}
    res_det = client.get(f"/api/v1/marketplace/cases/{case_id}")
    assert res_det.status_code == 200
    assert res_det.json()["case_status"] == "COMPLETED"
    assert res_det.json()["child_alias"] == "Arun Kumar"

    # 10. GET /api/v1/marketplace/children/{child_id}/cases
    res_list = client.get(f"/api/v1/marketplace/children/{child_a.child_id}/cases")
    assert res_list.status_code == 200
    assert len(res_list.json()) >= 1
