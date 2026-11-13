"""
STUDIQS® SmartParent™ (v6.3 Complete) - Diagnostic Intelligence API Router
=============================================================================
Module: src.smartparent.api.v1.diagnostic

Endpoints for Student 360 Diagnostic Profiles, Topic Mastery Tiers,
and Learning Gap Watchlist management with multi-tenant firewall.
=============================================================================
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.smartparent.api.deps import get_current_subscriber_id, get_db
from src.smartparent.schemas.diagnostic import (
    StudentDiagnosticSummaryResponse,
    ResolveGapRequest,
    ResolveGapResponse,
)
from src.smartparent.services.diagnostic_service import diagnostic_service

diagnostic_router = APIRouter(prefix="/diagnostic", tags=["Diagnostic Intelligence"])


@diagnostic_router.get(
    "/child/{child_id}",
    response_model=StudentDiagnosticSummaryResponse,
    summary="Get comprehensive Student 360 diagnostic telemetry",
)
def get_child_diagnostic_profile(
    child_id: uuid.UUID,
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
    db: Session = Depends(get_db),
):
    try:
        return diagnostic_service.get_child_diagnostic_summary(
            db=db,
            subscriber_id=subscriber_id,
            child_id=child_id,
        )
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch diagnostic profile: {str(e)}",
        )


@diagnostic_router.post(
    "/gaps/{gap_id}/resolve",
    response_model=ResolveGapResponse,
    summary="Update or resolve a child learning gap",
)
def resolve_child_gap(
    gap_id: uuid.UUID,
    payload: ResolveGapRequest,
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
    db: Session = Depends(get_db),
):
    try:
        return diagnostic_service.resolve_gap(
            db=db,
            subscriber_id=subscriber_id,
            gap_id=gap_id,
            payload=payload,
        )
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except KeyError as ke:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ke))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resolve learning gap: {str(e)}",
        )

