"""
STUDIQS® SmartParent™ (v6.2 & v6.3 Extension) - Section 14 & 27 Unit Test Suite
=============================================================================
Module: tests.unit.test_section14_help_support
Verifies:
  1. Self-Service FAQ Search, Keyword Scoring & Issue Deflection
  2. Support Ticket Sequential Numbering (TKT-YYYY-NNNNN)
  3. Continuous 48-Hour Hard SLA Countdown & Deadlines
  4. Auto-Triage & Priority Heuristics (URGENT, HIGH, NORMAL, LOW)
  5. 6-State Ticket Lifecycle State Machine & Transition Legality
  6. Reopen Policy Boundaries (Max 3 Reopens & Escalation to URGENT)
  7. Marketplace 48-Hour Evaluation Dispute Escrow Freeze Automation
  8. SLA Escalation Engine: 12h, 24h, 36h, and 48h Milestone Escalations
  9. Batch SLA Audit Operational Health Telemetry
  10. Multi-Party Threaded Messaging, First Response Auto-Stamping & Internal Note Isolation
=============================================================================
"""

import uuid
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.smartparent.db.base import Base
from src.smartparent.core.constants import (
    TicketStatus,
    TicketType,
    SupportTicketCategory,
    SupportTicketPriority,
    SupportSenderRole,
    SLAEscalationLevel,
    CaseStatus,
)
from src.smartparent.core.exceptions import (
    SmartParentException,
    TicketStateTransitionError,
)
from src.smartparent.db.models.auth import Subscriber, Child
from src.smartparent.db.models.support_ticket import (
    SupportTicket,
    SupportMessage,
    SupportSLAEvent,
)
from src.smartparent.db.models.marketplace import (
    EvaluationCase,
    CommissionLedger,
)
from src.smartparent.engines.section_14_help_support.self_service_faq_engine import (
    SelfServiceFAQEngine,
)
from src.smartparent.engines.section_14_help_support.support_ticket_engine import (
    SupportTicketEngine,
)
from src.smartparent.engines.section_14_help_support.sla_escalation_engine import (
    SLAEscalationEngine,
)
from src.smartparent.services.support_service import SupportService
from src.smartparent.schemas.support import (
    FAQSearchRequest,
    TicketCreateRequest,
    TicketResolveRequest,
    TicketReopenRequest,
    SupportMessageCreateRequest,
)


# =============================================================================
# In-Memory SQLite Test Fixtures
# =============================================================================

@pytest.fixture
def in_memory_db():
    """Provides isolated SQLite in-memory DB for Section 14 testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    # Create required tables
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
        ]
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def sample_subscriber(in_memory_db):
    """Creates a sample subscriber for support testing."""
    sub = Subscriber(
        subscriber_id=uuid.uuid4(),
        mobile_number="9876543210",
        parent_name="Suresh Kumar",
        email="suresh@example.com",
        password_hash="mock_hash_123",
        subscription_plan="ADVANCED",
    )
    in_memory_db.add(sub)
    in_memory_db.commit()
    in_memory_db.refresh(sub)
    return sub


# =============================================================================
# 1. Self-Service FAQ Engine Tests
# =============================================================================

def test_self_service_faq_browse_defaults():
    engine = SelfServiceFAQEngine()
    res = engine.execute_core({"query": "", "limit": 5})
    assert res.total_found >= 3
    assert len(res.results) <= 5
    assert res.results[0].relevance_score >= 1.0


def test_self_service_faq_keyword_search_pricing():
    engine = SelfServiceFAQEngine()
    res = engine.execute_core({"query": "subscription pricing plans cost", "limit": 5})
    assert res.total_found > 0
    top_match = res.results[0]
    assert "FAQ-BILL-001" in top_match.article.article_id
    assert "pricing" in top_match.matched_terms or "exact_title" in top_match.matched_terms
    assert res.suggested_ticket_category == SupportTicketCategory.BILLING_REFUND.value


def test_self_service_faq_dispute_search():
    engine = SelfServiceFAQEngine()
    res = engine.execute_core({"query": "dispute evaluation 48h escrow", "limit": 5})
    assert res.total_found > 0
    article_ids = [r.article.article_id for r in res.results]
    assert "FAQ-EXP-002" in article_ids or "FAQ-EXP-001" in article_ids


def test_self_service_faq_category_filter():
    engine = SelfServiceFAQEngine()
    res = engine.execute_core({
        "query": "",
        "category": SupportTicketCategory.MARKS_ENTRY.value,
        "limit": 10
    })
    assert res.total_found > 0
    for r in res.results:
        assert r.article.category == SupportTicketCategory.MARKS_ENTRY.value


# =============================================================================
# 2. Support Ticket State Machine & Triage Engine Tests
# =============================================================================

def test_ticket_number_formatting():
    engine = SupportTicketEngine()
    dt = datetime(2026, 11, 15, 10, 0, 0, tzinfo=timezone.utc)
    tkt_num = engine.format_ticket_number(42, created_at=dt)
    assert tkt_num == "TKT-2026-00042"


def test_continuous_48h_sla_deadline_computation():
    engine = SupportTicketEngine()
    start = datetime(2026, 10, 24, 14, 30, 0, tzinfo=timezone.utc)
    deadline = engine.calculate_sla_deadline(created_at=start)
    assert deadline == start + timedelta(hours=48)
    # Verify continuous clock: Saturday 14:30 + 48h = Monday 14:30
    assert deadline == datetime(2026, 10, 26, 14, 30, 0, tzinfo=timezone.utc)


def test_ticket_auto_triage_priorities():
    engine = SupportTicketEngine()

    # Dispute -> URGENT
    prio, note = engine.evaluate_priority_and_triage(
        category=SupportTicketCategory.BUG_REPORT.value,
        subject="Dispute expert marks",
        description="Marks are wrong",
        ticket_type=TicketType.CORRECTION_DISPUTE.value,
    )
    assert prio == SupportTicketPriority.URGENT.value

    # Payment Issue -> URGENT
    prio, _ = engine.evaluate_priority_and_triage(
        category=SupportTicketCategory.BILLING_REFUND.value,
        subject="Payment charged twice",
        description="Duplicate deduction via UPI",
        ticket_type=TicketType.PAYMENT_ISSUE.value,
    )
    assert prio == SupportTicketPriority.URGENT.value

    # Expert Delay -> HIGH
    prio, _ = engine.evaluate_priority_and_triage(
        category=SupportTicketCategory.BUG_REPORT.value,
        subject="Evaluation delayed",
        description="More than 48 hours elapsed",
        ticket_type=TicketType.EXPERT_DELAY.value,
    )
    assert prio == SupportTicketPriority.HIGH.value

    # General Question -> NORMAL
    prio, _ = engine.evaluate_priority_and_triage(
        category=SupportTicketCategory.GUIDANCE.value,
        subject="How to export PTM pack",
        description="Need printable PDF for school meeting",
    )
    assert prio == SupportTicketPriority.NORMAL.value


def test_ticket_legal_state_transitions():
    engine = SupportTicketEngine()

    # OPEN -> IN_PROGRESS
    res1 = engine.process_status_transition({
        "current_status": TicketStatus.OPEN.value,
        "target_status": TicketStatus.IN_PROGRESS.value,
        "actor_role": "SUPPORT_AGENT",
    })
    assert res1.is_allowed is True
    assert res1.new_status == TicketStatus.IN_PROGRESS.value

    # IN_PROGRESS -> RESOLVED
    res2 = engine.process_status_transition({
        "current_status": TicketStatus.IN_PROGRESS.value,
        "target_status": TicketStatus.RESOLVED.value,
        "actor_role": "SUPPORT_AGENT",
    })
    assert res2.is_allowed is True

    # RESOLVED -> CLOSED
    res3 = engine.process_status_transition({
        "current_status": TicketStatus.RESOLVED.value,
        "target_status": TicketStatus.CLOSED.value,
        "actor_role": "PARENT",
    })
    assert res3.is_allowed is True


def test_ticket_illegal_transition_rejection():
    engine = SupportTicketEngine()
    # Cannot jump directly from OPEN to REOPENED
    with pytest.raises(TicketStateTransitionError) as exc_info:
        engine.process_status_transition({
            "current_status": TicketStatus.OPEN.value,
            "target_status": TicketStatus.REOPENED.value,
            "actor_role": "PARENT",
        })
    assert "Cannot transition support ticket from 'OPEN' to 'REOPENED'" in str(exc_info.value)


def test_ticket_reopen_policy_and_escalation():
    engine = SupportTicketEngine()

    # 1st reopen -> allowed, normal priority
    res1 = engine.process_status_transition({
        "current_status": TicketStatus.RESOLVED.value,
        "target_status": TicketStatus.REOPENED.value,
        "actor_role": "PARENT",
        "current_reopen_count": 0,
    })
    assert res1.is_allowed is True
    assert res1.increment_reopen_count is True
    assert res1.escalated_priority is None

    # 2nd reopen -> auto-escalates to URGENT
    res2 = engine.process_status_transition({
        "current_status": TicketStatus.RESOLVED.value,
        "target_status": TicketStatus.REOPENED.value,
        "actor_role": "PARENT",
        "current_reopen_count": 1,
    })
    assert res2.is_allowed is True
    assert res2.escalated_priority == SupportTicketPriority.URGENT.value

    # 4th reopen -> exceeds max allowed (3)
    with pytest.raises(ValueError) as exc_info:
        engine.process_status_transition({
            "current_status": TicketStatus.RESOLVED.value,
            "target_status": TicketStatus.REOPENED.value,
            "actor_role": "PARENT",
            "current_reopen_count": 3,
        })
    assert "maximum allowed reopen limit" in str(exc_info.value)


def test_dispute_escrow_freeze_within_window():
    engine = SupportTicketEngine()
    completed_time = datetime.now(timezone.utc) - timedelta(hours=12)

    res = engine.evaluate_evaluation_dispute(
        case_id="CASE-101",
        case_status=CaseStatus.COMPLETED,
        completed_at=completed_time,
    )
    assert res["dispute_eligible"] is True
    assert res["freeze_escrow"] is True
    assert res["target_case_status"] == CaseStatus.DISPUTED.value


def test_dispute_rejected_after_48h_window():
    engine = SupportTicketEngine()
    completed_time = datetime.now(timezone.utc) - timedelta(hours=50)

    res = engine.evaluate_evaluation_dispute(
        case_id="CASE-102",
        case_status=CaseStatus.COMPLETED,
        completed_at=completed_time,
    )
    assert res["dispute_eligible"] is False
    assert res["freeze_escrow"] is False
    assert "48-hour dispute window has closed" in res["reason"]


# =============================================================================
# 3. 48-Hour Hard SLA Escalation Engine Tests
# =============================================================================

def test_sla_engine_countdown_and_milestones():
    engine = SLAEscalationEngine()
    base_time = datetime(2026, 10, 20, 10, 0, 0, tzinfo=timezone.utc)

    # 1. At 5 hours: Calm, on track
    t5 = base_time + timedelta(hours=5)
    t_data_5 = {
        "ticket_id": "T1",
        "ticket_number": "TKT-2026-00001",
        "ticket_status": "OPEN",
        "created_at": base_time,
        "first_response_at": None,
        "is_sla_breached": False,
    }
    tele5 = engine.evaluate_ticket_sla(t_data_5, current_time=t5)
    assert tele5.elapsed_hours == 5.0
    assert tele5.remaining_hours == 43.0
    assert tele5.urgency_level == "CALM"
    assert len(tele5.new_milestone_events) == 0

    # 2. At 13 hours without agent response: First response overdue!
    t13 = base_time + timedelta(hours=13)
    tele13 = engine.evaluate_ticket_sla(t_data_5, current_time=t13)
    assert tele13.is_first_response_overdue is True
    assert tele13.urgency_level == "ATTENTION_NEEDED"
    assert SLAEscalationLevel.FIRST_RESPONSE_12H.value in tele13.new_milestone_events

    # 3. At 25 hours: 24h reminder
    t25 = base_time + timedelta(hours=25)
    tele25 = engine.evaluate_ticket_sla(
        t_data_5,
        existing_milestones={SLAEscalationLevel.FIRST_RESPONSE_12H.value},
        current_time=t25
    )
    assert SLAEscalationLevel.REMINDER_24H.value in tele25.new_milestone_events

    # 4. At 37 hours: Lead Alert (Critical Warning)
    t37 = base_time + timedelta(hours=37)
    tele37 = engine.evaluate_ticket_sla(
        t_data_5,
        existing_milestones={
            SLAEscalationLevel.FIRST_RESPONSE_12H.value,
            SLAEscalationLevel.REMINDER_24H.value,
        },
        current_time=t37
    )
    assert tele37.urgency_level == "CRITICAL_WARNING"
    assert SLAEscalationLevel.LEAD_ALERT_36H.value in tele37.new_milestone_events

    # 5. At 49 hours: HARD SLA BREACHED!
    t49 = base_time + timedelta(hours=49)
    tele49 = engine.evaluate_ticket_sla(
        t_data_5,
        existing_milestones={
            SLAEscalationLevel.FIRST_RESPONSE_12H.value,
            SLAEscalationLevel.REMINDER_24H.value,
            SLAEscalationLevel.LEAD_ALERT_36H.value,
        },
        current_time=t49
    )
    assert tele49.is_sla_breached is True
    assert tele49.urgency_level == "BREACHED"
    assert SLAEscalationLevel.SLA_BREACHED_48H.value in tele49.new_milestone_events


def test_sla_engine_resolved_ticket_stops_escalations():
    engine = SLAEscalationEngine()
    base_time = datetime(2026, 10, 20, 10, 0, 0, tzinfo=timezone.utc)
    t_resolved = {
        "ticket_id": "T2",
        "ticket_number": "TKT-2026-00002",
        "ticket_status": "RESOLVED",
        "created_at": base_time,
        "first_response_at": base_time + timedelta(hours=4),
        "is_sla_breached": False,
    }
    # Evaluated at 50h
    tele = engine.evaluate_ticket_sla(t_resolved, current_time=base_time + timedelta(hours=50))
    # Should NOT be breached because it was resolved
    assert tele.is_sla_breached is False
    assert len(tele.new_milestone_events) == 0


def test_sla_batch_audit_summary():
    engine = SLAEscalationEngine()
    now = datetime.now(timezone.utc)

    tickets = [
        # Ticket 1: 5h old (Compliant)
        {"ticket_id": "1", "ticket_number": "TKT-1", "ticket_status": "OPEN", "created_at": now - timedelta(hours=5)},
        # Ticket 2: 38h old (At Risk)
        {"ticket_id": "2", "ticket_number": "TKT-2", "ticket_status": "IN_PROGRESS", "created_at": now - timedelta(hours=38), "first_response_at": now - timedelta(hours=30)},
        # Ticket 3: 52h old (Breached)
        {"ticket_id": "3", "ticket_number": "TKT-3", "ticket_status": "IN_PROGRESS", "created_at": now - timedelta(hours=52), "is_sla_breached": False},
        # Ticket 4: Terminal (Resolved) -> Should be ignored
        {"ticket_id": "4", "ticket_number": "TKT-4", "ticket_status": "RESOLVED", "created_at": now - timedelta(hours=60)},
    ]

    summary = engine.run_batch_sla_audit(tickets=tickets, current_time=now)
    assert summary.total_active_tickets == 3
    assert summary.sla_compliant_count == 1
    assert summary.at_risk_count == 1
    assert summary.breached_count == 1
    assert summary.overall_compliance_rate_pct == 66.7
    assert len(summary.escalations_to_dispatch) > 0


# =============================================================================
# 4. End-to-End SupportService Database Tests
# =============================================================================

def test_support_service_create_and_first_response_workflow(in_memory_db, sample_subscriber):
    service = SupportService(in_memory_db)

    # 1. Create Ticket
    create_req = TicketCreateRequest(
        category=SupportTicketCategory.MARKS_ENTRY.value,
        subject="Report card table missing Hindi marks",
        description="The scanned photo cropped the bottom table row for Hindi. Please help adjust.",
        priority="NORMAL",
    )
    ticket_resp = service.create_ticket(
        subscriber_id=sample_subscriber.subscriber_id,
        payload=create_req,
    )
    assert ticket_resp.ticket_number.startswith("TKT-")
    assert ticket_resp.ticket_status == TicketStatus.OPEN.value
    assert ticket_resp.first_response_at is None
    assert ticket_resp.is_sla_breached is False

    t_uuid = uuid.UUID(ticket_resp.ticket_id)

    # 2. Agent Posts First Response (Public)
    agent_id = uuid.uuid4()
    msg_req = SupportMessageCreateRequest(
        message_text="Hello Suresh, we have re-aligned the OCR coordinates and restored your child's Hindi marks.",
        is_internal_note=False,
    )
    agent_msg = service.add_message(
        ticket_id=t_uuid,
        sender_id=agent_id,
        sender_role="SUPPORT_AGENT",
        payload=msg_req,
    )
    assert agent_msg.sender_role == "SUPPORT_AGENT"

    # Verify first_response_at was automatically stamped and status moved to IN_PROGRESS
    db_ticket = in_memory_db.get(SupportTicket, t_uuid)
    assert db_ticket.first_response_at is not None
    assert db_ticket.ticket_status == TicketStatus.IN_PROGRESS.value

    # 3. Agent Posts Internal Note (Hidden from parent)
    note_req = SupportMessageCreateRequest(
        message_text="[INTERNAL] Confirmed OCR bounding box fix was applied via fitz table extraction.",
        is_internal_note=True,
    )
    service.add_message(
        ticket_id=t_uuid,
        sender_id=agent_id,
        sender_role="SUPPORT_AGENT",
        payload=note_req,
    )

    # 4. Check Parent View (Internal note must be masked!)
    parent_view = service.get_ticket_detail(
        ticket_id=t_uuid,
        requesting_user_id=sample_subscriber.subscriber_id,
        user_role="PARENT",
    )
    assert len(parent_view.messages) == 2  # Initial message + Agent public reply (Internal note hidden!)
    assert not any(m.is_internal_note for m in parent_view.messages)

    # 5. Check Admin View (Internal note visible!)
    admin_view = service.get_ticket_detail(
        ticket_id=t_uuid,
        requesting_user_id=agent_id,
        user_role="ADMIN",
    )
    assert len(admin_view.messages) == 3  # All 3 messages visible to admin
    assert any(m.is_internal_note for m in admin_view.messages)

    # 6. Resolve Ticket
    resolve_req = TicketResolveRequest(resolution_notes="Hindi marks updated to 74/100 as per original school marksheet.")
    resolved_resp = service.resolve_ticket(
        ticket_id=t_uuid,
        payload=resolve_req,
        agent_id=agent_id,
    )
    assert resolved_resp.ticket_status == TicketStatus.RESOLVED.value
    assert resolved_resp.resolved_at is not None

    # 7. Parent Reopens Ticket
    reopen_req = TicketReopenRequest(reopen_reason="Thank you, but the grade tier shows Band 2 instead of Band 1.")
    reopened_resp = service.reopen_ticket(
        ticket_id=t_uuid,
        subscriber_id=sample_subscriber.subscriber_id,
        payload=reopen_req,
    )
    assert reopened_resp.ticket_status == TicketStatus.REOPENED.value
    assert reopened_resp.reopen_count == 1


def test_support_service_evaluation_dispute_escrow_freeze(in_memory_db, sample_subscriber):
    service = SupportService(in_memory_db)
    now = datetime.now(timezone.utc)

    # Create child, completed EvaluationCase and CommissionLedger
    case_id = uuid.uuid4()
    expert_id = uuid.uuid4()
    child_id = uuid.uuid4()

    child = Child(
        child_id=child_id,
        subscriber_id=sample_subscriber.subscriber_id,
        student_name="Ananya Kumar",
        standard_class="Class 10",
        board="CBSE",
    )
    in_memory_db.add(child)

    case = EvaluationCase(
        case_id=case_id,
        subscriber_id=sample_subscriber.subscriber_id,
        child_id=child_id,
        expert_id=expert_id,
        subject="Physics",
        test_title="Mid-Term Assessment",
        case_status=CaseStatus.COMPLETED.value,
        completed_at=now - timedelta(hours=6),  # Completed 6 hours ago (within 48h window)
        gross_fee=250.0,
    )
    in_memory_db.add(case)

    ledger = CommissionLedger(
        ledger_id=uuid.uuid4(),
        case_id=case_id,
        expert_id=expert_id,
        gross_amount=250.0,
        platform_commission=50.0,
        expert_net_payout=200.0,
        payout_status="HELD",
    )
    in_memory_db.add(ledger)
    in_memory_db.commit()

    # Parent creates dispute ticket
    dispute_req = TicketCreateRequest(
        category=SupportTicketCategory.BUG_REPORT.value,
        ticket_type=TicketType.CORRECTION_DISPUTE.value,
        case_id=str(case_id),
        subject="Dispute Question 2 Ohm's Law grading",
        description="The formula derivation was correct. Expert deducted 2 marks unfairly.",
    )
    ticket_resp = service.create_ticket(
        subscriber_id=sample_subscriber.subscriber_id,
        payload=dispute_req,
    )

    # Assert priority was auto-escalated to URGENT
    assert ticket_resp.priority == SupportTicketPriority.URGENT.value

    # Verify case status transitioned to DISPUTED
    in_memory_db.refresh(case)
    assert case.case_status == CaseStatus.DISPUTED.value

    # Verify ledger payout was frozen
    in_memory_db.refresh(ledger)
    assert ledger.payout_status == "HELD_DISPUTE"
