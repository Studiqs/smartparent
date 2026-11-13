"""
STUDIQS® SmartParent™ (v6.2 & v6.3 Extension) - Notification & Engagement Schemas
=============================================================================
Module: src.smartparent.schemas.notification
Section 15: Notifications, Monthly Parent Pulse and Engagement

Type-safe Pydantic v2 schemas for:
  - In-app notification representations & pagination
  - Unread badge counter for mobile navigation bars
  - Programmatic notification event dispatch
  - Batch event broadcasting for background workers
  - Parent notification preferences & quiet hours
=============================================================================
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator

from src.smartparent.core.constants import NotificationEventType


class NotificationResponse(BaseModel):
    """Public representation of an in-app notification item."""
    model_config = ConfigDict(extra="ignore")

    notification_id: str
    subscriber_id: str
    child_id: Optional[str] = None
    event_type: str
    title: str
    message: str
    is_read: bool = False
    created_at: datetime
    action_url: Optional[str] = None
    action_label: Optional[str] = None
    priority: str = "NORMAL"
    icon_type: str = "SYSTEM"
    payload_json: Dict[str, Any] = Field(default_factory=dict)


class NotificationListResponse(BaseModel):
    """Paginated list of subscriber notifications with unread count."""
    model_config = ConfigDict(extra="ignore")

    items: List[NotificationResponse]
    total: int
    unread_count: int
    page: int
    limit: int


class UnreadCountResponse(BaseModel):
    """High-performance badge response for mobile and web navbar."""
    model_config = ConfigDict(extra="ignore")

    unread_count: int
    urgent_unread_count: int = 0


class NotificationCreateRequest(BaseModel):
    """Payload to trigger or dispatch a notification event."""
    model_config = ConfigDict(extra="ignore")

    subscriber_id: Optional[str] = Field(default=None, description="Target subscriber UUID (or current user)")
    child_id: Optional[str] = Field(default=None, description="Optional child UUID for student-specific events")
    event_type: str = Field(..., description="NotificationEventType constant")
    title: Optional[str] = Field(default=None, description="Optional custom title override")
    message: Optional[str] = Field(default=None, description="Optional custom message body override")
    action_url: Optional[str] = Field(default=None, description="Deep-link path (e.g. /reports/123/monthly)")
    action_label: Optional[str] = Field(default=None, description="Button call-to-action label")
    priority: Optional[str] = Field(default=None, description="'LOW', 'NORMAL', 'HIGH', 'URGENT'")
    language: str = Field(default="en", description="'en' or 'ta'")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Event variables for template interpolation")

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, v: str) -> str:
        clean = v.strip().upper()
        valid = [e.value for e in NotificationEventType]
        if clean not in valid:
            # Fallback to system alert if not in standard enum
            return NotificationEventType.REPORT_READY.value
        return clean


class NotificationBatchDispatchRequest(BaseModel):
    """Batch payload to dispatch multiple notifications at once."""
    model_config = ConfigDict(extra="ignore")

    notifications: List[NotificationCreateRequest] = Field(..., min_length=1, max_length=100)


class NotificationBatchDispatchResponse(BaseModel):
    """Result of batch notification dispatch."""
    model_config = ConfigDict(extra="ignore")

    total_received: int
    total_dispatched: int
    throttled_count: int
    items: List[NotificationResponse] = Field(default_factory=list)


class NotificationPreferencesSchema(BaseModel):
    """Subscriber notification channel & schedule preferences."""
    model_config = ConfigDict(extra="ignore")

    in_app_enabled: bool = True
    push_enabled: bool = True
    whatsapp_enabled: bool = False
    quiet_hours_enabled: bool = False
    quiet_hours_start: Optional[str] = "22:00"
    quiet_hours_end: Optional[str] = "07:00"
    preferred_language: str = "en"  # "en" or "ta"


class NotificationPreferencesResponse(BaseModel):
    """Response containing subscriber preferences."""
    model_config = ConfigDict(extra="ignore")

    subscriber_id: str
    preferences: NotificationPreferencesSchema
    updated_at: datetime


class MarkReadResponse(BaseModel):
    """Response when marking notifications as read."""
    model_config = ConfigDict(extra="ignore")

    success: bool
    updated_count: int
    message: str
