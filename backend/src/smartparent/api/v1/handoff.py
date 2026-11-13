"""
STUDIQS® SmartParent™ (v6.2 Complete) - Section 9 Parent Value & School/Tuition Lifecycle API
=============================================================================
Section 9 Endpoints (Working Specification v6.0 / v6.1):
1. GET /api/v1/handoff/moments/{child_id}                   -> Complete Master 7-Moment Lifecycle Status
2. GET /api/v1/handoff/moments/{child_id}/after-each-test   -> Moment 1: Post-test intelligence delta
3. GET /api/v1/handoff/moments/{child_id}/deeper-help       -> Moment 2: Weak subject diagnosis & expert trigger
4. GET /api/v1/handoff/moments/{child_id}/month-end         -> Moment 3: Month-end pulse & consolidated report
5. GET /api/v1/handoff/moments/{child_id}/term-end          -> Moment 4: Term-wise trajectory review
6. GET /api/v1/handoff/moments/{child_id}/year-end          -> Moment 5: Final yearly archive
7. GET /api/v1/handoff/moments/{child_id}/next-year-rollover-> Moment 6: Rollover status & prior report retention
8. GET /api/v1/handoff/ptm-pack/{child_id}                  -> Moment 7: PTM / Tuition Prep Pack
9. GET /api/v1/handoff/whatsapp-text/{child_id}             -> 1-Click WhatsApp Quick-Share deep-link
=============================================================================
"""

import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.smartparent.schemas.handoff import (
    PtmAudienceEnum,
    ParentValueMomentEnum,
    AfterEachTestSnapshotSchema,
    DeeperHelpDiagnosticSchema,
    MonthEndDigestSchema,
    TermEndReviewSchema,
    YearEndConsolidatedSchema,
    NextAcademicYearRolloverStatusSchema,
    PtmPackResponse,
    WhatsAppShareResponse,
    Section9MasterValueLifecycleResponse,
)
from src.smartparent.services.academic_handoff_service import AcademicHandoffService
from src.smartparent.api.deps import get_db, get_current_subscriber_id

router = APIRouter(prefix="/handoff", tags=["Section 9: Parent Value & School/Tuition Handoff"])


@router.get(
    "/moments/{child_id}",
    response_model=Section9MasterValueLifecycleResponse,
    summary="Retrieve Master Section 9 Parent Value Lifecycle across all 7 moments",
)
def get_all_lifecycle_moments(
    child_id: uuid.UUID,
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    """Returns status and intelligence for all 7 moments in Section 9."""
    service = AcademicHandoffService()
    try:
        return service.get_all_lifecycle_moments(db=db, subscriber_id=subscriber_id, child_id=child_id)
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/moments/{child_id}/after-each-test",
    response_model=AfterEachTestSnapshotSchema,
    summary="Moment 1: After Each Test snapshot & baseline trajectory delta",
)
def get_after_each_test(
    child_id: uuid.UUID,
    test_id: Optional[uuid.UUID] = Query(None, description="Optional specific evidence record ID"),
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    """Calculates immediate post-test score %, prior test movement delta, and next step."""
    service = AcademicHandoffService()
    try:
        return service.get_after_each_test_value(db=db, subscriber_id=subscriber_id, child_id=child_id, test_id=test_id)
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/moments/{child_id}/deeper-help",
    response_model=DeeperHelpDiagnosticSchema,
    summary="Moment 2: When a Subject Needs Deeper Help diagnosis & expert evaluation trigger",
)
def get_deeper_help(
    child_id: uuid.UUID,
    subject: Optional[str] = Query(None, description="Target subject, or omit to diagnose lowest scoring subject"),
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    """Identifies persistent weakness (<50%) and triggers expert evaluation recommendation."""
    service = AcademicHandoffService()
    try:
        return service.get_deeper_help_value(db=db, subscriber_id=subscriber_id, child_id=child_id, subject=subject)
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/moments/{child_id}/month-end",
    response_model=MonthEndDigestSchema,
    summary="Moment 3: Month End Monthly Parent Pulse + Monthly Consolidated Report",
)
def get_month_end(
    child_id: uuid.UUID,
    month: Optional[str] = Query(None, description="Month in YYYY-MM format, e.g. '2026-10'"),
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    """Delivers month-end Parent Pulse summary and consolidated report access."""
    service = AcademicHandoffService()
    try:
        return service.get_month_end_value(db=db, subscriber_id=subscriber_id, child_id=child_id, month_key=month)
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/moments/{child_id}/term-end",
    response_model=TermEndReviewSchema,
    summary="Moment 4: Term End Term-wise Consolidated Report & Consistency Rating",
)
def get_term_end(
    child_id: uuid.UUID,
    term_name: str = Query("Term 1", description="Term name e.g. 'Term 1', 'Midterm', 'Quarterly'"),
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    """Evaluates term-end consistency rating and syllabus progress."""
    service = AcademicHandoffService()
    try:
        return service.get_term_end_value(db=db, subscriber_id=subscriber_id, child_id=child_id, term_name=term_name)
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/moments/{child_id}/year-end",
    response_model=YearEndConsolidatedSchema,
    summary="Moment 5: Year End Final Yearly Consolidated Report & Permanent Archive",
)
def get_year_end(
    child_id: uuid.UUID,
    academic_year: Optional[str] = Query(None, description="Academic year e.g. '2025-2026'"),
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    """Delivers final annual consolidated report and archive status."""
    service = AcademicHandoffService()
    try:
        return service.get_year_end_value(db=db, subscriber_id=subscriber_id, child_id=child_id, academic_year=academic_year)
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/moments/{child_id}/next-year-rollover",
    response_model=NextAcademicYearRolloverStatusSchema,
    summary="Moment 6: Next Academic Year rollover verification (prior yearly report retained)",
)
def get_next_academic_year(
    child_id: uuid.UUID,
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    """Confirms only prior yearly report remains in history, intermediate drafts retired."""
    service = AcademicHandoffService()
    try:
        return service.get_next_academic_year_value(db=db, subscriber_id=subscriber_id, child_id=child_id)
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/ptm-pack/{child_id}",
    response_model=PtmPackResponse,
    summary="Moment 7: PTM / Tuition Prep Pack with Misconception Patterns & Talking Points",
)
def get_ptm_pack(
    child_id: uuid.UUID,
    subject: Optional[str] = Query(None, description="Filter by subject (e.g. 'Mathematics'), or omit for all subjects"),
    audience: PtmAudienceEnum = Query(PtmAudienceEnum.TEACHER, description="Target recipient: TEACHER, TUTOR, or COMPREHENSIVE"),
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    """Generates 1-page printable PTM / Tuition Prep Pack adhering to Praise First, Remediate Second."""
    service = AcademicHandoffService()
    try:
        return service.generate_ptm_pack(
            db=db,
            subscriber_id=subscriber_id,
            child_id=child_id,
            subject=subject,
            audience=audience,
        )
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/whatsapp-text/{child_id}",
    response_model=WhatsAppShareResponse,
    summary="Generate 1-click WhatsApp share payload and direct deep-link",
)
def get_whatsapp_text(
    child_id: uuid.UUID,
    subject: Optional[str] = Query(None, description="Optional subject filter"),
    audience: PtmAudienceEnum = Query(PtmAudienceEnum.TEACHER, description="Target recipient: TEACHER, TUTOR, or COMPREHENSIVE"),
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    """Returns WhatsApp-formatted text and pre-encoded deep-link for instant mobile sharing."""
    service = AcademicHandoffService()
    try:
        return service.get_whatsapp_share_payload(
            db=db,
            subscriber_id=subscriber_id,
            child_id=child_id,
            subject=subject,
            audience=audience,
        )
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
