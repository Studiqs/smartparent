"""
STUDIQS® SmartParent™ (v6.2 & v6.3 Extension) - Section 14 & 27 Integration Test Suite
=============================================================================
Module: tests.integration.test_section14_support_api
Tests the complete HTTP REST API surface for:
  1. GET  /api/v1/support/faq                   -> Knowledge Base search & issue deflection
  2. POST /api/v1/support/tickets               -> Sequential TKT numbering & 48h SLA initialization
  3. POST /api/v1/support/tickets (Dispute)      -> 48h Escrow freeze on evaluation cases
  4. GET  /api/v1/support/tickets               -> Parent ticket list (RLS isolation)
  5. GET  /api/v1/support/tickets/{id}          -> Detail view with internal note masking
  6. POST /api/v1/support/tickets/{id}/messages -> Conversation reply
  7. POST /api/v1/support/tickets/{id}/close    -> Ticket closure
  8. POST /api/v1/support/tickets/{id}/reopen   -> Reopen policy enforcement
  9. GET  /api/v1/admin/support/tickets         -> Admin triage listing & filters
  10. GET  /api/v1/admin/support/tickets/{id}    -> Admin detail view with internal notes
  11. POST /api/v1/admin/support/tickets/{id}/assign -> Ticket assignment
  12. POST /api/v1/admin/support/tickets/{id}/messages -> Admin internal note
  13. POST /api/v1/admin/support/tickets/{id}/resolve -> Ticket resolution
  14. POST /api/v1/admin/support/sla/scan       -> SLA escalation sweep
  15. GET  /api/v1/admin/support/metrics        -> Operational SLA metrics
=============================================================================
"""

import uuid
from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.smartparent.main import app
from src.smartparent.api.deps import get_db
from src.smartparent.db.base import Base
from src.smartparent.core.constants import (
    CaseStatus,
    SupportTicketCategory,
    SupportTicketPriority,
    TicketStatus,
    TicketType,
)
from src.smartparent.db.models.auth import Subscriber, Child
from src.smartparent.db.models.marketplace import EvaluationCase, CommissionLedger
from src.smartparent.db.models.support_ticket import (
    SupportTicket,
    SupportMessage,
    SupportSLAEvent,
)


@pytest.fixture
def client_with_db():
    """Sets up an in-memory SQLite DB and wires FastAPI dependency override."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            Subscriber.__table__,
            Child.__table__,
            EvaluationCase.__table__,
            CommissionLedger.__table__,
            SupportTicket.__table__,
            SupportMessage.__table__,
            SupportSLAEvent.__table__,
        ],
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    # Seed demo parent
    db = TestingSessionLocal()
    sub_id = uuid.uuid4()
    parent = Subscriber(
        subscriber_id=sub_id,
        mobile_number="+919876543210",
        parent_name="Kavitha Raman",
        password_hash="mock_hash",
        subscription_plan="PRO",
    )
    db.add(parent)
    db.commit()
    db.close()

    with TestClient(app) as test_client:
        yield test_client, sub_id, TestingSessionLocal

    app.dependency_overrides.clear()


# =============================================================================
# 1. Self-Service Knowledge Base Search API
# =============================================================================

def test_api_faq_search_keyword(client_with_db):
    client, _, _ = client_with_db
    res = client.get("/api/v1/support/faq?query=refund")
    assert res.status_code == 200
    data = res.json()
    assert data["total_found"] > 0
    assert any("refund" in item["article"]["title"].lower() or "refund" in item["article"]["content"].lower() for item in data["results"])


def test_api_faq_search_with_category(client_with_db):
    client, _, _ = client_with_db
    res = client.get(f"/api/v1/support/faq?query=refund&category={SupportTicketCategory.BILLING_REFUND.value}")
    assert res.status_code == 200
    data = res.json()
    assert data["total_found"] > 0


# =============================================================================
# 2. Support Ticket Lifecycle (Parent Facing)
# =============================================================================

def test_api_create_ticket_and_list(client_with_db):
    client, sub_id, _ = client_with_db

    headers = {"X-Subscriber-Id": str(sub_id)}
    payload = {
        "category": SupportTicketCategory.BILLING_REFUND.value,
        "subject": "Double charged for monthly subscription renewal",
        "description": "My bank account was debited twice on October 25th for the Rs. 499 plan.",
    }
    res = client.post("/api/v1/support/tickets", json=payload, headers=headers)
    assert res.status_code == 201
    ticket = res.json()

    assert ticket["ticket_number"].startswith("TKT-")
    assert ticket["ticket_status"] == TicketStatus.OPEN.value
    # Financial issue auto-triaged to URGENT
    assert ticket["priority"] == SupportTicketPriority.URGENT.value
    assert ticket["sla_deadline"] is not None

    ticket_id = ticket["ticket_id"]

    # List parent tickets
    list_res = client.get("/api/v1/support/tickets", headers=headers)
    assert list_res.status_code == 200
    tickets = list_res.json()["tickets"]
    assert len(tickets) == 1
    assert tickets[0]["ticket_id"] == ticket_id


def test_api_evaluation_dispute_escrow_freeze(client_with_db):
    client, sub_id, SessionFactory = client_with_db

    # Seed an EvaluationCase completed within 48h
    db = SessionFactory()
    case_id = uuid.uuid4()
    completed_time = datetime.now(timezone.utc) - timedelta(hours=10)
    case = EvaluationCase(
        case_id=case_id,
        subscriber_id=sub_id,
        child_id=uuid.uuid4(),
        subject="Physics",
        test_title="Grade 10 Mid-term",
        gross_fee=100.0,
        case_status=CaseStatus.COMPLETED.value,
        completed_at=completed_time,
    )
    db.add(case)
    db.commit()
    db.close()

    headers = {"X-Subscriber-Id": str(sub_id)}
    payload = {
        "category": SupportTicketCategory.GUIDANCE.value,
        "ticket_type": TicketType.CORRECTION_DISPUTE.value,
        "subject": "Dispute on Question 4 marking in Grade 10 Physics paper",
        "description": "Expert gave 0 marks for step derivation that matches textbook page 42.",
        "case_id": str(case_id),
    }
    res = client.post("/api/v1/support/tickets", json=payload, headers=headers)
    assert res.status_code == 201

    # Verify case status was automatically frozen to DISPUTED
    db = SessionFactory()
    reloaded_case = db.get(EvaluationCase, case_id)
    assert reloaded_case.case_status == CaseStatus.DISPUTED.value
    db.close()


def test_api_ticket_detail_and_internal_note_masking(client_with_db):
    client, sub_id, _ = client_with_db
    headers_parent = {"X-Subscriber-Id": str(sub_id)}
    headers_admin = {"X-Admin-Id": str(uuid.uuid4())}

    # 1. Create Ticket
    payload = {
        "category": SupportTicketCategory.BUG_REPORT.value,
        "subject": "OCR extraction misread marks on page 2",
        "description": "Scanned question paper showed 5/5 but Document AI parsed 3/5.",
    }
    res = client.post("/api/v1/support/tickets", json=payload, headers=headers_parent)
    ticket_id = res.json()["ticket_id"]

    # 2. Admin adds an internal note (Hidden from Parent)
    admin_note_payload = {
        "message_text": "INTERNAL NOTE: Cloud Vision OCR confidence score was 0.62. Escalated to vision team.",
        "is_internal_note": True,
    }
    admin_msg_res = client.post(
        f"/api/v1/admin/support/tickets/{ticket_id}/messages",
        json=admin_note_payload,
        headers=headers_admin,
    )
    assert admin_msg_res.status_code == 201

    # 3. Admin adds a public response
    admin_public_payload = {
        "message_text": "Hello Kavitha, we have reviewed the OCR logs and reprocessed your paper.",
        "is_internal_note": False,
    }
    client.post(
        f"/api/v1/admin/support/tickets/{ticket_id}/messages",
        json=admin_public_payload,
        headers=headers_admin,
    )

    # 4. Parent views detail: Internal note MUST BE MASKED
    parent_detail_res = client.get(
        f"/api/v1/support/tickets/{ticket_id}",
        headers=headers_parent,
    )
    assert parent_detail_res.status_code == 200
    messages_parent_sees = parent_detail_res.json()["messages"]
    assert len(messages_parent_sees) == 2  # Opening description + public response
    assert not any(msg["is_internal_note"] for msg in messages_parent_sees)

    # 5. Admin views detail: Internal note MUST BE VISIBLE
    admin_detail_res = client.get(
        f"/api/v1/admin/support/tickets/{ticket_id}",
        headers=headers_admin,
    )
    assert admin_detail_res.status_code == 200
    messages_admin_sees = admin_detail_res.json()["messages"]
    assert len(messages_admin_sees) == 3  # Opening + internal note + public response
    assert any(msg["is_internal_note"] for msg in messages_admin_sees)


def test_api_ticket_reopen_and_close(client_with_db):
    client, sub_id, _ = client_with_db
    headers = {"X-Subscriber-Id": str(sub_id)}

    # Create Ticket
    res = client.post(
        "/api/v1/support/tickets",
        json={"category": SupportTicketCategory.GUIDANCE.value, "subject": "Question", "description": "Details about subscription query"},
        headers=headers,
    )
    ticket_id = res.json()["ticket_id"]

    # Close Ticket
    close_res = client.post(f"/api/v1/support/tickets/{ticket_id}/close", headers=headers)
    assert close_res.status_code == 200
    assert close_res.json()["ticket_status"] == TicketStatus.CLOSED.value

    # Reopen Ticket
    reopen_res = client.post(
        f"/api/v1/support/tickets/{ticket_id}/reopen",
        json={"reopen_reason": "Issue recurred after latest app update"},
        headers=headers,
    )
    assert reopen_res.status_code == 200
    reopened = reopen_res.json()
    assert reopened["ticket_status"] == TicketStatus.REOPENED.value
    assert reopened["reopen_count"] == 1


# =============================================================================
# 3. Admin Support Triage & SLA Operations
# =============================================================================

def test_api_admin_triage_assign_resolve(client_with_db):
    client, sub_id, _ = client_with_db
    headers_parent = {"X-Subscriber-Id": str(sub_id)}
    admin_id = uuid.uuid4()
    headers_admin = {"X-Admin-Id": str(admin_id)}

    # Create Ticket
    create_res = client.post(
        "/api/v1/support/tickets",
        json={"category": SupportTicketCategory.LOGIN_ACCOUNT.value, "subject": "OTP not arriving", "description": "Mobile SMS delay on login attempt"},
        headers=headers_parent,
    )
    ticket_id = create_res.json()["ticket_id"]

    # Admin Triage List
    triage_res = client.get("/api/v1/admin/support/tickets", headers=headers_admin)
    assert triage_res.status_code == 200
    assert triage_res.json()["total"] >= 1

    # Admin Assign
    agent_id = uuid.uuid4()
    assign_res = client.post(
        f"/api/v1/admin/support/tickets/{ticket_id}/assign",
        json={"assigned_to": str(agent_id)},
        headers=headers_admin,
    )
    assert assign_res.status_code == 200
    assert assign_res.json()["assigned_to"] == str(agent_id)
    assert assign_res.json()["ticket_status"] == TicketStatus.IN_PROGRESS.value

    # Admin Resolve
    resolve_res = client.post(
        f"/api/v1/admin/support/tickets/{ticket_id}/resolve",
        json={"resolution_notes": "Telecom gateway route switched to backup provider."},
        headers=headers_admin,
    )
    assert resolve_res.status_code == 200
    assert resolve_res.json()["ticket_status"] == TicketStatus.RESOLVED.value
    assert resolve_res.json()["resolution_notes"] == "Telecom gateway route switched to backup provider."


def test_api_admin_sla_scan_and_metrics(client_with_db):
    client, _, _ = client_with_db
    headers_admin = {"X-Admin-Id": str(uuid.uuid4())}

    # Trigger SLA batch scan
    scan_res = client.post("/api/v1/admin/support/sla/scan", headers=headers_admin)
    assert scan_res.status_code == 200
    scan_data = scan_res.json()
    assert "total_active_tickets" in scan_data
    assert "audit_timestamp" in scan_data

    # Fetch SLA operational dashboard metrics
    metrics_res = client.get("/api/v1/admin/support/metrics", headers=headers_admin)
    assert metrics_res.status_code == 200
    metrics = metrics_res.json()
    assert "open_tickets" in metrics
    assert "breached_tickets" in metrics
    assert "overall_sla_compliance_pct" in metrics

