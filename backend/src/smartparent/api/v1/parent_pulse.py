"""
STUDIQS® SmartParent™ (v6.2 Complete) - Monthly Parent Pulse API Endpoints
=============================================================================
Section 6: Monthly Recurring Parent Value & Learning Cycle:
- GET  /api/v1/parent-pulse/{child_id}
- POST /api/v1/parent-pulse/generate
- GET  /api/v1/parent-pulse/actions/{child_id}
- GET  /api/v1/parent-pulse/history/{child_id}
=============================================================================
"""

import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.smartparent.schemas.parent_pulse import (
    MonthlyParentPulseResponse,
    GroundedActionItemSchema,
    GeneratePulseRequest,
)
from src.smartparent.services.parent_pulse_service import ParentPulseService
from src.smartparent.api.deps import get_db, get_current_subscriber_id

router = APIRouter(prefix="/parent-pulse", tags=["Monthly Parent Pulse & Learning Cycle"])


@router.get(
    "/{child_id}",
    response_model=MonthlyParentPulseResponse,
    summary="Retrieve active Monthly Parent Pulse & Learning Cycle",
)
def get_parent_pulse(
    child_id: uuid.UUID,
    month_key: Optional[str] = Query(None, description="Optional target month YYYY-MM"),
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    service = ParentPulseService()
    try:
        return service.get_or_synthesize_parent_pulse(
            db=db,
            subscriber_id=subscriber_id,
            child_id=child_id,
            month_key=month_key,
            force_refresh=False,
        )
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/generate",
    response_model=MonthlyParentPulseResponse,
    status_code=status.HTTP_200_OK,
    summary="Synthesize or refresh Monthly Parent Pulse",
)
def generate_parent_pulse(
    payload: GeneratePulseRequest,
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    service = ParentPulseService()
    try:
        return service.get_or_synthesize_parent_pulse(
            db=db,
            subscriber_id=subscriber_id,
            child_id=payload.child_id,
            month_key=payload.month_key,
            force_refresh=payload.force_refresh,
        )
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/actions/{child_id}",
    response_model=List[GroundedActionItemSchema],
    summary="Retrieve strictly Max 3 Grounded Parent Actions for Home screen",
)
def get_grounded_actions(
    child_id: uuid.UUID,
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    service = ParentPulseService()
    try:
        return service.get_grounded_actions(
            db=db,
            subscriber_id=subscriber_id,
            child_id=child_id,
        )
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/history/{child_id}",
    response_model=List[MonthlyParentPulseResponse],
    summary="Retrieve longitudinal Parent Pulse history",
)
def get_pulse_history(
    child_id: uuid.UUID,
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    service = ParentPulseService()
    try:
        return service.get_pulse_history(
            db=db,
            subscriber_id=subscriber_id,
            child_id=child_id,
        )
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
