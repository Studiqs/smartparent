"""
STUDIQS® SmartParent™ (v6.3) - Subscription & Billing Service Facade
=============================================================================
Module: src.smartparent.services.subscription_service

Provides clean, enterprise service methods for the API layer:
  - Plan catalog discovery & pricing quotes.
  - Indian GST 18% tax calculation.
  - Calendar-month validity calculation and status evaluation.
  - Pre-flight entitlement checks with soft-warning thresholds.
  - Daily-prorated plan upgrades and duration extension.
  - Management subscriber intelligence & MRR reports.
  - GST Tax Invoice generation.
=============================================================================
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from src.smartparent.engines.section_10_subscription_billing import (
    SubscriptionPricingEngine,
    CalendarValidityEngine,
    EntitlementQuotaEngine,
    SubscriberIntelligenceEngine,
    InvoiceGeneratorEngine,
    CheckoutQuoteSchema,
    PlanCatalogSummarySchema,
    SubscriptionStatusEvaluationSchema,
    RenewalReminderScheduleItem,
    EntitlementDecisionSchema,
    QuotaUsageOverviewSchema,
    UpgradeProrationQuoteSchema,
    MonthlyRevenueReportSchema,
    TaxInvoiceSchema,
)


class SubscriptionService:
    """
    Unified Subscription & Billing Service Facade.
    Connects API routers and background workers to Section 10 & 24/25 engines.
    """

    def __init__(self):
        self.pricing_engine = SubscriptionPricingEngine()
        self.validity_engine = CalendarValidityEngine()
        self.quota_engine = EntitlementQuotaEngine()
        self.intelligence_engine = SubscriberIntelligenceEngine()
        self.invoice_engine = InvoiceGeneratorEngine()

    # -------------------------------------------------------------------------
    # 1. Catalog & Checkout Quotes
    # -------------------------------------------------------------------------

    def get_plan_catalog(self, pricing_model: str = "PROPOSED") -> List[PlanCatalogSummarySchema]:
        """Returns customer-facing plan catalog with features and duration prices."""
        return self.pricing_engine.get_plan_catalog(pricing_model=pricing_model)

    def calculate_checkout_quote(
        self,
        plan_id: str,
        duration_months: int,
        state: str = "Tamil Nadu",
        pricing_model: str = "PROPOSED",
    ) -> CheckoutQuoteSchema:
        """Calculates exact gross price, base taxable value, GST breakdown, and savings."""
        return self.pricing_engine.calculate_checkout_quote(
            plan_id=plan_id,
            duration_months=duration_months,
            state=state,
            pricing_model=pricing_model,
        )

    # -------------------------------------------------------------------------
    # 2. Calendar Validity & Status
    # -------------------------------------------------------------------------

    def calculate_subscription_expiry(self, start_date: datetime, duration_months: int) -> datetime:
        """Calculates exact calendar-month expiry without drift."""
        return self.validity_engine.calculate_calendar_expiry(start_date, duration_months)

    def evaluate_status(
        self,
        expiry_date: datetime,
        is_paid: bool = True,
        is_trial: bool = False,
        is_cancelled: bool = False,
        current_time: Optional[datetime] = None,
    ) -> SubscriptionStatusEvaluationSchema:
        """Evaluates live status: ACTIVE, EXPIRING_SOON, EXPIRED, CANCELLED_ACTIVE, etc."""
        return self.validity_engine.evaluate_status(
            expiry_date=expiry_date,
            is_paid=is_paid,
            is_trial=is_trial,
            is_cancelled=is_cancelled,
            current_time=current_time,
        )

    def generate_renewal_reminder_schedule(
        self,
        start_date: datetime,
        expiry_date: datetime,
    ) -> List[RenewalReminderScheduleItem]:
        """Generates 4-stage reminder schedule (7d, 3d, 1d, on-expiry)."""
        return self.validity_engine.generate_renewal_reminder_schedule(start_date, expiry_date)

    # -------------------------------------------------------------------------
    # 3. Entitlement & Quota Verification
    # -------------------------------------------------------------------------

    def check_entitlement(
        self,
        action_type: str,
        plan_id: str,
        current_usage: int,
        is_active: bool = True,
    ) -> EntitlementDecisionSchema:
        """Pre-flight check before performing a metered action."""
        return self.quota_engine.check_entitlement(
            action_type=action_type,
            plan_id=plan_id,
            current_usage=current_usage,
            is_active=is_active,
        )

    def get_quota_dashboard(
        self,
        plan_id: str,
        month_key: str,
        usage_data: Dict[str, int],
    ) -> QuotaUsageOverviewSchema:
        """Returns 5-boundary usage overview for parent dashboard."""
        return self.quota_engine.get_quota_overview(plan_id, month_key, usage_data)

    def calculate_upgrade_proration(
        self,
        current_plan_id: str,
        current_price_paid: float,
        start_date: datetime,
        expiry_date: datetime,
        target_plan_id: str,
        target_duration_months: int = 1,
        pricing_model: str = "PROPOSED",
        current_time: Optional[datetime] = None,
    ) -> UpgradeProrationQuoteSchema:
        """Calculates fair daily-prorated credit and net payable today."""
        return self.quota_engine.calculate_upgrade_proration(
            current_plan_id=current_plan_id,
            current_price_paid=current_price_paid,
            start_date=start_date,
            expiry_date=expiry_date,
            target_plan_id=target_plan_id,
            target_duration_months=target_duration_months,
            pricing_model=pricing_model,
            current_time=current_time,
        )

    # -------------------------------------------------------------------------
    # 4. Invoices & Receipts
    # -------------------------------------------------------------------------

    def create_tax_invoice(
        self,
        sequence_number: int,
        subscriber_id: str,
        customer_name: str,
        customer_phone: str,
        customer_state: str,
        quote: CheckoutQuoteSchema,
        billing_start: datetime,
        billing_end: datetime,
        subscription_id: Optional[str] = None,
        payment_ref: Optional[str] = None,
        gateway_order_id: Optional[str] = None,
    ) -> TaxInvoiceSchema:
        """Generates itemized GST Tax Invoice record."""
        return self.invoice_engine.create_invoice(
            sequence_number=sequence_number,
            subscriber_id=subscriber_id,
            customer_name=customer_name,
            customer_phone=customer_phone,
            customer_state=customer_state,
            quote=quote,
            billing_start=billing_start,
            billing_end=billing_end,
            subscription_id=subscription_id,
            payment_ref=payment_ref,
            gateway_order_id=gateway_order_id,
        )

    # -------------------------------------------------------------------------
    # 5. Management Subscriber Intelligence & MRR
    # -------------------------------------------------------------------------

    def generate_monthly_revenue_report(
        self,
        month_key: str,
        active_subscriptions: List[Dict[str, Any]],
        opening_subscribers: int,
        new_subscribers: int,
        renewed_subscribers: int,
        expired_subscribers: int,
        cancelled_subscribers: int,
        actual_cash_collected: float,
        refunds: float = 0.0,
    ) -> MonthlyRevenueReportSchema:
        """Generates audited MRR, churn, and cohort breakdown report."""
        return self.intelligence_engine.generate_monthly_revenue_report(
            month_key=month_key,
            active_subscriptions=active_subscriptions,
            opening_subscribers=opening_subscribers,
            new_subscribers=new_subscribers,
            renewed_subscribers=renewed_subscribers,
            expired_subscribers=expired_subscribers,
            cancelled_subscribers=cancelled_subscribers,
            actual_cash_collected=actual_cash_collected,
            refunds=refunds,
        )
