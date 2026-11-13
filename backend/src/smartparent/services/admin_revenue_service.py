"""
STUDIQS® SmartParent™ - Section 25.2 & 25.3 Admin Revenue Intelligence Service
=============================================================================
Module: src.smartparent.services.admin_revenue_service

Implements Section 25 Management Requirements:
  1. Section 25.2: Multi-month MRR Normalization (Annual/12, Half-Yearly/6, etc.),
     Cash collections vs MRR, ARPU, Churn Rate, separating unique paying parents
     from paid child subscriptions.
  2. Section 25.3: Monthly Subscriber Reporting (Opening active, New acquired,
     Renewed, Expired, Cancelled, Closing active) with Plan and Duration distributions.
  3. Export Engine: Production CSV export for executive management and audit.
=============================================================================
"""

import io
import csv
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, and_, or_

from src.smartparent.db.models.subscription import (
    Subscription,
    BillingInvoice,
    SubscriptionPrice,
)
from src.smartparent.db.models.auth import Subscriber
from src.smartparent.db.models.marketplace import PaymentOrder
from src.smartparent.engines.section_10_subscription_billing import (
    SubscriberIntelligenceEngine,
    SubscriptionPricingEngine,
)
from src.smartparent.schemas.admin_revenue import (
    PlanRevenueBreakdownSchema,
    DurationRevenueBreakdownSchema,
    TaxLiabilityBreakdownSchema,
    MarketplaceRevenueBreakdownSchema,
    ExecutiveMRRKPISummaryResponse,
    MonthlySubscriberReportResponse,
)

logger = logging.getLogger("STUDIQS_AdminRevenueService")


class AdminRevenueService:
    """
    Management Revenue & Subscription Intelligence Service (Section 25).
    """

    def __init__(self):
        self.intel_engine = SubscriberIntelligenceEngine()
        self.pricing_engine = SubscriptionPricingEngine()

    @staticmethod
    def _parse_month_bounds(month_key: str) -> Tuple[datetime, datetime]:
        """Calculates exact UTC month start and end boundaries."""
        year, month = map(int, month_key.split("-"))
        start_dt = datetime(year, month, 1, 0, 0, 0, tzinfo=timezone.utc)
        if month == 12:
            end_dt = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=timezone.utc) - timedelta(microseconds=1)
        else:
            end_dt = datetime(year, month + 1, 1, 0, 0, 0, tzinfo=timezone.utc) - timedelta(microseconds=1)
        return start_dt, end_dt

    def get_executive_kpis(self, db: Session) -> ExecutiveMRRKPISummaryResponse:
        """
        Section 25.2 Management Dashboard Mandatory KPIs.
        """
        now_utc = datetime.now(timezone.utc)
        month_key = now_utc.strftime("%Y-%m")
        month_start, month_end = self._parse_month_bounds(month_key)

        # 1. Total Registered Parents vs Unique Paying Parents
        total_registered_parents = db.query(func.count(Subscriber.subscriber_id)).scalar() or 0

        # Unique parents who currently hold an ACTIVE subscription
        unique_paying_parents_count = (
            db.query(func.count(func.distinct(Subscription.subscriber_id)))
            .filter(Subscription.status == "ACTIVE")
            .scalar()
            or 0
        )

        # Total active subscription seats (can be multiple if parent has multiple children)
        active_subscriptions_records = (
            db.query(Subscription)
            .filter(Subscription.status == "ACTIVE")
            .all()
        )
        total_active_child_subscriptions = len(active_subscriptions_records)

        # 2. Multi-Month MRR Normalization across all active subscriptions
        active_sub_payloads: List[Dict[str, Any]] = []
        for sub in active_subscriptions_records:
            # Determine contracted price paid for this subscription
            price_paid = 0.0
            latest_inv = (
                db.query(BillingInvoice)
                .filter(BillingInvoice.subscription_id == sub.subscription_id, BillingInvoice.payment_status == "PAID")
                .first()
            )
            if latest_inv:
                price_paid = float(latest_inv.total_amount)
            else:
                price_paid = self.pricing_engine.get_price(sub.plan_id, sub.duration_months)

            active_sub_payloads.append({
                "plan_id": sub.plan_id,
                "duration_months": sub.duration_months,
                "price_paid": price_paid,
            })

        # 3. Cash Collections MTD & Cumulative Tax Breakdown
        invoices = db.query(BillingInvoice).all()

        total_gross = sum(float(inv.total_amount or 0.0) for inv in invoices if inv.payment_status == "PAID")
        total_taxable = sum(float(inv.taxable_amount or 0.0) for inv in invoices if inv.payment_status == "PAID")
        total_cgst = sum(float(inv.cgst_amount or 0.0) for inv in invoices if inv.payment_status == "PAID")
        total_sgst = sum(float(inv.sgst_amount or 0.0) for inv in invoices if inv.payment_status == "PAID")
        total_igst = sum(float(inv.igst_amount or 0.0) for inv in invoices if inv.payment_status == "PAID")

        # Cash collected this calendar month
        mtd_invoices = [
            inv for inv in invoices
            if inv.payment_status == "PAID" and inv.created_at and month_start <= (
                inv.created_at if inv.created_at.tzinfo else inv.created_at.replace(tzinfo=timezone.utc)
            ) <= month_end
        ]
        gross_cash_mtd = sum(float(inv.total_amount or 0.0) for inv in mtd_invoices)
        refunds_mtd = sum(float(inv.refund_amount or 0.0) for inv in mtd_invoices)
        net_cash_mtd = max(0.0, gross_cash_mtd - refunds_mtd)

        # 4. Expert Marketplace Collections
        orders = db.query(PaymentOrder).filter(PaymentOrder.payment_status == "PAID").all()
        market_gross = sum(float(o.amount or 0.0) for o in orders)
        market_platform_fee = round(market_gross * 0.20, 2)
        market_expert_escrow = round(market_gross * 0.80, 2)

        # 5. Engine Revenue Calculation
        # Count opening, new, expired, cancelled in current month
        all_subs = db.query(Subscription).all()
        opening = sum(1 for s in all_subs if s.created_at and (
            s.created_at if s.created_at.tzinfo else s.created_at.replace(tzinfo=timezone.utc)
        ) < month_start and s.status in ("ACTIVE", "PAST_DUE"))
        new_subs = sum(1 for s in all_subs if s.created_at and month_start <= (
            s.created_at if s.created_at.tzinfo else s.created_at.replace(tzinfo=timezone.utc)
        ) <= month_end and s.previous_subscription_id is None)
        renewed_subs = sum(1 for s in all_subs if s.created_at and month_start <= (
            s.created_at if s.created_at.tzinfo else s.created_at.replace(tzinfo=timezone.utc)
        ) <= month_end and s.previous_subscription_id is not None)
        expired_subs = sum(1 for s in all_subs if s.status == "EXPIRED" and s.expiry_date and month_start <= (
            s.expiry_date if s.expiry_date.tzinfo else s.expiry_date.replace(tzinfo=timezone.utc)
        ) <= month_end)
        cancelled_subs = sum(1 for s in all_subs if s.cancelled_at and month_start <= (
            s.cancelled_at if s.cancelled_at.tzinfo else s.cancelled_at.replace(tzinfo=timezone.utc)
        ) <= month_end)

        report = self.intel_engine.generate_monthly_revenue_report(
            month_key=month_key,
            active_subscriptions=active_sub_payloads,
            opening_subscribers=opening,
            new_subscribers=new_subs,
            renewed_subscribers=renewed_subs,
            expired_subscribers=expired_subs,
            cancelled_subscribers=cancelled_subs,
            actual_cash_collected=gross_cash_mtd,
            refunds=refunds_mtd,
        )

        # ARPU relative to unique paying parents
        arpu = round(report.monthly_recurring_revenue_mrr / unique_paying_parents_count, 2) if unique_paying_parents_count > 0 else 0.0

        tax_breakdown = TaxLiabilityBreakdownSchema(
            gross_collections=round(total_gross, 2),
            taxable_base=round(total_taxable, 2),
            total_gst_collected=round(total_cgst + total_sgst + total_igst, 2),
            cgst_liability=round(total_cgst, 2),
            sgst_liability=round(total_sgst, 2),
            igst_liability=round(total_igst, 2),
            invoices_issued_count=len([i for i in invoices if i.payment_status == "PAID"]),
        )

        marketplace_breakdown = MarketplaceRevenueBreakdownSchema(
            gross_case_volume=round(market_gross, 2),
            studiqs_platform_share_20pct=market_platform_fee,
            expert_escrow_payout_80pct=market_expert_escrow,
            completed_cases_count=len(orders),
        )

        return ExecutiveMRRKPISummaryResponse(
            calculated_at=now_utc.isoformat(),
            currency="INR",
            normalized_mrr=report.monthly_recurring_revenue_mrr,
            annualized_run_rate_arr=round(report.monthly_recurring_revenue_mrr * 12.0, 2),
            gross_cash_collections_mtd=round(gross_cash_mtd, 2),
            net_cash_collections_mtd=round(net_cash_mtd, 2),
            total_registered_parents=total_registered_parents,
            unique_paying_parents_count=unique_paying_parents_count,
            total_active_child_subscriptions=total_active_child_subscriptions,
            arpu=arpu,
            churn_rate_pct=report.churn_rate_pct,
            renewal_rate_pct=report.renewal_rate_pct,
            plan_breakdown=[
                PlanRevenueBreakdownSchema(
                    plan_id=p.plan_id,
                    active_subscriptions=p.active_subscriptions,
                    normalized_mrr=p.normalized_mrr,
                    percentage_of_mrr=p.percentage_of_mrr,
                )
                for p in report.plan_breakdown
            ],
            duration_breakdown=[
                DurationRevenueBreakdownSchema(
                    duration_label=d.duration_label,
                    duration_months=d.duration_months,
                    active_subscriptions=d.active_subscriptions,
                    normalized_mrr=d.normalized_mrr,
                    total_contract_value=d.total_contract_value,
                )
                for d in report.duration_breakdown
            ],
            tax_breakdown=tax_breakdown,
            expert_marketplace_revenue=marketplace_breakdown,
            blended_net_revenue=round(report.monthly_recurring_revenue_mrr + market_platform_fee, 2),
        )

    def get_monthly_subscriber_report(
        self,
        db: Session,
        month_key: Optional[str] = None,
    ) -> MonthlySubscriberReportResponse:
        """
        Section 25.3 Monthly Subscriber Reporting:
        Allows management to select any month and view complete movement and financials.
        """
        now_utc = datetime.now(timezone.utc)
        target_month = month_key or now_utc.strftime("%Y-%m")
        month_start, month_end = self._parse_month_bounds(target_month)

        all_subs = db.query(Subscription).all()
        invoices = db.query(BillingInvoice).all()

        # Invoices in target month
        month_invoices = [
            inv for inv in invoices
            if inv.created_at and month_start <= (
                inv.created_at if inv.created_at.tzinfo else inv.created_at.replace(tzinfo=timezone.utc)
            ) <= month_end
        ]
        paid_invoices = [inv for inv in month_invoices if inv.payment_status == "PAID"]
        failed_invoices = [inv for inv in month_invoices if inv.payment_status == "FAILED"]

        gross_cash = sum(float(inv.total_amount or 0.0) for inv in paid_invoices)
        refunds = sum(float(inv.refund_amount or 0.0) for inv in paid_invoices)

        # Cohort movements
        opening = sum(1 for s in all_subs if s.created_at and (
            s.created_at if s.created_at.tzinfo else s.created_at.replace(tzinfo=timezone.utc)
        ) < month_start and s.status in ("ACTIVE", "PAST_DUE"))

        new_subs = sum(1 for s in all_subs if s.created_at and month_start <= (
            s.created_at if s.created_at.tzinfo else s.created_at.replace(tzinfo=timezone.utc)
        ) <= month_end and s.previous_subscription_id is None)

        renewed_subs = sum(1 for s in all_subs if s.created_at and month_start <= (
            s.created_at if s.created_at.tzinfo else s.created_at.replace(tzinfo=timezone.utc)
        ) <= month_end and s.previous_subscription_id is not None)

        expired_subs = sum(1 for s in all_subs if s.status == "EXPIRED" and s.expiry_date and month_start <= (
            s.expiry_date if s.expiry_date.tzinfo else s.expiry_date.replace(tzinfo=timezone.utc)
        ) <= month_end)

        cancelled_subs = sum(1 for s in all_subs if s.cancelled_at and month_start <= (
            s.cancelled_at if s.cancelled_at.tzinfo else s.cancelled_at.replace(tzinfo=timezone.utc)
        ) <= month_end)

        # Active subscriptions in target month
        active_in_month = [
            s for s in all_subs
            if s.status == "ACTIVE" or (
                s.created_at and (s.created_at if s.created_at.tzinfo else s.created_at.replace(tzinfo=timezone.utc)) <= month_end and
                s.expiry_date and (s.expiry_date if s.expiry_date.tzinfo else s.expiry_date.replace(tzinfo=timezone.utc)) >= month_start
            )
        ]

        active_payloads: List[Dict[str, Any]] = []
        for sub in active_in_month:
            price = self.pricing_engine.get_price(sub.plan_id, sub.duration_months)
            active_payloads.append({
                "plan_id": sub.plan_id,
                "duration_months": sub.duration_months,
                "price_paid": price,
            })

        report = self.intel_engine.generate_monthly_revenue_report(
            month_key=target_month,
            active_subscriptions=active_payloads,
            opening_subscribers=opening,
            new_subscribers=new_subs,
            renewed_subscribers=renewed_subs,
            expired_subscribers=expired_subs,
            cancelled_subscribers=cancelled_subs,
            actual_cash_collected=gross_cash,
            refunds=refunds,
        )

        return MonthlySubscriberReportResponse(
            month_key=target_month,
            opening_active_subscribers=report.opening_active_subscribers,
            new_subscribers_acquired=report.new_subscribers_acquired,
            renewed_subscribers=report.renewed_subscribers,
            expired_subscribers=report.expired_subscribers,
            cancelled_subscribers=report.cancelled_subscribers,
            closing_active_subscribers=report.closing_active_subscribers,
            gross_cash_collections=report.gross_cash_collections,
            total_refunds=report.total_refunds,
            net_cash_collections=report.net_cash_collections,
            monthly_recurring_revenue_mrr=report.monthly_recurring_revenue_mrr,
            arpu=report.arpu,
            churn_rate_pct=report.churn_rate_pct,
            renewal_rate_pct=report.renewal_rate_pct,
            failed_payments_count=len(failed_invoices),
            plan_breakdown=[
                PlanRevenueBreakdownSchema(
                    plan_id=p.plan_id,
                    active_subscriptions=p.active_subscriptions,
                    normalized_mrr=p.normalized_mrr,
                    percentage_of_mrr=p.percentage_of_mrr,
                )
                for p in report.plan_breakdown
            ],
            duration_breakdown=[
                DurationRevenueBreakdownSchema(
                    duration_label=d.duration_label,
                    duration_months=d.duration_months,
                    active_subscriptions=d.active_subscriptions,
                    normalized_mrr=d.normalized_mrr,
                    total_contract_value=d.total_contract_value,
                )
                for d in report.duration_breakdown
            ],
        )

    def export_monthly_report_csv(self, db: Session, month_key: Optional[str] = None) -> str:
        """
        Generates production-grade CSV financial ledger for executive download.
        """
        report = self.get_monthly_subscriber_report(db=db, month_key=month_key)

        output = io.StringIO()
        writer = csv.writer(output)

        # 1. Header Information
        writer.writerow(["STUDIQS SMARTPARENT - MONTHLY SUBSCRIBER & REVENUE REPORT"])
        writer.writerow(["Reporting Month", report.month_key])
        writer.writerow(["Generated At", datetime.now(timezone.utc).isoformat()])
        writer.writerow(["Currency", "INR"])
        writer.writerow([])

        # 2. Executive Summary KPIs
        writer.writerow(["--- EXECUTIVE FINANCIAL METRICS ---"])
        writer.writerow(["Metric", "Value"])
        writer.writerow(["Normalized MRR (Monthly Recurring Revenue)", f"Rs {report.monthly_recurring_revenue_mrr:,.2f}"])
        writer.writerow(["Annualized Run-Rate (ARR)", f"Rs {report.monthly_recurring_revenue_mrr * 12:,.2f}"])
        writer.writerow(["Gross Cash Collections MTD", f"Rs {report.gross_cash_collections:,.2f}"])
        writer.writerow(["Total Refunds", f"Rs {report.total_refunds:,.2f}"])
        writer.writerow(["Net Cash Collections MTD", f"Rs {report.net_cash_collections:,.2f}"])
        writer.writerow(["Average Revenue Per User (ARPU)", f"Rs {report.arpu:,.2f}"])
        writer.writerow(["Subscriber Churn Rate", f"{report.churn_rate_pct:.2f}%"])
        writer.writerow(["Subscriber Renewal Rate", f"{report.renewal_rate_pct:.2f}%"])
        writer.writerow(["Failed Payment Attempts", report.failed_payments_count])
        writer.writerow([])

        # 3. Subscriber Cohort Movement
        writer.writerow(["--- SUBSCRIBER COHORT MOVEMENT ---"])
        writer.writerow(["Stage", "Count"])
        writer.writerow(["Opening Active Subscribers", report.opening_active_subscribers])
        writer.writerow(["New Subscribers Acquired", report.new_subscribers_acquired])
        writer.writerow(["Renewed Subscribers", report.renewed_subscribers])
        writer.writerow(["Expired Subscribers", report.expired_subscribers])
        writer.writerow(["Cancelled Subscribers", report.cancelled_subscribers])
        writer.writerow(["Closing Active Subscribers", report.closing_active_subscribers])
        writer.writerow([])

        # 4. Plan Breakdown
        writer.writerow(["--- PLAN DISTRIBUTION BREAKDOWN ---"])
        writer.writerow(["Plan ID", "Active Subscriptions", "Normalized MRR (Rs)", "MRR Share %"])
        for p in report.plan_breakdown:
            writer.writerow([p.plan_id, p.active_subscriptions, f"{p.normalized_mrr:,.2f}", f"{p.percentage_of_mrr:.1f}%"])
        writer.writerow([])

        # 5. Duration Breakdown
        writer.writerow(["--- DURATION DISTRIBUTION BREAKDOWN ---"])
        writer.writerow(["Duration Label", "Months", "Active Subscriptions", "Normalized MRR (Rs)", "Total Contract Value (Rs)"])
        for d in report.duration_breakdown:
            writer.writerow([d.duration_label, d.duration_months, d.active_subscriptions, f"{d.normalized_mrr:,.2f}", f"{d.total_contract_value:,.2f}"])

        return output.getvalue()


admin_revenue_service = AdminRevenueService()

