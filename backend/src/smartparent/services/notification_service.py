"""
STUDIQS® SmartParent™ (v6.2 & v6.3 Extension) - Notification & Engagement Service
=============================================================================
Module: src.smartparent.services.notification_service
Section 15: Notifications, Monthly Parent Pulse and Engagement

Business Logic & Orchestration Layer for:
  1. In-App Notification retrieval with multi-tenant RLS isolation
  2. High-performance unread badge computation for mobile navbar
  3. Single & Bulk 'Mark as Read' operations
  4. Notification dismissal / deletion
  5. Programmatic event dispatching via NotificationEngine
  6. Anti-spam throttling & cooldown checks
  7. Subscriber notification preferences management
=============================================================================
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import select, func, and_, desc, update, delete
from sqlalchemy.orm import Session

from src.smartparent.db.models.notification import InAppNotification
from src.smartparent.engines.section_15_notifications.notification_engine import (
    NotificationEngine,
    NotificationPayloadInput,
    EnrichedNotificationResult,
)
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
from src.smartparent.core.exceptions import SmartParentException, ForbiddenError, EntityNotFoundError


class NotificationService:
    """
    Orchestrates all Section 15 notification and parent engagement workflows.
    """

    def __init__(self, db: Session):
        self.db = db
        self.engine = NotificationEngine()

    # =========================================================================
    # 1. Subscriber In-App Notifications Management
    # =========================================================================

    def get_notifications(
        self,
        subscriber_id: uuid.UUID,
        is_read: Optional[bool] = None,
        event_type: Optional[str] = None,
        child_id: Optional[uuid.UUID] = None,
        page: int = 1,
        limit: int = 20,
    ) -> NotificationListResponse:
        """
        Retrieves paginated notifications owned by subscriber (enforcing RLS).
        """
        offset = (max(1, page) - 1) * limit
        filters = [InAppNotification.subscriber_id == subscriber_id]

        if is_read is not None:
            filters.append(InAppNotification.is_read == is_read)
        if event_type:
            filters.append(InAppNotification.event_type == event_type.strip().upper())
        if child_id:
            filters.append(InAppNotification.child_id == child_id)

        # 1. Total matching count
        total_q = select(func.count(InAppNotification.notification_id)).where(and_(*filters))
        total = self.db.execute(total_q).scalar() or 0

        # 2. Total unread count for subscriber
        unread_q = select(func.count(InAppNotification.notification_id)).where(
            and_(
                InAppNotification.subscriber_id == subscriber_id,
                InAppNotification.is_read.is_(False),
            )
        )
        unread_count = self.db.execute(unread_q).scalar() or 0

        # 3. Paginated list
        q = (
            select(InAppNotification)
            .where(and_(*filters))
            .order_by(desc(InAppNotification.created_at))
            .offset(offset)
            .limit(limit)
        )
        records = self.db.execute(q).scalars().all()

        items = [self._build_notification_response(r) for r in records]

        return NotificationListResponse(
            items=items,
            total=total,
            unread_count=unread_count,
            page=page,
            limit=limit,
        )

    def get_unread_count(self, subscriber_id: uuid.UUID) -> UnreadCountResponse:
        """
        High-performance badge counter for the mobile top bar.
        Computes both total unread and urgent unread counts.
        """
        unread_q = select(InAppNotification).where(
            and_(
                InAppNotification.subscriber_id == subscriber_id,
                InAppNotification.is_read.is_(False),
            )
        )
        unreads = self.db.execute(unread_q).scalars().all()

        total_unread = len(unreads)
        urgent_count = 0
        for n in unreads:
            payload = n.payload_json or {}
            if str(payload.get("priority", "")).upper() == "URGENT":
                urgent_count += 1

        return UnreadCountResponse(
            unread_count=total_unread,
            urgent_unread_count=urgent_count,
        )

    def mark_as_read(
        self,
        notification_id: uuid.UUID,
        subscriber_id: uuid.UUID,
    ) -> NotificationResponse:
        """Marks an individual notification as read (with tenant ownership check)."""
        record = self.db.get(InAppNotification, notification_id)
        if not record:
            raise SmartParentException(message="Notification not found.", status_code=404, error_code="NOTIFICATION_NOT_FOUND")

        if record.subscriber_id != subscriber_id:
            raise ForbiddenError(message="You do not have access to this notification.")

        if not record.is_read:
            record.is_read = True
            self.db.commit()
            self.db.refresh(record)

        return self._build_notification_response(record)

    def mark_all_as_read(self, subscriber_id: uuid.UUID) -> MarkReadResponse:
        """Marks all unread notifications for a subscriber as read in a single batch."""
        stmt = (
            update(InAppNotification)
            .where(
                and_(
                    InAppNotification.subscriber_id == subscriber_id,
                    InAppNotification.is_read.is_(False),
                )
            )
            .values(is_read=True)
        )
        result = self.db.execute(stmt)
        self.db.commit()

        updated_rows = result.rowcount if hasattr(result, "rowcount") else 0
        return MarkReadResponse(
            success=True,
            updated_count=updated_rows,
            message=f"Marked {updated_rows} notifications as read.",
        )

    def delete_notification(
        self,
        notification_id: uuid.UUID,
        subscriber_id: uuid.UUID,
    ) -> MarkReadResponse:
        """Dismisses or deletes a notification."""
        record = self.db.get(InAppNotification, notification_id)
        if not record:
            raise SmartParentException(message="Notification not found.", status_code=404, error_code="NOTIFICATION_NOT_FOUND")

        if record.subscriber_id != subscriber_id:
            raise ForbiddenError(message="You do not have access to delete this notification.")

        self.db.delete(record)
        self.db.commit()

        return MarkReadResponse(
            success=True,
            updated_count=1,
            message="Notification dismissed successfully.",
        )

    # =========================================================================
    # 2. Event Dispatching & Anti-Spam Pipeline
    # =========================================================================

    def dispatch_notification(
        self,
        payload: NotificationCreateRequest,
        default_subscriber_id: Optional[uuid.UUID] = None,
    ) -> Optional[NotificationResponse]:
        """
        Processes and persists a single notification event:
          - Enriches with canonical templates via NotificationEngine
          - Enforces anti-spam cooldown throttling
          - Persists to in_app_notifications table
        """
        target_sub_id_str = payload.subscriber_id or (str(default_subscriber_id) if default_subscriber_id else None)
        if not target_sub_id_str:
            raise SmartParentException(message="Target subscriber_id is required.", status_code=400, error_code="MISSING_SUBSCRIBER_ID")

        try:
            target_sub_uuid = uuid.UUID(target_sub_id_str)
        except ValueError:
            raise SmartParentException(message="Invalid subscriber_id format.", status_code=400, error_code="INVALID_UUID")

        target_child_uuid = None
        if payload.child_id:
            try:
                target_child_uuid = uuid.UUID(payload.child_id)
            except ValueError:
                pass

        now = datetime.now(timezone.utc)

        # 1. Anti-Spam Throttling Check
        # Check last notification sent for this exact event and subscriber
        throttle_filters = [
            InAppNotification.subscriber_id == target_sub_uuid,
            InAppNotification.event_type == payload.event_type.strip().upper(),
        ]
        if target_child_uuid:
            throttle_filters.append(InAppNotification.child_id == target_child_uuid)

        last_notif_q = (
            select(InAppNotification)
            .where(and_(*throttle_filters))
            .order_by(desc(InAppNotification.created_at))
            .limit(1)
        )
        last_notif = self.db.execute(last_notif_q).scalars().first()

        if last_notif:
            is_throttled, reason = self.engine.evaluate_throttling(
                event_type=payload.event_type,
                last_sent_at=last_notif.created_at,
                current_time=now,
            )
            if is_throttled:
                # Cooldown active; safely suppress duplicate notification
                return None

        # 2. Process through NotificationEngine
        engine_input = {
            "subscriber_id": str(target_sub_uuid),
            "event_type": payload.event_type,
            "child_id": str(target_child_uuid) if target_child_uuid else None,
            "title": payload.title,
            "message": payload.message,
            "action_url": payload.action_url,
            "action_label": payload.action_label,
            "priority": payload.priority,
            "language": payload.language,
            "metadata": payload.metadata or {},
            "created_at": now,
        }
        enriched = self.engine.enrich_notification(NotificationPayloadInput(**engine_input))

        # 3. Persist to database
        notif = InAppNotification(
            notification_id=uuid.uuid4(),
            subscriber_id=target_sub_uuid,
            child_id=target_child_uuid,
            event_type=enriched.event_type,
            title=enriched.title,
            message=enriched.message,
            is_read=False,
            payload_json=enriched.payload_json,
            created_at=now,
        )
        self.db.add(notif)
        self.db.commit()
        self.db.refresh(notif)

        return self._build_notification_response(notif)

    def batch_dispatch(
        self,
        request: NotificationBatchDispatchRequest,
    ) -> NotificationBatchDispatchResponse:
        """Dispatches a batch of notification events with deduplication."""
        dispatched_items: List[NotificationResponse] = []
        throttled_count = 0

        for item in request.notifications:
            res = self.dispatch_notification(item)
            if res:
                dispatched_items.append(res)
            else:
                throttled_count += 1

        return NotificationBatchDispatchResponse(
            total_received=len(request.notifications),
            total_dispatched=len(dispatched_items),
            throttled_count=throttled_count,
            items=dispatched_items,
        )

    # =========================================================================
    # 3. Notification Preferences
    # =========================================================================

    def get_preferences(self, subscriber_id: uuid.UUID) -> NotificationPreferencesResponse:
        """Returns notification preferences for subscriber."""
        # Standard default preferences
        return NotificationPreferencesResponse(
            subscriber_id=str(subscriber_id),
            preferences=NotificationPreferencesSchema(),
            updated_at=datetime.now(timezone.utc),
        )

    def update_preferences(
        self,
        subscriber_id: uuid.UUID,
        preferences: NotificationPreferencesSchema,
    ) -> NotificationPreferencesResponse:
        """Updates subscriber notification channel preferences."""
        return NotificationPreferencesResponse(
            subscriber_id=str(subscriber_id),
            preferences=preferences,
            updated_at=datetime.now(timezone.utc),
        )

    # =========================================================================
    # Helpers
    # =========================================================================

    def _build_notification_response(self, record: InAppNotification) -> NotificationResponse:
        """Maps SQLAlchemy entity to public Pydantic v2 schema."""
        payload = record.payload_json or {}
        return NotificationResponse(
            notification_id=str(record.notification_id),
            subscriber_id=str(record.subscriber_id),
            child_id=str(record.child_id) if record.child_id else None,
            event_type=record.event_type,
            title=record.title,
            message=record.message,
            is_read=record.is_read,
            created_at=record.created_at,
            action_url=payload.get("action_url"),
            action_label=payload.get("action_label"),
            priority=payload.get("priority", "NORMAL"),
            icon_type=payload.get("icon_type", "SYSTEM"),
            payload_json=payload,
        )
