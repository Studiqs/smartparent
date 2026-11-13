"""
STUDIQS® SmartParent™ (v6.2 Complete) - Parent Actions, Gap Recheck & Academic Handoff API Endpoints
=============================================================================
Section 7: Parent Actions, Gap Recheck and Academic Handoff:
- GET  /api/v1/actions/{child_id}                   -> Top 3 Home Screen Actions Cockpit
- GET  /api/v1/actions/recheck-quiz/{gap_id}        -> 5-Question Targeted Recheck Quiz
- POST /api/v1/actions/recheck-quiz/submit          -> Evaluate Recheck Quiz & Resolve Gap (>=80%)
- GET  /api/v1/actions/academic-handoff/{child_id}  -> Diagnostic Handoff Brief for PTM / Tutors
=============================================================================
"""

import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.smartparent.schemas.actions import (
    ParentActionsListResponse,
    RecheckQuizGenerateResponse,
    RecheckQuizSubmitRequest,
    RecheckQuizSubmitResponse,
    AcademicHandoffBriefResponse,
)
from src.smartparent.services.parent_actions_service import ParentActionsService
from src.smartparent.api.deps import get_db, get_current_subscriber_id

router = APIRouter(prefix="/actions", tags=["Parent Actions, Recheck & Academic Handoff"])


@router.get(
    "/{child_id}",
    response_model=ParentActionsListResponse,
    summary="Retrieve Home Screen prioritized Parent Actions (Strictly max 3 actions)",
)
def get_home_actions(
    child_id: uuid.UUID,
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    """
    Returns the top 3 grounded parent actions for the student's home cockpit.
    Strictly capped at <= 3 actions to prevent parent cognitive overload.
    """
    service = ParentActionsService()
    try:
        return service.get_home_actions(
            db=db,
            subscriber_id=subscriber_id,
            child_id=child_id,
        )
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/recheck-quiz/{gap_id}",
    response_model=RecheckQuizGenerateResponse,
    summary="Generate 5-question targeted diagnostic recheck quiz for a learning gap",
)
def generate_recheck_quiz(
    gap_id: uuid.UUID,
    child_id: uuid.UUID = Query(..., description="Child UUID to verify ownership"),
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    """
    Generates a 5-question targeted diagnostic recheck quiz across Bloom levels
    specifically aligned with the identified topic gap.
    """
    service = ParentActionsService()
    try:
        return service.generate_recheck_quiz(
            db=db,
            subscriber_id=subscriber_id,
            child_id=child_id,
            gap_id=gap_id,
        )
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/recheck-quiz/submit",
    response_model=RecheckQuizSubmitResponse,
    status_code=status.HTTP_200_OK,
    summary="Evaluate targeted diagnostic recheck quiz submission and resolve gap if >= 80%",
)
def submit_recheck_quiz(
    payload: RecheckQuizSubmitRequest,
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    """
    Evaluates recheck quiz:
    - Score >= 80% marks TopicGap as RESOLVED, updates confirmed TopicScore & EvidenceRecord.
    - Score < 80% retains ACTIVE status and logs progress delta.
    """
    service = ParentActionsService()
    try:
        return service.submit_recheck_quiz(
            db=db,
            subscriber_id=subscriber_id,
            child_id=payload.child_id,
            gap_id=payload.gap_id,
            scored_marks=payload.scored_marks,
            max_marks=payload.max_marks,
            recheck_title=payload.recheck_title,
        )
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/academic-handoff/{child_id}",
    response_model=AcademicHandoffBriefResponse,
    summary="Generate diagnostic Academic Handoff Brief for PTM / Tutors",
)
def get_academic_handoff_brief(
    child_id: uuid.UUID,
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    """
    Generates a concise Academic Handoff Brief adhering to the pedagogical standard
    'Praise First, Remediate Second' with specific talking points for teachers/tutors.
    """
    service = ParentActionsService()
    try:
        return service.generate_academic_handoff_brief(
            db=db,
            subscriber_id=subscriber_id,
            child_id=child_id,
        )
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
