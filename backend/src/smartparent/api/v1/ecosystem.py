"""
STUDIQS® SmartParent™ - Cross-Product Ecosystem & DPDP Consent API
=============================================================================
Module: src.smartparent.api.v1.ecosystem
Implements Change 4 & Change 6 of the Studiqs Change Control Addendum.

Endpoints:
  - GET  /api/v1/ecosystem/discovery-card        : Official SmartParent promotional card for Academy Connect
  - POST /api/v1/ecosystem/cross-product-consent : Record affirmative parental consent for academy referral
  - POST /api/v1/ecosystem/revoke-consent        : Revoke consent and invalidate referral token
  - GET  /api/v1/ecosystem/redeem-referral       : Academy redemption validation for referral token
=============================================================================
"""

import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.smartparent.api.deps import get_db, get_current_subscriber_id
from src.smartparent.schemas.ecosystem import (
    SmartParentDiscoveryCardResponse,
    CrossProductConsentRequest,
    CrossProductConsentResponse,
    RevokeConsentRequest,
)
from src.smartparent.services.consent_boundary_service import ConsentBoundaryService

router = APIRouter(prefix="/ecosystem", tags=["Ecosystem Cross-Promotion & DPDP Consent"])


@router.get(
    "/discovery-card",
    response_model=SmartParentDiscoveryCardResponse,
    summary="Get 'Discover Studiqs SmartParent' Promotional Card Payload",
    description="Provides standardized marketing and plan ladder card data for Academy Connect integration.",
)
def get_discovery_card(
    referral_source: str = Query("academy_connect", description="Inbound partner or app identifier"),
):
    return SmartParentDiscoveryCardResponse(
        product_name="STUDIQS® SmartParent™",
        tagline="Independent Class 1–12 Parent Learning Intelligence & Syllabus Diagnostics",
        features=[
            "Pure Question-Paper Based Cognitive Evidence (Zero Fake Mastery)",
            "Longitudinal 3-Month Consistency Slope & 60-Day Direction Delta",
            "Root-Cause Topic Gap Identification with Prerequisite Tree Tracing",
            "ReportLab Pixel-Perfect Vector PDF Monthly & Term Reports",
            "Ask Studiqs Socratic AI Voice Assistant (Whisper STT with Safe Guardrails)",
            "Verified CBSE / State Board Subject Expert Evaluation (48-Hour Hard SLA)",
        ],
        pricing_ladder={
            "Basic": "₹200 per child/month",
            "Advanced": "₹400 per child/month",
            "Pro": "₹600 per child/month",
        },
        view_plans_url="https://studiqs.com/smartparent/plans?ref=" + referral_source,
        referral_campaign_id=f"camp_cross_promo_{referral_source}",
        statutory_notice=(
            "Separate subscription; accounts and academic data are not automatically joined "
            "without affirmative parental choice under the DPDP Act 2023."
        ),
    )


@router.post(
    "/cross-product-consent",
    response_model=CrossProductConsentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record Affirmative Parental Consent for Academy Gap Remediation Handoff",
    description="Statutory DPDP Act 2023 consent capture. Generates a 72-hour scoped handoff token.",
)
def record_consent(
    payload: CrossProductConsentRequest,
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
    db: Session = Depends(get_db),
):
    try:
        return ConsentBoundaryService.record_affirmative_consent(
            db=db,
            subscriber_id=subscriber_id,
            request=payload,
        )
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/revoke-consent",
    summary="Revoke External Academy Remediation Consent",
)
def revoke_consent(
    payload: RevokeConsentRequest,
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    try:
        ConsentBoundaryService.revoke_consent(subscriber_id=subscriber_id, request=payload)
        return {"status": "REVOKED", "message": "Cross-product referral consent revoked successfully."}
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except KeyError as ke:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ke))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/redeem-referral",
    summary="Verify and Redeem Scoped Remediation Token (Academy Gateway)",
)
def redeem_referral_token(
    token: str = Query(..., description="Encrypted 72-hour handoff token"),
):
    data = ConsentBoundaryService.verify_token(token)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Referral token is invalid, expired (>72 hours), or has been revoked by the parent.",
        )
    return {
        "status": "VALID",
        "redemption_payload": data,
        "notice": "Parental consent verified under DPDP Act 2023. Raw grades remain private.",
    }

