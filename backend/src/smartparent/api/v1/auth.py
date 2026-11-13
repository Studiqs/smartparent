"""
STUDIQS® SmartParent™ (v6.2 & v6.3 Complete) - Authentication & Onboarding Router
=============================================================================
Working Specification v6.0 / v6.1 Section 2:
Consumer journey: Mobile number -> OTP -> Add student -> class/board -> subjects -> first result.

FastAPI REST Endpoints:
  1. POST   /api/v1/auth/otp/send          -> Send 6-digit OTP with 60s cooldown & rate limiting
  2. POST   /api/v1/auth/otp/verify        -> Verify OTP & issue dual PyJWT tokens (access + refresh)
  3. POST   /api/v1/auth/token/refresh     -> Silent refresh token rotation with replay detection
  4. POST   /api/v1/auth/logout            -> Terminate current session
  5. POST   /api/v1/auth/logout-all        -> Global remote session termination
  6. GET    /api/v1/auth/sessions          -> List all authorized active device sessions
  7. DELETE /api/v1/auth/sessions/{id}     -> Revoke a specific remote device session
  8. POST   /api/v1/auth/student           -> Ultra-simple student onboarding (< 5 mins)
  9. GET    /api/v1/auth/students          -> List children under logged-in parent
  10. GET   /api/v1/auth/students/{id}     -> Get child 360 baseline profile (B2C isolated)
  11. GET   /api/v1/auth/curriculum/subjects-> Auto-suggest syllabus subjects
=============================================================================
"""

import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Header, status
from sqlalchemy.orm import Session

from src.smartparent.api.deps import (
    get_db,
    get_current_subscriber_id,
)
from src.smartparent.schemas.auth import (
    SendOTPRequest,
    SendOTPResponse,
    VerifyOTPRequest,
    AuthTokenResponse,
    RefreshTokenRequest,
    RefreshTokenResponse,
    SessionDetailResponse,
    SessionListResponse,
    LogoutResponse,
    AddStudentRequest,
    AddStudentResponse,
    StudentProfileResponse,
    SubjectCatalogResponse,
    PasswordLoginRequest,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    SubscriberProfileResponse,
    UpdateSubscriberProfileRequest,
    UpdateStudentRequest,
    GenericAuthMessageResponse,
)
from src.smartparent.services.auth_service import AuthService, auth_service

router = APIRouter(prefix="/auth", tags=["Section 2: Authentication & Onboarding"])


# =============================================================================
# 1. Mobile OTP Authentication & Token Issuance
# =============================================================================

@router.post(
    "/otp/send",
    response_model=SendOTPResponse,
    status_code=status.HTTP_200_OK,
    summary="Step 1: Request OTP for mobile authentication",
    description="Validates Indian mobile number and issues a 6-digit verification code with 60s cooldown and hourly rate limit.",
)
def send_otp(
    payload: SendOTPRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    ip_addr = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    try:
        return auth_service.send_otp(
            mobile_number=payload.mobile_number,
            db=db,
            ip_address=ip_addr,
            user_agent=ua,
            is_dev_sandbox=True,
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS if "Please wait" in str(ve) or "Too many" in str(ve) else status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/otp/verify",
    response_model=AuthTokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Step 2: Verify OTP and log in / register subscriber",
    description="Validates OTP code. Creates new subscriber if first-time user; returns PyJWT dual tokens and active session ID.",
)
def verify_otp(
    payload: VerifyOTPRequest,
    request: Request,
    parent_name: Optional[str] = Query(None, description="Optional parent display name"),
    db: Session = Depends(get_db),
):
    ip_addr = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    try:
        return auth_service.verify_otp(
            db=db,
            mobile_number=payload.mobile_number,
            otp=payload.otp,
            parent_name=parent_name,
            session_token=payload.session_token,
            ip_address=ip_addr,
            user_agent=ua,
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# =============================================================================
# 2. Token Lifecycle & Session Management
# =============================================================================

@router.post(
    "/token/refresh",
    response_model=RefreshTokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Rotate JWT Refresh Token",
    description="Exchanges an active refresh token for a fresh token pair. Enforces automatic replay attack detection.",
)
def refresh_token(
    payload: RefreshTokenRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    ip_addr = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    try:
        return auth_service.rotate_refresh_token(
            db=db,
            refresh_token=payload.refresh_token,
            ip_address=ip_addr,
            user_agent=ua,
        )
    except PermissionError as pe:
        # Replay attack
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/logout",
    response_model=LogoutResponse,
    status_code=status.HTTP_200_OK,
    summary="Terminate Current Session",
    description="Revokes the active refresh token session for the authenticated subscriber.",
)
def logout(
    x_session_id: Optional[str] = Header(None, alias="X-Session-Id"),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
    db: Session = Depends(get_db),
):
    sess_uuid = None
    if x_session_id:
        try:
            sess_uuid = uuid.UUID(x_session_id)
        except ValueError:
            pass

    return auth_service.logout_session(
        db=db,
        subscriber_id=subscriber_id,
        session_id=sess_uuid,
    )


@router.post(
    "/logout-all",
    response_model=LogoutResponse,
    status_code=status.HTTP_200_OK,
    summary="Global Remote Logout",
    description="Revokes all active sessions across all devices for this parent account.",
)
def logout_all(
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
    db: Session = Depends(get_db),
):
    return auth_service.logout_all_sessions(
        db=db,
        subscriber_id=subscriber_id,
    )


@router.get(
    "/sessions",
    response_model=SessionListResponse,
    status_code=status.HTTP_200_OK,
    summary="List Active Device Sessions",
    description="Returns all logged-in devices and sessions for this parent account.",
)
def list_sessions(
    x_session_id: Optional[str] = Header(None, alias="X-Session-Id"),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
    db: Session = Depends(get_db),
):
    curr_uuid = None
    if x_session_id:
        try:
            curr_uuid = uuid.UUID(x_session_id)
        except ValueError:
            pass

    return auth_service.list_active_sessions(
        db=db,
        subscriber_id=subscriber_id,
        current_session_id=curr_uuid,
    )


@router.delete(
    "/sessions/{session_id}",
    response_model=LogoutResponse,
    status_code=status.HTTP_200_OK,
    summary="Revoke Remote Device Session",
    description="Administratively terminates a specific device session.",
)
def revoke_session(
    session_id: uuid.UUID,
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
    db: Session = Depends(get_db),
):
    return auth_service.logout_session(
        db=db,
        subscriber_id=subscriber_id,
        session_id=session_id,
    )


# =============================================================================
# 3. Ultra-Simple Student Onboarding (< 5 mins)
# =============================================================================

@router.post(
    "/student",
    response_model=AddStudentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Step 3: Ultra-simple student onboarding (< 5 mins)",
    description="Single name field, class/board dropdown, auto-suggested subjects. Never blocks on optional fields.",
)
def add_student(
    payload: AddStudentRequest,
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    try:
        return auth_service.add_student(
            db=db,
            subscriber_id=subscriber_id,
            payload=payload,
        )
    except (ValueError, PermissionError) as pe:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(pe))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/students",
    response_model=List[StudentProfileResponse],
    status_code=status.HTTP_200_OK,
    summary="List all registered children under current parent account",
)
def list_students(
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    try:
        return auth_service.list_children(db=db, subscriber_id=subscriber_id)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/students/{child_id}",
    response_model=StudentProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Get single child profile & baseline context",
    description="Enforces strict B2C multi-tenant isolation. Rejects foreign subscriber access.",
)
def get_student_profile(
    child_id: uuid.UUID,
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    try:
        return auth_service.get_child_profile(
            db=db,
            subscriber_id=subscriber_id,
            child_id=child_id,
        )
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/curriculum/subjects",
    response_model=SubjectCatalogResponse,
    status_code=status.HTTP_200_OK,
    summary="Auto-suggest official curriculum subjects for dropdown",
)
def get_curriculum_subjects(
    board: str = Query(..., description="Curriculum board (e.g. CBSE, ICSE, TN State Board)"),
    standard_class: str = Query(..., description="Grade/class (e.g. Class 10)"),
    stream_id: Optional[str] = Query(None, description="Stream for Class 11-12"),
):
    try:
        subjects = auth_service.get_suggested_subjects(
            board=board,
            standard_class=standard_class,
            stream_id=stream_id,
        )
        return SubjectCatalogResponse(
            board=board,
            standard_class=standard_class,
            stream_id=stream_id,
            subjects=subjects,
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# =============================================================================
# 4. Password Authentication & Password Management Endpoints
# =============================================================================

@router.post(
    "/login/password",
    response_model=AuthTokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Login via Mobile/Email and Password",
    description="Authenticates subscriber using registered credentials and returns active JWT token pair.",
)
def login_with_password(
    payload: PasswordLoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    ip_addr = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    try:
        return auth_service.login_with_password(
            db=db,
            mobile_or_email=payload.mobile_or_email,
            password=payload.password,
            ip_address=ip_addr,
            user_agent=ua,
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/password/change",
    response_model=GenericAuthMessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Change or set account password",
    description="Updates password for authenticated subscriber with 12-round bcrypt hash.",
)
def change_password(
    payload: ChangePasswordRequest,
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
    db: Session = Depends(get_db),
):
    try:
        return auth_service.change_password(
            db=db,
            subscriber_id=subscriber_id,
            old_password=payload.old_password,
            new_password=payload.new_password,
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/password/forgot",
    response_model=SendOTPResponse,
    status_code=status.HTTP_200_OK,
    summary="Request password reset OTP",
    description="Dispatches a 6-digit verification code to the registered mobile number for password reset.",
)
def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    ip_addr = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    try:
        return auth_service.forgot_password_request(
            db=db,
            mobile_number=payload.mobile_number,
            ip_address=ip_addr,
            user_agent=ua,
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND if "No account" in str(ve) else status.HTTP_429_TOO_MANY_REQUESTS, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/password/reset",
    response_model=AuthTokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Reset password with OTP",
    description="Verifies the OTP code, resets the password, and logs the subscriber in immediately.",
)
def reset_password(
    payload: ResetPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    ip_addr = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    try:
        return auth_service.reset_password_with_otp(
            db=db,
            mobile_number=payload.mobile_number,
            otp=payload.otp,
            new_password=payload.new_password,
            session_token=payload.session_token,
            ip_address=ip_addr,
            user_agent=ua,
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# =============================================================================
# 5. Parent Profile & Student Profile Update Endpoints
# =============================================================================

@router.get(
    "/profile",
    response_model=SubscriberProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Parent Account Profile",
)
def get_parent_profile(
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
    db: Session = Depends(get_db),
):
    try:
        return auth_service.get_subscriber_profile(db=db, subscriber_id=subscriber_id)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.put(
    "/profile",
    response_model=SubscriberProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Update Parent Account Profile",
)
def update_parent_profile(
    payload: UpdateSubscriberProfileRequest,
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
    db: Session = Depends(get_db),
):
    try:
        return auth_service.update_subscriber_profile(
            db=db,
            subscriber_id=subscriber_id,
            parent_name=payload.parent_name,
            email=payload.email,
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.put(
    "/students/{child_id}",
    response_model=StudentProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Update Child Profile & Academic Details",
    description="Updates student profile enforcing strict B2C multi-tenant subscriber boundary.",
)
def update_student_profile(
    child_id: uuid.UUID,
    payload: UpdateStudentRequest,
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
    db: Session = Depends(get_db),
):
    try:
        return auth_service.update_student(
            db=db,
            subscriber_id=subscriber_id,
            child_id=child_id,
            payload=payload,
        )
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete(
    "/students/{child_id}",
    response_model=GenericAuthMessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Archive / Soft-Delete Child Profile",
)
def delete_student_profile(
    child_id: uuid.UUID,
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
    db: Session = Depends(get_db),
):
    try:
        return auth_service.delete_student(
            db=db,
            subscriber_id=subscriber_id,
            child_id=child_id,
        )
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

