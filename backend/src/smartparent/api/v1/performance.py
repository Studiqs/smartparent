"""
STUDIQS® SmartParent™ (v6.2 Complete) - Performance & Consistency API Endpoints
=============================================================================
Section 5: Performance, Monthly Consistency & Topic Intelligence:
- GET  /api/v1/performance/{child_id}
- GET  /api/v1/performance/consistency/{child_id}
- GET  /api/v1/performance/gap-closure/{child_id}
- POST /api/v1/performance/gap-recheck
=============================================================================
"""

import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.smartparent.schemas.performance import (
    Section5PerformanceResponse,
    GapRecheckRequestSchema,
    GapRecheckResponseSchema,
    SubjectMonthlyConsistencySchema,
    GapClosureSummarySchema,
)
from src.smartparent.services.performance_service import PerformanceService

router = APIRouter(prefix="/performance", tags=["Performance, Consistency & Gaps"])


from src.smartparent.api.deps import get_db, get_current_subscriber_id


@router.get(
    "/{child_id}",
    response_model=Section5PerformanceResponse,
    summary="Retrieve full Section 5 Performance & Consistency Intelligence",
)
def get_performance_intelligence(
    child_id: uuid.UUID,
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    service = PerformanceService()
    try:
        return service.get_performance_intelligence(db=db, subscriber_id=subscriber_id, child_id=child_id)
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/consistency/{child_id}",
    response_model=List[SubjectMonthlyConsistencySchema],
    summary="Retrieve Subject Monthly Consistency Progressions",
)
def get_subject_consistency(
    child_id: uuid.UUID,
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    service = PerformanceService()
    try:
        intel = service.get_performance_intelligence(db=db, subscriber_id=subscriber_id, child_id=child_id)
        return intel.subject_consistencies
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/gap-closure/{child_id}",
    response_model=GapClosureSummarySchema,
    summary="Retrieve Topic Gap Closure and Watchlist Status",
)
def get_gap_closure_summary(
    child_id: uuid.UUID,
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    service = PerformanceService()
    try:
        intel = service.get_performance_intelligence(db=db, subscriber_id=subscriber_id, child_id=child_id)
        return intel.gap_closure_summary
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/gap-recheck",
    response_model=GapRecheckResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Submit a diagnostic recheck for a topic gap and evaluate closure",
)
def submit_gap_recheck(
    payload: GapRecheckRequestSchema,
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    service = PerformanceService()
    try:
        return service.execute_gap_recheck(
            db=db,
            subscriber_id=subscriber_id,
            child_id=payload.child_id,
            gap_id=payload.gap_id,
            scored_marks=payload.recheck_scored_marks,
            max_marks=payload.recheck_max_marks,
            recheck_title=payload.recheck_title,
            test_date=payload.test_date,
        )
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
