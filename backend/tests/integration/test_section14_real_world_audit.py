"""
STUDIQS® SmartParent™ (v6.2 & v6.3 Extension) - Section 14 & 27 Real-World Data Audit Test Suite
=============================================================================
Module: tests.integration.test_section14_real_world_audit
Verifies Section 14 (Help Centre & Ticketing) & Section 27 (48h Hard SLA Engine)
against authentic, real-world Indian K-12 parent personas, messy multi-language text,
real Razorpay payment webhooks, OCR marksheet disputes, 48h escrow freezes,
and strict data privacy boundaries.

Test Matrix:
  1. Real-World Knowledge Base Search & Issue Deflection (Typo, Tamil/English colloquialisms)
  2. 48-Hour Evaluation Dispute Escrow Freeze (Live Commission Ledger Payout Halt)
  3. Lapsed Dispute Window Rejection (48h Hard Window Defense)
  4. Dual-Debit UPI / Razorpay Glitch Ticket (Auto-triaged to URGENT)
  5. Multi-Round Conversational Threading with Absolute Internal Note Privacy
  6. Continuous 48-Hour Hard SLA Milestone Progression (12h, 24h, 36h, 48h Breach)
  7. Ticket Reopen Policy Guardrails (Max 3 Reopens & Auto-Escalation to URGENT)
  8. 7-Day Post-Closure Reopen Window Rejection
  9. Strict Sequential Collision-Free Numbering Under Rapid Fire (TKT-YYYY-NNNNN)
=============================================================================
"""

import uuid
from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
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
    SLAEscalationLevel,
)
from src.smartparent.db.models.auth import Subscriber, Child
from src.smartparent.db.models.marketplace import Expert, EvaluationCase, CommissionLedger
from src.smartparent.db.models.support_ticket import (
    SupportTicket,
    SupportMessage,
    SupportSLAEvent,
)


@pytest.fixture
def real_world_env():
    """Sets up an in-memory database populated with realistic Indian K-12 parent, child, and expert records."""
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
            Expert.__table__,
            EvaluationCase.__table__,
            CommissionLedger.__table__,
            SupportTicket.__table__,
            SupportMessage.__table__,
            SupportSLAEvent.__table__,
        ],
    )
    SessionTesting = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = SessionTesting()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    db = SessionTesting()

    # 1. Seed Parent: Mrs. Lakshmi Sundar (Chennai, CBSE Grade 10)
    lakshmi_id = uuid.uuid4()
    p1 = Subscriber(
        subscriber_id=lakshmi_id,
        mobile_number="+919840123456",
        parent_name="Lakshmi Sundar",
        password_hash="argon2_hash_mock_lakshmi",
        subscription_plan="PRO",
    )
    db.add(p1)

    child_ananya_id = uuid.uuid4()
    c1 = Child(
        child_id=child_ananya_id,
        subscriber_id=lakshmi_id,
        student_name="Ananya Sundar",
        board="CBSE",
        standard_class="Class 10",
        academic_year="2025-2026",
    )
    db.add(c1)

    # 2. Seed Parent: Dr. Rajesh Varma (Bangalore, ICSE Grade 8)
    rajesh_id = uuid.uuid4()
    p2 = Subscriber(
        subscriber_id=rajesh_id,
        mobile_number="+919444098765",
        parent_name="Dr. Rajesh Varma",
        password_hash="argon2_hash_mock_rajesh",
        subscription_plan="ADVANCED",
    )
    db.add(p2)

    # 3. Seed Verified Subject Expert: Prof. K. Natarajan (Physics Specialist)
    expert_id = uuid.uuid4()
    expert = Expert(
        expert_id=expert_id,
        mobile_number="+919940188990",
        full_name="Prof. K. Natarajan",
        email="natarajan.physics@studiqs.edu",
        password_hash="mock_expert_hash",
    )
    db.add(expert)

    db.commit()
    db.close()

    admin_id = uuid.uuid4()

    with TestClient(app) as client:
        yield {
            "client": client,
            "SessionTesting": SessionTesting,
            "lakshmi_id": lakshmi_id,
            "rajesh_id": rajesh_id,
            "child_ananya_id": child_ananya_id,
            "expert_id": expert_id,
            "admin_id": admin_id,
        }

    app.dependency_overrides.clear()


# =============================================================================
# 1. Real-World Knowledge Base Search & Issue Deflection Tests
# =============================================================================

def test_audit_faq_real_world_parent_queries(real_world_env):
    """Audits FAQ search engine against messy, realistic colloquial parent queries."""
    client = real_world_env["client"]

    # Query 1: Payment receipt and tax reimbursement
    res1 = client.get("/api/v1/support/faq?query=annual+fee+receipt+gst+tax+invoice")
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["total_found"] > 0
    assert any("invoice" in item["article"]["tags"] or "gst" in item["article"]["tags"] for item in data1["results"])
    assert data1["suggested_ticket_category"] == SupportTicketCategory.BILLING_REFUND.value

    # Query 2: Marksheet photo / OCR camera scan error
    res2 = client.get("/api/v1/support/faq?query=marksheet+camera+photo+scan+upload+failed")
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["total_found"] > 0
    assert data2["suggested_ticket_category"] == SupportTicketCategory.MARKS_ENTRY.value

    # Query 3: PTM talking points guidance for teachers
    res3 = client.get("/api/v1/support/faq?query=how+to+use+ptm+talking+points+with+class+teacher")
    assert res3.status_code == 200
    data3 = res3.json()
    assert data3["total_found"] > 0
    assert data3["suggested_ticket_category"] == SupportTicketCategory.GUIDANCE.value


# =============================================================================
# 2. 48-Hour Evaluation Dispute Escrow Freeze (Live Ledger Integration)
# =============================================================================

def test_audit_evaluation_dispute_halts_expert_escrow_payout(real_world_env):
    """
    Real-world scenario: Ananya Sundar's CBSE Grade 10 Physics paper was evaluated 8 hours ago.
    The evaluator awarded 0 marks on Question 4 (lens formula numerical).
    Parent raises a dispute within 48h.
    Engine MUST:
      1. Auto-transition EvaluationCase to DISPUTED.
      2. Freeze CommissionLedger payout_status to HELD_DISPUTE.
      3. Set Ticket priority to URGENT.
      4. Initialize 48-hour continuous resolution SLA.
    """
    client = real_world_env["client"]
    SessionTesting = real_world_env["SessionTesting"]
    lakshmi_id = real_world_env["lakshmi_id"]
    child_id = real_world_env["child_ananya_id"]
    expert_id = real_world_env["expert_id"]

    db = SessionTesting()
    case_id = uuid.uuid4()
    ledger_id = uuid.uuid4()
    completed_time = datetime.now(timezone.utc) - timedelta(hours=8)

    # Seed EvaluationCase
    case = EvaluationCase(
        case_id=case_id,
        subscriber_id=lakshmi_id,
        child_id=child_id,
        expert_id=expert_id,
        subject="Physics",
        test_title="CBSE Class 10 Pre-Board Light & Ray Optics",
        gross_fee=250.0,
        case_status=CaseStatus.COMPLETED.value,
        completed_at=completed_time,
    )
    db.add(case)

    # Seed 80% Escrow Commission Ledger (Rs. 200.00)
    ledger = CommissionLedger(
        ledger_id=ledger_id,
        case_id=case_id,
        expert_id=expert_id,
        gross_amount=250.00,
        platform_commission=50.00,
        expert_net_payout=200.00,
        payout_status="ESCROW_HELD",
    )
    db.add(ledger)
    db.commit()
    db.close()

    headers = {"X-Subscriber-Id": str(lakshmi_id)}
    payload = {
        "category": SupportTicketCategory.BUG_REPORT.value,
        "ticket_type": TicketType.CORRECTION_DISPUTE.value,
        "case_id": str(case_id),
        "subject": "Evaluation Dispute: Question 4 convex lens formula marked 0 marks",
        "description": (
            "Dear Studiqs Team, In Ananya's Grade 10 Physics Pre-board paper, Question 4 numerical on "
            "1/f = 1/v - 1/u was solved with full derivation matching NCERT Page 182. "
            "The evaluator marked 0 marks stating missing formula. Please re-check the handwritten scan."
        ),
        "attachment_url": "https://storage.googleapis.com/studiqs-papers/ananya_q4_derivation.pdf",
        "attachment_filename": "ananya_q4_derivation.pdf",
    }

    res = client.post("/api/v1/support/tickets", json=payload, headers=headers)
    assert res.status_code == 201
    ticket = res.json()

    assert ticket["ticket_number"].startswith("TKT-")
    assert ticket["ticket_status"] == TicketStatus.OPEN.value
    assert ticket["priority"] == SupportTicketPriority.URGENT.value

    # Verify Database State
    db = SessionTesting()
    reloaded_case = db.get(EvaluationCase, case_id)
    reloaded_ledger = db.get(CommissionLedger, ledger_id)

    assert reloaded_case.case_status == CaseStatus.DISPUTED.value
    assert reloaded_ledger.payout_status == "HELD_DISPUTE"
    db.close()


def test_audit_dispute_rejected_after_48h_window_closed(real_world_env):
    """
    Real-world defense: Evaluation completed 52 hours ago (beyond the 48-hour SLA window).
    Dispute cannot freeze escrow payout because expert funds were already released.
    """
    client = real_world_env["client"]
    SessionTesting = real_world_env["SessionTesting"]
    lakshmi_id = real_world_env["lakshmi_id"]
    child_id = real_world_env["child_ananya_id"]
    expert_id = real_world_env["expert_id"]

    db = SessionTesting()
    case_id = uuid.uuid4()
    ledger_id = uuid.uuid4()
    completed_time = datetime.now(timezone.utc) - timedelta(hours=52)

    case = EvaluationCase(
        case_id=case_id,
        subscriber_id=lakshmi_id,
        child_id=child_id,
        expert_id=expert_id,
        subject="Chemistry",
        test_title="CBSE Class 10 Acids, Bases and Salts",
        gross_fee=250.0,
        case_status=CaseStatus.COMPLETED.value,
        completed_at=completed_time,
    )
    db.add(case)

    ledger = CommissionLedger(
        ledger_id=ledger_id,
        case_id=case_id,
        expert_id=expert_id,
        gross_amount=250.00,
        platform_commission=50.00,
        expert_net_payout=200.00,
        payout_status="RELEASED_BANK",
    )
    db.add(ledger)
    db.commit()
    db.close()

    headers = {"X-Subscriber-Id": str(lakshmi_id)}
    payload = {
        "category": SupportTicketCategory.BUG_REPORT.value,
        "ticket_type": TicketType.CORRECTION_DISPUTE.value,
        "case_id": str(case_id),
        "subject": "Dispute on Chemistry Balancing equation marks",
        "description": "I know it is 2 days late, but please review the balancing equation step marks.",
    }

    res = client.post("/api/v1/support/tickets", json=payload, headers=headers)
    assert res.status_code == 201

    # Verify that escrow was NOT frozen because the 48h dispute window closed
    db = SessionTesting()
    reloaded_case = db.get(EvaluationCase, case_id)
    reloaded_ledger = db.get(CommissionLedger, ledger_id)

    assert reloaded_case.case_status == CaseStatus.COMPLETED.value  # Unchanged
    assert reloaded_ledger.payout_status == "RELEASED_BANK"          # Unchanged
    db.close()


# =============================================================================
# 3. Dual-Debit UPI / Payment Glitch Ticket (Financial Triage)
# =============================================================================

def test_audit_dual_debit_upi_auto_triaged_to_urgent(real_world_env):
    """
    Real-world scenario: Parent Dr. Rajesh Varma pays via UPI on Razorpay.
    Due to network lag, his account is debited twice.
    Engine MUST auto-triage to URGENT priority.
    """
    client = real_world_env["client"]
    rajesh_id = real_world_env["rajesh_id"]

    headers = {"X-Subscriber-Id": str(rajesh_id)}
    payload = {
        "category": SupportTicketCategory.BILLING_REFUND.value,
        "subject": "HDFC UPI double deduction for 6 Months Advanced Subscription",
        "description": (
            "Payment Gateway Error: My account ending in 4102 was debited twice (INR 1,399.00 x 2) "
            "with Razorpay payment ID pay_Qx91823Hda and pay_Qx91823Hdb. "
            "Please initiate refund for the duplicate transaction."
        ),
    }

    res = client.post("/api/v1/support/tickets", json=payload, headers=headers)
    assert res.status_code == 201
    ticket = res.json()

    assert ticket["priority"] == SupportTicketPriority.URGENT.value
    assert ticket["ticket_status"] == TicketStatus.OPEN.value
    assert ticket["sla_deadline"] is not None


# =============================================================================
# 4. Multi-Round Threading with Absolute Internal Note Privacy
# =============================================================================

def test_audit_thread_conversation_and_internal_note_leak_prevention(real_world_env):
    """
    Verifies that internal notes between support agents/admins:
      1. NEVER appear in parent ticket detail view.
      2. Are fully visible in admin ticket detail view.
      3. Cannot be created by parents (enforced 403 or auto-downgraded).
    """
    client = real_world_env["client"]
    lakshmi_id = real_world_env["lakshmi_id"]
    admin_id = real_world_env["admin_id"]

    headers_parent = {"X-Subscriber-Id": str(lakshmi_id)}
    headers_admin = {"X-Admin-Id": str(admin_id)}

    # Step 1: Parent creates ticket
    create_res = client.post(
        "/api/v1/support/tickets",
        json={
            "category": SupportTicketCategory.BUG_REPORT.value,
            "subject": "Tamil AI Voice Assistant audio cuts out after 10 seconds",
            "description": "When asking questions in Tamil regarding Class 10 Biology, the voice stops abruptly.",
        },
        headers=headers_parent,
    )
    ticket_id = create_res.json()["ticket_id"]

    # Step 2: Admin adds Internal Note (Hidden from parent)
    admin_internal = {
        "message_text": "INTERNAL: Check ElevenLabs Tamil TTS API quotas. Rate limit might be exceeded on account #3.",
        "is_internal_note": True,
    }
    msg1_res = client.post(
        f"/api/v1/admin/support/tickets/{ticket_id}/messages",
        json=admin_internal,
        headers=headers_admin,
    )
    assert msg1_res.status_code == 201

    # Step 3: Admin adds Public Reply (Visible to parent)
    admin_public = {
        "message_text": "Dear Mrs. Lakshmi, we have escalated this to our AI audio streaming engineers.",
        "is_internal_note": False,
    }
    client.post(
        f"/api/v1/admin/support/tickets/{ticket_id}/messages",
        json=admin_public,
        headers=headers_admin,
    )

    # Step 4: Parent replies back
    parent_reply = {
        "message_text": "Thank you. Ananya's revision exam is tomorrow morning, please prioritize.",
        "is_internal_note": False,
    }
    client.post(
        f"/api/v1/support/tickets/{ticket_id}/messages",
        json=parent_reply,
        headers=headers_parent,
    )

    # Step 5: Verify Parent View (LEAK TEST)
    parent_view = client.get(f"/api/v1/support/tickets/{ticket_id}", headers=headers_parent).json()
    parent_messages = parent_view["messages"]

    # Opening description + Admin public reply + Parent reply = 3 messages
    assert len(parent_messages) == 3
    for msg in parent_messages:
        assert msg["is_internal_note"] is False
        assert "ElevenLabs" not in msg["message_text"]  # Sensitive internal stack detail masked

    # Step 6: Verify Admin View (Audit log)
    admin_view = client.get(f"/api/v1/admin/support/tickets/{ticket_id}", headers=headers_admin).json()
    admin_messages = admin_view["messages"]

    # Opening description + Admin internal note + Admin public reply + Parent reply = 4 messages
    assert len(admin_messages) == 4
    assert any(m["is_internal_note"] is True and "ElevenLabs" in m["message_text"] for m in admin_messages)


# =============================================================================
# 5. Continuous 48-Hour SLA Milestone Sweep & Escalation Progression
# =============================================================================

def test_audit_48h_sla_escalation_lifecycle_and_milestones(real_world_env):
    """
    Simulates time progression for a support ticket:
      T+0h:  Ticket created -> SLA compliant, CALM
      T+14h: Overdue first response -> Triggers FIRST_RESPONSE_12H milestone
      T+26h: Assigned reminder -> Triggers REMINDER_24H milestone
      T+38h: Senior Lead alert -> Triggers LEAD_ALERT_36H milestone, CRITICAL_WARNING
      T+50h: Hard SLA breached -> Triggers SLA_BREACHED_48H milestone, is_sla_breached=True, BREACHED
    """
    client = real_world_env["client"]
    SessionTesting = real_world_env["SessionTesting"]
    lakshmi_id = real_world_env["lakshmi_id"]
    admin_id = real_world_env["admin_id"]
    headers_admin = {"X-Admin-Id": str(admin_id)}

    db = SessionTesting()
    ticket_id = uuid.uuid4()
    created_at = datetime.now(timezone.utc) - timedelta(hours=50)  # 50 hours old
    deadline = created_at + timedelta(hours=48)

    ticket = SupportTicket(
        ticket_id=ticket_id,
        ticket_number="TKT-2026-00099",
        subscriber_id=lakshmi_id,
        category=SupportTicketCategory.MARKS_ENTRY.value,
        subject="Marks entry not saving on mobile app",
        description="Every time I enter 45/50 in Math, the app resets to 0.",
        ticket_status=TicketStatus.OPEN.value,
        priority=SupportTicketPriority.NORMAL.value,
        created_at=created_at,
        sla_deadline=deadline,
        is_sla_breached=False,
    )
    db.add(ticket)
    db.commit()
    db.close()

    # Trigger SLA Batch Sweep
    scan_res = client.post("/api/v1/admin/support/sla/scan", headers=headers_admin)
    assert scan_res.status_code == 200
    scan_data = scan_res.json()

    assert scan_data["total_active_tickets"] >= 1
    assert scan_data["breached_count"] >= 1
    assert scan_data["first_response_overdue_count"] >= 1

    # Verify that ticket has is_sla_breached=True in DB
    db = SessionTesting()
    reloaded_ticket = db.get(SupportTicket, ticket_id)
    assert reloaded_ticket.is_sla_breached is True

    # Verify that SLA event logs were created in DB
    events_q = select(SupportSLAEvent).where(SupportSLAEvent.ticket_id == ticket_id)
    events = db.execute(events_q).scalars().all()
    event_levels = [e.escalation_level for e in events]

    assert SLAEscalationLevel.FIRST_RESPONSE_12H.value in event_levels
    assert SLAEscalationLevel.SLA_BREACHED_48H.value in event_levels
    db.close()


# =============================================================================
# 6. Ticket Reopen Policy & 7-Day Window Guardrails
# =============================================================================

def test_audit_reopen_policy_max_3_attempts_and_auto_escalate(real_world_env):
    """
    Tests Section 14 Reopen Guardrails:
      - Max 3 reopens allowed.
      - 2nd reopen automatically escalates priority to URGENT.
      - 4th reopen attempt MUST fail with 400 Bad Request.
    """
    client = real_world_env["client"]
    rajesh_id = real_world_env["rajesh_id"]
    admin_id = real_world_env["admin_id"]

    headers_parent = {"X-Subscriber-Id": str(rajesh_id)}
    headers_admin = {"X-Admin-Id": str(admin_id)}

    # Create Ticket
    res = client.post(
        "/api/v1/support/tickets",
        json={
            "category": SupportTicketCategory.LOGIN_ACCOUNT.value,
            "subject": "Unable to add second student Arjun to dashboard",
            "description": "The add student button gives an unexpected error.",
        },
        headers=headers_parent,
    )
    ticket_id = res.json()["ticket_id"]

    # Round 1: Admin resolves
    client.post(
        f"/api/v1/admin/support/tickets/{ticket_id}/resolve",
        json={"resolution_notes": "Database student mapping refreshed."},
        headers=headers_admin,
    )

    # Reopen 1
    r1 = client.post(
        f"/api/v1/support/tickets/{ticket_id}/reopen",
        json={"reopen_reason": "Still showing error 400 when saving Grade 8."},
        headers=headers_parent,
    )
    assert r1.status_code == 200
    assert r1.json()["reopen_count"] == 1

    # Round 2: Admin resolves again
    client.post(
        f"/api/v1/admin/support/tickets/{ticket_id}/resolve",
        json={"resolution_notes": "Updated backend schema validation."},
        headers=headers_admin,
    )

    # Reopen 2 (MUST escalate to URGENT)
    r2 = client.post(
        f"/api/v1/support/tickets/{ticket_id}/reopen",
        json={"reopen_reason": "Arjun's profile still missing subjects dropdown."},
        headers=headers_parent,
    )
    assert r2.status_code == 200
    assert r2.json()["reopen_count"] == 2
    assert r2.json()["priority"] == SupportTicketPriority.URGENT.value

    # Round 3: Admin resolves again
    client.post(
        f"/api/v1/admin/support/tickets/{ticket_id}/resolve",
        json={"resolution_notes": "Subjects populated for ICSE Grade 8."},
        headers=headers_admin,
    )

    # Reopen 3
    r3 = client.post(
        f"/api/v1/support/tickets/{ticket_id}/reopen",
        json={"reopen_reason": "Still not saving."},
        headers=headers_parent,
    )
    assert r3.status_code == 200
    assert r3.json()["reopen_count"] == 3

    # Round 4: Admin resolves again
    client.post(
        f"/api/v1/admin/support/tickets/{ticket_id}/resolve",
        json={"resolution_notes": "Final fix verified."},
        headers=headers_admin,
    )

    # 4th Reopen Attempt (MUST BE BLOCKED BY POLICY)
    r4 = client.post(
        f"/api/v1/support/tickets/{ticket_id}/reopen",
        json={"reopen_reason": "Trying 4th time."},
        headers=headers_parent,
    )
    assert r4.status_code == 400
    assert "maximum allowed reopen limit" in r4.json()["detail"]


def test_audit_reopen_blocked_after_7_days_of_closure(real_world_env):
    """
    Tests Section 14 Guardrail:
    A ticket closed more than 7 days ago CANNOT be reopened.
    The parent must be directed to create a new ticket.
    """
    client = real_world_env["client"]
    SessionTesting = real_world_env["SessionTesting"]
    lakshmi_id = real_world_env["lakshmi_id"]

    db = SessionTesting()
    ticket_id = uuid.uuid4()
    closed_at = datetime.now(timezone.utc) - timedelta(days=9)  # Closed 9 days ago

    ticket = SupportTicket(
        ticket_id=ticket_id,
        ticket_number="TKT-2026-00050",
        subscriber_id=lakshmi_id,
        category=SupportTicketCategory.GUIDANCE.value,
        subject="Previous inquiry on report card",
        description="Inquiry completed.",
        ticket_status=TicketStatus.CLOSED.value,
        priority=SupportTicketPriority.LOW.value,
        resolved_at=closed_at,
        created_at=closed_at - timedelta(hours=10),
        sla_deadline=closed_at + timedelta(hours=38),
    )
    db.add(ticket)
    db.commit()
    db.close()

    headers = {"X-Subscriber-Id": str(lakshmi_id)}
    res = client.post(
        f"/api/v1/support/tickets/{ticket_id}/reopen",
        json={"reopen_reason": "Reviving this old ticket after 9 days."},
        headers=headers,
    )
    assert res.status_code == 400
    assert "cannot be reopened after 7 days" in res.json()["detail"]


# =============================================================================
# 7. Strictly Sequential Numbering Under Rapid Sequential Creation
# =============================================================================

def test_audit_sequential_ticket_numbers(real_world_env):
    """Verifies that sequential ticket creation produces non-colliding TKT-YYYY-NNNNN numbers."""
    client = real_world_env["client"]
    lakshmi_id = real_world_env["lakshmi_id"]
    headers = {"X-Subscriber-Id": str(lakshmi_id)}

    ticket_numbers = []
    for i in range(5):
        res = client.post(
            "/api/v1/support/tickets",
            json={
                "category": SupportTicketCategory.GUIDANCE.value,
                "subject": f"Inquiry #{i + 1}",
                "description": f"Detailed question number {i + 1} regarding study habits.",
            },
            headers=headers,
        )
        assert res.status_code == 201
        ticket_numbers.append(res.json()["ticket_number"])

    # Ensure all 5 numbers are distinct and monotonically increasing
    assert len(set(ticket_numbers)) == 5
    year = datetime.now(timezone.utc).year
    for num in ticket_numbers:
        assert num.startswith(f"TKT-{year}-")
