"""
STUDIQS® SmartParent™ (v6.2 Complete) - Section 8 Board Readiness & Share Mode API Endpoints
=============================================================================
Section 8: Board Readiness, Achievements and Share Mode:
- GET  /api/v1/readiness/student/{child_id}/board       -> Board Exam Readiness & High-Weightage Risk Radar
- GET  /api/v1/readiness/student/{child_id}/achievements -> Unlocked Milestone Badges & Progress
- POST /api/v1/readiness/share/generate                 -> Generate 72-Hour Expiring Secure Share Link
- GET  /api/v1/readiness/share/active/{child_id}        -> List Parent Share Links with Live Countdown
- POST /api/v1/readiness/share/revoke/{token_id}        -> Instant Parent Revocation
- GET  /api/v1/readiness/share/view/{share_token}       -> Public Zero-Leakage Tutor / Mentor View
=============================================================================
"""

import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.smartparent.schemas.readiness import (
    BoardReadinessResponse,
    StudentAchievementsResponse,
    GenerateShareLinkRequest,
    ShareLinkResponse,
    ActiveShareTokensListResponse,
    RevokeShareLinkResponse,
    PublicSharedReportResponse,
)
from src.smartparent.services.readiness_service import ReadinessService

router = APIRouter(prefix="/readiness", tags=["Board Readiness, Achievements & Share Mode"])


from src.smartparent.api.deps import get_db, get_current_subscriber_id


@router.get(
    "/student/{child_id}/board",
    response_model=BoardReadinessResponse,
    summary="Retrieve student Board Exam Readiness Index, Risk Radar & Score Corridor",
)
def get_board_readiness(
    child_id: uuid.UUID,
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    """
    Evaluates comprehensive Board Exam Readiness for Secondary & Senior Secondary students.
    Features:
    - Syllabus coverage and mastery gauge
    - High-weightage topic risk radar
    - 3-point deterministic score corridor (Lower, Most Likely, Upper)
    - Readiness tier (READY, ON_TRACK, NEEDS_ATTENTION, CRITICAL_RISK)
    - Class 11 stream selection aptitude alignment
    """
    service = ReadinessService()
    try:
        return service.get_board_readiness(
            db=db,
            subscriber_id=subscriber_id,
            child_id=child_id,
        )
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/student/{child_id}/achievements",
    response_model=StudentAchievementsResponse,
    summary="Retrieve student academic achievements and unlocked milestone badges",
)
def get_student_achievements(
    child_id: uuid.UUID,
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    """
    Evaluates verified test evidence to award authentic learning milestone badges:
    - Centum Club
    - Consistency Champion
    - Topic Gap Slayer
    - Syllabus Pioneer
    - Board Ready
    - Persistent Scholar
    - Subject Maestro
    """
    service = ReadinessService()
    try:
        return service.get_student_achievements(
            db=db,
            subscriber_id=subscriber_id,
            child_id=child_id,
        )
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/share/generate",
    response_model=ShareLinkResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate 72-hour parent-authorized time-limited cryptographic share link",
)
def generate_share_link(
    payload: GenerateShareLinkRequest,
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    """
    Creates a secure, time-limited cryptographic share token for school teachers,
    private tutors, or family mentors with an auto-destruct countdown timer.
    """
    service = ReadinessService()
    try:
        return service.generate_share_token(
            db=db,
            subscriber_id=subscriber_id,
            child_id=payload.child_id,
            duration_hours=payload.duration_hours,
        )
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/share/active/{child_id}",
    response_model=ActiveShareTokensListResponse,
    summary="List all active and historical share links for student with live countdown",
)
def list_active_share_tokens(
    child_id: uuid.UUID,
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    """
    Provides parent management of all generated tutor share links with live countdowns.
    """
    service = ReadinessService()
    try:
        return service.list_active_share_tokens(
            db=db,
            subscriber_id=subscriber_id,
            child_id=child_id,
        )
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/share/revoke/{token_id}",
    response_model=RevokeShareLinkResponse,
    summary="Instantly revoke parent-authorized share link",
)
def revoke_share_link(
    token_id: uuid.UUID,
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    """
    Parent-controlled instant revocation switch.
    Immediately terminates external access to the diagnostic brief.
    """
    service = ReadinessService()
    try:
        return service.revoke_share_token(
            db=db,
            subscriber_id=subscriber_id,
            token_id=token_id,
        )
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/share/view/{share_token}",
    response_model=PublicSharedReportResponse,
    summary="Public zero-privacy-leakage diagnostic view for verified home tutors and teachers",
)
def view_public_shared_report(
    share_token: str,
    db: Session = Depends(get_db),
):
    """
    Public read-only diagnostic brief accessed by verified tutors via parent share links.
    Strict Non-Negotiable Privacy Boundary:
    - Strips subscriber identity, phone number, and email
    - Strips billing, subscription, and payments data
    - Strips sibling and family profile details
    - Returns only child diagnostic readiness, strengths, and remedial gaps
    """
    service = ReadinessService()
    try:
        return service.get_public_shared_report(
            db=db,
            share_token=share_token,
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
