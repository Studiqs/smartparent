"""
STUDIQS® SmartParent™ (v6.2 & v6.3 Extension) - Section 15 Notification Engine Unit Tests
=============================================================================
Module: tests.unit.test_section15_notification_engine
Section 15: Notifications, Monthly Parent Pulse and Engagement

Validates:
  1. BaseEngine lifecycle & zero-crash resilience
  2. Canonical event template interpolation (English & Tamil)
  3. Action deep-link and button label resolution
  4. Automatic priority & icon classification (URGENT, HIGH, NORMAL, LOW)
  5. Anti-spam throttling and cooldown heuristics
  6. Safe degraded fallback handling
=============================================================================
"""

import uuid
from datetime import datetime, timedelta, timezone
import pytest

from src.smartparent.engines.section_15_notifications.notification_engine import (
    NotificationEngine,
    NotificationPayloadInput,
    EnrichedNotificationResult,
    EVENT_TEMPLATES,
)
from src.smartparent.core.constants import NotificationEventType


@pytest.fixture
def engine():
    return NotificationEngine()


# =============================================================================
# 1. BaseEngine Lifecycle & Templates
# =============================================================================

def test_engine_initialization_and_health(engine):
    assert engine.name == "NotificationEngine"
    status = engine.health_check()
    assert status["status"] == "healthy"
    assert status["circuit_state"] == "CLOSED"


def test_report_ready_notification_template_english(engine):
    payload = NotificationPayloadInput(
        subscriber_id=str(uuid.uuid4()),
        child_id=str(uuid.uuid4()),
        event_type=NotificationEventType.REPORT_READY.value,
        language="en",
        metadata={
            "student_name": "Ananya",
            "report_month": "October 2026",
        },
    )
    result = engine.run(payload.model_dump())
    assert isinstance(result, EnrichedNotificationResult)
    assert result.event_type == NotificationEventType.REPORT_READY.value
    assert "Monthly Parent Pulse Report Ready" in result.title
    assert "Ananya's October 2026 learning cycle report is now available." in result.message
    assert result.action_label == "View Report"
    assert f"/reports/{payload.child_id}/monthly" in result.action_url
    assert result.priority == "HIGH"
    assert result.icon_type == "REPORT"


def test_report_ready_notification_template_tamil(engine):
    payload = NotificationPayloadInput(
        subscriber_id=str(uuid.uuid4()),
        child_id=str(uuid.uuid4()),
        event_type=NotificationEventType.REPORT_READY.value,
        language="ta",
        metadata={
            "student_name": "அனன்யா",
            "report_month": "அக்டோபர் 2026",
        },
    )
    result = engine.run(payload.model_dump())
    assert "மாதாந்திர கற்றல் அறிக்கை தயாராக உள்ளது" in result.title
    assert "அனன்யா-ன் அக்டோபர் 2026 மாதாந்திர அறிக்கை" in result.message
    assert result.action_label == "அறிக்கையை பார்க்க"
    assert result.priority == "HIGH"


def test_topic_recheck_due_template(engine):
    payload = NotificationPayloadInput(
        subscriber_id=str(uuid.uuid4()),
        child_id=str(uuid.uuid4()),
        event_type=NotificationEventType.TOPIC_RECHECK_DUE.value,
        metadata={
            "student_name": "Arjun",
            "subject": "Mathematics",
            "topic_name": "Quadratic Equations",
            "topic_id": "MATH-10-CH4-TOPIC1",
        },
    )
    result = engine.run(payload.model_dump())
    assert "Quadratic Equations" in result.title
    assert "14 days since Arjun diagnosed a gap in Mathematics" in result.message
    assert result.action_label == "Start Recheck"
    assert "topic=MATH-10-CH4-TOPIC1" in result.action_url
    assert result.priority == "HIGH"


def test_evaluation_completed_template(engine):
    case_id = str(uuid.uuid4())
    payload = NotificationPayloadInput(
        subscriber_id=str(uuid.uuid4()),
        child_id=str(uuid.uuid4()),
        event_type=NotificationEventType.EVALUATION_COMPLETED.value,
        metadata={
            "student_name": "Zara",
            "subject": "Physics",
            "expert_name": "Prof. Natarajan",
            "case_id": case_id,
        },
    )
    result = engine.run(payload.model_dump())
    assert "Evaluated Answer Sheet Ready!" in result.title
    assert "Prof. Natarajan has finalized digital marking" in result.message
    assert result.action_url == f"/evaluations/{case_id}/pdf"
    assert result.action_label == "View Annotations"
    assert result.priority == "HIGH"


# =============================================================================
# 2. Priority & Urgency Scoring
# =============================================================================

def test_payment_failed_auto_triaged_to_urgent(engine):
    payload = NotificationPayloadInput(
        subscriber_id=str(uuid.uuid4()),
        event_type=NotificationEventType.PAYMENT_FAILED.value,
        metadata={"amount": "1399.00"},
    )
    result = engine.run(payload.model_dump())
    assert result.priority == "URGENT"
    assert "Rs. 1399.00 was declined" in result.message
    assert result.icon_type == "PAYMENT"


def test_support_sla_breached_auto_triaged_to_urgent(engine):
    payload = NotificationPayloadInput(
        subscriber_id=str(uuid.uuid4()),
        event_type=NotificationEventType.SUPPORT_SLA_BREACHED.value,
        metadata={"ticket_number": "TKT-2026-00042", "ticket_id": "mock_id"},
    )
    result = engine.run(payload.model_dump())
    assert result.priority == "URGENT"
    assert "TKT-2026-00042 exceeded 48-hour SLA deadline" in result.message
    assert result.icon_type == "SUPPORT"


def test_custom_overrides_precedence(engine):
    payload = NotificationPayloadInput(
        subscriber_id=str(uuid.uuid4()),
        event_type=NotificationEventType.NEW_RESULT_PROCESSED.value,
        title="Custom Custom Title Alert",
        message="Custom custom message override.",
        action_url="/custom/url",
        action_label="Click Here",
        priority="URGENT",
    )
    result = engine.run(payload.model_dump())
    assert result.title == "Custom Custom Title Alert"
    assert result.message == "Custom custom message override."
    assert result.action_url == "/custom/url"
    assert result.action_label == "Click Here"
    assert result.priority == "URGENT"


# =============================================================================
# 3. Anti-Spam Frequency Throttling Heuristics
# =============================================================================

def test_anti_spam_throttling_within_cooldown():
    now = datetime.now(timezone.utc)
    recent = now - timedelta(minutes=10)  # Sent 10 min ago (within 30 min cooldown)

    is_throttled, reason = NotificationEngine.evaluate_throttling(
        event_type=NotificationEventType.TOPIC_RECHECK_DUE.value,
        last_sent_at=recent,
        current_time=now,
        custom_cooldown_seconds=1800,
    )
    assert is_throttled is True
    assert "Throttled" in reason
    assert "Cooldown active" in reason


def test_anti_spam_throttling_after_cooldown_expires():
    now = datetime.now(timezone.utc)
    old = now - timedelta(minutes=45)  # Sent 45 min ago (past 30 min cooldown)

    is_throttled, reason = NotificationEngine.evaluate_throttling(
        event_type=NotificationEventType.TOPIC_RECHECK_DUE.value,
        last_sent_at=old,
        current_time=now,
        custom_cooldown_seconds=1800,
    )
    assert is_throttled is False
    assert reason is None


# =============================================================================
# 4. Safe Degraded Fallback Handling
# =============================================================================

def test_engine_fallback_on_invalid_data(engine):
    # Missing required subscriber_id will trigger fallback
    fallback_res = engine.fallback(ValueError("Missing subscriber"), {"event_type": "TEST"})
    assert isinstance(fallback_res, EnrichedNotificationResult)
    assert fallback_res.title == "Notification Alert"
    assert fallback_res.action_url == "/dashboard"
