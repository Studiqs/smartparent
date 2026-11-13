"""
STUDIQS® SmartParent™ (v6.2 Complete) - Phase 3 Security & RLS Test Suite
Verifies Bcrypt, PyJWT, Section 21 Anti-Contact Scrubber, Domain Exceptions & RLS
"""

import uuid
import pytest
from src.smartparent.core.exceptions import (
    AntiContactViolationError,
    AuthenticationError,
    InvalidTokenError,
    PlanQuotaExceededError,
    TamilExclusionError,
    TokenExpiredError,
)
from src.smartparent.core.rls import generate_rls_sql_policies
from src.smartparent.core.security import (
    assert_anti_contact_compliance,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    inspect_anti_contact_boundary,
    redact_contact_details,
    verify_password,
)


# ==============================================================================
# 1. BCRYPT PASSWORD HASHING TESTS
# ==============================================================================
def test_password_hashing_and_verification():
    password = "SuperSecretParentPassword123!"
    hashed = get_password_hash(password)

    assert hashed != password
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False


def test_password_hashing_long_password_guardrail():
    # Long passwords (> 72 bytes) should not cause bcrypt to crash
    long_password = "A" * 200
    hashed = get_password_hash(long_password)

    assert verify_password(long_password, hashed) is True
    assert verify_password("A" * 70, hashed) is False


# ==============================================================================
# 2. JWT TOKEN MANAGEMENT TESTS
# ==============================================================================
def test_jwt_access_and_refresh_tokens():
    sub_id = str(uuid.uuid4())
    data = {"sub": sub_id, "role": "SUBSCRIBER", "plan": "PRO"}

    access_token = create_access_token(data)
    decoded_access = decode_token(access_token)

    assert decoded_access["sub"] == sub_id
    assert decoded_access["role"] == "SUBSCRIBER"
    assert decoded_access["plan"] == "PRO"
    assert decoded_access["token_type"] == "access"

    refresh_token = create_refresh_token(data)
    decoded_refresh = decode_token(refresh_token)

    assert decoded_refresh["sub"] == sub_id
    assert decoded_refresh["token_type"] == "refresh"


def test_invalid_token_handling():
    with pytest.raises(InvalidTokenError):
        decode_token("invalid.token.string")


# ==============================================================================
# 3. SECTION 21 ANTI-CONTACT BOUNDARY REGEX SCRUBBER TESTS
# ==============================================================================
@pytest.mark.parametrize(
    "prohibited_text,expected_reason_substring",
    [
        ("Call me on 9876543210 for doubts", "Phone number"),
        ("Send paper to +91 94444 12345 please", "Phone number"),
        ("My email is tutor_expert@gmail.com", "Email address"),
        ("Check my notes at https://mycourses.in/study", "External URL"),
        ("Message me at wa.me/919876543210", "External URL"),
        ("Pay fee directly to my upi sundar@okhdfcbank", "UPI payment handle"),
        ("Pay me via expert@paytm", "UPI payment handle"),
        ("Please message me on whatsapp", "Off-platform"),
        ("Call me directly outside the platform", "Off-platform"),
    ],
)
def test_anti_contact_boundary_violations(prohibited_text, expected_reason_substring):
    is_violation, reasons = inspect_anti_contact_boundary(prohibited_text)
    assert is_violation is True
    assert any(expected_reason_substring.lower() in r.lower() for r in reasons)

    with pytest.raises(AntiContactViolationError):
        assert_anti_contact_compliance(prohibited_text)


def test_anti_contact_boundary_allowed_academic_messages():
    safe_messages = [
        "Please recheck question 4 calculation on page 2.",
        "The step marks for the integration problem seem lower than expected.",
        "Kindly review the physics ray diagram for reflection.",
        "Thank you for the detailed feedback on chemistry stoichiometry.",
    ]
    for msg in safe_messages:
        is_violation, reasons = inspect_anti_contact_boundary(msg)
        assert is_violation is False, f"False positive on safe message: {msg}"
        assert_anti_contact_compliance(msg)


def test_contact_redaction():
    text = "Call 9876543210 or email test@gmail.com or pay sundar@okaxis"
    redacted = redact_contact_details(text)

    assert "9876543210" not in redacted
    assert "test@gmail.com" not in redacted
    assert "sundar@okaxis" not in redacted
    assert "[PHONE_REDACTED]" in redacted
    assert "[EMAIL_REDACTED]" in redacted
    assert "[UPI_REDACTED]" in redacted


# ==============================================================================
# 4. DOMAIN EXCEPTIONS TESTS
# ==============================================================================
def test_domain_exceptions_status_codes():
    auth_err = AuthenticationError("Login required")
    assert auth_err.status_code == 401

    quota_err = PlanQuotaExceededError("Upload limit reached", "UPLOADS", 4, 4)
    assert quota_err.status_code == 403
    assert quota_err.details["current_used"] == 4
    assert quota_err.details["limit"] == 4

    tamil_err = TamilExclusionError()
    assert tamil_err.status_code == 400
    assert "WHERE subject != 'TAMIL'" in tamil_err.message


# ==============================================================================
# 5. POSTGRESQL 16 RLS POLICIES DDL TEST
# ==============================================================================
def test_rls_sql_policies_generation():
    sql = generate_rls_sql_policies()
    assert "ALTER TABLE children ENABLE ROW LEVEL SECURITY;" in sql
    assert "ALTER TABLE evidence_records ENABLE ROW LEVEL SECURITY;" in sql
    assert "app.current_subscriber_id" in sql
