"""
STUDIQS® SmartParent™ (v6.2 & v6.3 Extension) - In-App Notification & Engagement API Router
=============================================================================
Module: src.smartparent.api.v1.notification
Section 15: Notifications, Monthly Parent Pulse and Engagement

Endpoints:
  1. GET    /api/v1/notifications                  -> List subscriber notifications (RLS isolated)
  2. GET    /api/v1/notifications/unread-count     -> Fast unread badge counter for mobile navbar
  3. PATCH  /api/v1/notifications/{id}/read        -> Mark individual notification as read
  4. POST   /api/v1/notifications/mark-all-read    -> Bulk mark all subscriber notifications as read
  5. DELETE /api/v1/notifications/{id}             -> Dismiss/delete individual notification
  6. POST   /api/v1/notifications/dispatch         -> Dispatch single notification event
  7. POST   /api/v1/notifications/batch-dispatch   -> Broadcast batch of notification events
  8. GET    /api/v1/notifications/preferences      -> Get subscriber notification settings
  9. PUT    /api/v1/notifications/preferences      -> Update subscriber notification settings
=============================================================================
"""

import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.smartparent.api.deps import get_db, get_current_subscriber_id
from src.smartparent.schemas.notification import (
    NotificationResponse,
    NotificationListResponse,
    UnreadCountResponse,
    NotificationCreateRequest,
    NotificationBatchDispatchRequest,
    NotificationBatchDispatchResponse,
    NotificationPreferencesSchema,
    NotificationPreferencesResponse,
    MarkReadResponse,
)
from src.smartparent.services.notification_service import NotificationService
from src.smartparent.core.exceptions import SmartParentException

router = APIRouter(prefix="/notifications", tags=["Section 15: Notifications & Parent Engagement"])


@router.get(
    "",
    response_model=NotificationListResponse,
    summary="List In-App Notifications",
    description="Retrieves paginated notifications owned by the authenticated parent, with filters for unread status and event category.",
)
def list_notifications(
    is_read: Optional[bool] = Query(None, description="Filter by read/unread status"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    child_id: Optional[uuid.UUID] = Query(None, description="Filter by specific child"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    service = NotificationService(db)
    return service.get_notifications(
        subscriber_id=subscriber_id,
        is_read=is_read,
        event_type=event_type,
        child_id=child_id,
        page=page,
        limit=limit,
    )


@router.get(
    "/unread-count",
    response_model=UnreadCountResponse,
    summary="Get Unread Badge Counter",
    description="High-performance endpoint for mobile top bars returning unread and urgent badge counts.",
)
def get_unread_count(
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    service = NotificationService(db)
    return service.get_unread_count(subscriber_id)


@router.patch(
    "/{notification_id}/read",
    response_model=NotificationResponse,
    summary="Mark Notification as Read",
    description="Marks a specific notification as read by the authenticated subscriber.",
)
def mark_notification_read(
    notification_id: uuid.UUID,
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    service = NotificationService(db)
    try:
        return service.mark_as_read(notification_id=notification_id, subscriber_id=subscriber_id)
    except SmartParentException as spe:
        raise HTTPException(status_code=spe.status_code, detail=spe.message)


@router.post(
    "/mark-all-read",
    response_model=MarkReadResponse,
    summary="Mark All Notifications as Read",
    description="Marks all unread notifications for the authenticated subscriber as read in one atomic transaction.",
)
def mark_all_read(
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    service = NotificationService(db)
    return service.mark_all_as_read(subscriber_id)


@router.delete(
    "/{notification_id}",
    response_model=MarkReadResponse,
    summary="Dismiss Notification",
    description="Permanently deletes or dismisses an individual notification.",
)
def delete_notification(
    notification_id: uuid.UUID,
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    service = NotificationService(db)
    try:
        return service.delete_notification(notification_id=notification_id, subscriber_id=subscriber_id)
    except SmartParentException as spe:
        raise HTTPException(status_code=spe.status_code, detail=spe.message)


@router.post(
    "/dispatch",
    response_model=Optional[NotificationResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Dispatch Notification Event",
    description="Dispatches a single notification event. Automatically resolves templates, applies anti-spam throttling, and delivers deep-links.",
)
def dispatch_notification(
    payload: NotificationCreateRequest,
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    service = NotificationService(db)
    try:
        res = service.dispatch_notification(payload=payload, default_subscriber_id=subscriber_id)
        if res is None:
            # Throttled by anti-spam guard
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Notification suppressed by anti-spam frequency throttling.",
            )
        return res
    except SmartParentException as spe:
        raise HTTPException(status_code=spe.status_code, detail=spe.message)


@router.post(
    "/batch-dispatch",
    response_model=NotificationBatchDispatchResponse,
    summary="Batch Dispatch Notifications",
    description="Broadcasts multiple notification events for background workers and system event listeners.",
)
def batch_dispatch_notifications(
    request: NotificationBatchDispatchRequest,
    db: Session = Depends(get_db),
):
    service = NotificationService(db)
    return service.batch_dispatch(request)


@router.get(
    "/preferences",
    response_model=NotificationPreferencesResponse,
    summary="Get Notification Preferences",
    description="Retrieves the parent's notification preferences, channel settings, and quiet hours schedule.",
)
def get_preferences(
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    service = NotificationService(db)
    return service.get_preferences(subscriber_id)


@router.put(
    "/preferences",
    response_model=NotificationPreferencesResponse,
    summary="Update Notification Preferences",
    description="Updates the parent's channel preferences, quiet hours schedule, and preferred language.",
)
def update_preferences(
    preferences: NotificationPreferencesSchema,
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    service = NotificationService(db)
    return service.update_preferences(subscriber_id=subscriber_id, preferences=preferences)
