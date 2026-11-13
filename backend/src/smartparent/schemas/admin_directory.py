"""
STUDIQS® SmartParent™ (v6.3 Complete) - Admin Subscriber Directory Schemas
=============================================================================
Module: src.smartparent.schemas.admin_directory
Section 25.4: Administrative Searchable Subscriber Directory & Manual Overrides

Defines strict Pydantic v2 schemas for executive subscriber management:
  - Search & Multi-criteria filtering (Plan, Duration, Expiry, Status, Query)
  - Detailed 360 Account Overview (Children, Billing Invoices, Tickets, Audits)
  - Authorized Manual Subscription Adjustments with mandatory audit reason
=============================================================================
"""

import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class AdminSubscriberDirectoryItemSchema(BaseModel):
    """Summarized subscriber entity for directory indexing and tables."""
    model_config = ConfigDict(from_attributes=True)

    subscriber_id: uuid.UUID
    parent_name: str
    mobile_number: str
    email: Optional[str] = None
    subscription_plan: str
    duration_months: int = 1
    subscribed_children_count: int = 0
    children_names: List[str] = Field(default_factory=list)
    subscription_start_date: Optional[datetime] = None
    subscription_end_date: Optional[datetime] = None
    subscription_status: str
    days_until_expiry: Optional[int] = None
    auto_renew: bool = False
    last_successful_payment_date: Optional[datetime] = None
    last_successful_payment_amount: Optional[float] = None
    total_revenue_collected: float = 0.0
    support_ticket_count: int = 0
    created_at: datetime


class AdminSubscriberDirectoryResponse(BaseModel):
    """Paginated subscriber directory response."""
    total_subscribers: int
    page: int
    page_size: int
    total_pages: int
    subscribers: List[AdminSubscriberDirectoryItemSchema]


class AdminChildDetailItem(BaseModel):
    """Child profile linked to subscriber."""
    model_config = ConfigDict(from_attributes=True)

    child_id: uuid.UUID
    student_name: str
    standard_class: str
    board: str
    academic_year: Optional[str] = "2025-2026"


class AdminSubscriberDetailResponse(BaseModel):
    """Deep 360 overview of subscriber account, children, payments, and tickets."""
    subscriber: AdminSubscriberDirectoryItemSchema
    children: List[AdminChildDetailItem]
    subscriptions_history: List[Dict[str, Any]]
    payment_invoices: List[Dict[str, Any]]
    support_tickets: List[Dict[str, Any]]
    adjustment_audits: List[Dict[str, Any]]


class ManualSubscriptionAdjustmentRequest(BaseModel):
    """Mandatory administrative adjustment payload with audit trail."""
    action_type: str = Field(
        ...,
        pattern="^(EXTEND_VALIDITY|CHANGE_PLAN|OVERRIDE_STATUS)$",
        description="Action type: EXTEND_VALIDITY, CHANGE_PLAN, or OVERRIDE_STATUS",
    )
    new_plan_id: Optional[str] = Field(None, description="Required for CHANGE_PLAN (BASIC, ADVANCED, PRO)")
    extend_days: Optional[int] = Field(None, ge=1, le=365, description="Days to extend expiry for EXTEND_VALIDITY")
    new_status: Optional[str] = Field(None, description="Required for OVERRIDE_STATUS (ACTIVE, CANCELLED, etc.)")
    admin_user: str = Field(..., min_length=2, max_length=100, description="Username or email of admin actor")
    reason: str = Field(..., min_length=5, max_length=500, description="Mandatory business reason for adjustment")


class ManualSubscriptionAdjustmentResponse(BaseModel):
    """Result of manual administrative subscription adjustment."""
    audit_id: uuid.UUID
    subscriber_id: uuid.UUID
    subscription_id: uuid.UUID
    admin_user: str
    action_type: str
    previous_state: Dict[str, Any]
    new_state: Dict[str, Any]
    reason: str
    adjusted_at: datetime
    message: str

