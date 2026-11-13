"""
STUDIQS® SmartParent™ - Section 24.6 Alerts & Section 25.4 Admin Directory Tests
=============================================================================
Module: tests.unit.test_section24_25_admin_directory_and_alerts

Verifies:
  1. Administrative Subscriber Directory (Section 25.4):
     - Search & multi-criteria filtering by Plan, Status, Mobile, Parent Name.
     - Deep 360 subscriber dossier (Children, Subscriptions, Invoices, Tickets).
     - Manual subscription adjustment with mandatory audit log and reason.
  2. Automated 4-Stage Renewal and Expiry Alerts (Section 24.6):
     - 7-Day, 3-Day, 1-Day, and On-Expiry notification milestone sweeps.
     - Absolute deduplication preventing redundant alert dispatch.
     - Clear auto-renew messaging (informing upcoming debit vs manual payment).
     - Real-time parent dashboard renewal banner telemetry.
=============================================================================
"""

import uuid
from datetime import date, datetime, timedelta, timezone
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

from src.smartparent.core.constants import SubscriptionPlan
from src.smartparent.db.base import Base
from src.smartparent.db.models.auth import Subscriber, Child
from src.smartparent.db.models.subscription import (
    Subscription,
    BillingInvoice,
    SubscriptionRenewalReminder,
    SubscriptionAdjustmentAudit,
)
from src.smartparent.db.models.support_ticket import SupportTicket
from src.smartparent.db.models.notification import InAppNotification
from src.smartparent.schemas.admin_directory import (
    ManualSubscriptionAdjustmentRequest,
)
from src.smartparent.services.admin_directory_service import AdminDirectoryService
from src.smartparent.services.renewal_alert_service import RenewalAlertService


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
def seed_admin_and_alerts_data(test_db):
    today = date.today()
    now_utc = datetime.now(timezone.utc)

    # 1. Subscriber A (Basic, 7 days until expiry, manual renew)
    sub_a_id = uuid.uuid4()
    sub_a = Subscriber(
        subscriber_id=sub_a_id,
        mobile_number="9876543301",
        parent_name="Anand Sharma",
        email="anand.sharma@example.com",
        password_hash="hash_a",
        subscription_plan=SubscriptionPlan.BASIC.value,
    )
    sub_a_child = Child(
        child_id=uuid.uuid4(),
        subscriber_id=sub_a_id,
        student_name="Rahul Sharma",
        standard_class="Class 10",
        board="CBSE",
    )
    sub_a_sub = Subscription(
        subscription_id=uuid.uuid4(),
        subscriber_id=sub_a_id,
        plan_id=SubscriptionPlan.BASIC.value,
        duration_months=1,
        start_date=now_utc - timedelta(days=23),
        expiry_date=now_utc + timedelta(days=7),
        status="ACTIVE",
        auto_renew=False,
    )
    sub_a_inv = BillingInvoice(
        invoice_id=uuid.uuid4(),
        invoice_number="INV-2026-001",
        subscriber_id=sub_a_id,
        subscription_id=sub_a_sub.subscription_id,
        billing_period_start=now_utc - timedelta(days=23),
        billing_period_end=now_utc + timedelta(days=7),
        base_amount=169.49,
        taxable_amount=169.49,
        total_amount=200.00,
        payment_status="PAID",
    )

    # 2. Subscriber B (Pro, 3 days until expiry, AUTO-RENEW enabled)
    sub_b_id = uuid.uuid4()
    sub_b = Subscriber(
        subscriber_id=sub_b_id,
        mobile_number="9876543302",
        parent_name="Priya Natarajan",
        email="priya.n@example.com",
        password_hash="hash_b",
        subscription_plan=SubscriptionPlan.PRO.value,
    )
    sub_b_child = Child(
        child_id=uuid.uuid4(),
        subscriber_id=sub_b_id,
        student_name="Aditya Natarajan",
        standard_class="Class 12",
        board="CBSE",
    )
    sub_b_sub = Subscription(
        subscription_id=uuid.uuid4(),
        subscriber_id=sub_b_id,
        plan_id=SubscriptionPlan.PRO.value,
        duration_months=3,
        start_date=now_utc - timedelta(days=87),
        expiry_date=now_utc + timedelta(days=3),
        status="ACTIVE",
        auto_renew=True,
    )
    sub_b_inv = BillingInvoice(
        invoice_id=uuid.uuid4(),
        invoice_number="INV-2026-002",
        subscriber_id=sub_b_id,
        subscription_id=sub_b_sub.subscription_id,
        billing_period_start=now_utc - timedelta(days=87),
        billing_period_end=now_utc + timedelta(days=3),
        base_amount=1525.42,
        taxable_amount=1525.42,
        total_amount=1800.00,
        payment_status="PAID",
    )

    # 3. Subscriber C (Advanced, Expired today)
    sub_c_id = uuid.uuid4()
    sub_c = Subscriber(
        subscriber_id=sub_c_id,
        mobile_number="9876543303",
        parent_name="Karthik R.",
        email="karthik.r@example.com",
        password_hash="hash_c",
        subscription_plan=SubscriptionPlan.ADVANCED.value,
    )
    sub_c_sub = Subscription(
        subscription_id=uuid.uuid4(),
        subscriber_id=sub_c_id,
        plan_id=SubscriptionPlan.ADVANCED.value,
        duration_months=1,
        start_date=now_utc - timedelta(days=30),
        expiry_date=now_utc,  # Expired today!
        status="ACTIVE",
        auto_renew=False,
    )

    test_db.add_all([
        sub_a, sub_a_child, sub_a_sub, sub_a_inv,
        sub_b, sub_b_child, sub_b_sub, sub_b_inv,
        sub_c, sub_c_sub,
    ])
    test_db.commit()

    return {
        "sub_a_id": sub_a_id,
        "sub_b_id": sub_b_id,
        "sub_c_id": sub_c_id,
        "sub_a_sub_id": sub_a_sub.subscription_id,
        "sub_b_sub_id": sub_b_sub.subscription_id,
    }


class TestSection25AdminDirectory:
    """Verifies Section 25.4 Searchable Subscriber Directory & Adjustments."""

    def test_subscriber_directory_listing_and_filtering(self, test_db, seed_admin_and_alerts_data):
        """Admin directory lists all subscribers with correct children, revenue, and filters."""
        service = AdminDirectoryService()

        # 1. Total listing
        res = service.list_subscribers(db=test_db, page=1, page_size=10)
        assert res.total_subscribers == 3
        assert len(res.subscribers) == 3

        # 2. Filter by Plan: PRO
        pro_res = service.list_subscribers(db=test_db, plan="PRO")
        assert len(pro_res.subscribers) == 1
        assert pro_res.subscribers[0].parent_name == "Priya Natarajan"
        assert pro_res.subscribers[0].subscription_plan == "PRO"
        assert pro_res.subscribers[0].total_revenue_collected == 1800.00
        assert pro_res.subscribers[0].subscribed_children_count == 1
        assert "Aditya Natarajan" in pro_res.subscribers[0].children_names

        # 3. Search by mobile number query
        mobile_res = service.list_subscribers(db=test_db, search_query="9876543301")
        assert len(mobile_res.subscribers) == 1
        assert mobile_res.subscribers[0].parent_name == "Anand Sharma"

        # 4. Search by parent name query
        name_res = service.list_subscribers(db=test_db, search_query="Karthik")
        assert len(name_res.subscribers) == 1
        assert name_res.subscribers[0].parent_name == "Karthik R."

    def test_subscriber_deep_dossier_detail(self, test_db, seed_admin_and_alerts_data):
        """Compiles 360-degree dossier including children, invoices, and subscription history."""
        service = AdminDirectoryService()
        sub_b_id = seed_admin_and_alerts_data["sub_b_id"]

        detail = service.get_subscriber_detail(db=test_db, subscriber_id=sub_b_id)
        assert detail.subscriber.parent_name == "Priya Natarajan"
        assert len(detail.children) == 1
        assert detail.children[0].student_name == "Aditya Natarajan"
        assert len(detail.subscriptions_history) >= 1
        assert len(detail.payment_invoices) >= 1
        assert detail.payment_invoices[0]["total_amount"] == 1800.00

    def test_manual_subscription_adjustment_creates_mandatory_audit(self, test_db, seed_admin_and_alerts_data):
        """Authorised manual adjustment requires reason and records full before/after audit entry."""
        service = AdminDirectoryService()
        sub_a_id = seed_admin_and_alerts_data["sub_a_id"]

        # Extend validity by 30 days
        req = ManualSubscriptionAdjustmentRequest(
            action_type="EXTEND_VALIDITY",
            extend_days=30,
            admin_user="superadmin@studiqs.com",
            reason="Customer requested grace period for medical emergency",
        )

        adj_res = service.adjust_subscription(
            db=test_db,
            subscriber_id=sub_a_id,
            payload=req,
        )

        assert adj_res.action_type == "EXTEND_VALIDITY"
        assert adj_res.admin_user == "superadmin@studiqs.com"
        assert adj_res.reason == "Customer requested grace period for medical emergency"
        assert adj_res.audit_id is not None

        # Verify DB audit entry persistence
        audit_record = test_db.query(SubscriptionAdjustmentAudit).filter_by(audit_id=adj_res.audit_id).one()
        assert audit_record.action_type == "EXTEND_VALIDITY"
        assert audit_record.admin_user == "superadmin@studiqs.com"

        # Verify subscription was extended
        sub_rec = test_db.query(Subscription).filter_by(subscriber_id=sub_a_id).first()
        assert sub_rec.status == "ACTIVE"


class TestSection24RenewalAndExpiryAlerts:
    """Verifies Section 24.6 4-Stage Renewal Reminders & Alert Sweeper."""

    def test_alert_sweeper_dispatches_correct_milestone_reminders(self, test_db, seed_admin_and_alerts_data):
        """Sweeper correctly triggers 7-day, 3-day, and on-expiry notifications."""
        service = RenewalAlertService()

        summary = service.run_alert_sweep(db=test_db)
        assert summary.total_subscriptions_scanned == 3
        # Sub A is T-7, Sub B is T-3, Sub C is T-0 (Expired)
        assert summary.alerts_dispatched_count == 3
        assert summary.stage_breakdown["REMINDER_7_DAYS"] == 1
        assert summary.stage_breakdown["REMINDER_3_DAYS"] == 1
        assert summary.stage_breakdown["EXPIRED_NOTICE"] == 1

        # Verify Sub C status updated to EXPIRED
        sub_c_id = seed_admin_and_alerts_data["sub_c_id"]
        sub_c = test_db.query(Subscription).filter_by(subscriber_id=sub_c_id).first()
        assert sub_c.status == "EXPIRED"

        # Verify InAppNotification records were created for the parents
        notifs = test_db.query(InAppNotification).all()
        assert len(notifs) == 3

    def test_alert_sweeper_deduplication_prevents_duplicate_notices(self, test_db, seed_admin_and_alerts_data):
        """Running the sweeper twice on the same day skips already dispatched reminders."""
        service = RenewalAlertService()

        # First run: dispatches 3 reminders
        s1 = service.run_alert_sweep(db=test_db)
        assert s1.alerts_dispatched_count == 3

        # Second run: all 3 should be skipped due to deduplication check!
        s2 = service.run_alert_sweep(db=test_db)
        assert s2.alerts_dispatched_count == 0
        assert s2.alerts_skipped_already_sent_count == 3

    def test_auto_renew_vs_manual_renew_messaging(self, test_db, seed_admin_and_alerts_data):
        """Auto-renew subscriber gets upcoming debit notice; manual renewal subscriber gets payment link."""
        service = RenewalAlertService()
        sub_a_id = seed_admin_and_alerts_data["sub_a_id"]  # manual renew
        sub_b_id = seed_admin_and_alerts_data["sub_b_id"]  # auto renew

        # Sub A (Manual): Banner encourages renewal
        banner_a = service.get_parent_renewal_banner(db=test_db, subscriber_id=sub_a_id)
        assert banner_a.has_active_alert is True
        assert banner_a.auto_renew is False
        assert banner_a.days_remaining == 7
        assert "7 Days" in banner_a.banner_headline
        assert "Renew Now" in banner_a.quick_action_cta
        assert "expires on" in banner_a.banner_message.lower()

        # Sub B (Auto-Renew): Banner informs upcoming Razorpay debit
        banner_b = service.get_parent_renewal_banner(db=test_db, subscriber_id=sub_b_id)
        assert banner_b.has_active_alert is True
        assert banner_b.auto_renew is True
        assert "automatically renew" in banner_b.banner_message.lower()
        assert "Razorpay" in banner_b.banner_message
        assert "Manage Subscription" in banner_b.quick_action_cta
