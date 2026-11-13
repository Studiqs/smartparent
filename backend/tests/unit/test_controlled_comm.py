"""
Unit Tests for STUDIQS® SmartParent™ Controlled Communication Engine (Engine 11)
Verifies:
  - Section 21 Anti-Contact boundary enforcement
  - Indian phone numbers (standard, +91, spaced, spelled-out digits)
  - Standard & obfuscated email address detection
  - External links, WhatsApp URLs, Zoom/Meet references
  - UPI payment handle detection (@okhdfcbank, @paytm)
  - Zero false-positives on academic discussions (questions, marks, equations, pages)
  - Redaction policy mode
  - Fail-closed fallback and CircuitBreaker stability
"""

import pytest
from src.smartparent.engines.controlled_comm import (
    ControlledCommEngine,
    MessagePayloadSchema,
    CommunicationModerationResultSchema,
)
from src.smartparent.core.constants import MessageSenderType


@pytest.fixture
def comm_engine():
    return ControlledCommEngine()


# ==============================================================================
# 1. Prohibited Contact Identifiers Detection
# ==============================================================================

@pytest.mark.parametrize(
    "prohibited_msg,expected_violation",
    [
        ("Call me at 9876543210 for quick doubts", "PHONE_NUMBER"),
        ("Send your answer to +91 94444 12345 please", "PHONE_NUMBER"),
        ("Contact 9 8 4 0 1 2 3 4 5 6 directly", "PHONE_NUMBER"),
        ("Call me at nine eight four zero one two three four five six", "SPELLED_PHONE_NUMBER"),
        ("My personal email is teacher_maths@gmail.com", "EMAIL_ADDRESS"),
        ("Send paper to tutor [at] yahoo [dot] com", "EMAIL_ADDRESS"),
        ("Check the solved paper at https://privatetuition.in/cbse", "EXTERNAL_URL"),
        ("Chat with me on wa.me/919876543210", "EXTERNAL_URL"),
        ("Join my class on zoom meeting tonight", "EXTERNAL_URL"),
        ("Pay evaluation fee to sundar@okhdfcbank", "UPI_HANDLE"),
        ("Direct fee transfer to expert@paytm", "UPI_HANDLE"),
        ("Please message me on whatsapp directly", "OFF_PLATFORM_SOLICITATION"),
        ("Call me directly outside the platform", "OFF_PLATFORM_SOLICITATION"),
    ]
)
def test_controlled_comm_blocks_prohibited_content(comm_engine, prohibited_msg, expected_violation):
    payload = {
        "case_id": "CASE-101",
        "sender_type": MessageSenderType.EXPERT,
        "sender_id": "EXPERT-1",
        "message_text": prohibited_msg,
        "policy_action": "BLOCK"
    }

    result = comm_engine.execute(payload)

    assert isinstance(result, CommunicationModerationResultSchema)
    assert result.is_blocked is True
    assert result.safety_tier == "CRITICAL" or result.safety_tier == "MODERATE"
    assert any(expected_violation in v for v in result.violation_types)
    assert "Message blocked" in result.sanitized_text


# ==============================================================================
# 2. Academic Communication Whitelist (Zero False Positives)
# ==============================================================================

@pytest.mark.parametrize(
    "academic_text",
    [
        "Please recheck question 4 calculation on page 2.",
        "The step marks for the integration problem seem lower than expected.",
        "In question 9, there are 8 sub-parts with 10 total marks.",
        "Kindly review the physics ray diagram for reflection and refraction in section B.",
        "The balanced reaction is 2H2 + O2 -> 2H2O as taught in NCERT chapter 1.",
        "Student scored 45 marks out of 50 in unit test 3.",
        "Please provide feedback on question 12 trigonometry proof.",
    ]
)
def test_controlled_comm_allows_academic_discussions(comm_engine, academic_text):
    payload = {
        "case_id": "CASE-102",
        "sender_type": MessageSenderType.PARENT,
        "sender_id": "PARENT-1",
        "message_text": academic_text,
        "policy_action": "BLOCK"
    }

    result = comm_engine.execute(payload)

    assert result.is_blocked is False
    assert result.safety_tier == "SAFE"
    assert len(result.violation_types) == 0
    assert result.sanitized_text == academic_text


# ==============================================================================
# 3. Redaction Mode Policy
# ==============================================================================

def test_controlled_comm_redaction_mode(comm_engine):
    payload = {
        "case_id": "CASE-103",
        "sender_type": MessageSenderType.EXPERT,
        "sender_id": "EXPERT-2",
        "message_text": "Good effort on problem 4. For extra doubt clearing, call 9876543210 or email test@gmail.com.",
        "policy_action": "REDACT"
    }

    result = comm_engine.execute(payload)

    assert result.is_blocked is False
    assert "9876543210" not in result.sanitized_text
    assert "test@gmail.com" not in result.sanitized_text
    assert "[PHONE_REDACTED]" in result.sanitized_text
    assert "[EMAIL_REDACTED]" in result.sanitized_text
    assert "Good effort on problem 4" in result.sanitized_text


# ==============================================================================
# 4. Fail-Closed Fallback on Error
# ==============================================================================

def test_controlled_comm_fails_closed_on_error(comm_engine):
    """Engine must fail-closed (block messages) if inspection pipeline encounters an error."""
    result = comm_engine.fallback(RuntimeError("Inspection timeout"), {"case_id": "CASE-FAIL", "message_text": "Some text"})

    assert result.is_blocked is True
    assert result.safety_tier == "CRITICAL"
    assert "Security inspection fallback triggered" in result.block_reason


# ==============================================================================
# 5. Circuit Breaker Integration
# ==============================================================================

def test_controlled_comm_circuit_breaker(comm_engine):
    comm_engine.circuit_breaker.failure_threshold = 2

    class CrashingPayload:
        def __bool__(self):
            return True
        def __getattr__(self, name):
            raise RuntimeError("Payload crash")

    comm_engine.execute(CrashingPayload())
    comm_engine.execute(CrashingPayload())

    assert comm_engine.circuit_breaker.is_open()
    comm_engine.reset_circuit()
    assert comm_engine.circuit_breaker.is_closed()
