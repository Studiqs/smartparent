"""
STUDIQS® SmartParent™ (v6.3 Complete) - Production Backend Deliverables Verification
=====================================================================================
Module: tests.unit.test_production_backend_deliverables
Validates:
  1. Section 24: BillingService & Vector GST Tax Invoice PDF generation
  2. Section 24: Razorpay HMAC Webhook listener & signature validation
  3. Section 25: Admin Management Revenue Intelligence & MRR analytics
  4. Section 2: Sub-3-Minute Consumer Onboarding Service
  5. In-Memory Redis Caching & OTP sliding-window rate limiter
  6. Celery Async Task Architecture & Routing
=====================================================================================
"""

import hmac
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from src.smartparent.db.base import Base
from src.smartparent.main import app
from src.smartparent.db.session import get_db
from src.smartparent.services.billing_service import BillingService
from src.smartparent.services.onboarding_service import OnboardingService, QuickOnboardingRequest
from src.smartparent.services.subscription_service import SubscriptionService
from src.smartparent.utils.redis_cache import RedisCacheService
from src.smartparent.core.celery_app import celery_app
import src.smartparent.tasks.evidence_tasks as ev_tasks
import src.smartparent.tasks.sla_watchdog_tasks as sla_tasks
from src.smartparent.db.models.auth import Subscriber, Child
from src.smartparent.db.models.subscription import BillingInvoice, Subscription
from src.smartparent.db.models.marketplace import EvaluationCase, PaymentOrder
from src.smartparent.core.constants import CaseStatus, PaymentStatus
from src.smartparent.config import settings

from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID

@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"

@compiles(PG_UUID, "sqlite")
def compile_uuid_sqlite(type_, compiler, **kw):
    return "CHAR(36)"


@pytest.fixture
def db_session():
    """In-memory SQLite session for testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client(db_session):
    """FastAPI TestClient with overridden DB dependency."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# =============================================================================
# 1. SECTION 24: GST TAX INVOICE & BILLING SERVICE TESTS
# =============================================================================

class TestBillingAndGstInvoicing:
    """Verifies B2C compliant GST invoice PDF creation and signature math."""

    def test_generate_gst_invoice_pdf_creates_valid_bytes(self, tmp_path):
        """PDF generation must output valid non-empty PDF bytes starting with %PDF-."""
        billing_service = BillingService(upload_dir=str(tmp_path))

        invoice_data = {
            "invoice_number": "INV-202610-A912BC",
            "invoice_date": "31-Oct-2026",
            "parent_name": "Sundaram R.",
            "mobile_number": "+919876543210",
            "email": "sundaram.r@example.com",
            "buyer_state": "Tamil Nadu",
            "plan_description": "Studiqs SmartParent Advanced (HALF_YEARLY)",
            "taxable_amount": 1185.59,
            "cgst_amount": 106.71,
            "sgst_amount": 106.70,
            "igst_amount": 0.0,
            "total_amount": 1399.00,
            "razorpay_payment_id": "pay_live_test_12345",
            "razorpay_order_id": "order_live_test_67890",
        }

        out_pdf = tmp_path / "test_invoice.pdf"
        pdf_bytes = billing_service.generate_gst_invoice_pdf(invoice_data, output_path=str(out_pdf))

        assert len(pdf_bytes) > 1000
        assert pdf_bytes.startswith(b"%PDF-")
        assert out_pdf.exists()

    def test_razorpay_hmac_signature_verification(self):
        """Validates HMAC-SHA256 signature verification."""
        secret = "test_secret_key_123"
        order_id = "order_abc"
        payment_id = "pay_xyz"

        payload = f"{order_id}|{payment_id}"
        valid_sig = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()

        assert BillingService.verify_razorpay_signature(order_id, payment_id, valid_sig, secret=secret) is True
        assert BillingService.verify_razorpay_signature(order_id, payment_id, "invalid_signature", secret=secret) is False


# =============================================================================
# 2. SECTION 24: RAZORPAY WEBHOOK LISTENER API TESTS
# =============================================================================

class TestRazorpayWebhookApi:
    """Verifies live webhook ingestion, HMAC validation, and fulfillment."""

    def test_webhook_rejects_invalid_signature(self, client):
        """Invalid X-Razorpay-Signature must return HTTP 400."""
        payload = json.dumps({"event": "payment.captured"})
        response = client.post(
            "/api/v1/webhooks/razorpay",
            content=payload,
            headers={"X-Razorpay-Signature": "tampered_fake_signature"},
        )
        assert response.status_code == 400
        assert "signature" in response.json()["detail"].lower()

    def test_webhook_fulfills_case_payment(self, client, db_session):
        """payment.captured must transition EvaluationCase to AWAITING_UPLOAD."""
        # 1. Setup subscriber & case
        sub = Subscriber(
            subscriber_id=uuid.uuid4(),
            mobile_number="+919444000111",
            parent_name="Anand S.",
            password_hash="mock",
        )
        child = Child(
            child_id=uuid.uuid4(),
            subscriber_id=sub.subscriber_id,
            student_name="Karthik",
            standard_class="Class 10",
            board="CBSE",
        )
        db_session.add_all([sub, child])
        db_session.flush()

        case = EvaluationCase(
            case_id=uuid.uuid4(),
            subscriber_id=sub.subscriber_id,
            child_id=child.child_id,
            subject="Mathematics",
            test_title="Algebra Drill",
            case_status=CaseStatus.ASSIGNED.value,
            gross_fee=299.0,
        )
        order = PaymentOrder(
            order_id=uuid.uuid4(),
            case_id=case.case_id,
            subscriber_id=sub.subscriber_id,
            gateway_order_id="order_test_case_888",
            amount=299.0,
            payment_status=PaymentStatus.CREATED.value,
        )
        db_session.add_all([case, order])
        db_session.commit()

        # 2. Construct Webhook Payload
        webhook_body = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_test_case_999",
                        "order_id": "order_test_case_888",
                        "amount": 29900,
                        "notes": {
                            "case_id": str(case.case_id),
                        },
                    }
                }
            },
        }
        raw_bytes = json.dumps(webhook_body).encode("utf-8")
        secret = settings.RAZORPAY_WEBHOOK_SECRET or "dev_webhook_secret"
        sig = hmac.new(secret.encode("utf-8"), raw_bytes, hashlib.sha256).hexdigest()

        # 3. Post to Webhook
        res = client.post(
            "/api/v1/webhooks/razorpay",
            content=raw_bytes,
            headers={"X-Razorpay-Signature": sig},
        )
        assert res.status_code == 200
        assert res.json()["status"] == "success"

        # 4. Assert DB state transition
        db_session.refresh(case)
        db_session.refresh(order)
        assert case.case_status == CaseStatus.AWAITING_UPLOAD.value
        assert order.payment_status == PaymentStatus.PAID.value


# =============================================================================
# 3. SECTION 25: ADMIN REVENUE & MRR DASHBOARD TESTS
# =============================================================================

class TestAdminRevenueDashboard:
    """Verifies executive MRR, ARR, and collections analytics."""

    def test_admin_revenue_summary_endpoint(self, client, db_session):
        """GET /api/v1/admin/revenue/summary must return computed MRR and tax liability."""
        sub = Subscriber(
            subscriber_id=uuid.uuid4(),
            mobile_number="+919555111222",
            parent_name="Meena R.",
            password_hash="mock",
        )
        db_session.add(sub)
        db_session.flush()

        inv = BillingInvoice(
            invoice_id=uuid.uuid4(),
            invoice_number="INV-202610-001",
            subscriber_id=sub.subscriber_id,
            billing_period_start=datetime.now(timezone.utc),
            billing_period_end=datetime.now(timezone.utc),
            base_amount=1399.0,
            discount_amount=0.0,
            taxable_amount=1185.59,
            cgst_amount=106.71,
            sgst_amount=106.70,
            igst_amount=0.0,
            total_amount=1399.0,
            currency="INR",
            payment_status="PAID",
        )
        db_session.add(inv)
        db_session.commit()

        res = client.get("/api/v1/admin/revenue/summary")
        assert res.status_code == 200
        data = res.json()

        assert data["currency"] == "INR"
        assert data["mrr"] >= 1185.59
        assert data["arr"] == round(data["mrr"] * 12.0, 2)
        assert data["active_subscribers_count"] >= 1
        assert data["subscription_revenue"]["total_gst_collected"] >= 213.41


# =============================================================================
# 4. SECTION 2: SUB-3-MINUTE CONSUMER ONBOARDING SERVICE TESTS
# =============================================================================

class TestConsumerOnboardingService:
    """Verifies minimal friction 3-minute onboarding."""

    def test_sub_3_minute_onboarding_success(self, db_session):
        service = OnboardingService()
        req = QuickOnboardingRequest(
            mobile_number="9876543210",
            parent_name="Venkatesh K.",
            email="venkatesh.k@example.com",
            child_name="Arjun Venkatesh",
            board="CBSE",
            standard_class="Class 9",
        )

        res = service.onboard_subscriber_and_child(db_session, req)
        assert res.onboarding_status == "COMPLETED"
        assert res.parent_name == "Venkatesh K."
        assert res.student_name == "Arjun Venkatesh"
        assert res.board == "CBSE"
        assert res.standard_class == "Class 9"
        assert len(res.access_token) > 20
        assert len(res.refresh_token) > 20


# =============================================================================
# 5. REDIS CACHING & CELERY CONFIGURATION TESTS
# =============================================================================

class TestRedisAndCeleryInfrastructure:
    """Verifies background tasks and caching resilience."""

    def test_redis_cache_service_fallback_when_offline(self):
        """When Redis is offline or unreachable, cache must degrade safely without crashing."""
        cache = RedisCacheService(url="redis://non_existent_host_123:6379/0")
        assert cache.get_cached_taxonomy("CBSE", "Class 10", "Maths") is None
        assert cache.check_and_increment_otp_rate_limit("+919876543210") is True

    def test_celery_task_registration_and_routes(self):
        """Verifies Celery tasks are properly declared and registered."""
        registered_tasks = set(celery_app.tasks.keys())
        expected = [
            ev_tasks.parse_question_paper_async_task.name,
            ev_tasks.generate_vector_report_pdf_async_task.name,
            sla_tasks.check_expert_cases_sla_breach_task.name,
            sla_tasks.monthly_pulse_cron_task.name,
        ]
        for t in expected:
            assert t in registered_tasks, f"Missing registered task: {t}"
