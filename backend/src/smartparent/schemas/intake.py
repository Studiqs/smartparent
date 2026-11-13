"""
STUDIQS® SmartParent™ (v6.2 & v6.3 Extension) - Evidence Intake & QP Schemas
=============================================================================
Module: src.smartparent.schemas.intake
Section 3: Zero-Friction Data Feed and Evidence Intake
Strict Pydantic v2 Contracts for Evidence Ingestion, Quick Marks & Question Review
=============================================================================
"""

import uuid
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict


class EvidenceTypeEnum(str, Enum):
    QUESTION_PAPER = "QUESTION_PAPER"
    RESULT_CARD = "RESULT_CARD"
    QUICK_MARKS = "QUICK_MARKS"
    EXCEL_MARKS_GRID = "EXCEL_MARKS_GRID"


class EvidenceStatusEnum(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"


# =============================================================================
# 1. Evidence Upload & Status Schemas
# =============================================================================

class EvidenceUploadResponse(BaseModel):
    """Returned immediately upon receiving an exam paper / report card file."""
    model_config = ConfigDict(extra="ignore")

    evidence_id: uuid.UUID
    subscriber_id: uuid.UUID
    child_id: uuid.UUID
    subject: str
    test_title: str
    evidence_type: EvidenceTypeEnum
    status: EvidenceStatusEnum
    file_name: str
    message: str
    created_at: datetime


class EvidenceStatusResponse(BaseModel):
    """Polling status for background Document AI & OCR question parsing."""
    model_config = ConfigDict(extra="ignore")

    evidence_id: uuid.UUID
    child_id: uuid.UUID
    status: EvidenceStatusEnum
    evidence_type: EvidenceTypeEnum
    subject: str
    test_title: str
    total_questions: int = 0
    total_max_marks: float = 0.0
    total_scored_marks: float = 0.0
    is_ready_for_review: bool = False
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class EvidenceListItemSchema(BaseModel):
    """Individual item in a child's evidence upload history."""
    model_config = ConfigDict(extra="ignore")

    evidence_id: uuid.UUID
    child_id: uuid.UUID
    evidence_type: EvidenceTypeEnum
    subject: str
    test_title: str
    test_date: date
    total_scored_marks: float
    total_max_marks: float
    percentage: float
    status: EvidenceStatusEnum
    total_questions: int = 0
    created_at: datetime


# =============================================================================
# 2. Parsed Question Review & Line-Item Marks
# =============================================================================

class ParsedQuestionItemSchema(BaseModel):
    """Individual parsed question item for student/parent review."""
    model_config = ConfigDict(extra="ignore")

    question_id: uuid.UUID
    question_number: str
    question_stem: str
    max_marks: float
    scored_marks: Optional[float] = None
    mapped_topic_id: Optional[str] = None
    mapped_topic_name: Optional[str] = None
    chapter_name: Optional[str] = None
    mapping_confidence: float = 0.0
    manual_review_flag: bool = False


class ParsedPaperDetailResponse(BaseModel):
    """Complete parsed question paper with line-item questions for review."""
    model_config = ConfigDict(extra="ignore")

    evidence_id: uuid.UUID
    qp_id: Optional[uuid.UUID] = None
    child_id: uuid.UUID
    child_name: str
    subject: str
    test_title: str
    test_date: date
    total_questions: int
    total_max_marks: float
    total_scored_marks: float
    status: EvidenceStatusEnum
    questions: List[ParsedQuestionItemSchema] = Field(default_factory=list)


class QuestionMarkInput(BaseModel):
    """Line-item mark input for a specific question."""
    model_config = ConfigDict(extra="ignore")

    question_id: uuid.UUID
    scored_marks: float = Field(..., ge=0.0, description="Marks awarded to student")
    is_correct: Optional[bool] = None
    mistake_type: Optional[str] = Field(
        default=None,
        description="e.g. Conceptual Inversion, Calculation Error, Incomplete Step",
    )


class ConfirmQuestionMarksRequest(BaseModel):
    """Payload to confirm or adjust per-question marks and finalize evidence."""
    model_config = ConfigDict(extra="ignore")

    marks: List[QuestionMarkInput] = Field(..., min_length=1)
    notes: Optional[str] = None


class ConfirmQuestionMarksResponse(BaseModel):
    """Confirmation outcome and updated telemetry status."""
    model_config = ConfigDict(extra="ignore")

    evidence_id: uuid.UUID
    child_id: uuid.UUID
    subject: str
    status: EvidenceStatusEnum
    total_scored_marks: float
    total_max_marks: float
    percentage: float
    topic_scores_updated: int
    message: str


# =============================================================================
# 3. Quick Marks Feed Schemas
# =============================================================================

class QuickMarksFeedRequest(BaseModel):
    """Sub-1-minute fast marks entry without uploading full PDF/image."""
    model_config = ConfigDict(extra="ignore")

    child_id: uuid.UUID
    subject: str = Field(..., min_length=2, max_length=50)
    test_title: str = Field(..., min_length=2, max_length=150)
    test_date: date
    total_scored_marks: float = Field(..., ge=0.0)
    total_max_marks: float = Field(..., gt=0.0)
    exam_type: Optional[str] = Field(
        default="MONTHLY_UNIT_TEST",
        description="UNIT_TEST | MID_TERM | QUARTERLY | HALF_YEARLY | ANNUAL",
    )


class QuickMarksFeedResponse(BaseModel):
    """Result of Quick Marks ingestion."""
    model_config = ConfigDict(extra="ignore")

    evidence_id: uuid.UUID
    child_id: uuid.UUID
    subject: str
    test_title: str
    total_scored_marks: float
    total_max_marks: float
    percentage: float
    mastery_delta_estimate: float = 0.0
    status: EvidenceStatusEnum = EvidenceStatusEnum.CONFIRMED
    message: str
    created_at: datetime

