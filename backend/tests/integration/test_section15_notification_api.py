"""
STUDIQS® SmartParent™ (v6.2 & v6.3 Extension) - Section 15 Notification API Integration Tests
=============================================================================
Module: tests.integration.test_section15_notification_api
Section 15: Notifications, Monthly Parent Pulse and Engagement

Validates the full REST API surface:
  1. GET    /api/v1/notifications                  -> Multi-tenant RLS isolation, pagination, filters
  2. GET    /api/v1/notifications/unread-count     -> Fast unread & urgent badge counters
  3. PATCH  /api/v1/notifications/{id}/read        -> Single mark-as-read + 403 RLS protection
  4. POST   /api/v1/notifications/mark-all-read    -> Atomic bulk mark-all-read
  5. DELETE /api/v1/notifications/{id}             -> Dismiss / delete + 403 RLS protection
  6. POST   /api/v1/notifications/dispatch         -> Canonical templating (EN/TA) + 429 Anti-Spam throttling
  7. POST   /api/v1/notifications/batch-dispatch   -> Broadcast batch dispatch with deduplication
  8. GET/PUT /api/v1/notifications/preferences     -> Channel preferences & quiet hours management
=============================================================================
"""

import uuid
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.smartparent.main import app
from src.smartparent.api.deps import get_db
from src.smartparent.db.base import Base
from src.smartparent.db.models.auth import Subscriber, Child
from src.smartparent.db.models.notification import InAppNotification
from src.smartparent.core.constants import NotificationEventType


@pytest.fixture
def client_with_db():
    """Sets up an in-memory SQLite DB with required models for Section 15 testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            Subscriber.__table__,
            Child.__table__,
            InAppNotification.__table__,
        ],
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    # Seed 2 distinct subscribers for strict multi-tenant isolation testing
    db = TestingSessionLocal()
    sub_1_id = uuid.uuid4()
    parent_1 = Subscriber(
        subscriber_id=sub_1_id,
        mobile_number="+919876543210",
        parent_name="Meenakshi Sundaram",
        password_hash="mock_hash_1",
        subscription_plan="PRO",
    )
    sub_2_id = uuid.uuid4()
    parent_2 = Subscriber(
        subscriber_id=sub_2_id,
        mobile_number="+919876543211",
        parent_name="Rajesh Kumar",
        password_hash="mock_hash_2",
        subscription_plan="PRO",
    )
    db.add_all([parent_1, parent_2])

    child_1_id = uuid.uuid4()
    child_1 = Child(
        child_id=child_1_id,
        subscriber_id=sub_1_id,
        student_name="Ananya Sundar",
        standard_class="Class 10",
        board="CBSE",
    )
    db.add(child_1)
    db.commit()
    db.close()

    with TestClient(app) as test_client:
        yield test_client, sub_1_id, sub_2_id, child_1_id, TestingSessionLocal

    app.dependency_overrides.clear()


# =============================================================================
# 1. Dispatch Notification & Canonical Templating (English & Tamil)
# =============================================================================

def test_dispatch_notification_english_canonical_template(client_with_db):
    client, sub_1_id, sub_2_id, child_1_id, TestingSessionLocal = client_with_db

    headers = {"X-Subscriber-Id": str(sub_1_id)}
    payload = {
        "event_type": NotificationEventType.REPORT_READY.value,
        "child_id": str(child_1_id),
        "language": "en",
        "metadata": {
            "student_name": "Ananya",
            "report_month": "October 2026",
        },
    }

    resp = client.post("/api/v1/notifications/dispatch", json=payload, headers=headers)
    assert resp.status_code == 201
    data = resp.json()

    assert data["event_type"] == NotificationEventType.REPORT_READY.value
    assert "Monthly Parent Pulse Report Ready" in data["title"]
    assert "Ananya's October 2026 learning cycle report is now available." in data["message"]
    assert data["action_label"] == "View Report"
    assert f"/reports/{child_1_id}/monthly" in data["action_url"]
    assert data["priority"] == "HIGH"
    assert data["icon_type"] == "REPORT"
    assert data["is_read"] is False


def test_dispatch_notification_tamil_canonical_template(client_with_db):
    client, sub_1_id, sub_2_id, child_1_id, TestingSessionLocal = client_with_db

    headers = {"X-Subscriber-Id": str(sub_1_id)}
    payload = {
        "event_type": NotificationEventType.TOPIC_RECHECK_DUE.value,
        "child_id": str(child_1_id),
        "language": "ta",
        "metadata": {
            "student_name": "அனன்யா",
            "subject": "Mathematics",
            "topic_name": "இருபடி சமன்பாடுகள்",
            "topic_id": "MATH-10-CH4",
        },
    }

    resp = client.post("/api/v1/notifications/dispatch", json=payload, headers=headers)
    assert resp.status_code == 201
    data = resp.json()

    assert "மறு ஆய்வு தேவை" in data["title"]
    assert "அனன்யா" in data["message"]
    assert data["action_label"] == "பயிற்சி செய்ய"
    assert data["priority"] == "HIGH"


# =============================================================================
# 2. Anti-Spam Frequency Throttling Guard (429 HTTP Code)
# =============================================================================

def test_anti_spam_throttling_on_rapid_duplicate_events(client_with_db):
    client, sub_1_id, sub_2_id, child_1_id, TestingSessionLocal = client_with_db

    headers = {"X-Subscriber-Id": str(sub_1_id)}
    payload = {
        "event_type": NotificationEventType.TOPIC_RECHECK_DUE.value,
        "child_id": str(child_1_id),
        "metadata": {
            "student_name": "Ananya",
            "subject": "Physics",
            "topic_name": "Light Reflection",
        },
    }

    # First dispatch succeeds
    resp1 = client.post("/api/v1/notifications/dispatch", json=payload, headers=headers)
    assert resp1.status_code == 201

    # Immediate second duplicate dispatch triggers anti-spam 429
    resp2 = client.post("/api/v1/notifications/dispatch", json=payload, headers=headers)
    assert resp2.status_code == 429
    assert "anti-spam frequency throttling" in resp2.json()["detail"]


# =============================================================================
# 3. Listing Notifications & Multi-Tenant RLS Isolation
# =============================================================================

def test_list_notifications_multi_tenant_isolation(client_with_db):
    client, sub_1_id, sub_2_id, child_1_id, TestingSessionLocal = client_with_db

    # Dispatch one notification for Parent 1
    client.post(
        "/api/v1/notifications/dispatch",
        json={
            "event_type": NotificationEventType.EVALUATION_COMPLETED.value,
            "child_id": str(child_1_id),
            "metadata": {"student_name": "Ananya", "subject": "Science"},
        },
        headers={"X-Subscriber-Id": str(sub_1_id)},
    )

    # Dispatch one notification for Parent 2
    client.post(
        "/api/v1/notifications/dispatch",
        json={
            "event_type": NotificationEventType.PAYMENT_RECEIVED.value,
            "metadata": {"amount": "1399", "plan_name": "PRO"},
        },
        headers={"X-Subscriber-Id": str(sub_2_id)},
    )

    # Query as Parent 1: Should only see their 1 notification
    resp1 = client.get("/api/v1/notifications", headers={"X-Subscriber-Id": str(sub_1_id)})
    assert resp1.status_code == 200
    res_data1 = resp1.json()
    assert res_data1["total"] == 1
    assert res_data1["items"][0]["subscriber_id"] == str(sub_1_id)
    assert res_data1["items"][0]["event_type"] == NotificationEventType.EVALUATION_COMPLETED.value

    # Query as Parent 2: Should only see Parent 2's notification
    resp2 = client.get("/api/v1/notifications", headers={"X-Subscriber-Id": str(sub_2_id)})
    assert resp2.status_code == 200
    res_data2 = resp2.json()
    assert res_data2["total"] == 1
    assert res_data2["items"][0]["subscriber_id"] == str(sub_2_id)
    assert res_data2["items"][0]["event_type"] == NotificationEventType.PAYMENT_RECEIVED.value


# =============================================================================
# 4. Fast Unread & Urgent Badge Counter
# =============================================================================

def test_fast_unread_and_urgent_badge_counter(client_with_db):
    client, sub_1_id, sub_2_id, child_1_id, TestingSessionLocal = client_with_db
    headers = {"X-Subscriber-Id": str(sub_1_id)}

    # Initially 0 unread
    resp = client.get("/api/v1/notifications/unread-count", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["unread_count"] == 0
    assert resp.json()["urgent_unread_count"] == 0

    # Dispatch a NORMAL notification
    client.post(
        "/api/v1/notifications/dispatch",
        json={
            "event_type": NotificationEventType.EXPERT_ASSIGNED.value,
            "metadata": {"student_name": "Ananya", "subject": "Maths"},
        },
        headers=headers,
    )

    # Dispatch an URGENT notification (Payment Failed)
    client.post(
        "/api/v1/notifications/dispatch",
        json={
            "event_type": NotificationEventType.PAYMENT_FAILED.value,
            "metadata": {"amount": "1399"},
        },
        headers=headers,
    )

    resp2 = client.get("/api/v1/notifications/unread-count", headers=headers)
    assert resp2.status_code == 200
    badge = resp2.json()
    assert badge["unread_count"] == 2
    assert badge["urgent_unread_count"] == 1  # 1 urgent payment failed


# =============================================================================
# 5. Single Mark As Read & RLS Protection
# =============================================================================

def test_mark_individual_notification_as_read(client_with_db):
    client, sub_1_id, sub_2_id, child_1_id, TestingSessionLocal = client_with_db
    headers_1 = {"X-Subscriber-Id": str(sub_1_id)}
    headers_2 = {"X-Subscriber-Id": str(sub_2_id)}

    # Create notification for Parent 1
    create_resp = client.post(
        "/api/v1/notifications/dispatch",
        json={
            "event_type": NotificationEventType.REPORT_READY.value,
            "metadata": {"student_name": "Ananya"},
        },
        headers=headers_1,
    )
    notif_id = create_resp.json()["notification_id"]

    # Parent 2 tries to mark Parent 1's notification as read -> 403 Forbidden
    hack_resp = client.patch(f"/api/v1/notifications/{notif_id}/read", headers=headers_2)
    assert hack_resp.status_code == 403

    # Parent 1 marks it as read -> 200 OK
    read_resp = client.patch(f"/api/v1/notifications/{notif_id}/read", headers=headers_1)
    assert read_resp.status_code == 200
    assert read_resp.json()["is_read"] is True

    # Unread counter reflects reduction
    counter_resp = client.get("/api/v1/notifications/unread-count", headers=headers_1)
    assert counter_resp.json()["unread_count"] == 0


# =============================================================================
# 6. Bulk Mark All As Read
# =============================================================================

def test_bulk_mark_all_read(client_with_db):
    client, sub_1_id, sub_2_id, child_1_id, TestingSessionLocal = client_with_db
    headers_1 = {"X-Subscriber-Id": str(sub_1_id)}

    # Dispatch 2 distinct notifications
    client.post(
        "/api/v1/notifications/dispatch",
        json={"event_type": NotificationEventType.ANSWER_SHEET_RECEIVED.value, "metadata": {"student_name": "Ananya"}},
        headers=headers_1,
    )
    client.post(
        "/api/v1/notifications/dispatch",
        json={"event_type": NotificationEventType.EVALUATION_UNDER_REVIEW.value, "metadata": {"student_name": "Ananya"}},
        headers=headers_1,
    )

    # Verify unread count is 2
    assert client.get("/api/v1/notifications/unread-count", headers=headers_1).json()["unread_count"] == 2

    # Bulk mark all read
    bulk_resp = client.post("/api/v1/notifications/mark-all-read", headers=headers_1)
    assert bulk_resp.status_code == 200
    assert bulk_resp.json()["success"] is True
    assert bulk_resp.json()["updated_count"] == 2

    # Verify unread count is 0
    assert client.get("/api/v1/notifications/unread-count", headers=headers_1).json()["unread_count"] == 0


# =============================================================================
# 7. Dismissal / Deletion with RLS Guard
# =============================================================================

def test_delete_notification(client_with_db):
    client, sub_1_id, sub_2_id, child_1_id, TestingSessionLocal = client_with_db
    headers_1 = {"X-Subscriber-Id": str(sub_1_id)}
    headers_2 = {"X-Subscriber-Id": str(sub_2_id)}

    # Create notification for Parent 1
    create_resp = client.post(
        "/api/v1/notifications/dispatch",
        json={"event_type": NotificationEventType.SUBSCRIPTION_EXPIRING_SOON.value, "metadata": {"days_left": "5"}},
        headers=headers_1,
    )
    notif_id = create_resp.json()["notification_id"]

    # Parent 2 tries to delete -> 403 Forbidden
    del_forbidden = client.delete(f"/api/v1/notifications/{notif_id}", headers=headers_2)
    assert del_forbidden.status_code == 403

    # Parent 1 deletes -> 200 OK
    del_ok = client.delete(f"/api/v1/notifications/{notif_id}", headers=headers_1)
    assert del_ok.status_code == 200
    assert del_ok.json()["success"] is True

    # Attempting to delete again -> 404 Not Found
    del_not_found = client.delete(f"/api/v1/notifications/{notif_id}", headers=headers_1)
    assert del_not_found.status_code == 404


# =============================================================================
# 8. Batch Dispatching with Deduplication
# =============================================================================

def test_batch_dispatch_notifications(client_with_db):
    client, sub_1_id, sub_2_id, child_1_id, TestingSessionLocal = client_with_db

    batch_payload = {
        "notifications": [
            {
                "subscriber_id": str(sub_1_id),
                "event_type": NotificationEventType.INVOICE_GENERATED.value,
                "metadata": {"invoice_number": "INV-2026-999", "amount": "1399"},
            },
            {
                "subscriber_id": str(sub_2_id),
                "event_type": NotificationEventType.SUPPORT_TICKET_CREATED.value,
                "metadata": {"ticket_number": "TKT-2026-00101"},
            },
            # Duplicate for sub_1 should be throttled
            {
                "subscriber_id": str(sub_1_id),
                "event_type": NotificationEventType.INVOICE_GENERATED.value,
                "metadata": {"invoice_number": "INV-2026-999", "amount": "1399"},
            },
        ]
    }

    resp = client.post("/api/v1/notifications/batch-dispatch", json=batch_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_received"] == 3
    assert data["total_dispatched"] == 2
    assert data["throttled_count"] == 1


# =============================================================================
# 9. Subscriber Notification Preferences & Quiet Hours
# =============================================================================

def test_get_and_update_notification_preferences(client_with_db):
    client, sub_1_id, sub_2_id, child_1_id, TestingSessionLocal = client_with_db
    headers = {"X-Subscriber-Id": str(sub_1_id)}

    # 1. Get default preferences
    get_resp = client.get("/api/v1/notifications/preferences", headers=headers)
    assert get_resp.status_code == 200
    pref_data = get_resp.json()
    assert pref_data["preferences"]["in_app_enabled"] is True
    assert pref_data["preferences"]["preferred_language"] == "en"

    # 2. Update preferences: enable Tamil, set quiet hours
    update_payload = {
        "in_app_enabled": True,
        "push_enabled": True,
        "whatsapp_enabled": False,
        "quiet_hours_enabled": True,
        "quiet_hours_start": "21:30",
        "quiet_hours_end": "07:00",
        "preferred_language": "ta",
    }

    put_resp = client.put("/api/v1/notifications/preferences", json=update_payload, headers=headers)
    assert put_resp.status_code == 200
    updated = put_resp.json()["preferences"]
    assert updated["preferred_language"] == "ta"
    assert updated["quiet_hours_enabled"] is True
    assert updated["quiet_hours_start"] == "21:30"
    assert updated["whatsapp_enabled"] is False
