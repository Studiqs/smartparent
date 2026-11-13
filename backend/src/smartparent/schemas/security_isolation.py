"""
STUDIQS® SmartParent™ (v6.2 Complete) - Section 16 Security, Isolation & Document Handling Schemas
=============================================================================
Defines Pydantic v2 schemas for Section 16 (Working Specification v6.0 / v6.1):
1. Family row-level isolation & boundary verification
2. Expert case-level isolation & scoped case access
3. Object/file private paths & cryptographically signed expiring URLs
4. Role field leakage scrubbers (Expert view vs Subscriber view)
5. AI context isolation boundaries
6. Report & Evaluation document retention lifecycle
=============================================================================
"""

import uuid
from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class SignedUrlScopeEnum(str, Enum):
    """Authorized scope for signed document URLs."""
    FAMILY_EVIDENCE = "FAMILY_EVIDENCE"
    REPORT_DOWNLOAD = "REPORT_DOWNLOAD"
    EXPERT_QUESTION_SET = "EXPERT_QUESTION_SET"
    STUDENT_ORIGINAL = "STUDENT_ORIGINAL"
    CORRECTED_COPY = "CORRECTED_COPY"


class GenerateSignedUrlRequest(BaseModel):
    """Request payload to generate a scoped, time-limited signed URL."""
    model_config = ConfigDict(extra="ignore")

    scope: SignedUrlScopeEnum
    resource_path: str = Field(..., description="Target private storage path")
    child_id: Optional[str] = None
    evaluation_id: Optional[str] = None
    expires_in_seconds: int = Field(default=900, ge=60, le=86400, description="TTL in seconds (default: 15 min)")


class SignedUrlResponse(BaseModel):
    """Cryptographically signed, expiring URL response."""
    model_config = ConfigDict(extra="ignore")

    resource_path: str
    signed_url: str
    signature: str
    expires_at: str
    scope: str
    ttl_seconds: int


class VerifySignedUrlRequest(BaseModel):
    """Request to verify signed URL validity and authorization."""
    model_config = ConfigDict(extra="ignore")

    resource_path: str
    signature: str
    expires_at: str
    scope: str


class VerifySignedUrlResponse(BaseModel):
    """Result of signature verification."""
    model_config = ConfigDict(extra="ignore")

    is_valid: bool
    reason: Optional[str] = None
    resource_path: str
    scope: str


class SanitizedExpertCaseView(BaseModel):
    """
    Expert's isolated view of an assigned case.
    Strictly masks parent phone, email, billing, family history, and sibling data.
    """
    model_config = ConfigDict(extra="ignore")

    evaluation_id: str
    student_alias: str = Field(..., description="First name or alias only, no surname/contact")
    standard_class: str
    board: str
    subject: str
    status: str
    assigned_question_set_url: Optional[str] = None
    submitted_answer_sheet_url: Optional[str] = None
    corrected_copy_url: Optional[str] = None
    total_max_marks: float = 100.0
    turnaround_deadline: Optional[str] = None
    # Masked fields confirmation
    parent_contact_masked: bool = True
    family_history_masked: bool = True
    sibling_data_masked: bool = True


class SanitizedSubscriberExpertProfile(BaseModel):
    """
    Subscriber's view of an expert profile.
    Strictly masks expert KYC, bank details, payout ledger, internal queue, and commission splits.
    """
    model_config = ConfigDict(extra="ignore")

    expert_id: str
    display_name: str
    photo_url: Optional[str] = None
    subjects: List[str] = Field(default_factory=list)
    boards: List[str] = Field(default_factory=list)
    classes: List[str] = Field(default_factory=list)
    qualifications: str
    experience_years: int = 0
    average_rating: float = 5.0
    total_reviews_count: int = 0
    turnaround_hours: int = 48
    evaluation_fee_inr: float = 500.0
    # Masked fields confirmation
    bank_payout_details_masked: bool = True
    kyc_identity_masked: bool = True
    commission_percentage_masked: bool = True


class ReportRetentionAuditItemSchema(BaseModel):
    """Audit status of an individual report in the retention lifecycle."""
    model_config = ConfigDict(extra="ignore")

    report_id: str
    report_type: str
    academic_year: str
    period_key: str
    retention_status: str = Field(..., description="'ACTIVE_CURRENT_YEAR', 'PERMANENT_HISTORICAL_ARCHIVE', 'RETIRED_INTERMEDIATE_DRAFT'")
    is_accessible_to_parent: bool
    pdf_storage_path: Optional[str] = None


class ReportRetentionAuditResponse(BaseModel):
    """Audit breakdown of a student's consolidated reports across academic years."""
    model_config = ConfigDict(extra="ignore")

    child_id: str
    current_academic_year: str
    total_reports_found: int
    active_current_year_reports_count: int
    permanent_historical_archives_count: int
    retired_intermediate_drafts_count: int
    reports: List[ReportRetentionAuditItemSchema] = Field(default_factory=list)


class EvaluationRetentionAuditResponse(BaseModel):
    """Retention status for an expert evaluation case."""
    model_config = ConfigDict(extra="ignore")

    evaluation_id: str
    academic_year: str
    case_completed_at: Optional[str] = None
    is_within_dispute_window: bool
    statutory_financial_audit_retained: bool = True
    artifacts_download_active: bool
    retention_policy: str

