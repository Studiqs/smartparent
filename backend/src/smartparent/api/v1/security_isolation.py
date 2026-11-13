"""
STUDIQS® SmartParent™ (v6.2 Complete) - Section 16 Security, Isolation & Document Handling Router
=============================================================================
Module: src.smartparent.api.v1.security_isolation
Section 16: Backend, Subscriber/Expert Isolation, Security, Retention & Document Handling

Endpoints:
1. POST /api/v1/isolation/signed-url                   -> Generate scoped, expiring signed URL
2. POST /api/v1/isolation/verify-url                   -> Verify signed token validity
3. GET  /api/v1/isolation/retention/reports/{child_id} -> Audit student report retention lifecycle
4. GET  /api/v1/isolation/retention/evaluations/{id}   -> Audit evaluation retention status
5. GET  /api/v1/isolation/sanitized/case/{id}          -> Expert isolated case view
6. GET  /api/v1/isolation/sanitized/expert/{id}        -> Subscriber isolated expert view
=============================================================================
"""

import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.smartparent.schemas.security_isolation import (
    GenerateSignedUrlRequest,
    SignedUrlResponse,
    VerifySignedUrlRequest,
    VerifySignedUrlResponse,
    SanitizedExpertCaseView,
    SanitizedSubscriberExpertProfile,
    ReportRetentionAuditResponse,
    EvaluationRetentionAuditResponse,
)
from src.smartparent.services.isolation_security_service import IsolationSecurityService

router = APIRouter(prefix="/isolation", tags=["Section 16: Security, Isolation & Document Retention"])


from src.smartparent.api.deps import get_db, get_current_subscriber_id, get_current_expert_id


@router.post(
    "/signed-url",
    response_model=SignedUrlResponse,
    summary="Generate Scoped Expiring Signed URL",
    description="Generates an expiring HMAC-SHA256 signed URL for private cloud storage access after boundary verification.",
)
def generate_signed_url(
    request: GenerateSignedUrlRequest,
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    service = IsolationSecurityService()
    try:
        return service.generate_signed_document_url(db=db, subscriber_id=subscriber_id, request=request)
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/verify-url",
    response_model=VerifySignedUrlResponse,
    summary="Verify Signed URL Token",
    description="Validates cryptographic signature integrity and expiration for document access.",
)
def verify_signed_url(request: VerifySignedUrlRequest):
    service = IsolationSecurityService()
    return service.verify_signed_url_token(request)


@router.get(
    "/retention/reports/{child_id}",
    response_model=ReportRetentionAuditResponse,
    summary="Audit Report Retention Lifecycle",
    description="Audits report retention: active current-year reports vs retired intermediate drafts and permanent historical archives.",
)
def audit_report_retention(
    child_id: uuid.UUID,
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    service = IsolationSecurityService()
    try:
        return service.audit_child_report_retention(db=db, subscriber_id=subscriber_id, child_id=child_id)
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/retention/evaluations/{evaluation_id}",
    response_model=EvaluationRetentionAuditResponse,
    summary="Audit Evaluation Retention Lifecycle",
    description="Audits expert evaluation case retention against 7-year statutory audit policy and dispute window.",
)
def audit_evaluation_retention(
    evaluation_id: uuid.UUID,
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    service = IsolationSecurityService()
    try:
        return service.audit_evaluation_retention(db=db, subscriber_id=subscriber_id, evaluation_id=evaluation_id)
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/sanitized/case/{evaluation_id}",
    response_model=SanitizedExpertCaseView,
    summary="Get Sanitized Case for Expert",
    description="Returns case details with parent phone, email, billing, family history, and sibling data strictly scrubbed.",
)
def get_sanitized_case_for_expert(
    evaluation_id: uuid.UUID,
    db: Session = Depends(get_db),
    expert_id: uuid.UUID = Depends(get_current_expert_id),
):
    service = IsolationSecurityService()
    try:
        return service.get_sanitized_case_for_expert(db=db, expert_id=expert_id, evaluation_id=evaluation_id)
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/sanitized/expert/{expert_id}",
    response_model=SanitizedSubscriberExpertProfile,
    summary="Get Sanitized Expert Profile for Subscriber",
    description="Returns expert public profile with KYC, bank details, payout records, and commission splits strictly scrubbed.",
)
def get_sanitized_expert_profile(
    expert_id: uuid.UUID,
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    service = IsolationSecurityService()
    try:
        return service.get_sanitized_expert_profile_for_subscriber(db=db, subscriber_id=subscriber_id, expert_id=expert_id)
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

