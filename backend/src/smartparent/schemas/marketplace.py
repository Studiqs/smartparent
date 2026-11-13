"""
STUDIQS® SmartParent™ (v6.2 Complete) - Subject Expert Marketplace Schemas
Pydantic v2 Type-Safe Schemas for Section 11 (9-Step Lifecycle & Controlled Communication)
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, ConfigDict


# =============================================================================
# 1. Expert Public Catalog & Filtering (Steps 1 & 2)
# =============================================================================

class ExpertPublicCard(BaseModel):
    """
    Publicly visible Expert Card.
    Strictly masks private contact details (phone, email) under Section 11 privacy rules.
    """
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    expert_id: str
    display_alias: str
    bio: Optional[str] = None
    qualified_boards: List[str] = Field(default_factory=list)
    qualified_classes: List[str] = Field(default_factory=list)
    qualified_subjects: List[str] = Field(default_factory=list)
    sla_turnaround_hours: int = 48
    per_case_fee: float
    rating_avg: float = 5.0
    total_reviews: int = 0


class ExpertCatalogResponse(BaseModel):
    """List of approved experts matching filter criteria."""
    model_config = ConfigDict(extra="ignore")

    total_count: int
    matched_subject: Optional[str] = None
    matched_class: Optional[str] = None
    matched_board: Optional[str] = None
    experts: List[ExpertPublicCard] = Field(default_factory=list)


# =============================================================================
# 2. Evaluation Booking & Payment Order (Step 3)
# =============================================================================

class CreateEvaluationCaseRequest(BaseModel):
    """Payload to initiate a new expert evaluation case."""
    model_config = ConfigDict(extra="ignore")

    child_id: str
    subject: str
    test_title: str
    expert_id: str
    question_paper_path: Optional[str] = None


class PaymentOrderInitiateResponse(BaseModel):
    """Razorpay-compatible payment order initiation details."""
    model_config = ConfigDict(extra="ignore")

    order_id: str
    case_id: str
    gateway_order_id: str
    amount: float
    currency: str = "INR"
    key_id: str = "rzp_test_smartparent"
    payment_status: str


class ConfirmPaymentRequest(BaseModel):
    """Payload to confirm successful payment gateway capture."""
    model_config = ConfigDict(extra="ignore")

    gateway_payment_id: str


# =============================================================================
# 3. Paper Assignment & Student Upload (Steps 4 & 5)
# =============================================================================

class AssignQuestionPaperRequest(BaseModel):
    """Expert assigns question paper or question set to the case."""
    model_config = ConfigDict(extra="ignore")

    question_paper_path: str


class UploadAnswerSheetRequest(BaseModel):
    """Parent uploads child's offline written answer sheet scan."""
    model_config = ConfigDict(extra="ignore")

    answer_sheet_path: str


# =============================================================================
# 4. Expert Correction & Intelligence Update (Steps 6, 7 & 8)
# =============================================================================

class QuestionScoreItem(BaseModel):
    """Line-item evaluated question score with topic linkage."""
    model_config = ConfigDict(extra="ignore")

    question_no: Union[int, str]
    topic_name: str
    marks_scored: float = Field(..., ge=0.0)
    max_marks: float = Field(..., gt=0.0)
    remarks: Optional[str] = None


class CompleteEvaluationSubmissionRequest(BaseModel):
    """Expert submits vector annotated PDF and line-item question marks."""
    model_config = ConfigDict(extra="ignore")

    evaluated_pdf_path: str
    evaluations: List[QuestionScoreItem] = Field(..., min_length=1)
    overall_feedback: Optional[str] = None


class IntelligenceSyncResultResponse(BaseModel):
    """Automated Student 360 & Topic Intelligence Sync Result."""
    model_config = ConfigDict(extra="ignore")

    evidence_id: str
    scored_marks: float
    total_max_marks: float
    percentage: float
    topics_updated: List[str] = Field(default_factory=list)
    gaps_resolved: List[str] = Field(default_factory=list)
    gaps_flagged: List[str] = Field(default_factory=list)


# =============================================================================
# 5. Rating, Review & Dispute (Step 9 & Escrow)
# =============================================================================

class CreateExpertReviewRequest(BaseModel):
    """Parent review submission after completed case."""
    model_config = ConfigDict(extra="ignore")

    rating: int = Field(..., ge=1, le=5)
    feedback_text: Optional[str] = None


class ExpertReviewResponse(BaseModel):
    """Details of saved expert review."""
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    review_id: str
    case_id: str
    child_id: str
    expert_id: str
    rating: int
    feedback_text: Optional[str] = None
    created_at: str


class RaiseDisputeRequest(BaseModel):
    """Parent challenge payload within 48-hour escrow window."""
    model_config = ConfigDict(extra="ignore")

    dispute_reason: str = Field(..., min_length=5)


# =============================================================================
# 6. Anti-Contact In-Platform Messaging (Section 21/22)
# =============================================================================

class SendCaseMessageRequest(BaseModel):
    """Message payload for case thread."""
    model_config = ConfigDict(extra="ignore")

    message_text: str = Field(..., min_length=1)


class CaseMessageResponse(BaseModel):
    """Moderated message item in thread."""
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    message_id: str
    case_id: str
    sender_type: str
    sender_id: str
    message_text: str
    is_blocked: bool = False
    block_reason: Optional[str] = None
    sent_at: str


# =============================================================================
# 7. Case Detail & Lifecycle Summary
# =============================================================================

class EvaluationCaseDetailResponse(BaseModel):
    """360 view of an evaluation case across all 9 lifecycle steps."""
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    case_id: str
    subscriber_id: str
    child_id: str
    child_alias: str
    standard_class: str
    board: str
    expert_id: Optional[str] = None
    expert_alias: Optional[str] = None
    subject: str
    test_title: str
    case_status: str
    question_paper_path: Optional[str] = None
    answer_sheet_path: Optional[str] = None
    evaluated_pdf_path: Optional[str] = None
    gross_fee: float
    platform_commission: float
    expert_net_payout: float
    payout_status: Optional[str] = None
    submitted_at: Optional[str] = None
    completed_at: Optional[str] = None
    created_at: str
    sla_turnaround_hours: int = 48
    sla_breached: bool = False
    can_dispute: bool = False
    review: Optional[ExpertReviewResponse] = None
