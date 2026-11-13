"""
Unit Tests for STUDIQS® SmartParent™ Evaluation Case State Machine Engine (Engine 12)
Verifies:
  - Validated state transitions across 9-step case lifecycle
  - Illegal state transition rejections (e.g., ASSIGNED -> COMPLETED)
  - 48-Hour SLA turnaround tracking and breach detection
  - 20% Platform / 80% Expert net financial escrow calculation
  - 48-Hour post-completion dispute lock
  - Question-level evaluation summary & mastery tier assignment
  - Fail-safe fallback and CircuitBreaker stability
"""

import pytest
from datetime import datetime, timedelta, timezone
from src.smartparent.engines.case_workflow import (
    CaseWorkflowEngine,
    CaseTransitionPayloadSchema,
    CaseWorkflowResultSchema,
    QuestionScoreItemSchema,
)
from src.smartparent.core.constants import CaseStatus, MasteryTier


@pytest.fixture
def workflow_engine():
    return CaseWorkflowEngine()


# ==============================================================================
# 1. State Machine Legal Transitions
# ==============================================================================

def test_transition_assigned_to_awaiting_upload(workflow_engine):
    payload = {
        "case_id": "CASE-001",
        "current_status": CaseStatus.ASSIGNED,
        "target_status": CaseStatus.AWAITING_UPLOAD,
        "actor_type": "EXPERT",
        "gross_fee": 250.0,
    }
    result = workflow_engine.execute(payload)

    assert isinstance(result, CaseWorkflowResultSchema)
    assert result.transition_allowed is True
    assert result.previous_status == "ASSIGNED"
    assert result.new_status == "AWAITING_UPLOAD"


def test_transition_awaiting_upload_to_submitted(workflow_engine):
    now = datetime.now(timezone.utc)
    payload = {
        "case_id": "CASE-002",
        "current_status": CaseStatus.AWAITING_UPLOAD,
        "target_status": CaseStatus.SUBMITTED,
        "actor_type": "PARENT",
        "answer_sheet_path": "uploads/cases/CASE-002/answers.pdf",
        "submitted_at": now,
        "gross_fee": 500.0,
    }
    result = workflow_engine.execute(payload)

    assert result.transition_allowed is True
    assert result.new_status == "SUBMITTED"
    assert result.sla_info["sla_target_hours"] == 48.0
    assert result.sla_info["hours_elapsed"] == 0.0
    assert result.sla_info["is_breached"] is False


def test_transition_submitted_to_under_review(workflow_engine):
    now = datetime.now(timezone.utc)
    payload = {
        "case_id": "CASE-003",
        "current_status": CaseStatus.SUBMITTED,
        "target_status": CaseStatus.UNDER_REVIEW,
        "actor_type": "EXPERT",
        "submitted_at": now - timedelta(hours=4),
        "gross_fee": 250.0,
    }
    result = workflow_engine.execute(payload)

    assert result.transition_allowed is True
    assert result.new_status == "UNDER_REVIEW"
    assert result.sla_info["hours_elapsed"] >= 3.9
    assert result.sla_info["is_breached"] is False


def test_transition_under_review_to_completed_with_evaluations(workflow_engine):
    now = datetime.now(timezone.utc)
    evaluations = [
        {"question_no": 1, "topic": "Trigonometry", "marks_scored": 4.0, "max_marks": 5.0},
        {"question_no": 2, "topic": "Trigonometry", "marks_scored": 5.0, "max_marks": 5.0},
        {"question_no": 3, "topic": "Linear Equations", "marks_scored": 2.0, "max_marks": 5.0},
        {"question_no": 4, "topic": "Probability", "marks_scored": 5.0, "max_marks": 5.0},
    ]

    payload = {
        "case_id": "CASE-004",
        "current_status": CaseStatus.UNDER_REVIEW,
        "target_status": CaseStatus.COMPLETED,
        "actor_type": "EXPERT",
        "evaluated_pdf_path": "evaluations/graded/CASE-004.pdf",
        "gross_fee": 500.0,
        "submitted_at": now - timedelta(hours=18),
        "completed_at": now,
        "evaluations": evaluations,
        "expert_feedback": "Excellent work in Trigonometry. Practice required in Linear Equations word problems."
    }
    result = workflow_engine.execute(payload)

    assert result.transition_allowed is True
    assert result.new_status == "COMPLETED"

    # Financial Escrow Split: 20% platform (₹100), 80% expert (₹400)
    fin = result.financial_info
    assert fin["gross_fee"] == 500.0
    assert fin["platform_commission"] == 100.0
    assert fin["expert_net_payout"] == 400.0
    assert fin["escrow_status"] == "HELD"
    assert fin["dispute_eligible"] is True

    # Evaluation Summary Check: 16/20 marks = 80.0% -> STRONG tier
    ev = result.evaluation_summary
    assert ev["total_scored_marks"] == 16.0
    assert ev["total_max_marks"] == 20.0
    assert ev["percentage"] == 80.0
    assert ev["mastery_tier"] == MasteryTier.STRONG.value
    assert any(w["topic"] == "Linear Equations" for w in ev["weak_topics"])


# ==============================================================================
# 2. Illegal Transition Rejections
# ==============================================================================

def test_illegal_jump_from_assigned_to_completed_rejected(workflow_engine):
    """Case cannot jump directly to COMPLETED without submission and review."""
    payload = {
        "case_id": "CASE-005",
        "current_status": CaseStatus.ASSIGNED,
        "target_status": CaseStatus.COMPLETED,
        "actor_type": "EXPERT",
    }
    result = workflow_engine.execute(payload)
    assert result.transition_allowed is False
    assert "Illegal state transition" in result.transition_message


def test_completed_cannot_transition_to_awaiting_upload(workflow_engine):
    payload = {
        "case_id": "CASE-006",
        "current_status": CaseStatus.COMPLETED,
        "target_status": CaseStatus.AWAITING_UPLOAD,
        "actor_type": "EXPERT",
    }
    result = workflow_engine.execute(payload)
    assert result.transition_allowed is False


# ==============================================================================
# 3. 48-Hour Dispute Window
# ==============================================================================

def test_dispute_allowed_within_48h(workflow_engine):
    now = datetime.now(timezone.utc)
    payload = {
        "case_id": "CASE-007",
        "current_status": CaseStatus.COMPLETED,
        "target_status": CaseStatus.DISPUTED,
        "actor_type": "PARENT",
        "completed_at": now - timedelta(hours=24),  # 24 hours ago (within 48h window)
        "dispute_reason": "Question 3 marks calculation error on step 2.",
        "gross_fee": 250.0,
    }
    result = workflow_engine.execute(payload)

    assert result.transition_allowed is True
    assert result.new_status == "DISPUTED"
    assert result.financial_info["escrow_status"] == "FROZEN_DISPUTE"


def test_dispute_rejected_after_48h_window_expired(workflow_engine):
    now = datetime.now(timezone.utc)
    payload = {
        "case_id": "CASE-008",
        "current_status": CaseStatus.COMPLETED,
        "target_status": CaseStatus.DISPUTED,
        "actor_type": "PARENT",
        "completed_at": now - timedelta(hours=50),  # 50 hours ago (window closed!)
        "dispute_reason": "Re-evaluation request after deadline.",
        "gross_fee": 250.0,
    }
    result = workflow_engine.execute(payload)

    assert result.transition_allowed is False
    assert "Dispute window expired" in result.transition_message


# ==============================================================================
# 4. SLA Breach Detection
# ==============================================================================

def test_sla_breach_detection(workflow_engine):
    now = datetime.now(timezone.utc)
    payload = {
        "case_id": "CASE-009",
        "current_status": CaseStatus.SUBMITTED,
        "target_status": CaseStatus.UNDER_REVIEW,
        "actor_type": "EXPERT",
        "submitted_at": now - timedelta(hours=55),  # 55 hours ago (>48h SLA)
        "gross_fee": 250.0,
    }
    result = workflow_engine.execute(payload)

    assert result.transition_allowed is True
    assert result.sla_info["is_breached"] is True
    assert result.sla_info["urgency_level"] == "BREACHED"
    assert result.sla_info["hours_elapsed"] >= 54.9


# ==============================================================================
# 5. Circuit Breaker Integration
# ==============================================================================

def test_case_workflow_circuit_breaker(workflow_engine):
    workflow_engine.circuit_breaker.failure_threshold = 2

    class CrashingPayload:
        def __bool__(self):
            return True
        def __getattr__(self, name):
            raise RuntimeError("Workflow crash")

    workflow_engine.execute(CrashingPayload())
    workflow_engine.execute(CrashingPayload())

    assert workflow_engine.circuit_breaker.is_open()
    workflow_engine.reset_circuit()
    assert workflow_engine.circuit_breaker.is_closed()
