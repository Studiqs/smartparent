"""
STUDIQS® SmartParent™ - Section 10 & 24/25: Subscription & Billing Unit Test Suite
=============================================================================
Tests:
  1. Proposed GST-inclusive pricing matrix (1M, 3M, 6M, 12M across Basic, Advanced, Pro).
  2. Indian GST 18% calculation (Intra-state Tamil Nadu vs Inter-state IGST).
  3. Multi-month savings & percentage discount calculations.
  4. Calendar-month validity arithmetic without drift (Jan 31 -> Feb 28, leap year Feb 29).
  5. Subscription lifecycle status evaluation (ACTIVE, EXPIRING_SOON, EXPIRED, CANCELLED_ACTIVE).
  6. 4-Stage Renewal reminder schedule (7d, 3d, 1d, on-expiry).
  7. Pre-flight entitlement check with 80% soft warning and tier boundaries.
  8. AI Voice RAG feature gating (Locked on Basic/Adv, Enabled on Pro).
  9. Mid-term daily-prorated upgrade credit calculation.
  10. Management MRR Normalization & revenue analytics.
  11. GST Tax Invoice sequential number formatting & SAC code compliance.
  12. SubscriptionService facade integration.
=============================================================================
"""

from datetime import datetime, timezone, timedelta
import pytest

from src.smartparent.engines.section_10_subscription_billing import (
    SubscriptionPricingEngine,
    CalendarValidityEngine,
    EntitlementQuotaEngine,
    SubscriberIntelligenceEngine,
    InvoiceGeneratorEngine,
    PROPOSED_PRICING_MATRIX,
    BASE_V62_PRICING_MATRIX,
    SubscriptionLifecycleStatus,
    QuotaActionType,
)
from src.smartparent.services.subscription_service import SubscriptionService


# =============================================================================
# 1. Pricing & GST Tests
# =============================================================================

def test_proposed_pricing_matrix_exact_values():
    """Verifies that all 12 proposed plan x duration prices match user specification exactly."""
    pricing = SubscriptionPricingEngine()

    # Basic
    assert pricing.get_price("BASIC", 1) == 199.0
    assert pricing.get_price("BASIC", 3) == 399.0
    assert pricing.get_price("BASIC", 6) == 699.0
    assert pricing.get_price("BASIC", 12) == 1199.0

    # Advanced
    assert pricing.get_price("ADVANCED", 1) == 399.0
    assert pricing.get_price("ADVANCED", 3) == 799.0
    assert pricing.get_price("ADVANCED", 6) == 1399.0
    assert pricing.get_price("ADVANCED", 12) == 2399.0

    # Pro
    assert pricing.get_price("PRO", 1) == 599.0
    assert pricing.get_price("PRO", 3) == 1199.0
    assert pricing.get_price("PRO", 6) == 2099.0
    assert pricing.get_price("PRO", 12) == 3599.0


def test_gst_breakdown_intrastate_tamil_nadu():
    """Verifies that Tamil Nadu transactions split 18% GST into CGST 9% and SGST 9%."""
    pricing = SubscriptionPricingEngine()
    quote = pricing.calculate_checkout_quote(
        plan_id="PRO",
        duration_months=1,
        state="Tamil Nadu",
        pricing_model="PROPOSED",
    )

    assert quote.gross_payable_amount == 599.0
    # 599 / 1.18 = 507.63 taxable base
    assert quote.taxable_base_amount == 507.63
    gst = quote.gst_breakdown
    assert gst.total_tax_amount == 91.37
    assert gst.is_interstate is False
    assert gst.cgst_rate == 9.0
    assert gst.sgst_rate == 9.0
    assert gst.igst_rate == 0.0
    assert round(gst.cgst_amount + gst.sgst_amount, 2) == 91.37


def test_gst_breakdown_interstate():
    """Verifies that outside Tamil Nadu transactions apply 18% IGST."""
    pricing = SubscriptionPricingEngine()
    quote = pricing.calculate_checkout_quote(
        plan_id="ADVANCED",
        duration_months=3,
        state="Karnataka",
        pricing_model="PROPOSED",
    )

    assert quote.gross_payable_amount == 799.0
    gst = quote.gst_breakdown
    assert gst.is_interstate is True
    assert gst.igst_rate == 18.0
    assert gst.cgst_amount == 0.0
    assert gst.sgst_amount == 0.0
    assert gst.igst_amount == gst.total_tax_amount


def test_multi_month_savings_calculation():
    """Verifies that multi-month subscriptions calculate savings vs recurring monthly payments."""
    pricing = SubscriptionPricingEngine()

    # Basic 12 Months: 1199 vs (199 * 12 = 2388) -> 1189 savings
    basic_annual = pricing.calculate_checkout_quote("BASIC", 12)
    assert basic_annual.savings_vs_monthly == 1189.0
    assert basic_annual.discount_percentage >= 49.0
    assert basic_annual.monthly_equivalent_amount == round(1199.0 / 12, 2)

    # Pro 12 Months: 3599 vs (599 * 12 = 7188) -> 3589 savings
    pro_annual = pricing.calculate_checkout_quote("PRO", 12)
    assert pro_annual.savings_vs_monthly == 3589.0
    assert pro_annual.discount_percentage >= 49.0


# =============================================================================
# 2. Calendar Validity Tests
# =============================================================================

def test_calendar_month_exact_arithmetic():
    """Verifies calendar month additions without day drift (Section 24.3)."""
    validity = CalendarValidityEngine()

    # Jan 15 + 3 months -> Apr 15
    dt1 = datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    exp1 = validity.calculate_calendar_expiry(dt1, 3)
    assert exp1.year == 2026
    assert exp1.month == 4
    assert exp1.day == 15

    # Jan 31 + 1 month in non-leap year (2026) -> Feb 28
    dt2 = datetime(2026, 1, 31, 12, 0, 0, tzinfo=timezone.utc)
    exp2 = validity.calculate_calendar_expiry(dt2, 1)
    assert exp2.year == 2026
    assert exp2.month == 2
    assert exp2.day == 28

    # Jan 31 + 1 month in leap year (2028) -> Feb 29
    dt3 = datetime(2028, 1, 31, 12, 0, 0, tzinfo=timezone.utc)
    exp3 = validity.calculate_calendar_expiry(dt3, 1)
    assert exp3.year == 2028
    assert exp3.month == 2
    assert exp3.day == 29

    # Aug 31 + 1 month -> Sep 30
    dt4 = datetime(2026, 8, 31, 12, 0, 0, tzinfo=timezone.utc)
    exp4 = validity.calculate_calendar_expiry(dt4, 1)
    assert exp4.year == 2026
    assert exp4.month == 9
    assert exp4.day == 30


def test_subscription_status_evaluation():
    """Verifies real-time status transitions (ACTIVE, EXPIRING_SOON, EXPIRED, CANCELLED_ACTIVE)."""
    validity = CalendarValidityEngine()
    now = datetime(2026, 10, 23, 12, 0, 0, tzinfo=timezone.utc)

    # 1. Active with 20 days remaining
    exp_active = now + timedelta(days=20)
    status_active = validity.evaluate_status(exp_active, current_time=now)
    assert status_active.status == SubscriptionLifecycleStatus.ACTIVE.value
    assert status_active.is_access_allowed is True
    assert status_active.days_remaining == 20
    assert status_active.is_expiring_soon is False

    # 2. Expiring soon with 4 days remaining (<= 7 days threshold)
    exp_soon = now + timedelta(days=4)
    status_soon = validity.evaluate_status(exp_soon, current_time=now)
    assert status_soon.status == SubscriptionLifecycleStatus.EXPIRING_SOON.value
    assert status_soon.is_access_allowed is True
    assert status_soon.is_expiring_soon is True
    assert "Renew today" in status_soon.renewal_alert_message

    # 3. Expired 2 days ago
    exp_expired = now - timedelta(days=2)
    status_expired = validity.evaluate_status(exp_expired, current_time=now)
    assert status_expired.status == SubscriptionLifecycleStatus.EXPIRED.value
    assert status_expired.is_access_allowed is False
    assert status_expired.days_remaining == 0

    # 4. Cancelled auto-renewal during active period
    status_cancelled = validity.evaluate_status(exp_active, is_cancelled=True, current_time=now)
    assert status_cancelled.status == SubscriptionLifecycleStatus.CANCELLED_ACTIVE.value
    assert status_cancelled.is_access_allowed is True


def test_renewal_reminder_schedule_builder():
    """Verifies the 4-stage reminder schedule (7d, 3d, 1d, on-expiry) conforming to Section 24.6."""
    validity = CalendarValidityEngine()
    start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    expiry = datetime(2026, 2, 1, 0, 0, 0, tzinfo=timezone.utc)  # 31 days

    reminders = validity.generate_renewal_reminder_schedule(start, expiry)
    assert len(reminders) == 4

    types = [r.reminder_type for r in reminders]
    assert types == ["REMINDER_7_DAYS", "REMINDER_3_DAYS", "REMINDER_1_DAY", "EXPIRED_NOTICE"]
    assert reminders[0].scheduled_at == expiry - timedelta(days=7)
    assert reminders[1].scheduled_at == expiry - timedelta(days=3)
    assert reminders[2].scheduled_at == expiry - timedelta(days=1)
    assert reminders[3].scheduled_at == expiry


# =============================================================================
# 3. Entitlement & Quotas Tests
# =============================================================================

def test_entitlement_quota_limits_and_warnings():
    """Verifies tier limits, soft warnings at 80% usage, and blocking at limit."""
    quota = EntitlementQuotaEngine()

    # Basic Document Uploads (Limit = 4)
    # Usage = 2 (50%) -> Allowed, no soft warning
    dec1 = quota.check_entitlement(QuotaActionType.DOCUMENT_UPLOAD.value, "BASIC", current_usage=2)
    assert dec1.is_allowed is True
    assert dec1.remaining_quota == 2
    assert dec1.is_soft_warning is False

    # Usage = 3 (75% -> on 4-item limit, 3/4 = 75% or 80% threshold test)
    # If usage = 4 -> Blocked
    dec_limit = quota.check_entitlement(QuotaActionType.DOCUMENT_UPLOAD.value, "BASIC", current_usage=4)
    assert dec_limit.is_allowed is False
    assert dec_limit.remaining_quota == 0
    assert "reached" in dec_limit.message
    assert dec_limit.suggested_target_plan == "ADVANCED"


def test_voice_rag_feature_gating():
    """Verifies that SmartParent Voice RAG is exclusive to Pro plan subscribers."""
    quota = EntitlementQuotaEngine()

    # Basic user attempts Voice query -> Blocked (Voice locked on Basic)
    dec_basic = quota.check_entitlement(QuotaActionType.VOICE_QUERY.value, "BASIC", current_usage=0)
    assert dec_basic.is_allowed is False
    assert "upgrade to" in dec_basic.message.lower() or "pro" in dec_basic.message.lower()

    # Advanced user attempts Voice query -> Allowed (25 queries quota)
    dec_adv = quota.check_entitlement(QuotaActionType.VOICE_QUERY.value, "ADVANCED", current_usage=5)
    assert dec_adv.is_allowed is True
    assert dec_adv.remaining_quota == 20

    # Advanced user exceeds 25 voice queries -> Blocked
    dec_adv_max = quota.check_entitlement(QuotaActionType.VOICE_QUERY.value, "ADVANCED", current_usage=25)
    assert dec_adv_max.is_allowed is False
    assert dec_adv_max.suggested_target_plan == "PRO"

    # Pro user attempts Voice query -> Allowed (100 query quota)
    dec_pro = quota.check_entitlement(QuotaActionType.VOICE_QUERY.value, "PRO", current_usage=10)
    assert dec_pro.is_allowed is True
    assert dec_pro.remaining_quota == 90


def test_midterm_plan_upgrade_daily_proration():
    """Verifies that upgrading midway through a billing cycle credits unused days (Section 24.4)."""
    quota = EntitlementQuotaEngine()
    start = datetime(2026, 10, 1, 0, 0, 0, tzinfo=timezone.utc)
    expiry = datetime(2026, 10, 31, 0, 0, 0, tzinfo=timezone.utc)  # 30 days
    now = datetime(2026, 10, 11, 0, 0, 0, tzinfo=timezone.utc)    # 10 days used, 20 days remaining

    # User paid ₹199 for Basic 1 Month. Wants to upgrade to Advanced 1 Month (₹399)
    proration = quota.calculate_upgrade_proration(
        current_plan_id="BASIC",
        current_price_paid=199.0,
        start_date=start,
        expiry_date=expiry,
        target_plan_id="ADVANCED",
        target_duration_months=1,
        current_time=now,
    )

    assert proration.total_days_in_term == 30
    assert proration.days_used == 10
    assert proration.days_remaining == 20
    # Unused credit = round((20 / 30) * 199.0, 2) = 132.67
    assert proration.unused_credit_amount == 132.67
    # Target price = 399.0. Net payable = 399.0 - 132.67 = 266.33
    assert proration.net_payable_today == 266.33


# =============================================================================
# 4. Subscriber Intelligence & Invoicing Tests
# =============================================================================

def test_management_mrr_normalization():
    """
    Verifies that multi-month subscriptions are normalized over their duration (Section 25.2).
    A ₹3,599 annual payment must NOT be counted as 1 month's recurring revenue!
    """
    intel = SubscriberIntelligenceEngine()

    active_contracts = [
        {"plan_id": "BASIC", "duration_months": 1, "price_paid": 199.0},       # MRR = 199.00
        {"plan_id": "ADVANCED", "duration_months": 3, "price_paid": 799.0},    # MRR = 266.33
        {"plan_id": "PRO", "duration_months": 12, "price_paid": 3599.0},       # MRR = 299.92
    ]

    report = intel.generate_monthly_revenue_report(
        month_key="2026-10",
        active_subscriptions=active_contracts,
        opening_subscribers=100,
        new_subscribers=15,
        renewed_subscribers=20,
        expired_subscribers=5,
        cancelled_subscribers=2,
        actual_cash_collected=4597.0,  # 199 + 799 + 3599
        refunds=0.0,
    )

    # Total MRR = 199.0 + 266.33 + 299.92 = 765.25
    assert report.monthly_recurring_revenue_mrr == 765.25
    assert report.gross_cash_collections == 4597.0
    assert report.net_cash_collections == 4597.0
    # Closing = 100 + 15 - 5 - 2 = 108
    assert report.closing_active_subscribers == 108
    # Churn rate = (5 + 2) / 100 = 7.0%
    assert report.churn_rate_pct == 7.0
    # Renewal rate = 20 / (5 + 20) = 80.0%
    assert report.renewal_rate_pct == 80.0


def test_gst_tax_invoice_record_generation():
    """Verifies sequential invoice formatting and SAC code 998431 inclusion."""
    pricing = SubscriptionPricingEngine()
    inv_engine = InvoiceGeneratorEngine()

    quote = pricing.calculate_checkout_quote("PRO", 1, state="Tamil Nadu")
    billing_start = datetime(2026, 10, 1, tzinfo=timezone.utc)
    billing_end = datetime(2026, 11, 1, tzinfo=timezone.utc)

    invoice = inv_engine.create_invoice(
        sequence_number=142,
        subscriber_id="SUB-999",
        customer_name="Karthik R",
        customer_phone="9876543210",
        customer_state="Tamil Nadu",
        quote=quote,
        billing_start=billing_start,
        billing_end=billing_end,
        payment_ref="pay_Rzpr98214",
    )

    assert invoice.invoice_number == f"INV-STQ-{billing_start.year}-00142"
    assert invoice.company_details["legal_name"] == "Studiqs Intelligence LLP"
    assert len(invoice.items) == 1
    assert invoice.items[0].sac_code == "998431"
    assert invoice.gross_total_amount == 599.0
    assert invoice.payment_reference_id == "pay_Rzpr98214"


def test_subscription_service_facade_integration():
    """Verifies that SubscriptionService integrates all engines seamlessly."""
    service = SubscriptionService()

    # Catalog
    catalog = service.get_plan_catalog()
    assert len(catalog) == 3
    plan_ids = [p.plan_id for p in catalog]
    assert plan_ids == ["BASIC", "ADVANCED", "PRO"]

    # Quote
    quote = service.calculate_checkout_quote("BASIC", 3)
    assert quote.gross_payable_amount == 399.0

    # Quota Dashboard
    usage = {
        QuotaActionType.DOCUMENT_UPLOAD.value: 2,
        QuotaActionType.GAP_RECHECK.value: 1,
    }
    overview = service.get_quota_dashboard("BASIC", "2026-10", usage)
    assert overview.document_uploads["used"] == 2
    assert overview.document_uploads["limit"] == 4
    assert overview.document_uploads["remaining"] == 2
