"""
STUDIQS® SmartParent™ (v6.3 Complete) - Management Revenue & Intelligence Dashboard API
========================================================================================
Module: src.smartparent.api.v1.admin.dashboard
Section 25: Management MRR, Collections & Subscriber Growth Intelligence

Provides real-time SaaS financial telemetry:
  1. Section 25.2: Normalized MRR & ARR (accounting for multi-month contracts).
  2. Cash Collections MTD vs MRR.
  3. Unique Customer Parents vs Paid Child Subscriptions separation.
  4. SaaS Metrics: ARPU, Churn Rate, Renewal Rate.
  5. Section 25.3: Monthly Subscriber Cohort Report & CSV Export.
  6. Invoices Audit Trail.
========================================================================================
"""

import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from src.smartparent.db.session import get_db
from src.smartparent.db.models.subscription import BillingInvoice
from src.smartparent.services.admin_revenue_service import admin_revenue_service
from src.smartparent.schemas.admin_revenue import (
    ExecutiveMRRKPISummaryResponse,
    MonthlySubscriberReportResponse,
)

logger = logging.getLogger("STUDIQS_AdminRevenue")

router = APIRouter(prefix="/admin/revenue", tags=["Section 25: Management Revenue Intelligence"])


@router.get(
    "/summary",
    response_model=ExecutiveMRRKPISummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Executive MRR & Collections Summary",
    description="Section 25.2: Computes multi-month normalized MRR, ARR, collections, ARPU, churn rate, and plan/duration distributions.",
)
def get_revenue_summary(
    db: Session = Depends(get_db),
) -> ExecutiveMRRKPISummaryResponse:
    """Computes executive SaaS metrics for management."""
    return admin_revenue_service.get_executive_kpis(db=db)


@router.get(
    "/monthly-report",
    response_model=MonthlySubscriberReportResponse,
    status_code=status.HTTP_200_OK,
    summary="Monthly Subscriber Movement & Financial Ledger",
    description="Section 25.3: Select any month (YYYY-MM) to view opening, new, renewed, expired, cancelled, and closing subscribers.",
)
def get_monthly_report(
    month: Optional[str] = Query(None, description="Month in YYYY-MM format (e.g. 2026-11). Defaults to current month."),
    db: Session = Depends(get_db),
) -> MonthlySubscriberReportResponse:
    """Returns detailed subscriber cohort movement and revenue for the target month."""
    return admin_revenue_service.get_monthly_subscriber_report(db=db, month_key=month)


@router.get(
    "/monthly-report/export",
    status_code=status.HTTP_200_OK,
    summary="Export Monthly Financial Report to CSV",
    description="Section 25.3: Downloads audited monthly subscriber movement and revenue ledger as a CSV file.",
)
def export_monthly_report_csv(
    month: Optional[str] = Query(None, description="Month in YYYY-MM format. Defaults to current month."),
    db: Session = Depends(get_db),
):
    """Generates and streams an audited CSV financial report."""
    target_month = month or admin_revenue_service.intel_engine.get_now_utc().strftime("%Y-%m") if hasattr(admin_revenue_service.intel_engine, 'get_now_utc') else "CURRENT"
    csv_text = admin_revenue_service.export_monthly_report_csv(db=db, month_key=month)

    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=studiqs_financial_report_{target_month}.csv",
        },
    )


@router.get(
    "/invoices",
    status_code=status.HTTP_200_OK,
    summary="List All Formal Tax Invoices",
    description="Returns chronological audit trail of all generated B2C GST tax invoices.",
)
def list_all_invoices(
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Lists audit trail of issued invoices."""
    invoices = (
        db.query(BillingInvoice)
        .order_by(BillingInvoice.created_at.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "invoice_id": str(inv.invoice_id),
            "invoice_number": inv.invoice_number,
            "subscriber_id": str(inv.subscriber_id),
            "taxable_amount": float(inv.taxable_amount),
            "total_amount": float(inv.total_amount),
            "payment_status": inv.payment_status,
            "razorpay_payment_id": inv.razorpay_payment_id,
            "invoice_pdf_url": inv.invoice_pdf_url,
            "created_at": inv.created_at.isoformat() if inv.created_at else None,
        }
        for inv in invoices
    ]
