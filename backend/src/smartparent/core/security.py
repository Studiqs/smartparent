"""
STUDIQS® SmartParent™ (v6.2 Complete) - Security & Cryptographic Core
Bcrypt Password Hashing, PyJWT Token Generation & Section 21 Anti-Contact Moderation
"""

import re
import hmac
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
import bcrypt
import jwt
from src.smartparent.config import settings
from src.smartparent.core.exceptions import (
    AntiContactViolationError,
    InvalidTokenError,
    TokenExpiredError,
)

# ==============================================================================
# 1. BCRYPT PASSWORD HASHING (With 72-Byte Truncation Guardrail)
# ==============================================================================
# Standard bcrypt fails or overflows when plain password exceeds 72 bytes.
# We explicitly truncate the encoded byte array to 72 bytes to prevent DOS / crashes.
MAX_BCRYPT_PASSWORD_BYTES = 72


def get_password_hash(password: str) -> str:
    """Hashes a plaintext password using bcrypt with a salt."""
    password_bytes = password.encode("utf-8")[:MAX_BCRYPT_PASSWORD_BYTES]
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Constant-time verification of plaintext password against bcrypt hash."""
    try:
        plain_bytes = plain_password.encode("utf-8")[:MAX_BCRYPT_PASSWORD_BYTES]
        hashed_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(plain_bytes, hashed_bytes)
    except Exception:
        return False


# ==============================================================================
# 2. PYJWT TOKEN MANAGEMENT (Access & Refresh Tokens)
# ==============================================================================
def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Creates an HMAC-SHA256 signed JWT Access Token.
    Encodes subject identifier, role claims, and expiration.
    """
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "token_type": "access",
        "jti": to_encode.get("jti") or uuid.uuid4().hex,
    })
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Creates an HMAC-SHA256 signed JWT Refresh Token with extended validity."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    to_encode.update({
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "token_type": "refresh",
    })
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> Dict[str, Any]:
    """
    Decodes and validates a JWT token.
    Raises domain exceptions on expired signatures or malformed tokens.
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise TokenExpiredError("Authentication token has expired. Please log in again.")
    except jwt.PyJWTError as e:
        raise InvalidTokenError(f"Invalid authentication token: {str(e)}")


def hash_token(token: str) -> str:
    """Computes SHA-256 hash of a token for secure session tracking without storing raw tokens."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_secure_otp(length: int = 6) -> str:
    """Generates an unbiased cryptographically secure n-digit OTP."""
    upper_bound = 10 ** length
    code = secrets.randbelow(upper_bound)
    return f"{code:0{length}d}"


def hash_otp(otp: str, salt: str) -> str:
    """Computes HMAC-SHA256 salted hash of an OTP using system SECRET_KEY."""
    key = settings.SECRET_KEY.encode("utf-8")
    msg = f"{salt}:{otp}".encode("utf-8")
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def verify_otp_hash(otp: str, salt: str, expected_hash: str) -> bool:
    """Constant-time comparison of OTP against salted HMAC-SHA256 hash."""
    actual_hash = hash_otp(otp, salt)
    return hmac.compare_digest(actual_hash, expected_hash)


# ==============================================================================
# 3. SECTION 21 ANTI-CONTACT REGEX SCRUBBER & MODERATION ENGINE
# NON-NEGOTIABLE SAFETY & BUSINESS RULE:
# Blocks phone numbers, emails, URLs, UPI IDs, social links, and solicitation keywords
# in Case Messages, Reviews, and Expert/Parent communication.
# ==============================================================================

# 1. Indian Phone Numbers (10 digits starting with 6-9, optional +91, 0, hyphens, spaces, dots)
PHONE_REGEX = re.compile(
    r"(?:\+?91[\-\s\.]?)?(?:0)?[6-9]\d{2}[\-\s\.]?\d{3}[\-\s\.]?\d{4}\b|"
    r"\b[6-9](?:[\-\s\.]?\d){9}\b",
    re.IGNORECASE,
)

# 2. Email Addresses
EMAIL_REGEX = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
    re.IGNORECASE,
)

# 3. External URLs, Domain Links, and Social Shorteners
URL_REGEX = re.compile(
    r"https?://(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&//=]*)|"
    r"\b(?:www\.)[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b|"
    r"\b(?:wa\.me|t\.me|bit\.ly|tinyurl\.com|instagram\.com|facebook\.com|linkedin\.com)/[^\s]+",
    re.IGNORECASE,
)

# 4. UPI Payment Handles
UPI_REGEX = re.compile(
    r"\b[a-zA-Z0-9.\-_]{2,256}@(okaxis|okhdfcbank|okicici|oksbi|paytm|upi|ybl|axl|ibl|apl|idfcbank|federal)\b",
    re.IGNORECASE,
)

# 5. Off-Platform Solicitation Keywords & Contact Triggers
SOLICITATION_REGEX = re.compile(
    r"\b(?:whatsapp|watsapp|whatsap|telegram|gpay|phonepe|paytm\s+me|call\s+me|contact\s+outside|"
    r"reach\s+me\s+at|reach\s+out\s+privately|pay\s+directly|direct\s+payment|gpay\s+pannunga|"
    r"whatsapp-la\s+anupu)\b",
    re.IGNORECASE,
)


def inspect_anti_contact_boundary(text: str) -> Tuple[bool, List[str]]:
    """
    Audits a message text against Section 21 Anti-Contact Boundary rules.
    Returns:
        (is_violation, list_of_violation_reasons)
    """
    violations: List[str] = []

    if PHONE_REGEX.search(text):
        violations.append("Phone number detected")

    if EMAIL_REGEX.search(text):
        violations.append("Email address detected")

    if URL_REGEX.search(text):
        violations.append("External URL or social link detected")

    if UPI_REGEX.search(text):
        violations.append("UPI payment handle detected")

    if SOLICITATION_REGEX.search(text):
        violations.append("Off-platform contact/solicitation keyword detected")

    return (len(violations) > 0, violations)


def assert_anti_contact_compliance(text: str) -> None:
    """
    Enforces Section 21 boundary. Raises AntiContactViolationError if text
    contains prohibited contact identifiers or off-platform solicitation.
    """
    is_violation, reasons = inspect_anti_contact_boundary(text)
    if is_violation:
        raise AntiContactViolationError(
            f"Message violates Section 21 Anti-Contact Boundary: {', '.join(reasons)}. "
            "All expert and parent communication must remain strictly within Studiqs."
        )


def redact_contact_details(text: str) -> str:
    """
    Sanitizes message text by replacing any prohibited contact information
    with redaction masks. Safe for audit logs or masked UI views.
    """
    redacted = PHONE_REGEX.sub("[PHONE_REDACTED]", text)
    redacted = EMAIL_REGEX.sub("[EMAIL_REDACTED]", redacted)
    redacted = URL_REGEX.sub("[LINK_REDACTED]", redacted)
    redacted = UPI_REGEX.sub("[UPI_REDACTED]", redacted)
    return redacted
