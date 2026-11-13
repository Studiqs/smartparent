"""
STUDIQS® SmartParent™ - Public Visitor Preview API
=============================================================================
Module: src.smartparent.api.v1.public_preview
Implements Change 2 & Change 7 of the Studiqs Change Control Addendum.

Endpoints:
  - POST /api/v1/preview/quick-marks : Unauthenticated 3-card preview with locked teasers
  - GET  /api/v1/preview/status      : Check anonymous preview limit and parameters
=============================================================================
"""

from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from src.smartparent.api.deps import get_db
from src.smartparent.schemas.ecosystem import (
    PublicPreviewRequest,
    PublicPreviewResponse,
)
from src.smartparent.services.public_preview_service import (
    PublicPreviewService,
    MAX_DAILY_ANONYMOUS_PREVIEWS,
)

router = APIRouter(prefix="/preview", tags=["Public Visitor Preview (Unauthenticated)"])


@router.post(
    "/quick-marks",
    response_model=PublicPreviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate 3-Card Unlocked / Blurred Preview for Anonymous Visitor",
    description="Allows prospective parents to preview topic mastery with blurred gap teasers without logging in.",
)
def generate_public_preview(
    payload: PublicPreviewRequest,
    x_anonymous_session_id: Optional[str] = Header(None, alias="X-Anonymous-Session-Id"),
    db: Session = Depends(get_db),
):
    session_id = x_anonymous_session_id or "anon_guest_session"
    try:
        return PublicPreviewService.generate_preview(
            db=db,
            request=payload,
            anonymous_session_id=session_id,
        )
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/status",
    summary="Get Public Preview Limits and Guidelines",
)
def get_preview_status():
    return {
        "is_public_preview_enabled": True,
        "max_daily_previews_per_session": MAX_DAILY_ANONYMOUS_PREVIEWS,
        "supported_boards": ["CBSE", "Tamil Nadu State Board"],
        "smartparent_plan_ladder": {
            "Basic": "₹200 / child / month",
            "Advanced": "₹400 / child / month",
            "Pro": "₹600 / child / month",
        },
        "cta": "Unlock Full 360° Diagnostic Telemetry — from ₹200/month",
    }

