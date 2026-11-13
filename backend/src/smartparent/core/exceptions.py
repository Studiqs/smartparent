"""
STUDIQS® SmartParent™ (v6.2 Complete) - Domain Exceptions
Typed HTTP & Business Logic Exceptions across all 22 Specification Sections
"""

from typing import Any, Dict, Optional


class SmartParentException(Exception):
    """Base exception for all domain errors within Studiqs SmartParent."""

    def __init__(
        self,
        message: str,
        status_code: int = 400,
        error_code: str = "SMARTPARENT_ERROR",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details or {}


# ==============================================================================
# 1. AUTHENTICATION & SECURITY EXCEPTIONS (Section 2)
# ==============================================================================
class AuthenticationError(SmartParentException):
    """Raised when authentication credentials or OTP are invalid."""

    def __init__(self, message: str = "Authentication failed.", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=401,
            error_code="AUTHENTICATION_FAILED",
            details=details,
        )


class TokenExpiredError(AuthenticationError):
    """Raised when JWT Access or Refresh token has expired."""

    def __init__(self, message: str = "Token has expired.", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, details=details)
        self.error_code = "TOKEN_EXPIRED"


class InvalidTokenError(AuthenticationError):
    """Raised when JWT signature is malformed or invalid."""

    def __init__(self, message: str = "Invalid authentication token.", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, details=details)
        self.error_code = "INVALID_TOKEN"


class ForbiddenError(SmartParentException):
    """Raised when an authenticated user attempts to access an unauthorized resource."""

    def __init__(self, message: str = "Access forbidden.", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=403,
            error_code="FORBIDDEN_ACCESS",
            details=details,
        )


# ==============================================================================
# 2. ENTITY & RESOURCE EXCEPTIONS
# ==============================================================================
class EntityNotFoundError(SmartParentException):
    """Raised when a requested resource does not exist or does not belong to tenant."""

    def __init__(self, message: str = "Requested resource not found.", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=404,
            error_code="ENTITY_NOT_FOUND",
            details=details,
        )


class DuplicateEntityError(SmartParentException):
    """Raised when unique constraints are violated (e.g. mobile number already registered)."""

    def __init__(self, message: str = "Resource already exists.", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=409,
            error_code="DUPLICATE_RESOURCE",
            details=details,
        )


# ==============================================================================
# 3. PLAN ENTITLEMENT & QUOTA EXCEPTIONS (Section 10)
# ==============================================================================
class PlanQuotaExceededError(SmartParentException):
    """Raised when subscriber exceeds monthly uploads, rechecks, or diagnostics."""

    def __init__(self, message: str, quota_type: str, current_used: int, limit: int):
        super().__init__(
            message=message,
            status_code=403,
            error_code="PLAN_QUOTA_EXCEEDED",
            details={
                "quota_type": quota_type,
                "current_used": current_used,
                "limit": limit,
                "upgrade_prompt": "Please upgrade your subscription plan for higher limits.",
            },
        )


# ==============================================================================
# 4. SECTION 21 ANTI-CONTACT & TAMIL EXCLUSION EXCEPTIONS
# ==============================================================================
class AntiContactViolationError(SmartParentException):
    """
    NON-NEGOTIABLE SAFETY RULE:
    Raised when messages or reviews contain phone numbers, emails, URLs, or external contact.
    """

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=400,
            error_code="ANTI_CONTACT_VIOLATION",
            details=details,
        )


class TamilExclusionError(SmartParentException):
    """
    MANDATORY SECTION 21 RULE:
    Raised when an intake or diagnostic query attempts to process Tamil for Topic Intelligence.
    """

    def __init__(
        self,
        message: str = (
            "Tamil subject is strictly excluded from Topic Intelligence per Section 21 specification. "
            "WHERE subject != 'TAMIL' enforced."
        ),
    ):
        super().__init__(
            message=message,
            status_code=400,
            error_code="TAMIL_EXCLUSION_RULE",
        )


# ==============================================================================
# 5. MARKETPLACE & CASE WORKFLOW EXCEPTIONS (Section 11, 12)
# ==============================================================================
class CaseStateTransitionError(SmartParentException):
    """Raised when an illegal case lifecycle state transition is attempted."""

    def __init__(self, current_status: str, attempted_status: str):
        super().__init__(
            message=f"Cannot transition evaluation case from '{current_status}' to '{attempted_status}'.",
            status_code=409,
            error_code="ILLEGAL_STATE_TRANSITION",
            details={"current_status": current_status, "attempted_status": attempted_status},
        )


# ==============================================================================
# 6. EVIDENCE INTAKE & DOCUMENT AI EXCEPTIONS (Section 3)
# ==============================================================================
class EvidenceParsingError(SmartParentException):
    """Raised when Question Paper parsing or Marksheet OCR fails."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=422,
            error_code="EVIDENCE_PARSING_FAILED",
            details=details,
        )


# ==============================================================================
# 7. PRO VOICE ASSISTANT EXCEPTIONS (Section 22)
# ==============================================================================
class VoicePillarViolationError(SmartParentException):
    """Raised when a voice query attempts state mutation or queries outside the 6 Voice Pillars."""

    def __init__(self, message: str):
        super().__init__(
            message=message,
            status_code=403,
            error_code="VOICE_FIREWALL_BLOCK",
        )


# ==============================================================================
# 8. SUBSCRIPTION & BILLING EXCEPTIONS (Section 24 - v6.3)
# ==============================================================================
class SubscriptionExpiredError(SmartParentException):
    """Raised when a subscriber attempts to access paid features with an expired subscription."""

    def __init__(
        self,
        message: str = (
            "Your subscription has expired. Please renew to continue accessing premium features. "
            "Your historical academic data is safely preserved."
        ),
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=message,
            status_code=403,
            error_code="SUBSCRIPTION_EXPIRED",
            details=details,
        )


class SubscriptionUpgradeRequiredError(SmartParentException):
    """Raised when a feature requires a higher subscription plan (e.g., Pro-only video)."""

    def __init__(
        self,
        required_plan: str,
        current_plan: str,
        message: Optional[str] = None,
    ):
        msg = message or (
            f"This feature requires the {required_plan} plan. "
            f"Your current plan is {current_plan}. Please upgrade to access this feature."
        )
        super().__init__(
            message=msg,
            status_code=403,
            error_code="UPGRADE_REQUIRED",
            details={
                "required_plan": required_plan,
                "current_plan": current_plan,
            },
        )


class PaymentVerificationError(SmartParentException):
    """Raised when Razorpay payment signature verification or webhook processing fails."""

    def __init__(self, message: str = "Payment verification failed.", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=400,
            error_code="PAYMENT_VERIFICATION_FAILED",
            details=details,
        )


# ==============================================================================
# 9. SUPPORT CENTRE & SLA EXCEPTIONS (Section 27 - v6.3)
# ==============================================================================
class SLABreachError(SmartParentException):
    """Raised when a support ticket exceeds the 48-hour SLA deadline."""

    def __init__(self, ticket_number: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=f"Support ticket {ticket_number} has breached the 48-hour SLA deadline.",
            status_code=500,
            error_code="SLA_BREACHED",
            details=details or {"ticket_number": ticket_number},
        )


class TicketStateTransitionError(SmartParentException):
    """Raised when an illegal support ticket state transition is attempted."""

    def __init__(self, current_status: str, attempted_status: str):
        super().__init__(
            message=f"Cannot transition support ticket from '{current_status}' to '{attempted_status}'.",
            status_code=409,
            error_code="ILLEGAL_TICKET_TRANSITION",
            details={"current_status": current_status, "attempted_status": attempted_status},
        )


# ==============================================================================
# 10. VIDEO TUTORIAL ACCESS EXCEPTIONS (Section 26 - v6.3)
# ==============================================================================
class VideoAccessDeniedError(SmartParentException):
    """Raised when a subscriber attempts to access a video restricted to a higher plan tier."""

    def __init__(
        self,
        video_title: str,
        required_plan: str,
        message: Optional[str] = None,
    ):
        msg = message or (
            f"Access to '{video_title}' requires the {required_plan} plan. "
            "Please upgrade your subscription to watch this tutorial."
        )
        super().__init__(
            message=msg,
            status_code=403,
            error_code="VIDEO_ACCESS_DENIED",
            details={"video_title": video_title, "required_plan": required_plan},
        )

