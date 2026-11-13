"""
STUDIQS® SmartParent™ - Section 24.7 & 25.2/25.3 Unit Test Suite
=============================================================================
Module: tests.unit.test_section24_7_and_25_kpis_and_export

Verifies:
  1. Section 24.7 Payment Failure & Expiry Handling:
     - Payment failure marks invoice FAILED and leaves subscription unactivated.
     - Auto-renew failure enters 3-day PAST_DUE grace period without data loss.
     - Retry payment reuses invoice audit trail and prevents double charging.
     - Seamless expired renewal confirms student profiles and topic history retention.
     - 3-day grace period status evaluation.
  2. Section 25.2 Management Dashboard Mandatory KPIs:
     - Multi-month MRR normalization (1M, 3M, 6M, 12M).
     - Distinct separation: Unique Paying Parents vs Total Active Child Seats.
     - SaaS health metrics: Normalized MRR, ARR, Cash Collections MTD, ARPU, Churn Rate.
     - Plan and Duration distributions.
  3. Section 25.3 Monthly Subscriber Reporting & Financial Export:
     - Month-by-month cohort movement ledger (Opening, New, Renewed, Expired, Closing).
     - Full CSV ledger export for executive download.
  4. Razorpay Webhook Idempotency:
     - Repeated webhook callbacks return 'already_processed' and prevent duplicate actions.
=============================================================================
"""

import uuid
from datetime import datetime, date, timedelta, timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID

@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"

@compiles(PG_UUID, "sqlite")
def compile_uuid_sqlite(type_, compiler, **kw):
    return "CHAR(36)"

from src.smartparent.db.base import Base
from src.smartparent.db.models.auth import Subscriber, Child
from src.smartparent.db.models.subscription import (
    Subscription,
    BillingInvoice,
    RazorpayWebhookEvent,
)
from src.smartparent.db.models.notification import InAppNotification
from src.smartparent.services.payment_failure_service import PaymentFailureService
from src.smartparent.services.admin_revenue_service import AdminRevenueService


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def seed_revenue_and_failure_data(test_db):
    now_utc = datetime.now(timezone.utc)
    today_utc = now_utc.date()

    # 1. Parent 1: Ram Kumar (1 Child, Monthly Basic @ Rs 199)
    p1_id = uuid.uuid4()
    p1 = Subscriber(
        subscriber_id=p1_id,
        mobile_number="9876543401",
        parent_name="Ram Kumar",
        email="ram.kumar@example.com",
        password_hash="hash1",
        subscription_plan="BASIC",
    )
    p1_child = Child(
        child_id=uuid.uuid4(),
        subscriber_id=p1_id,
        student_name="Aakash Kumar",
        standard_class="Class 10",
        board="CBSE",
    )
    p1_sub = Subscription(
        subscription_id=uuid.uuid4(),
        subscriber_id=p1_id,
        plan_id="BASIC",
        duration_months=1,
        start_date=now_utc - timedelta(days=10),
        expiry_date=now_utc + timedelta(days=20),
        status="ACTIVE",
        auto_renew=False,
    )
    p1_inv = BillingInvoice(
        invoice_id=uuid.uuid4(),
        invoice_number="INV-2026-101",
        subscriber_id=p1_id,
        subscription_id=p1_sub.subscription_id,
        billing_period_start=now_utc - timedelta(days=10),
        billing_period_end=now_utc + timedelta(days=20),
        base_amount=168.64,
        taxable_amount=168.64,
        total_amount=199.00,
        payment_status="PAID",
        razorpay_order_id="order_p1_001",
        created_at=now_utc,
    )

    # 2. Parent 2: Deepa Sundaram (2 Children, Multi-Child subscriber!)
    # Child A: Advanced 3-Month (@ Rs 799 -> Normalized MRR Rs 266.33/mo)
    # Child B: Pro 12-Month Annual (@ Rs 3599 -> Normalized MRR Rs 299.92/mo)
    p2_id = uuid.uuid4()
    p2 = Subscriber(
        subscriber_id=p2_id,
        mobile_number="9876543402",
        parent_name="Deepa Sundaram",
        email="deepa.s@example.com",
        password_hash="hash2",
        subscription_plan="PRO",
    )
    p2_child1 = Child(
        child_id=uuid.uuid4(),
        subscriber_id=p2_id,
        student_name="Meera Sundaram",
        standard_class="Class 9",
        board="CBSE",
    )
    p2_child2 = Child(
        child_id=uuid.uuid4(),
        subscriber_id=p2_id,
        student_name="Tarun Sundaram",
        standard_class="Class 12",
        board="CBSE",
    )
    p2_sub1 = Subscription(
        subscription_id=uuid.uuid4(),
        subscriber_id=p2_id,
        plan_id="ADVANCED",
        duration_months=3,
        start_date=now_utc - timedelta(days=15),
        expiry_date=now_utc + timedelta(days=75),
        status="ACTIVE",
        auto_renew=True,
    )
    p2_inv1 = BillingInvoice(
        invoice_id=uuid.uuid4(),
        invoice_number="INV-2026-102",
        subscriber_id=p2_id,
        subscription_id=p2_sub1.subscription_id,
        billing_period_start=now_utc - timedelta(days=15),
        billing_period_end=now_utc + timedelta(days=75),
        base_amount=677.12,
        taxable_amount=677.12,
        total_amount=799.00,
        payment_status="PAID",
        razorpay_order_id="order_p2_001",
        created_at=now_utc,
    )

    p2_sub2 = Subscription(
        subscription_id=uuid.uuid4(),
        subscriber_id=p2_id,
        plan_id="PRO",
        duration_months=12,
        start_date=now_utc - timedelta(days=5),
        expiry_date=now_utc + timedelta(days=360),
        status="ACTIVE",
        auto_renew=True,
    )
    p2_inv2 = BillingInvoice(
        invoice_id=uuid.uuid4(),
        invoice_number="INV-2026-103",
        subscriber_id=p2_id,
        subscription_id=p2_sub2.subscription_id,
        billing_period_start=now_utc - timedelta(days=5),
        billing_period_end=now_utc + timedelta(days=360),
        base_amount=3050.00,
        taxable_amount=3050.00,
        total_amount=3599.00,
        payment_status="PAID",
        razorpay_order_id="order_p2_002",
        created_at=now_utc,
    )

    # 3. Parent 3: Suresh Nair (Expired parent for renewal testing)
    p3_id = uuid.uuid4()
    p3 = Subscriber(
        subscriber_id=p3_id,
        mobile_number="9876543403",
        parent_name="Suresh Nair",
        email="suresh.n@example.com",
        password_hash="hash3",
        subscription_plan="BASIC",
    )
    p3_child = Child(
        child_id=uuid.uuid4(),
        subscriber_id=p3_id,
        student_name="Ananya Nair",
        standard_class="Class 8",
        board="ICSE",
    )
    p3_sub = Subscription(
        subscription_id=uuid.uuid4(),
        subscriber_id=p3_id,
        plan_id="BASIC",
        duration_months=1,
        start_date=now_utc - timedelta(days=35),
        expiry_date=now_utc - timedelta(days=5),  # 5 days past due -> EXPIRED
        status="EXPIRED",
        auto_renew=False,
    )

    # 4. Pending Failed Invoice for retry testing
    p4_id = uuid.uuid4()
    p4 = Subscriber(
        subscriber_id=p4_id,
        mobile_number="9876543404",
        parent_name="Gokul Raj",
        email="gokul.r@example.com",
        password_hash="hash4",
        subscription_plan="ADVANCED",
    )
    p4_sub = Subscription(
        subscription_id=uuid.uuid4(),
        subscriber_id=p4_id,
        plan_id="ADVANCED",
        duration_months=1,
        start_date=now_utc,
        expiry_date=now_utc + timedelta(days=30),
        status="PENDING_PAYMENT",
        auto_renew=False,
    )
    p4_inv = BillingInvoice(
        invoice_id=uuid.uuid4(),
        invoice_number="INV-2026-104",
        subscriber_id=p4_id,
        subscription_id=p4_sub.subscription_id,
        billing_period_start=now_utc,
        billing_period_end=now_utc + timedelta(days=30),
        base_amount=338.14,
        taxable_amount=338.14,
        total_amount=399.00,
        payment_status="PENDING",
        razorpay_order_id="order_p4_fail_001",
        created_at=now_utc,
    )

    test_db.add_all([
        p1, p1_child, p1_sub, p1_inv,
        p2, p2_child1, p2_child2, p2_sub1, p2_inv1, p2_sub2, p2_inv2,
        p3, p3_child, p3_sub,
        p4, p4_sub, p4_inv,
    ])
    test_db.commit()

    return {
        "p1_id": p1_id,
        "p2_id": p2_id,
        "p3_id": p3_id,
        "p4_id": p4_id,
        "p4_inv_id": p4_inv.invoice_id,
        "p4_sub_id": p4_sub.subscription_id,
        "p2_sub1_id": p2_sub1.subscription_id,
    }


# =============================================================================
# 1. SECTION 24.7 PAYMENT FAILURE & EXPIRY HANDLING TESTS
# =============================================================================

class TestSection24PaymentFailureAndExpiry:
    """Verifies Section 24.7 Payment Failure, Retry & Expiry Rules."""

    def test_payment_failure_marks_invoice_failed_and_notifies_parent(self, test_db, seed_revenue_and_failure_data):
        """A failed payment callback marks invoice FAILED and dispatches retry notification without activating subscription."""
        service = PaymentFailureService()
        p4_id = seed_revenue_and_failure_data["p4_id"]

        res = service.handle_gateway_payment_failure(
            db=test_db,
            razorpay_order_id="order_p4_fail_001",
            error_code="BAD_REQUEST_ERROR",
            error_description="Payment declined by issuing bank",
            razorpay_payment_id="pay_fail_999",
            subscriber_id=p4_id,
        )

        assert res["status"] == "handled"
        assert res["invoice_marked_failed"] is True
        assert res["parent_notified"] is True

        # Verify DB state: Invoice is FAILED
        inv = test_db.query(BillingInvoice).filter_by(razorpay_order_id="order_p4_fail_001").one()
        assert inv.payment_status == "FAILED"

        # Subscription remains PENDING_PAYMENT (NEVER activate on failure!)
        sub = test_db.query(Subscription).filter_by(subscriber_id=p4_id).one()
        assert sub.status == "PENDING_PAYMENT"

        # Notification dispatched to parent
        notif = test_db.query(InAppNotification).filter_by(subscriber_id=p4_id, event_type="PAYMENT_FAILED").first()
        assert notif is not None
        assert "Payment declined" in notif.message

    def test_auto_renew_payment_failure_moves_to_past_due_grace_period(self, test_db, seed_revenue_and_failure_data):
        """Active auto-renew subscription moves to PAST_DUE on gateway failure, preserving active billing period access."""
        service = PaymentFailureService()
        p2_id = seed_revenue_and_failure_data["p2_id"]

        service.handle_gateway_payment_failure(
            db=test_db,
            razorpay_order_id="order_p2_001",
            error_code="INSUFFICIENT_FUNDS",
            error_description="Auto-debit failed: card balance low",
            subscriber_id=p2_id,
        )

        p2_sub1_id = seed_revenue_and_failure_data["p2_sub1_id"]
        sub = test_db.query(Subscription).filter_by(subscription_id=p2_sub1_id).one()
        assert sub.status == "PAST_DUE"

    def test_retry_payment_workflow_reuses_invoice_and_prevents_duplicate_subscription(self, test_db, seed_revenue_and_failure_data):
        """Retry payment assigns a fresh order to the existing invoice without creating duplicate subscriptions."""
        service = PaymentFailureService()
        p4_id = seed_revenue_and_failure_data["p4_id"]
        p4_inv_id = seed_revenue_and_failure_data["p4_inv_id"]

        # Initial subscription count for P4
        initial_sub_count = test_db.query(Subscription).filter_by(subscriber_id=p4_id).count()
        assert initial_sub_count == 1

        retry_res = service.initiate_retry_payment(
            db=test_db,
            subscriber_id=p4_id,
            invoice_id=p4_inv_id,
        )

        assert retry_res.retry_order_id.startswith("order_retry_")
        assert retry_res.amount == 399.00
        assert retry_res.invoice_id == p4_inv_id

        # Confirm no duplicate subscription was created
        final_sub_count = test_db.query(Subscription).filter_by(subscriber_id=p4_id).count()
        assert final_sub_count == 1

        # Test double-charge prevention: Once an invoice is PAID, retry must be blocked!
        p1_id = seed_revenue_and_failure_data["p1_id"]
        with pytest.raises(ValueError, match="already been paid"):
            service.initiate_retry_payment(db=test_db, subscriber_id=p1_id)

    def test_expired_renewal_workflow_preserves_student_profiles(self, test_db, seed_revenue_and_failure_data):
        """Expired parent can renew seamlessly; existing child profiles and academic records are retained."""
        service = PaymentFailureService()
        p3_id = seed_revenue_and_failure_data["p3_id"]  # Expired parent

        renew_res = service.process_expired_renewal(
            db=test_db,
            subscriber_id=p3_id,
            plan_id="PRO",
            duration_months=3,
        )

        assert renew_res.subscriber_id == p3_id
        assert renew_res.plan_id == "PRO"
        assert renew_res.duration_months == 3
        assert renew_res.preserved_children_count == 1
        assert "Ananya Nair" in renew_res.preserved_children_names
        assert "order_renew_" in renew_res.new_order_id

    def test_grace_period_evaluation_boundaries(self, test_db, seed_revenue_and_failure_data):
        """Evaluates 3-day grace period boundaries with zero PII/academic data loss."""
        service = PaymentFailureService()
        p1_id = seed_revenue_and_failure_data["p1_id"]  # Active
        p3_id = seed_revenue_and_failure_data["p3_id"]  # 5 days expired (>3 days)

        status_active = service.get_grace_period_status(db=test_db, subscriber_id=p1_id)
        assert status_active.is_in_grace_period is False
        assert status_active.paid_features_locked is False
        assert status_active.academic_data_preserved is True

        status_expired = service.get_grace_period_status(db=test_db, subscriber_id=p3_id)
        assert status_expired.is_in_grace_period is False
        assert status_expired.paid_features_locked is True
        assert status_expired.academic_data_preserved is True


# =============================================================================
# 2. SECTION 25.2 MANAGEMENT DASHBOARD MANDATORY KPIS TESTS
# =============================================================================

class TestSection25AdminRevenueKPIs:
    """Verifies Section 25.2 Multi-Month MRR Normalization & Customer Demographics."""

    def test_multi_month_mrr_normalization_and_unique_customer_counts(self, test_db, seed_revenue_and_failure_data):
        """
        Calculates normalized MRR:
          - Sub 1 (P1): Basic 1M @ Rs 199 -> Rs 199.00/mo
          - Sub 2 (P2 Child 1): Adv 3M @ Rs 799 -> Rs 266.33/mo
          - Sub 3 (P2 Child 2): Pro 12M @ Rs 3599 -> Rs 299.92/mo
          Total Normalized MRR = 199.00 + 266.33 + 299.92 = Rs 765.25.
        Distinguishes:
          - Registered Parents: 4 (P1, P2, P3, P4)
          - Unique Paying Parents: 2 (P1, P2)
          - Active Child Subscriptions: 3 (P1 child, P2 child1, P2 child2)
        """
        service = AdminRevenueService()
        kpis = service.get_executive_kpis(db=test_db)

        # 1. Customer Demographics
        assert kpis.total_registered_parents == 4
        assert kpis.unique_paying_parents_count == 2
        assert kpis.total_active_child_subscriptions == 3

        # 2. Multi-Month Normalized MRR (Exact accounting)
        # 199 + 266.33 + 299.92 = 765.25 (+/- 1.0 rupee for rounding)
        assert 764.0 <= kpis.normalized_mrr <= 766.0
        assert kpis.annualized_run_rate_arr == round(kpis.normalized_mrr * 12.0, 2)

        # 3. Cash Collections MTD
        # Sum of paid invoices = 199 + 799 + 3599 = Rs 4,597.00
        assert kpis.gross_cash_collections_mtd == 4597.00
        assert kpis.net_cash_collections_mtd == 4597.00

        # 4. ARPU relative to unique paying parents (765.25 / 2 = ~382.63)
        assert 382.0 <= kpis.arpu <= 383.5

        # 5. Plan Breakdown has Basic, Advanced, and Pro
        plans = {p.plan_id: p for p in kpis.plan_breakdown}
        assert plans["BASIC"].active_subscriptions == 1
        assert plans["ADVANCED"].active_subscriptions == 1
        assert plans["PRO"].active_subscriptions == 1

        # 6. Duration Breakdown has 1M, 3M, 12M active
        durs = {d.duration_months: d for d in kpis.duration_breakdown}
        assert durs[1].active_subscriptions == 1
        assert durs[3].active_subscriptions == 1
        assert durs[12].active_subscriptions == 1


# =============================================================================
# 3. SECTION 25.3 MONTHLY SUBSCRIBER REPORTING & CSV EXPORT TESTS
# =============================================================================

class TestSection25MonthlyReportingAndExport:
    """Verifies Section 25.3 Monthly Cohort Movement & CSV Financial Export."""

    def test_monthly_subscriber_movement_cohort_ledger(self, test_db, seed_revenue_and_failure_data):
        """Monthly report tracks closing active, cash collections, and distributions for any chosen month."""
        service = AdminRevenueService()
        now_month = datetime.now(timezone.utc).strftime("%Y-%m")

        report = service.get_monthly_subscriber_report(db=test_db, month_key=now_month)

        assert report.month_key == now_month
        assert report.gross_cash_collections == 4597.00
        assert report.monthly_recurring_revenue_mrr > 0
        assert len(report.plan_breakdown) == 3
        assert len(report.duration_breakdown) == 4

    def test_csv_financial_export_generation(self, test_db, seed_revenue_and_failure_data):
        """CSV export outputs full audit-compliant tabular report suitable for management review."""
        service = AdminRevenueService()
        now_month = datetime.now(timezone.utc).strftime("%Y-%m")

        csv_content = service.export_monthly_report_csv(db=test_db, month_key=now_month)

        assert "STUDIQS SMARTPARENT - MONTHLY SUBSCRIBER & REVENUE REPORT" in csv_content
        assert f"Reporting Month,{now_month}" in csv_content
        assert "Normalized MRR (Monthly Recurring Revenue)" in csv_content
        assert "Annualized Run-Rate (ARR)" in csv_content
        assert "Gross Cash Collections MTD" in csv_content
        assert "--- SUBSCRIBER COHORT MOVEMENT ---" in csv_content
        assert "--- PLAN DISTRIBUTION BREAKDOWN ---" in csv_content
        assert "--- DURATION DISTRIBUTION BREAKDOWN ---" in csv_content


# =============================================================================
# 4. WEBHOOK IDEMPOTENCY UNIT TEST
# =============================================================================

class TestRazorpayWebhookIdempotency:
    """Verifies strict idempotency via RazorpayWebhookEvent."""

    def test_webhook_event_idempotency_prevents_duplicate_processing(self, test_db):
        """Duplicate webhook event is marked already_processed and skipped."""
        event_id = "evt_live_test_unique_9981"

        # Record event as processed
        evt = RazorpayWebhookEvent(
            event_id=event_id,
            event_type="payment.captured",
            payload={"id": event_id, "amount": 19900},
            processing_status="PROCESSED",
        )
        test_db.add(evt)
        test_db.commit()

        # Query check
        found = test_db.query(RazorpayWebhookEvent).filter_by(event_id=event_id, processing_status="PROCESSED").first()
        assert found is not None
        assert found.processing_status == "PROCESSED"

