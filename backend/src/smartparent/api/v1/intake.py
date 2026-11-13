"""
STUDIQS® SmartParent™ (v6.2 & v6.3 Extension) - Evidence Intake & QP API Router
=============================================================================
Module: src.smartparent.api.v1.intake
Section 3: Zero-Friction Data Feed and Evidence Intake

Endpoints:
  - POST /api/v1/evidence/upload         : Upload exam paper PDF/Image (Document AI)
  - GET  /api/v1/evidence/{evidence_id}/status : Poll OCR/parsing progress
  - GET  /api/v1/evidence/{evidence_id}  : Retrieve parsed questions & marks for review
  - GET  /api/v1/evidence/child/{child_id} : List all evidence upload history for child
  - POST /api/v1/evidence/quick-marks    : Sub-1-minute fast marks entry
  - POST /api/v1/evidence/{evidence_id}/confirm-marks : Confirm question marks & commit TopicScores
=============================================================================
"""

import uuid
from datetime import date
from typing import List, Optional
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from src.smartparent.api.deps import get_current_subscriber_id, get_db
from src.smartparent.schemas.intake import (
    EvidenceUploadResponse,
    EvidenceStatusResponse,
    EvidenceListItemSchema,
    ParsedPaperDetailResponse,
    QuickMarksFeedRequest,
    QuickMarksFeedResponse,
    ConfirmQuestionMarksRequest,
    ConfirmQuestionMarksResponse,
)
from src.smartparent.services.intake_service import IntakeService

router = APIRouter(prefix="/evidence", tags=["Section 3: Evidence Intake & QP Intelligence"])
_service = IntakeService()


@router.post(
    "/upload",
    response_model=EvidenceUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload Exam Paper PDF or Image for Document AI Parsing",
    description="Accepts PDF, PNG, or JPEG question papers (max 25MB) and queues asynchronous Document AI parsing.",
)
async def upload_evidence(
    child_id: uuid.UUID = Form(..., description="Target child profile UUID"),
    subject: str = Form(..., min_length=2, max_length=50, description="Subject name"),
    test_title: str = Form(..., min_length=2, max_length=150, description="Exam or test title"),
    test_date: date = Form(default_factory=date.today, description="Date exam was taken"),
    file: UploadFile = File(..., description="Question paper PDF or camera photo scan"),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
    db: Session = Depends(get_db),
):
    # Validate file extension
    valid_extensions = (".pdf", ".png", ".jpg", ".jpeg", ".webp")
    filename = file.filename or "uploaded_paper.pdf"
    if not any(filename.lower().endswith(ext) for ext in valid_extensions):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format. Allowed extensions: {', '.join(valid_extensions)}",
        )

    content = await file.read()
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File size exceeds the 25MB maximum limit.",
        )

    try:
        return _service.upload_question_paper(
            db=db,
            subscriber_id=subscriber_id,
            child_id=child_id,
            subject=subject,
            test_title=test_title,
            test_date=test_date,
            file_bytes=content,
            file_name=filename,
        )
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process evidence upload: {str(e)}",
        )


@router.get(
    "/{evidence_id}/status",
    response_model=EvidenceStatusResponse,
    summary="Poll Question Paper Document AI Processing Status",
)
def get_evidence_status(
    evidence_id: uuid.UUID,
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
    db: Session = Depends(get_db),
):
    try:
        return _service.get_evidence_status(
            db=db,
            subscriber_id=subscriber_id,
            evidence_id=evidence_id,
        )
    except KeyError as ke:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ke))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/{evidence_id}",
    response_model=ParsedPaperDetailResponse,
    summary="Get Parsed Questions and Syllabus Topics for Review",
)
def get_parsed_paper(
    evidence_id: uuid.UUID,
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
    db: Session = Depends(get_db),
):
    try:
        return _service.get_parsed_paper(
            db=db,
            subscriber_id=subscriber_id,
            evidence_id=evidence_id,
        )
    except KeyError as ke:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ke))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/child/{child_id}",
    response_model=List[EvidenceListItemSchema],
    summary="List Evidence Upload History for Child",
)
def list_child_evidence(
    child_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=100),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
    db: Session = Depends(get_db),
):
    try:
        return _service.list_child_evidence(
            db=db,
            subscriber_id=subscriber_id,
            child_id=child_id,
            limit=limit,
        )
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/quick-marks",
    response_model=QuickMarksFeedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Sub-1-Minute Fast Marks Entry (Zero Friction)",
    description="Allows parents to enter confirmed subject marks immediately without scanning full question papers.",
)
def submit_quick_marks(
    payload: QuickMarksFeedRequest,
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
    db: Session = Depends(get_db),
):
    try:
        return _service.submit_quick_marks(
            db=db,
            subscriber_id=subscriber_id,
            request=payload,
        )
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/{evidence_id}/confirm-marks",
    response_model=ConfirmQuestionMarksResponse,
    summary="Confirm Per-Question Marks and Synchronize TopicScores",
    description="Records student scored marks per question, updates the total exam score, and updates Topic Intelligence.",
)
def confirm_question_marks(
    evidence_id: uuid.UUID,
    payload: ConfirmQuestionMarksRequest,
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
    db: Session = Depends(get_db),
):
    try:
        return _service.confirm_question_marks(
            db=db,
            subscriber_id=subscriber_id,
            evidence_id=evidence_id,
            payload=payload,
        )
    except KeyError as ke:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ke))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

