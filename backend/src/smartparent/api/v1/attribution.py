"""
STUDIQS® SmartParent™ - Attribution Ledger & Funnel Telemetry API
=============================================================================
Module: src.smartparent.api.v1.attribution
Implements Change 3, Change 4, and Change 5 of the Studiqs Change Control Addendum.

Endpoints:
  - POST /api/v1/attribution/events       : Ingest conversion funnel telemetry
  - POST /api/v1/attribution/link-session : Link anonymous discovery events to subscriber
  - GET  /api/v1/attribution/funnel       : Get 13-stage measurable funnel telemetry
=============================================================================
"""

import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.smartparent.api.deps import get_db, get_current_subscriber_id
from src.smartparent.schemas.ecosystem import (
    TelemetryBatchRequest,
    TelemetryIngestResponse,
    LinkAnonymousSessionRequest,
    LinkAnonymousSessionResponse,
)
from src.smartparent.services.attribution_service import AttributionService

router = APIRouter(prefix="/attribution", tags=["Attribution & Conversion Telemetry"])


@router.post(
    "/events",
    response_model=TelemetryIngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest Measurable Conversion Funnel Events",
    description="Captures top-of-funnel events with 5-second deduplication and bot filtering.",
)
def ingest_telemetry_events(payload: TelemetryBatchRequest):
    try:
        return AttributionService.ingest_events(payload.events)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/link-session",
    response_model=LinkAnonymousSessionResponse,
    summary="Link Anonymous Discovery Events to Authenticated Subscriber Profile",
)
def link_session(
    payload: LinkAnonymousSessionRequest,
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    try:
        return AttributionService.link_anonymous_session(
            subscriber_id=subscriber_id,
            anonymous_session_id=payload.anonymous_session_id,
            consent_given=payload.consent_given,
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/funnel",
    summary="Retrieve 13-Stage Conversion Funnel Telemetry & Abandonment Metrics",
)
def get_funnel_metrics():
    return AttributionService.get_funnel_summary()

