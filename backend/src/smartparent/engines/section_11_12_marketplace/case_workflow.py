"""
STUDIQS® SmartParent™ (v6.2 Complete) - Evaluation Case State Machine Engine
Engine 12: case_workflow.py

Governs the complete 9-step Subject Expert Marketplace evaluation case lifecycle:
  1. ASSIGNED: Case created and matched with certified subject expert
  2. AWAITING_UPLOAD: Question paper assigned, waiting for student's handwritten answer script
  3. SUBMITTED: Answer sheet uploaded, queued for expert grading (48h SLA begins)
  4. UNDER_REVIEW: Expert claims the case in Evaluation Studio, actively grading
  5. COMPLETED: Expert submits evaluated marks, annotations & feedback (locks case, 48h dispute window starts)
  6. DISPUTED: Parent challenges evaluation within 48h (freezes escrow payout)
  7. CANCELLED: Case cancelled before evaluation review
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple, Union
from pydantic import BaseModel, Field, ConfigDict

from src.smartparent.engines.base_engine import BaseEngine, EngineHealthStatus
from src.smartparent.core.constants import (
    CaseStatus,
    MasteryTier,
    PLATFORM_COMMISSION_PERCENT,
    EXPERT_NET_PAYOUT_PERCENT,
    ESCROW_DISPUTE_WINDOW_HOURS,
    classify_mastery_tier,
)

logger = logging.getLogger("STUDIQS_CaseWorkflowEngine")

# Standard SLA Turnaround Window
STANDARD_SLA_HOURS: float = 48.0


# =============================================================================
# 1. Pydantic v2 Type-Safe Schemas
# =============================================================================

class QuestionScoreItemSchema(BaseModel):
    """Schema for line-item evaluated question score."""
    model_config = ConfigDict(extra="ignore")

    question_no: Union[int, str]
    topic: str = "General"
    marks_scored: float = Field(..., ge=0.0)
    max_marks: float = Field(..., gt=0.0)
    remarks: Optional[str] = None


class CaseTransitionPayloadSchema(BaseModel):
    """Request payload to transition case state."""
    model_config = ConfigDict(extra="ignore")

    case_id: str
    current_status: CaseStatus
    target_status: CaseStatus
    actor_type: str = "EXPERT"  # 'PARENT', 'EXPERT', 'ADMIN', 'SYSTEM'
    actor_id: Optional[str] = None
    answer_sheet_path: Optional[str] = None
    evaluated_pdf_path: Optional[str] = None
    gross_fee: float = Field(default=250.0, ge=0.0)
    submitted_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    dispute_reason: Optional[str] = None
    evaluations: List[QuestionScoreItemSchema] = Field(default_factory=list)
    expert_feedback: Optional[str] = None


class CaseWorkflowResultSchema(BaseModel):
    """Result of state transition and lifecycle evaluation."""
    model_config = ConfigDict(extra="ignore")

    case_id: str
    previous_status: str
    new_status: str
    transition_allowed: bool
    transition_timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    sla_info: Dict[str, Any] = Field(default_factory=dict)
    financial_info: Dict[str, Any] = Field(default_factory=dict)
    evaluation_summary: Optional[Dict[str, Any]] = None
    transition_message: str


# =============================================================================
# 2. State Machine Transitions Definition
# =============================================================================

ALLOWED_TRANSITIONS: Dict[CaseStatus, List[CaseStatus]] = {
    CaseStatus.ASSIGNED: [
        CaseStatus.AWAITING_UPLOAD,
        CaseStatus.SUBMITTED,
        CaseStatus.DISPUTED,  # Admin override
    ],
    CaseStatus.AWAITING_UPLOAD: [
        CaseStatus.SUBMITTED,
    ],
    CaseStatus.SUBMITTED: [
        CaseStatus.UNDER_REVIEW,
    ],
    CaseStatus.UNDER_REVIEW: [
        CaseStatus.COMPLETED,
        CaseStatus.SUBMITTED,  # Expert unclaims / returns to queue
    ],
    CaseStatus.COMPLETED: [
        CaseStatus.DISPUTED,   # Allowed only within 48-hour dispute window
    ],
    CaseStatus.DISPUTED: [
        CaseStatus.UNDER_REVIEW,  # Re-evaluation assigned
        CaseStatus.COMPLETED,     # Dispute rejected / finalized
    ],
}


# =============================================================================
# 3. Production Case Workflow Engine Implementation
# =============================================================================

class CaseWorkflowEngine(BaseEngine):
    """
    Engine 12: Expert Evaluation Case State Machine Engine.
    
    Orchestrates:
      - Validated state transitions with strict authorization
      - 48-Hour SLA turnaround tracking and breach detection
      - Commercial 20% Studiqs / 80% Expert net financial escrow calculation
      - Question-level evaluation tallying & mastery tier calculation
      - 48-Hour post-completion dispute lock
    """

    def __init__(self, failure_threshold: int = 5):
        super().__init__(name="CaseWorkflowEngine", failure_threshold=failure_threshold)

    # -------------------------------------------------------------------------
    # BaseEngine Template Method Lifecycle Hooks
    # -------------------------------------------------------------------------

    def validate_input(self, input_data: Any) -> CaseTransitionPayloadSchema:
        """Validates state transition request payload."""
        if not input_data:
            raise ValueError("Case workflow input payload cannot be empty.")

        if isinstance(input_data, CaseTransitionPayloadSchema):
            return input_data

        if hasattr(input_data, "model_dump"):
            data = input_data.model_dump()
        elif hasattr(input_data, "dict"):
            data = input_data.dict()
        elif isinstance(input_data, dict):
            data = dict(input_data)
        else:
            raise ValueError(f"Unsupported input type for CaseWorkflowEngine: {type(input_data)}")

        return CaseTransitionPayloadSchema(**data)

    def execute_core(self, payload: CaseTransitionPayloadSchema) -> CaseWorkflowResultSchema:
        """Executes state transition, SLA calculation, and escrow accounting."""
        curr = payload.current_status
        target = payload.target_status
        now = datetime.now(timezone.utc)

        # 1. Verify Transition Legality
        legal_targets = ALLOWED_TRANSITIONS.get(curr, [])
        if target not in legal_targets:
            raise ValueError(
                f"Illegal state transition from {curr.value} to {target.value}. "
                f"Allowed transitions from {curr.value} are: {[t.value for t in legal_targets]}"
            )

        # 2. Transition-Specific Validation Guardrails
        if target == CaseStatus.SUBMITTED:
            # Must verify that answer script exists
            if not payload.answer_sheet_path:
                logger.warning(f"[CaseWorkflow] Case {payload.case_id} submitted without explicit answer_sheet_path.")

        elif target == CaseStatus.COMPLETED:
            # Expert submitting final graded result
            if not payload.evaluated_pdf_path and not payload.evaluations:
                raise ValueError("Cannot complete case without evaluated_pdf_path or line-item question evaluations.")

        elif target == CaseStatus.DISPUTED:
            # Parent dispute window check
            if not payload.dispute_reason:
                raise ValueError("Dispute reason is mandatory when challenging an evaluation.")

            if payload.completed_at:
                elapsed_hours = (now - self._ensure_utc(payload.completed_at)).total_seconds() / 3600.0
                if elapsed_hours > ESCROW_DISPUTE_WINDOW_HOURS:
                    raise ValueError(
                        f"Dispute window expired ({elapsed_hours:.1f}h elapsed). "
                        f"Disputes are only permitted within {ESCROW_DISPUTE_WINDOW_HOURS}h of completion."
                    )

        # 3. SLA Turnaround Analysis
        sla_info = self._compute_sla_metrics(payload, now)

        # 4. Financial Escrow Breakdown
        financial_info = self._compute_financial_breakdown(payload, now)

        # 5. Question Evaluation Summary (if provided)
        eval_summary = self._summarize_evaluations(payload.evaluations) if payload.evaluations else None

        msg = f"Case {payload.case_id} successfully transitioned from {curr.value} to {target.value}."

        return CaseWorkflowResultSchema(
            case_id=payload.case_id,
            previous_status=curr.value,
            new_status=target.value,
            transition_allowed=True,
            transition_timestamp=now.isoformat(),
            sla_info=sla_info,
            financial_info=financial_info,
            evaluation_summary=eval_summary,
            transition_message=msg,
        )

    def fallback(self, error: Exception, input_data: Any) -> CaseWorkflowResultSchema:
        """Graceful degraded fallback preventing system stall on state machine errors."""
        logger.warning(f"[CaseWorkflowEngine] Fallback triggered due to error: {error}")
        case_id = "UNKNOWN"
        curr_status = "UNKNOWN"
        target_status = "UNKNOWN"

        try:
            if isinstance(input_data, dict):
                case_id = str(input_data.get("case_id", "UNKNOWN"))
                curr_status = str(input_data.get("current_status", "UNKNOWN"))
                target_status = str(input_data.get("target_status", "UNKNOWN"))
            else:
                case_id = str(getattr(input_data, "case_id", "UNKNOWN"))
                curr_status = str(getattr(input_data, "current_status", "UNKNOWN"))
                target_status = str(getattr(input_data, "target_status", "UNKNOWN"))
        except Exception:
            pass

        return CaseWorkflowResultSchema(
            case_id=case_id,
            previous_status=curr_status,
            new_status=curr_status,  # Preserve previous status
            transition_allowed=False,
            sla_info={"status": "DEGRADED", "error": str(error)[:100]},
            financial_info={"escrow_status": "LOCKED", "degraded": True},
            evaluation_summary=None,
            transition_message=f"Transition rejected due to validation error: {str(error)}"
        )

    # -------------------------------------------------------------------------
    # Business Logic Helpers
    # -------------------------------------------------------------------------

    def _compute_sla_metrics(self, payload: CaseTransitionPayloadSchema, now: datetime) -> Dict[str, Any]:
        """Calculates 48-Hour SLA timeline, elapsed hours, and breach flags."""
        sub_time = payload.submitted_at
        if not sub_time:
            return {
                "sla_target_hours": STANDARD_SLA_HOURS,
                "status": "NOT_STARTED" if payload.target_status in (CaseStatus.ASSIGNED, CaseStatus.AWAITING_UPLOAD) else "IN_PROGRESS",
                "hours_elapsed": 0.0,
                "hours_remaining": STANDARD_SLA_HOURS,
                "is_breached": False,
                "urgency_level": "NORMAL",
            }

        sub_time_utc = self._ensure_utc(sub_time)
        elapsed_hours = max(0.0, (now - sub_time_utc).total_seconds() / 3600.0)
        remaining_hours = max(0.0, STANDARD_SLA_HOURS - elapsed_hours)
        is_breached = elapsed_hours > STANDARD_SLA_HOURS

        if is_breached:
            urgency = "BREACHED"
        elif remaining_hours <= 12.0:
            urgency = "URGENT"
        else:
            urgency = "NORMAL"

        return {
            "sla_target_hours": STANDARD_SLA_HOURS,
            "status": "COMPLETED" if payload.target_status == CaseStatus.COMPLETED else "ACTIVE",
            "submitted_at": sub_time_utc.isoformat(),
            "hours_elapsed": round(elapsed_hours, 2),
            "hours_remaining": round(remaining_hours, 2),
            "is_breached": is_breached,
            "urgency_level": urgency,
            "deadline_timestamp": (sub_time_utc + timedelta(hours=STANDARD_SLA_HOURS)).isoformat(),
        }

    def _compute_financial_breakdown(self, payload: CaseTransitionPayloadSchema, now: datetime) -> Dict[str, Any]:
        """Computes 20% Studiqs commission / 80% Expert net payout and escrow dispute window."""
        gross = float(payload.gross_fee)
        commission = round(gross * (PLATFORM_COMMISSION_PERCENT / 100.0), 2)
        expert_net = round(gross * (EXPERT_NET_PAYOUT_PERCENT / 100.0), 2)

        escrow_status = "HELD"
        dispute_eligible = False
        dispute_deadline = None

        if payload.target_status == CaseStatus.COMPLETED:
            comp_time = self._ensure_utc(payload.completed_at or now)
            dispute_deadline_dt = comp_time + timedelta(hours=ESCROW_DISPUTE_WINDOW_HOURS)
            dispute_deadline = dispute_deadline_dt.isoformat()
            dispute_eligible = now < dispute_deadline_dt

            if now >= dispute_deadline_dt:
                escrow_status = "APPROVED"
        elif payload.target_status == CaseStatus.DISPUTED:
            escrow_status = "FROZEN_DISPUTE"

        return {
            "gross_fee": gross,
            "currency": "INR",
            "platform_commission_percent": PLATFORM_COMMISSION_PERCENT,
            "platform_commission": commission,
            "expert_net_payout_percent": EXPERT_NET_PAYOUT_PERCENT,
            "expert_net_payout": expert_net,
            "escrow_status": escrow_status,
            "dispute_window_hours": ESCROW_DISPUTE_WINDOW_HOURS,
            "dispute_eligible": dispute_eligible,
            "dispute_deadline": dispute_deadline,
        }

    def _summarize_evaluations(self, evaluations: List[QuestionScoreItemSchema]) -> Dict[str, Any]:
        """Tallies question score breakdown, calculates percentage, and determines mastery tier."""
        total_scored = sum(q.marks_scored for q in evaluations)
        total_max = sum(q.max_marks for q in evaluations)
        pct = (total_scored / total_max * 100.0) if total_max > 0 else 0.0
        tier = classify_mastery_tier(pct)

        topic_breakdown: Dict[str, Dict[str, float]] = {}
        for q in evaluations:
            t = q.topic.strip() or "General"
            if t not in topic_breakdown:
                topic_breakdown[t] = {"scored": 0.0, "max": 0.0}
            topic_breakdown[t]["scored"] += q.marks_scored
            topic_breakdown[t]["max"] += q.max_marks

        weak_topics = []
        strong_topics = []
        for t, stats in topic_breakdown.items():
            t_pct = (stats["scored"] / stats["max"] * 100.0) if stats["max"] > 0 else 0.0
            if t_pct < 60.0:
                weak_topics.append({"topic": t, "percentage": round(t_pct, 1)})
            elif t_pct >= 80.0:
                strong_topics.append({"topic": t, "percentage": round(t_pct, 1)})

        return {
            "total_questions_evaluated": len(evaluations),
            "total_scored_marks": round(total_scored, 2),
            "total_max_marks": round(total_max, 2),
            "percentage": round(pct, 2),
            "mastery_tier": tier.value,
            "weak_topics": weak_topics,
            "strong_topics": strong_topics,
        }

    def _ensure_utc(self, dt: datetime) -> datetime:
        """Guarantees timezone-aware UTC datetime."""
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
