"""
STUDIQS® SmartParent™ (v6.3 Complete) - Admin Subscriber Directory API Router
=============================================================================
Module: src.smartparent.api.v1.admin.subscribers
Section 25.4: Administrative Searchable Subscriber Directory & Manual Overrides
Section 24.6: Renewal Alert Sweeper Operations

Endpoints:
  - GET  /api/v1/admin/subscribers                     : Searchable, filterable subscriber directory
  - GET  /api/v1/admin/subscribers/{subscriber_id}     : Detailed 360-degree subscriber dossier
  - POST /api/v1/admin/subscribers/{subscriber_id}/adjust : Manual adjustment with audit entry
  - POST /api/v1/admin/subscribers/alerts/sweep        : Trigger 4-stage renewal alert sweep
  - GET  /api/v1/admin/subscribers/alerts/reminders    : View audit history of dispatched reminders
=============================================================================
"""

import uuid
from datetime import date
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.smartparent.db.session import get_db
from src.smartparent.schemas.admin_directory import (
    AdminSubscriberDirectoryResponse,
    AdminSubscriberDetailResponse,
    ManualSubscriptionAdjustmentRequest,
    ManualSubscriptionAdjustmentResponse,
)
from src.smartparent.schemas.renewal_alerts import (
    TriggerAlertSweepRequest,
    AlertSweepSummaryResponse,
)
from src.smartparent.services.admin_directory_service import admin_directory_service
from src.smartparent.services.renewal_alert_service import renewal_alert_service

admin_subscribers_router = APIRouter(prefix="/admin/subscribers", tags=["Admin Subscriber Directory (Section 25.4)"])


@admin_subscribers_router.get(
    "",
    response_model=AdminSubscriberDirectoryResponse,
    summary="Searchable administrative subscriber directory",
    description="Multi-criteria filtering by plan, duration, status, search term, and expiry window.",
)
def list_subscribers_directory(
    plan: Optional[str] = Query(None, description="BASIC, ADVANCED, PRO"),
    duration_months: Optional[int] = Query(None, description="1, 3, 6, 12"),
    status: Optional[str] = Query(None, description="ACTIVE, EXPIRING_SOON, EXPIRED, CANCELLED"),
    search_query: Optional[str] = Query(None, description="Search by parent name, mobile number, or email"),
    expiry_before: Optional[date] = Query(None, description="Filter subscriptions expiring before this date"),
    expiry_after: Optional[date] = Query(None, description="Filter subscriptions expiring after this date"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return admin_directory_service.list_subscribers(
        db=db,
        plan=plan,
        duration_months=duration_months,
        status=status,
        search_query=search_query,
        expiry_before=expiry_before,
        expiry_after=expiry_after,
        page=page,
        page_size=page_size,
    )


@admin_subscribers_router.get(
    "/{subscriber_id}",
    response_model=AdminSubscriberDetailResponse,
    summary="Get 360-degree subscriber dossier",
    description="Exhaustive breakdown of children, subscriptions, invoices, tickets, and adjustment audits.",
)
def get_subscriber_dossier(
    subscriber_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    try:
        return admin_directory_service.get_subscriber_detail(
            db=db,
            subscriber_id=subscriber_id,
        )
    except KeyError as ke:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ke))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch subscriber dossier: {str(e)}",
        )


@admin_subscribers_router.post(
    "/{subscriber_id}/adjust",
    response_model=ManualSubscriptionAdjustmentResponse,
    summary="Manual subscription adjustment with audit log",
    description="Extends validity, overrides plan tier, or updates status. Requires mandatory reason.",
)
def adjust_subscriber_subscription(
    subscriber_id: uuid.UUID,
    payload: ManualSubscriptionAdjustmentRequest,
    db: Session = Depends(get_db),
):
    try:
        return admin_directory_service.adjust_subscription(
            db=db,
            subscriber_id=subscriber_id,
            payload=payload,
        )
    except KeyError as ke:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ke))
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Adjustment failed: {str(e)}",
        )


@admin_subscribers_router.post(
    "/alerts/sweep",
    response_model=AlertSweepSummaryResponse,
    summary="Trigger 4-stage automatic renewal reminder sweep",
    description="Evaluates all active subscriptions for 7d, 3d, 1d, and 0d expiry milestones.",
)
def trigger_renewal_alert_sweep(
    payload: TriggerAlertSweepRequest,
    db: Session = Depends(get_db),
):
    try:
        return renewal_alert_service.run_alert_sweep(
            db=db,
            target_date=payload.simulate_date,
            dry_run=payload.dry_run,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Alert sweep execution failed: {str(e)}",
        )


@admin_subscribers_router.get(
    "/alerts/reminders",
    summary="List dispatched renewal reminders audit log",
    description="Chronological log of all system renewal and expiry alerts sent to subscribers.",
)
def list_dispatched_reminders(
    subscriber_id: Optional[uuid.UUID] = Query(None, description="Optional subscriber filter"),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return renewal_alert_service.list_dispatched_reminders(
        db=db,
        subscriber_id=subscriber_id,
        limit=limit,
    )

