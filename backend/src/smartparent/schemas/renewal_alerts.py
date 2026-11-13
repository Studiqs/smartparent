"""
STUDIQS® SmartParent™ (v6.3 Complete) - Renewal & Expiry Alert Schemas
=============================================================================
Module: src.smartparent.schemas.renewal_alerts
Section 24.6: Automatic Renewal and Expiry Alerts

Defines Pydantic v2 schemas for the 4-stage reminder schedule:
  - 7 Days Prior: First reminder
  - 3 Days Prior: Second reminder
  - 1 Day Prior: Final urgent notice
  - On Expiry: Expired notification
  - Post-Renewal: Confirmation notice
=============================================================================
"""

import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class AlertStageEnum(StrEnum):
    """The 4 mandatory notification stages + renewal confirmation."""
    REMINDER_7_DAYS = "REMINDER_7_DAYS"
    REMINDER_3_DAYS = "REMINDER_3_DAYS"
    REMINDER_1_DAY = "REMINDER_1_DAY"
    EXPIRED_NOTICE = "EXPIRED_NOTICE"
    RENEWAL_CONFIRMATION = "RENEWAL_CONFIRMATION"


class RenewalAlertItemSchema(BaseModel):
    """Detailed dispatched or pending renewal reminder."""
    model_config = ConfigDict(from_attributes=True)

    reminder_id: uuid.UUID
    subscription_id: uuid.UUID
    subscriber_id: uuid.UUID
    reminder_type: str
    scheduled_at: datetime
    sent_at: Optional[datetime] = None
    is_sent: bool
    notification_channel: str
    alert_title: str
    alert_message: str
    created_at: datetime


class ParentRenewalAlertBannerResponse(BaseModel):
    """Real-time renewal alert banner displayed on mobile app and parent dashboard."""
    subscriber_id: uuid.UUID
    has_active_alert: bool
    alert_severity: str = Field(..., description="INFO, WARNING, CRITICAL, or EXPIRED")
    days_remaining: Optional[int] = None
    expiry_date: Optional[datetime] = None
    plan_id: str
    auto_renew: bool
    banner_headline: str
    banner_message: str
    quick_action_cta: str
    checkout_url: str


class TriggerAlertSweepRequest(BaseModel):
    """Execution parameters for the background renewal alert sweeper."""
    simulate_date: Optional[date] = Field(None, description="Optional target date for sweep simulation")
    dry_run: bool = Field(default=False, description="If True, evaluates candidates without persisting alerts")


class AlertSweepSummaryResponse(BaseModel):
    """Executive operational summary of the completed alert sweep."""
    sweep_timestamp: datetime
    total_subscriptions_scanned: int
    alerts_dispatched_count: int
    alerts_skipped_already_sent_count: int
    stage_breakdown: Dict[str, int]
    dispatched_alerts: List[Dict[str, Any]]

