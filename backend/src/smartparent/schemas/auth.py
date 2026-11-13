"""
STUDIQS® SmartParent™ (v6.2 Complete) - Section 2 Authentication & Onboarding Schemas
=============================================================================
Working Specification v6.0 / v6.1 Section 2:
- Mobile number -> OTP verification
- Ultra-simple student onboarding (Student Name, Class, Board, Academic Year, Subjects)
- Under 5-minute first value target
=============================================================================
"""

import re
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator, ConfigDict


class SendOTPRequest(BaseModel):
    """Request payload to initiate mobile OTP login."""
    model_config = ConfigDict(extra="ignore")

    mobile_number: str = Field(..., description="Indian 10-digit mobile number or E.164 (+91...)")

    @field_validator("mobile_number")
    @classmethod
    def validate_mobile(cls, v: str) -> str:
        cleaned = re.sub(r"[\s\-\(\)]", "", v)
        if cleaned.startswith("+91"):
            cleaned = cleaned[3:]
        elif cleaned.startswith("0"):
            cleaned = cleaned[1:]
        
        if not re.match(r"^[6-9]\d{9}$", cleaned):
            raise ValueError("Invalid Indian mobile number. Must be a 10-digit number starting with 6, 7, 8, or 9.")
        return f"+91{cleaned}"


class SendOTPResponse(BaseModel):
    """Response returned upon successful OTP dispatch."""
    status: str = "OTP_SENT"
    session_token: str = Field(..., description="Secure session verification token")
    mobile_number: str
    expires_in_seconds: int = 300
    cooldown_seconds: int = 60
    message: str = "6-digit OTP sent to registered mobile number"
    dev_otp: Optional[str] = Field(None, description="Test OTP exposed only in non-production environments")


class VerifyOTPRequest(BaseModel):
    """Payload to verify 6-digit OTP and complete authentication."""
    model_config = ConfigDict(extra="ignore")

    mobile_number: str = Field(..., description="Mobile number for which OTP was requested")
    otp: str = Field(..., min_length=6, max_length=6, description="6-digit verification code")
    session_token: Optional[str] = Field(None, description="Session token returned during send_otp")

    @field_validator("otp")
    @classmethod
    def validate_otp_digits(cls, v: str) -> str:
        if not v.isdigit() or len(v) != 6:
            raise ValueError("OTP must be exactly 6 digits.")
        return v

    @field_validator("mobile_number")
    @classmethod
    def validate_mobile(cls, v: str) -> str:
        cleaned = re.sub(r"[\s\-\(\)]", "", v)
        if cleaned.startswith("+91"):
            cleaned = cleaned[3:]
        elif cleaned.startswith("0"):
            cleaned = cleaned[1:]
        if not re.match(r"^[6-9]\d{9}$", cleaned):
            raise ValueError("Invalid Indian mobile number.")
        return f"+91{cleaned}"


class AuthTokenResponse(BaseModel):
    """JWT Bearer authentication response for authenticated subscriber."""
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: int = 3600
    session_id: Optional[str] = None
    subscriber_id: str
    mobile_number: str
    parent_name: str
    subscription_plan: str
    role: str = "parent"
    permissions: List[str] = []
    is_new_subscriber: bool


class RefreshTokenRequest(BaseModel):
    """Request payload to rotate JWT refresh token."""
    model_config = ConfigDict(extra="ignore")
    refresh_token: str = Field(..., description="Active PyJWT Refresh Token")


class RefreshTokenResponse(BaseModel):
    """Refreshed token response."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 3600


class SessionDetailResponse(BaseModel):
    """Active subscriber device session information."""
    session_id: str
    device_name: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    is_current: bool = False
    created_at: str
    last_active_at: str


class SessionListResponse(BaseModel):
    """List of active device sessions."""
    active_sessions: List[SessionDetailResponse]
    total_count: int


class LogoutResponse(BaseModel):
    """Logout confirmation response."""
    status: str = "LOGGED_OUT"
    message: str = "Session terminated successfully."
    revoked_sessions_count: int = 1


# =============================================================================
# Ultra-Simple Onboarding (Section 2 - PDF Page 4)
# =============================================================================

class AddStudentRequest(BaseModel):
    """
    Section 2: Ultra-Simple Student Onboarding Request Payload.
    Consumer journey: Mobile -> OTP -> Add student -> Class/Board -> Subjects -> First Result.
    Keeps onboarding deliberately short (< 5 mins). Never blocks on optional fields.
    """
    model_config = ConfigDict(extra="ignore")

    student_name: str = Field(..., min_length=2, max_length=100, description="Student/Child single name field")
    standard_class: str = Field(..., description="Class/grade (e.g. 'Class 10')")
    board: str = Field(..., description="Curriculum board (e.g. 'CBSE', 'ICSE', 'TN State Board')")
    academic_year: str = Field(default="2026-2027", description="Preselected academic year (e.g. '2026-2027')")
    stream_id: Optional[str] = Field(
        None, 
        description="Stream for Class 11-12: 'BIO_MATHS', 'CS_MATHS', 'COMMERCE', 'HUMANITIES'"
    )
    selected_subjects: Optional[List[str]] = Field(
        None, 
        description="Subjects confirmed/edited by parent; auto-suggested if omitted"
    )
    school_name: Optional[str] = Field(None, max_length=150, description="Optional school name; never blocks onboarding")
    section: Optional[str] = Field(None, max_length=20, description="Optional class section; never blocks onboarding")

    @field_validator("student_name")
    @classmethod
    def validate_name_clean(cls, v: str) -> str:
        cleaned = v.strip()
        if len(cleaned) < 2:
            raise ValueError("Student name must have at least 2 characters.")
        return cleaned


class AddStudentResponse(BaseModel):
    """Structured response returned upon successful student onboarding."""
    child_id: str
    subscriber_id: str
    student_name: str
    standard_class: str
    board: str
    stream_id: Optional[str] = None
    academic_year: str
    school_name: Optional[str] = None
    section: Optional[str] = None
    subjects: List[str]
    onboarding_status: str = "ONBOARDED"
    time_to_onboard_target: str = "UNDER_5_MINUTES"
    next_step: str = "RECORD_FIRST_RESULT"


class StudentProfileResponse(BaseModel):
    """Complete Student 360 profile view for a registered child."""
    child_id: str
    subscriber_id: str
    student_name: str
    standard_class: str
    board: str
    stream_id: Optional[str] = None
    academic_year: str
    school_name: Optional[str] = None
    section: Optional[str] = None
    subjects: List[str]
    is_active: bool = True
    diagnostic_status: str = "AWAITING_FIRST_RESULT"


class SubjectCatalogResponse(BaseModel):
    """Auto-suggested subjects for a given curriculum board and grade."""
    board: str
    standard_class: str
    stream_id: Optional[str] = None
    subjects: List[str]


# =============================================================================
# Password Authentication & Subscriber Profile Management Schemas
# =============================================================================

class PasswordLoginRequest(BaseModel):
    """Payload to authenticate subscriber via mobile number or email + password."""
    model_config = ConfigDict(extra="ignore")

    mobile_or_email: str = Field(..., description="Registered mobile number (e.g. +919876543210 or 9876543210) or email")
    password: str = Field(..., min_length=6, description="Subscriber account password")


class ChangePasswordRequest(BaseModel):
    """Payload to update password for authenticated subscriber."""
    model_config = ConfigDict(extra="ignore")

    old_password: Optional[str] = Field(None, description="Current password (optional if setting password first time after OTP signup)")
    new_password: str = Field(..., min_length=8, description="New strong password (min 8 characters)")

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
            raise ValueError("Password must contain at least one letter and one number.")
        return v


class ForgotPasswordRequest(BaseModel):
    """Payload to initiate password reset via OTP."""
    model_config = ConfigDict(extra="ignore")

    mobile_number: str = Field(..., description="Registered Indian mobile number")

    @field_validator("mobile_number")
    @classmethod
    def validate_mobile(cls, v: str) -> str:
        cleaned = re.sub(r"[\s\-\(\)]", "", v)
        if cleaned.startswith("+91"):
            cleaned = cleaned[3:]
        elif cleaned.startswith("0"):
            cleaned = cleaned[1:]
        if not re.match(r"^[6-9]\d{9}$", cleaned):
            raise ValueError("Invalid Indian mobile number.")
        return f"+91{cleaned}"


class ResetPasswordRequest(BaseModel):
    """Payload to verify OTP and set a new password."""
    model_config = ConfigDict(extra="ignore")

    mobile_number: str = Field(..., description="Registered mobile number")
    otp: str = Field(..., min_length=6, max_length=6, description="6-digit verification code")
    new_password: str = Field(..., min_length=8, description="New strong password")
    session_token: Optional[str] = Field(None, description="Session token from forgot password request")

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
            raise ValueError("Password must contain at least one letter and one number.")
        return v

    @field_validator("mobile_number")
    @classmethod
    def validate_mobile(cls, v: str) -> str:
        cleaned = re.sub(r"[\s\-\(\)]", "", v)
        if cleaned.startswith("+91"):
            cleaned = cleaned[3:]
        elif cleaned.startswith("0"):
            cleaned = cleaned[1:]
        if not re.match(r"^[6-9]\d{9}$", cleaned):
            raise ValueError("Invalid Indian mobile number.")
        return f"+91{cleaned}"


class SubscriberProfileResponse(BaseModel):
    """Parent subscriber account profile information."""
    subscriber_id: str
    mobile_number: str
    parent_name: str
    email: Optional[str] = None
    subscription_plan: str
    role: str = "parent"
    permissions: List[str] = []
    is_active: bool = True
    created_at: str


class UpdateSubscriberProfileRequest(BaseModel):
    """Payload to update parent profile details."""
    model_config = ConfigDict(extra="ignore")

    parent_name: Optional[str] = Field(None, min_length=2, max_length=100)
    email: Optional[str] = None


class UpdateStudentRequest(BaseModel):
    """Payload to edit student/child academic profile."""
    model_config = ConfigDict(extra="ignore")

    student_name: Optional[str] = Field(None, min_length=2, max_length=100)
    standard_class: Optional[str] = None
    board: Optional[str] = None
    stream_id: Optional[str] = None
    school_name: Optional[str] = None
    section: Optional[str] = None
    academic_year: Optional[str] = None
    selected_subjects: Optional[List[str]] = None


class GenericAuthMessageResponse(BaseModel):
    """Generic status response for password and profile operations."""
    status: str = "SUCCESS"
    message: str


