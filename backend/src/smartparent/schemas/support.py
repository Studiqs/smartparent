"""
STUDIQS® SmartParent™ (v6.2 & v6.3 Extension) - Support Centre & SLA Schemas
=============================================================================
Module: src.smartparent.schemas.support
Section 14: Help Centre, Ticketing and Support Operating Models
Section 27: 48-Hour Hard SLA Support Operating Model with Continuous Escalation

Type-safe Pydantic v2 schemas for:
  - Self-Service FAQ Search & Resolution
  - Support Ticket Creation, Triage, Status Transitions & Reopen
  - Threaded Asynchronous Messages & Attachments
  - 48-Hour Hard SLA Countdown, Escalation Milestones & Operational Telemetry
  - Administrative Triage, Metrics & Audit Logs
=============================================================================
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator

from src.smartparent.core.constants import (
    TicketStatus,
    SupportTicketCategory,
    SupportTicketPriority,
    SupportSenderRole,
    SLAEscalationLevel,
)


# =============================================================================
# 1. Self-Service FAQ & Knowledge Base Schemas
# =============================================================================

class FAQArticleSchema(BaseModel):
    """Knowledge base article representation."""
    model_config = ConfigDict(extra="ignore")

    article_id: str
    category: str
    title: str
    summary: str
    content: str
    tags: List[str] = Field(default_factory=list)
    action_label: Optional[str] = None
    action_deep_link: Optional[str] = None
    helpful_count: int = 0


class FAQSearchResultItemSchema(BaseModel):
    """Individual FAQ article search match with relevance score."""
    model_config = ConfigDict(extra="ignore")

    article: FAQArticleSchema
    relevance_score: float
    matched_terms: List[str] = Field(default_factory=list)


class FAQSearchRequest(BaseModel):
    """Payload to search knowledge base."""
    model_config = ConfigDict(extra="ignore")

    query: str = Field(default="", description="Search keywords, question, or problem description")
    category: Optional[str] = Field(default=None, description="Optional category filter")
    limit: int = Field(default=5, ge=1, le=20)


class FAQSearchResponse(BaseModel):
    """Search results response with resolution guidance."""
    model_config = ConfigDict(extra="ignore")

    query: str
    total_found: int
    results: List[FAQSearchResultItemSchema]
    suggested_ticket_category: Optional[str] = None
    fallback_message: Optional[str] = None


# =============================================================================
# 2. Threaded Message Schemas
# =============================================================================

class SupportMessageCreateRequest(BaseModel):
    """Request payload to post a message in a ticket thread."""
    model_config = ConfigDict(extra="ignore")

    message_text: str = Field(..., min_length=1, max_length=5000, description="Message body")
    attachment_url: Optional[str] = Field(default=None, description="URL to screenshot or report PDF")
    attachment_filename: Optional[str] = Field(default=None, description="Original filename of attachment")
    is_internal_note: bool = Field(default=False, description="Hidden internal note (agents/admins only)")


class SupportMessageResponse(BaseModel):
    """Message item in support thread."""
    model_config = ConfigDict(extra="ignore")

    message_id: str
    ticket_id: str
    sender_id: str
    sender_role: str
    message_text: str
    attachment_url: Optional[str] = None
    attachment_filename: Optional[str] = None
    is_internal_note: bool = False
    created_at: datetime


# =============================================================================
# 3. SLA Escalation Event Schemas
# =============================================================================

class SupportSLAEventResponse(BaseModel):
    """Audit log entry for automated 12h/24h/36h/48h SLA milestones."""
    model_config = ConfigDict(extra="ignore")

    event_id: str
    ticket_id: str
    escalation_level: str
    triggered_at: datetime
    notified_to: Optional[str] = None
    notes: Optional[str] = None


class TicketSLAStatusResponse(BaseModel):
    """Real-time continuous 48-hour SLA status for a ticket."""
    model_config = ConfigDict(extra="ignore")

    ticket_id: str
    ticket_number: str
    sla_deadline: datetime
    elapsed_hours: float
    remaining_hours: float
    progress_percentage: float
    is_first_response_pending: bool
    is_first_response_overdue: bool
    is_sla_breached: bool
    urgency_level: str  # 'CALM', 'ATTENTION_NEEDED', 'CRITICAL_WARNING', 'BREACHED'
    triggered_milestones: List[str] = Field(default_factory=list)


# =============================================================================
# 4. Support Ticket Request & Response Schemas
# =============================================================================

class TicketCreateRequest(BaseModel):
    """Payload to create a new support ticket."""
    model_config = ConfigDict(extra="ignore")

    category: str = Field(..., description="Category from SupportTicketCategory (e.g. BILLING_REFUND, MARKS_ENTRY)")
    subject: str = Field(..., min_length=3, max_length=200, description="Concise summary of problem")
    description: str = Field(..., min_length=10, max_length=10000, description="Detailed explanation of the issue")
    ticket_type: Optional[str] = Field(default=None, description="v6.2 type (e.g. CORRECTION_DISPUTE, PAYMENT_ISSUE)")
    case_id: Optional[str] = Field(default=None, description="Optional UUID of related evaluation case")
    priority: Optional[str] = Field(default=None, description="Optional initial priority override")
    attachment_url: Optional[str] = Field(default=None, description="Optional screenshot attachment URL")
    attachment_filename: Optional[str] = Field(default=None, description="Attachment filename")

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        clean = v.strip().upper()
        valid = [c.value for c in SupportTicketCategory]
        if clean not in valid:
            # Fallback to GUIDANCE if unrecognized
            return SupportTicketCategory.GUIDANCE.value
        return clean


class TicketUpdateRequest(BaseModel):
    """Payload to update ticket metadata."""
    model_config = ConfigDict(extra="ignore")

    priority: Optional[str] = None
    category: Optional[str] = None
    assigned_to: Optional[str] = None


class TicketAssignRequest(BaseModel):
    """Payload for administrative assignment to support agent."""
    model_config = ConfigDict(extra="ignore")

    assigned_to: str = Field(..., description="UUID of support agent")


class TicketResolveRequest(BaseModel):
    """Payload to mark ticket as resolved."""
    model_config = ConfigDict(extra="ignore")

    resolution_notes: str = Field(..., min_length=5, max_length=5000, description="Resolution details for parent")


class TicketReopenRequest(BaseModel):
    """Payload for subscriber to reopen resolved/closed ticket."""
    model_config = ConfigDict(extra="ignore")

    reopen_reason: str = Field(..., min_length=5, max_length=2000, description="Why the issue persists or was unresolved")


class SupportTicketResponse(BaseModel):
    """Core support ticket summary representation."""
    model_config = ConfigDict(extra="ignore")

    ticket_id: str
    ticket_number: str
    subscriber_id: str
    case_id: Optional[str] = None
    category: str
    ticket_type: Optional[str] = None
    subject: str
    description: str
    ticket_status: str
    priority: str
    assigned_to: Optional[str] = None
    assigned_at: Optional[datetime] = None
    sla_deadline: datetime
    first_response_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    is_sla_breached: bool = False
    resolution_notes: Optional[str] = None
    reopen_count: int = 0
    created_at: datetime
    updated_at: datetime
    # Enriched Telemetry
    elapsed_hours: Optional[float] = None
    remaining_hours: Optional[float] = None
    urgency_level: Optional[str] = None


class SupportTicketDetailResponse(SupportTicketResponse):
    """Detailed support ticket response including threaded messages and SLA audit events."""
    model_config = ConfigDict(extra="ignore")

    messages: List[SupportMessageResponse] = Field(default_factory=list)
    sla_events: List[SupportSLAEventResponse] = Field(default_factory=list)


class SupportTicketListResponse(BaseModel):
    """Paginated list of support tickets."""
    model_config = ConfigDict(extra="ignore")

    tickets: List[SupportTicketResponse]
    total: int
    page: int
    limit: int


# =============================================================================
# 5. Administrative SLA Audit & Metrics Schemas
# =============================================================================

class AdminSLABatchAuditResponse(BaseModel):
    """Operational response for automated SLA batch audit sweep."""
    model_config = ConfigDict(extra="ignore")

    total_active_tickets: int
    sla_compliant_count: int
    first_response_overdue_count: int
    at_risk_count: int
    breached_count: int
    overall_compliance_rate_pct: float
    audit_timestamp: str
    escalations_to_dispatch: List[Dict[str, Any]] = Field(default_factory=list)


class AdminSupportMetricsResponse(BaseModel):
    """Operational dashboard metrics for support leadership."""
    model_config = ConfigDict(extra="ignore")

    total_tickets: int
    open_tickets: int
    in_progress_tickets: int
    awaiting_customer_tickets: int
    resolved_tickets: int
    closed_tickets: int
    breached_tickets: int
    overall_sla_compliance_pct: float
    average_resolution_hours: float
    average_first_response_hours: float
    category_breakdown: Dict[str, int] = Field(default_factory=dict)
    priority_breakdown: Dict[str, int] = Field(default_factory=dict)
