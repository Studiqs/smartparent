"""
STUDIQS® SmartParent™ (v6.3 Complete) - Protected Video Tutorials API Router
=============================================================================
Module: src.smartparent.api.v1.tutorials
Section 26: Customer-Only Video Tutorials & In-Product Guidance

Endpoints:
  - GET  /api/v1/tutorials                      : Browse tutorial library with lock status
  - GET  /api/v1/tutorials/{video_id}/playback  : Get 15-minute authorized signed streaming session
  - POST /api/v1/tutorials/{video_id}/progress  : Report watch progress telemetry (>=90% completes)
  - GET  /api/v1/tutorials/contextual/{context_key} : Contextual ? help icon guidance for screens
  - GET  /api/v1/tutorials/onboarding-walkthrough   : First-time onboarding progression status
  - GET  /api/v1/tutorials/{video_id}/stream    : Validates signed HMAC token for video delivery
=============================================================================
"""

import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from src.smartparent.api.deps import get_current_subscriber_id, get_db
from src.smartparent.schemas.tutorial import (
    TutorialListResponse,
    TutorialPlaybackResponse,
    TutorialProgressUpdateRequest,
    TutorialProgressUpdateResponse,
    ContextualHelpResponse,
    OnboardingWalkthroughStatusResponse,
)
from src.smartparent.services.tutorial_service import tutorial_service

router = APIRouter(prefix="/tutorials", tags=["Section 26: Video Tutorials & Usage Guidance"])


@router.get(
    "",
    response_model=TutorialListResponse,
    summary="List customer-only tutorial videos with lock and progress metadata",
)
def list_tutorial_library(
    category: Optional[str] = Query(None, description="Optional category filter (ONBOARDING, ACADEMIC, REPORTS, etc.)"),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
    db: Session = Depends(get_db),
):
    """
    Returns the complete tutorial library.
    Videos are marked 'is_locked: True' if the subscriber's active plan tier
    is lower than the video's min_required_plan.
    """
    return tutorial_service.list_tutorials(
        db=db,
        subscriber_id=subscriber_id,
        category=category,
    )


@router.get(
    "/{video_id}/playback",
    response_model=TutorialPlaybackResponse,
    summary="Obtain short-lived signed streaming URL for a tutorial video",
)
def get_tutorial_playback(
    video_id: int,
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
    db: Session = Depends(get_db),
):
    """
    Validates entitlement and issues a 15-minute signed playback token.
    Throws 403 Forbidden if a Basic or Advanced user attempts to access Pro-only tutorials.
    """
    try:
        return tutorial_service.get_tutorial_playback_session(
            db=db,
            subscriber_id=subscriber_id,
            video_id=video_id,
        )
    except KeyError as ke:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ke))
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate streaming session: {str(e)}",
        )


@router.post(
    "/{video_id}/progress",
    response_model=TutorialProgressUpdateResponse,
    summary="Update playback watch progress telemetry",
)
def record_tutorial_watch_progress(
    video_id: int,
    payload: TutorialProgressUpdateRequest,
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
    db: Session = Depends(get_db),
):
    """
    Updates the subscriber's watch position.
    When watch progress reaches >= 90% of total duration, video is marked as COMPLETED.
    """
    try:
        return tutorial_service.record_watch_progress(
            db=db,
            subscriber_id=subscriber_id,
            video_id=video_id,
            watch_seconds=payload.watch_progress_seconds,
        )
    except KeyError as ke:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ke))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record watch progress: {str(e)}",
        )


@router.get(
    "/contextual/{context_key}",
    response_model=ContextualHelpResponse,
    summary="Resolve in-app ? help icon for a dashboard screen",
)
def get_contextual_help(
    context_key: str,
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
    db: Session = Depends(get_db),
):
    """
    Returns the associated demo video and quick pedagogical tip for a specific dashboard screen
    (e.g., ADD_MARKS, TOPIC_INTELLIGENCE, REPORT_CENTRE, SUBSCRIPTION, SUPPORT_CENTRE, ASK_STUDIQS).
    """
    return tutorial_service.get_contextual_help(
        db=db,
        subscriber_id=subscriber_id,
        context_key=context_key,
    )


@router.get(
    "/onboarding/walkthrough",
    response_model=OnboardingWalkthroughStatusResponse,
    summary="Get first-time subscriber onboarding progression",
)
def get_onboarding_walkthrough(
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
    db: Session = Depends(get_db),
):
    """
    Tracks whether a new parent has watched the initial onboarding walkthrough videos.
    """
    return tutorial_service.get_onboarding_walkthrough_status(
        db=db,
        subscriber_id=subscriber_id,
    )


@router.get(
    "/{video_id}/stream",
    summary="Stream video using authenticated signed HMAC token",
)
def stream_tutorial_video(
    video_id: int,
    token: str = Query(..., description="HMAC-SHA256 playback token"),
    sub: uuid.UUID = Query(..., description="Subscriber UUID"),
    exp: int = Query(..., description="Expiration epoch timestamp"),
    db: Session = Depends(get_db),
):
    """
    Validates the 15-minute HMAC signature.
    Prevents unauthorized or permanent link sharing outside active sessions.
    """
    is_valid = tutorial_service.verify_signed_token(
        video_id=video_id,
        subscriber_id=sub,
        expires_at_timestamp=exp,
        token=token,
    )
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Playback token is expired or invalid. Please request a fresh streaming session.",
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": "AUTHORIZED",
            "video_id": video_id,
            "subscriber_id": str(sub),
            "media_type": "video/mp4",
            "message": "Authorized video stream ready.",
        },
    )
