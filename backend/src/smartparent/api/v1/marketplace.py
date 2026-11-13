"""
STUDIQS® SmartParent™ (v6.2 Complete) - Subject Expert Marketplace API Router
=============================================================================
Router: api/v1/marketplace.py (Section 11 & 12 - Working Specification v6.0 / v6.1)
Endpoints:
1. GET  /api/v1/marketplace/experts                 -> Discover & filter verified experts (safe aliases only)
2. GET  /api/v1/marketplace/experts/{expert_id}     -> Expert public card (masked contact info)
3. POST /api/v1/marketplace/cases                   -> Book expert evaluation & generate payment order
4. POST /api/v1/marketplace/cases/{case_id}/pay     -> Confirm payment capture & move to AWAITING_UPLOAD
5. POST /api/v1/marketplace/cases/{case_id}/assign  -> Expert assigns question paper to case
6. POST /api/v1/marketplace/cases/{case_id}/upload  -> Upload answer script & start 48h SLA clock
7. POST /api/v1/marketplace/cases/{case_id}/claim   -> Expert claims case in Split-Screen Studio
8. POST /api/v1/marketplace/cases/{case_id}/complete-> Expert submits evaluation & syncs Student 360 intelligence
9. POST /api/v1/marketplace/cases/{case_id}/review  -> Rate expert 1–5 stars & controlled review
10. POST/api/v1/marketplace/cases/{case_id}/dispute -> Challenge evaluation within 48h escrow window
11. POST/api/v1/marketplace/cases/{case_id}/messages-> In-platform messaging with Section 21 anti-contact moderation
12. GET /api/v1/marketplace/cases/{case_id}/messages-> Case message thread
13. GET /api/v1/marketplace/cases/{case_id}         -> 360 case detail, SLA status & escrow breakdown
14. GET /api/v1/marketplace/children/{child_id}/cases-> List all evaluation cases for a child
=============================================================================
"""

import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.smartparent.schemas.marketplace import (
    ExpertPublicCard,
    ExpertCatalogResponse,
    CreateEvaluationCaseRequest,
    PaymentOrderInitiateResponse,
    ConfirmPaymentRequest,
    AssignQuestionPaperRequest,
    UploadAnswerSheetRequest,
    CompleteEvaluationSubmissionRequest,
    IntelligenceSyncResultResponse,
    CreateExpertReviewRequest,
    ExpertReviewResponse,
    RaiseDisputeRequest,
    SendCaseMessageRequest,
    CaseMessageResponse,
    EvaluationCaseDetailResponse,
)
from src.smartparent.services.marketplace_service import MarketplaceService
from src.smartparent.api.deps import get_db, get_current_subscriber_id, get_current_expert_id

router = APIRouter(prefix="/marketplace", tags=["Section 11: Subject Expert Marketplace"])


# =============================================================================
# 1. EXPERT DISCOVERY & CATALOG (STEPS 1 & 2)
# =============================================================================

@router.get(
    "/experts",
    response_model=ExpertCatalogResponse,
    summary="Step 1 & 2: Browse and filter verified subject experts",
    description="Returns vetted human experts filtered by board, class, and subject. Masks private contact details.",
)
def get_expert_catalog(
    board: Optional[str] = Query(None, description="Curriculum board (e.g. CBSE, ICSE, TN State Board)"),
    standard_class: Optional[str] = Query(None, description="Standard class (e.g. Class 10)"),
    subject: Optional[str] = Query(None, description="Academic subject (e.g. Mathematics, Science)"),
    min_rating: Optional[float] = Query(None, ge=1.0, le=5.0, description="Minimum rating average"),
    max_fee: Optional[float] = Query(None, ge=0.0, description="Maximum per-case evaluation fee"),
    db: Session = Depends(get_db),
):
    service = MarketplaceService()
    try:
        return service.get_expert_catalog(
            db=db,
            board=board,
            standard_class=standard_class,
            subject=subject,
            min_rating=min_rating,
            max_fee=max_fee,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/experts/{expert_id}",
    response_model=ExpertPublicCard,
    summary="Step 2: Get verified expert public profile card",
)
def get_expert_profile(
    expert_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    service = MarketplaceService()
    try:
        return service.get_expert_public_profile(db=db, expert_id=expert_id)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# 2. EVALUATION BOOKING & PAYMENT ORDER (STEP 3)
# =============================================================================

@router.post(
    "/cases",
    response_model=PaymentOrderInitiateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Step 3: Book expert evaluation case & initiate payment",
    description="Creates an EvaluationCase, checks monthly plan active case limits, and generates a Razorpay payment order.",
)
def create_evaluation_case(
    payload: CreateEvaluationCaseRequest,
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    service = MarketplaceService()
    try:
        case, order = service.create_evaluation_case(
            db=db,
            subscriber_id=subscriber_id,
            payload=payload,
        )
        return PaymentOrderInitiateResponse(
            order_id=str(order.order_id),
            case_id=str(case.case_id),
            gateway_order_id=order.gateway_order_id,
            amount=float(order.amount),
            currency="INR",
            key_id="rzp_test_smartparent",
            payment_status=order.payment_status,
        )
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/cases/{case_id}/pay",
    response_model=EvaluationCaseDetailResponse,
    summary="Step 3: Confirm payment gateway capture",
    description="Captures successful payment. Transitions case to AWAITING_UPLOAD.",
)
def confirm_payment(
    case_id: uuid.UUID,
    payload: ConfirmPaymentRequest,
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    service = MarketplaceService()
    try:
        service.confirm_payment(
            db=db,
            subscriber_id=subscriber_id,
            case_id=case_id,
            gateway_payment_id=payload.gateway_payment_id,
        )
        return service.get_case_detail(db=db, case_id=case_id, subscriber_id=subscriber_id)
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# 3. PAPER ASSIGNMENT & STUDENT UPLOAD (STEPS 4 & 5)
# =============================================================================

@router.post(
    "/cases/{case_id}/assign",
    response_model=EvaluationCaseDetailResponse,
    summary="Step 4: Expert assigns diagnostic question paper",
)
def assign_question_paper(
    case_id: uuid.UUID,
    payload: AssignQuestionPaperRequest,
    db: Session = Depends(get_db),
    expert_id: uuid.UUID = Depends(get_current_expert_id),
):
    service = MarketplaceService()
    try:
        service.assign_question_paper(
            db=db,
            expert_id=expert_id,
            case_id=case_id,
            question_paper_path=payload.question_paper_path,
        )
        return service.get_case_detail(db=db, case_id=case_id, expert_id=expert_id)
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/cases/{case_id}/upload-answer",
    response_model=EvaluationCaseDetailResponse,
    summary="Step 5: Parent uploads child's answer script scan",
    description="Uploads answer sheet scan. Transitions case to SUBMITTED and starts the 48-hour SLA clock.",
)
def upload_answer_sheet(
    case_id: uuid.UUID,
    payload: UploadAnswerSheetRequest,
    child_id: uuid.UUID = Query(..., description="Child UUID"),
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    service = MarketplaceService()
    try:
        service.upload_answer_sheet(
            db=db,
            subscriber_id=subscriber_id,
            child_id=child_id,
            case_id=case_id,
            answer_sheet_path=payload.answer_sheet_path,
        )
        return service.get_case_detail(db=db, case_id=case_id, subscriber_id=subscriber_id)
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# 4. EXPERT CORRECTION & INTELLIGENCE SYNC (STEPS 6, 7 & 8)
# =============================================================================

@router.post(
    "/cases/{case_id}/claim",
    response_model=EvaluationCaseDetailResponse,
    summary="Step 6: Expert claims case in Split-Screen Studio",
    description="Transitions case status from SUBMITTED to UNDER_REVIEW.",
)
def expert_claim_case(
    case_id: uuid.UUID,
    db: Session = Depends(get_db),
    expert_id: uuid.UUID = Depends(get_current_expert_id),
):
    service = MarketplaceService()
    try:
        service.expert_claim_case(db=db, expert_id=expert_id, case_id=case_id)
        return service.get_case_detail(db=db, case_id=case_id, expert_id=expert_id)
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/cases/{case_id}/complete",
    response_model=IntelligenceSyncResultResponse,
    summary="Step 7 & 8: Expert submits evaluation & syncs Student 360 intelligence",
    description="Submits annotated PDF and line-item question scores. Automatically creates EvidenceRecord, updates TopicScores, and resolves TopicGaps >= 80%.",
)
def expert_submit_evaluation(
    case_id: uuid.UUID,
    payload: CompleteEvaluationSubmissionRequest,
    db: Session = Depends(get_db),
    expert_id: uuid.UUID = Depends(get_current_expert_id),
):
    service = MarketplaceService()
    try:
        _, sync_res = service.expert_submit_evaluation(
            db=db,
            expert_id=expert_id,
            case_id=case_id,
            payload=payload,
        )
        return sync_res
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# 5. RATING, REVIEW & DISPUTES (STEP 9 & ESCROW)
# =============================================================================

@router.post(
    "/cases/{case_id}/review",
    response_model=ExpertReviewResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Step 9: Parent rates expert 1–5 stars & submits review",
    description="Allowed only after completed evaluation case. Updates expert rolling average rating.",
)
def rate_expert(
    case_id: uuid.UUID,
    payload: CreateExpertReviewRequest,
    child_id: uuid.UUID = Query(..., description="Child UUID"),
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    service = MarketplaceService()
    try:
        return service.rate_expert(
            db=db,
            subscriber_id=subscriber_id,
            child_id=child_id,
            case_id=case_id,
            payload=payload,
        )
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/cases/{case_id}/dispute",
    response_model=EvaluationCaseDetailResponse,
    summary="Challenge evaluation within 48-hour escrow window",
    description="Transitions case to DISPUTED and freezes escrow payout in HELD status.",
)
def raise_dispute(
    case_id: uuid.UUID,
    payload: RaiseDisputeRequest,
    child_id: uuid.UUID = Query(..., description="Child UUID"),
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    service = MarketplaceService()
    try:
        service.raise_dispute(
            db=db,
            subscriber_id=subscriber_id,
            child_id=child_id,
            case_id=case_id,
            payload=payload,
        )
        return service.get_case_detail(db=db, case_id=case_id, subscriber_id=subscriber_id)
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# 6. IN-PLATFORM MESSAGING (SECTION 21/22 ANTI-CONTACT BOUNDARY)
# =============================================================================

@router.post(
    "/cases/{case_id}/messages",
    response_model=CaseMessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Send in-platform message with anti-contact moderation",
    description="Scans text for phone numbers, emails, UPI IDs, and off-platform solicitation. Blocks or redacts violations.",
)
def send_case_message(
    case_id: uuid.UUID,
    payload: SendCaseMessageRequest,
    sender_type: str = Query("PARENT", pattern="^(PARENT|EXPERT)$"),
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    service = MarketplaceService()
    try:
        return service.send_case_message(
            db=db,
            case_id=case_id,
            sender_type=sender_type,
            sender_id=subscriber_id,
            message_text=payload.message_text,
        )
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/cases/{case_id}/messages",
    response_model=List[CaseMessageResponse],
    summary="Get case messaging thread",
)
def get_case_messages(
    case_id: uuid.UUID,
    user_type: str = Query("PARENT", pattern="^(PARENT|EXPERT)$"),
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    service = MarketplaceService()
    try:
        return service.get_case_messages(
            db=db,
            case_id=case_id,
            user_type=user_type,
            user_id=subscriber_id,
        )
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# 7. CASE DETAILS & LISTING
# =============================================================================

@router.get(
    "/cases/{case_id}",
    response_model=EvaluationCaseDetailResponse,
    summary="Get full 360 evaluation case details",
)
def get_case_detail(
    case_id: uuid.UUID,
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    service = MarketplaceService()
    try:
        return service.get_case_detail(db=db, case_id=case_id, subscriber_id=subscriber_id)
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/children/{child_id}/cases",
    response_model=List[EvaluationCaseDetailResponse],
    summary="List all evaluation cases for a child",
)
def get_child_cases(
    child_id: uuid.UUID,
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    service = MarketplaceService()
    try:
        return service.get_child_cases(db=db, subscriber_id=subscriber_id, child_id=child_id)
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
