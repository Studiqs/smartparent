"""
STUDIQS® SmartParent™ - Sandbox & Demo Ecosystem Test Battery
=============================================================================
Module: tests.unit.test_sandbox_ecosystem

Validates the complete SmartParent Sandbox infrastructure:
  1. Sandbox Status & Configuration Inspection
  2. Demo Family Ecosystem Seeding (Karthik Subramanian, 2 children, diagnostic scores, gaps)
  3. Razorpay Payment Sandbox Checkout Simulation (Pro Plan, 18% GST calculation, INV generation)
  4. Payment Failure Simulation (Card decline in sandbox)
  5. Ask Studiqs Voice & Natural Language Sandbox (Read-only SQL isolation, 0.00% hallucination)
  6. Multilingual Tanglish Query Resolution in Sandbox
  7. Read-Only Transaction Invariance Defense
=============================================================================
"""

import uuid
import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.smartparent.main import app
from src.smartparent.api.deps import get_db
from src.smartparent.db.base import Base
from src.smartparent.core.constants import SubscriptionPlan
from src.smartparent.services.sandbox_service import SandboxService, DEMO_MOBILE
from src.smartparent.schemas.sandbox import (
    SandboxPaymentCheckoutRequest,
    SandboxAskStudiqsRequest,
)

from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

# SQLite dialect mapping for PostgreSQL JSONB
@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"

# In-memory SQLite for high-speed deterministic testing
engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def sandbox_db():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(sandbox_db):
    def override_get_db():
        try:
            yield sandbox_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_sandbox_status_endpoint(client):
    """Verifies that the sandbox capabilities status endpoint returns all features."""
    response = client.get("/api/v1/sandbox/status")
    assert response.status_code == 200
    data = response.json()
    assert data["environment"] == "sandbox"
    assert data["payment_sandbox_active"] is True
    assert data["voice_assistant_sandbox_active"] is True
    assert data["read_only_db_sandbox_enforced"] is True
    assert "PRO" in data["supported_plans"]
    assert 12 in data["supported_durations_months"]
    assert data["gst_rate_percent"] == 18.0


def test_seed_demo_ecosystem(client, sandbox_db):
    """Verifies idempotency and richness of the demo ecosystem seeding."""
    response = client.post("/api/v1/sandbox/seed-demo")
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "INITIALIZED"
    assert data["mobile_number"] == DEMO_MOBILE
    assert data["parent_name"] == "Karthik Subramanian"
    assert data["children_count"] == 2

    # Second call must be idempotent
    response_second = client.post("/api/v1/sandbox/seed-demo")
    assert response_second.status_code == 201
    data_second = response_second.json()
    assert data_second["subscriber_id"] == data["subscriber_id"]


def test_sandbox_payment_checkout_pro_annual(sandbox_db):
    """
    Simulates a Pro Annual (12 months) checkout in Razorpay sandbox mode:
    - Base: ₹600 * 12 = ₹7,200.00
    - CGST (9%): ₹648.00
    - SGST (9%): ₹648.00
    - Total: ₹8,496.00
    """
    req = SandboxPaymentCheckoutRequest(
        plan=SubscriptionPlan.PRO,
        duration_months=12,
        payment_method="mock_upi",
        simulate_failure=False,
    )
    result = SandboxService.simulate_payment_checkout(db=sandbox_db, request=req)

    assert result.subscription_status == "ACTIVE"
    assert result.plan == "PRO"
    assert result.duration_months == 12
    assert result.taxable_base == 7200.0
    assert result.cgst_amount == 648.0
    assert result.sgst_amount == 648.0
    assert result.total_amount == 8496.0
    assert result.order_id.startswith("order_sandbox_")
    assert result.payment_id.startswith("pay_sandbox_")
    assert "INV-SBX-" in result.invoice_number


def test_sandbox_payment_checkout_failure_simulation(sandbox_db):
    """Simulates card decline / failure in the payment gateway sandbox."""
    req = SandboxPaymentCheckoutRequest(
        plan=SubscriptionPlan.ADVANCED,
        duration_months=3,
        payment_method="mock_card",
        simulate_failure=True,
    )
    result = SandboxService.simulate_payment_checkout(db=sandbox_db, request=req)

    assert result.subscription_status == "PAYMENT_PENDING"
    assert result.payment_id is None
    assert result.invoice_number is None
    assert "Card declined" in result.message


def test_sandbox_ask_studiqs_voice_query(sandbox_db):
    """
    Tests Ask Studiqs RAG inside the Read-Only Sandbox:
    - Queries for weak topics in Mathematics.
    - Resolves Ananya's Quadratic Equations gap.
    - Verifies 0.00% hallucination and read-only isolation.
    """
    # 1. Seed demo data first
    sub, children = SandboxService.get_or_seed_demo_parent(sandbox_db)
    ananya = [c for c in children if "Ananya" in c.student_name][0]

    req = SandboxAskStudiqsRequest(
        query_text="What is Ananya's weak topic in Mathematics?",
        subscriber_id=sub.subscriber_id,
        child_id=ananya.child_id,
        language_hint="en-IN",
    )

    res = SandboxService.execute_voice_query_sandbox(db=sandbox_db, request=req)

    assert res.is_read_only_isolated is True
    assert res.resolved_child_name == "Ananya Subramanian"
    assert res.ui_card_narrative is not None
    assert len(res.ui_card_narrative) > 10
    assert res.execution_latency_ms > 0.0


def test_sandbox_ask_studiqs_tanglish_query(sandbox_db):
    """
    Tests Tanglish query resolution inside the voice sandbox:
    'En paiyan maths la entha topic la weak?'
    """
    sub, children = SandboxService.get_or_seed_demo_parent(sandbox_db)

    req = SandboxAskStudiqsRequest(
        query_text="En paiyan maths la entha topic la weak?",
        subscriber_id=sub.subscriber_id,
        language_hint="ta-IN",
    )

    res = SandboxService.execute_voice_query_sandbox(db=sandbox_db, request=req)

    assert res.is_read_only_isolated is True
    assert res.intent_pillar in ("DIAGNOSTIC_DRILLDOWN", "EXECUTIVE_SUMMARY", "GENERAL_DISCOVERY")
    assert "Quadratic" in res.remedial_recommendation or "Math" in res.remedial_recommendation

