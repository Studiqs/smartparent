"""
STUDIQS® SmartParent™ - Ecosystem & Cross-Product Schemas
=============================================================================
Module: src.smartparent.schemas.ecosystem

Defines request/response contracts for:
  1. Public Visitor Preview (Change 2 & Change 7)
  2. 13-Stage Conversion Funnel Telemetry & Attribution (Change 3 & Change 5)
  3. DPDP Act 2023 Affirmative Consent & Academy Handoff (Change 4 & Change 6)
  4. 'Discover Studiqs SmartParent' Promotional Card (Change 6)
=============================================================================
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


# =============================================================================
# 1. 13-Stage Conversion Funnel Event Enums (Change 3)
# =============================================================================

class FunnelEventEnum(str, Enum):
    VISITOR_LANDED = "VISITOR_LANDED"
    SEARCH_PERFORMED = "SEARCH_PERFORMED"
    PREVIEW_GENERATED = "PREVIEW_GENERATED"
    PRICING_VIEWED = "PRICING_VIEWED"
    OTP_STARTED = "OTP_STARTED"
    OTP_COMPLETED = "OTP_COMPLETED"
    CHECKOUT_INITIATED = "CHECKOUT_INITIATED"
    SUBSCRIPTION_PAID = "SUBSCRIPTION_PAID"
    DASHBOARD_VIEWED = "DASHBOARD_VIEWED"
    GAP_WATCHLIST_VIEWED = "GAP_WATCHLIST_VIEWED"
    GAP_RECHECK_STARTED = "GAP_RECHECK_STARTED"
    EXPERT_EVALUATION_BOOKED = "EXPERT_EVALUATION_BOOKED"
    ACADEMY_CROSS_PROMO_CLICKED = "ACADEMY_CROSS_PROMO_CLICKED"


class VisitorStateEnum(str, Enum):
    ANONYMOUS_PREVIEW = "ANONYMOUS_PREVIEW"
    SUBSCRIBED = "SUBSCRIBED"


# =============================================================================
# 2. Public Visitor Preview Schemas (Change 2)
# =============================================================================

class PublicPreviewRequest(BaseModel):
    subject: str = Field(..., min_length=2, max_length=50, description="Subject name (e.g. Mathematics, Science)")
    test_title: str = Field(..., min_length=2, max_length=150, description="Exam or test title")
    standard_class: str = Field("Class 10", description="Academic Class (e.g. Class 10)")
    board: str = Field("CBSE", description="Curriculum board (CBSE / State Board)")
    total_scored_marks: float = Field(..., ge=0.0, description="Marks scored by student")
    total_max_marks: float = Field(..., gt=0.0, description="Maximum possible exam marks")

    @field_validator("total_max_marks")
    @classmethod
    def validate_marks(cls, v: float, values: Any) -> float:
        return v


class PublicPreviewCard(BaseModel):
    card_id: str
    title: str
    card_type: str  # "SCORE_SUMMARY" | "TOPIC_MASTERY" | "LOCKED_GAP" | "LOCKED_TRAJECTORY"
    is_locked: bool
    data: Dict[str, Any]
    teaser_message: Optional[str] = None


class PublicPreviewResponse(BaseModel):
    preview_id: uuid.UUID
    visitor_state: VisitorStateEnum = VisitorStateEnum.ANONYMOUS_PREVIEW
    subject: str
    percentage: float
    mastery_tier: str
    unlocked_cards: List[PublicPreviewCard]
    locked_teasers: List[PublicPreviewCard]
    plan_ladder: Dict[str, Any]
    cta_text: str
    cta_action: str
    remaining_daily_previews: int


# =============================================================================
# 3. Attribution & Ingestion Telemetry Schemas (Change 5)
# =============================================================================

class TelemetryEventSchema(BaseModel):
    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    event_name: FunnelEventEnum
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    anonymous_session_id: str = Field(..., min_length=4, max_length=64)
    subscriber_id: Optional[uuid.UUID] = None
    referral_id: Optional[str] = None
    source_utm: Optional[str] = None
    city: Optional[str] = None
    category: Optional[str] = None
    visitor_state: VisitorStateEnum = VisitorStateEnum.ANONYMOUS_PREVIEW
    consent_version: str = "v1.2_dpdp"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TelemetryBatchRequest(BaseModel):
    events: List[TelemetryEventSchema] = Field(..., min_length=1, max_length=50)


class TelemetryIngestResponse(BaseModel):
    ingested_count: int
    duplicates_filtered: int
    status: str = "SUCCESS"


class LinkAnonymousSessionRequest(BaseModel):
    anonymous_session_id: str = Field(..., min_length=4, max_length=64)
    consent_given: bool = True
    consent_version: str = "v1.2_dpdp"


class LinkAnonymousSessionResponse(BaseModel):
    subscriber_id: uuid.UUID
    anonymous_session_id: str
    linked_events_count: int
    message: str


# =============================================================================
# 4. DPDP Act 2023 Affirmative Consent & Academy Handoff (Change 4 & Change 6)
# =============================================================================

class CrossProductConsentRequest(BaseModel):
    child_id: uuid.UUID
    target_academy_id: uuid.UUID
    target_academy_name: str
    consented_subject: str
    consented_topic_gap: str
    parent_affirmative_consent: bool = Field(..., description="Explicit affirmative consent from parent")
    consent_version: str = "2026.1_DPDP"

    @field_validator("parent_affirmative_consent")
    @classmethod
    def must_be_true(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Affirmative parental consent is strictly required under the DPDP Act 2023.")
        return v


class CrossProductConsentResponse(BaseModel):
    consent_id: uuid.UUID
    child_id: uuid.UUID
    target_academy_name: str
    consented_subject: str
    is_consent_active: bool
    handoff_referral_token: str
    expires_at: datetime
    dpdp_compliance_notice: str


class RevokeConsentRequest(BaseModel):
    consent_id: uuid.UUID
    child_id: uuid.UUID


# =============================================================================
# 5. SmartParent Discovery Card for Academy Connect (Change 6)
# =============================================================================

class SmartParentDiscoveryCardResponse(BaseModel):
    product_name: str = "STUDIQS® SmartParent™"
    tagline: str = "Independent Class 1–12 Parent Learning Intelligence & Syllabus Diagnostics"
    features: List[str]
    pricing_ladder: Dict[str, str]
    view_plans_url: str
    referral_campaign_id: str
    statutory_notice: str

