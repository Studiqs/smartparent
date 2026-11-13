"""
STUDIQS® SmartParent™ (v6.2 Complete) - Report Centre & Student 360 API Endpoints
=============================================================================
Section 4: Student 360 & Consolidated Report Lifecycle Endpoints:
- GET  /api/v1/reports/student-360/{child_id}
- POST /api/v1/reports/consolidated
- GET  /api/v1/reports/current-year/{child_id}
- GET  /api/v1/reports/history/{child_id}
- GET  /api/v1/reports/{report_id}
- POST /api/v1/reports/rollover
=============================================================================
"""

import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.smartparent.schemas.reports import (
    Student360Response,
    ConsolidatedReportCreate,
    ConsolidatedReportResponse,
    AcademicYearRolloverRequest,
    AcademicYearRolloverResponse,
)
from src.smartparent.services.student_360_service import Student360Service
from src.smartparent.services.report_service import ReportService
from src.smartparent.db.models.consolidated_report import ConsolidatedReport

router = APIRouter(prefix="/reports", tags=["Reports & Student 360"])

from src.smartparent.api.deps import get_db, get_current_subscriber_id


@router.get(
    "/student-360/{child_id}",
    response_model=Student360Response,
    summary="Retrieve full Student 360 Intelligence View",
)
def get_student_360(
    child_id: uuid.UUID,
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    service = Student360Service()
    try:
        return service.get_student_360(db=db, subscriber_id=subscriber_id, child_id=child_id)
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/consolidated",
    response_model=ConsolidatedReportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate Monthly, Term, or Yearly Consolidated Report",
)
def create_consolidated_report(
    payload: ConsolidatedReportCreate,
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    service = ReportService()
    try:
        report = service.generate_consolidated_report(
            db=db,
            subscriber_id=subscriber_id,
            child_id=payload.child_id,
            report_type=payload.report_type,
            academic_year=payload.academic_year,
            period_key=payload.period_key,
            report_title=payload.report_title,
            include_pdf=payload.include_pdf,
        )
        return report
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/current-year/{child_id}",
    response_model=List[ConsolidatedReportResponse],
    summary="Get all active reports for current academic year",
)
def get_current_year_reports(
    child_id: uuid.UUID,
    academic_year: str = Query(..., example="2026-2027"),
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    service = ReportService()
    try:
        return service.get_current_year_reports(
            db=db,
            subscriber_id=subscriber_id,
            child_id=child_id,
            academic_year=academic_year,
        )
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))


@router.get(
    "/history/{child_id}",
    response_model=List[ConsolidatedReportResponse],
    summary="Get archived historical Yearly reports from previous academic years",
)
def get_report_history(
    child_id: uuid.UUID,
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    service = ReportService()
    try:
        return service.get_report_history(
            db=db,
            subscriber_id=subscriber_id,
            child_id=child_id,
        )
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))


@router.get(
    "/{report_id}",
    response_model=ConsolidatedReportResponse,
    summary="Get individual report detail and PDF path",
)
def get_report_detail(
    report_id: uuid.UUID,
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    report = (
        db.query(ConsolidatedReport)
        .filter(ConsolidatedReport.report_id == report_id, ConsolidatedReport.subscriber_id == subscriber_id)
        .first()
    )
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found or unauthorized.")
    return report


@router.post(
    "/rollover",
    response_model=AcademicYearRolloverResponse,
    summary="Execute Academic-Year Rollover & Archival",
)
def rollover_academic_year(
    payload: AcademicYearRolloverRequest,
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    service = ReportService()
    try:
        return service.execute_academic_year_rollover(
            db=db,
            subscriber_id=subscriber_id,
            child_id=payload.child_id,
            previous_academic_year=payload.previous_academic_year,
            new_academic_year=payload.new_academic_year,
            new_standard_class=payload.new_standard_class,
        )
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
