"""
STUDIQS® SmartParent™ (v6.2 Complete) - Section 4 Report Schemas
=============================================================================
Pydantic v2 Type-Safe Contracts for Student 360 & Consolidated Report Lifecycle:
1. Student 360 Comprehensive Intelligence View
2. Consolidated Report Generation (Monthly, Term-wise, Yearly)
3. Academic-Year Rollover & Historical Archival
=============================================================================
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict


# =============================================================================
# 1. Student 360 Intelligence Schemas
# =============================================================================

class SubjectMovementSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")

    subject_name: str
    current_marks: float = 0.0
    previous_marks: Optional[float] = None
    delta: Optional[float] = None
    consistency_tier: str = "Stable"  # 'Improving', 'Stable', 'Fluctuating', 'Declining'
    direction_symbol: str = "→"


class TopicGapSummarySchema(BaseModel):
    model_config = ConfigDict(extra="ignore")

    gap_id: Optional[str] = None
    subject: str
    topic_name: str
    status: str = "ACTIVE"  # 'ACTIVE', 'NEEDS_PRACTICE', 'RESOLVED'
    severity: str = "Critical"  # 'Critical', 'Moderate'


class Student360ProfileSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")

    child_id: str
    student_name: str
    standard_class: str
    board: str
    academic_year: str
    school_name: Optional[str] = None


class Student360Response(BaseModel):
    model_config = ConfigDict(extra="ignore")

    profile: Student360ProfileSchema
    overall_average: float = 0.0
    monthly_movement: float = 0.0
    subject_performance: List[SubjectMovementSchema] = Field(default_factory=list)
    top_unresolved_gaps: List[TopicGapSummarySchema] = Field(default_factory=list)
    parent_pulse_cards: List[Dict[str, Any]] = Field(default_factory=list)
    board_readiness: Optional[Dict[str, Any]] = None
    expert_evaluations: List[Dict[str, Any]] = Field(default_factory=list)
    evidence_count: int = 0
    last_updated: Optional[datetime] = None


# =============================================================================
# 2. Consolidated Report Lifecycle Schemas
# =============================================================================

class ConsolidatedReportCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    child_id: uuid.UUID
    report_type: str = Field(..., description="'MONTHLY', 'TERM', or 'YEARLY'")
    academic_year: str = Field(..., json_schema_extra={"example": "2026-2027"})
    period_key: str = Field(..., json_schema_extra={"example": "2026-10"}, description="e.g., '2026-10', 'TERM_1', 'YEAR_2026_2027'")
    report_title: Optional[str] = None
    include_pdf: bool = True


class ConsolidatedReportResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    report_id: uuid.UUID
    subscriber_id: uuid.UUID
    child_id: uuid.UUID
    report_type: str
    academic_year: str
    period_key: str
    report_title: str
    report_data: Dict[str, Any]
    pdf_storage_path: Optional[str] = None
    is_finalized: bool
    is_archived_yearly: bool
    generated_at: datetime


class AcademicYearRolloverRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    child_id: uuid.UUID
    previous_academic_year: str = Field(..., json_schema_extra={"example": "2025-2026"})
    new_academic_year: str = Field(..., json_schema_extra={"example": "2026-2027"})
    new_standard_class: Optional[str] = None  # e.g., 'Class 11' if promoted


class AcademicYearRolloverResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    child_id: uuid.UUID
    previous_academic_year: str
    new_academic_year: str
    archived_yearly_report_id: Optional[uuid.UUID] = None
    retired_reports_count: int = 0
    status: str = "COMPLETED"
    message: str
