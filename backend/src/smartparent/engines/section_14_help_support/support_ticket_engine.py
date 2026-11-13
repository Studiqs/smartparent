"""
STUDIQS® SmartParent™ (v6.2 Complete) - Support Ticket State Machine & Triage Engine
=============================================================================
Module: src.smartparent.engines.section_14_help_support.support_ticket_engine
Section 14: Help Centre, Ticketing and Support Operating Models (Human Ticketing Tier)

Governs:
  1. Human-Readable Sequential Ticket Number Generator (TKT-YYYY-NNNNN)
  2. Complete 6-State Ticket Lifecycle State Machine:
     OPEN → IN_PROGRESS → AWAITING_CUSTOMER → RESOLVED → CLOSED (with REOPENED loop)
  3. Continuous 48-Hour SLA Deadline Computation (Created At + 48 Hours)
  4. Marketplace 48-Hour Evaluation Dispute Escrow Freeze Automation:
     - Freezes expert commission disbursement in 48-hour escrow pending administrative review.
     - Transitions evaluation case status to DISPUTED.
  5. Intelligent Priority & Triage Categorization:
     - Auto-assigns URGENT/HIGH priority to payment issues and dispute cases.
  6. Reopen Policy & Guardrails:
     - Enforces max 3 reopens with auto-escalation to Senior Support Lead.
=============================================================================
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple, Union
from pydantic import BaseModel, Field, ConfigDict

from src.smartparent.engines.section_00_core.base_engine import BaseEngine
from src.smartparent.core.constants import (
    TicketType,
    TicketStatus,
    SupportTicketCategory,
    SupportTicketPriority,
    CaseStatus,
    ESCROW_DISPUTE_WINDOW_HOURS,
)
from src.smartparent.core.exceptions import TicketStateTransitionError

logger = logging.getLogger("STUDIQS_SupportTicketEngine")


# =============================================================================
# 1. State Machine Legal Transitions Definition
# =============================================================================

LEGAL_TICKET_TRANSITIONS: Dict[str, List[str]] = {
    TicketStatus.OPEN.value: [
        TicketStatus.IN_PROGRESS.value,
        TicketStatus.AWAITING_CUSTOMER.value,
        TicketStatus.RESOLVED.value,
        TicketStatus.CLOSED.value,
    ],
    TicketStatus.IN_PROGRESS.value: [
        TicketStatus.AWAITING_CUSTOMER.value,
        TicketStatus.RESOLVED.value,
        TicketStatus.CLOSED.value,
    ],
    TicketStatus.AWAITING_CUSTOMER.value: [
        TicketStatus.IN_PROGRESS.value,
        TicketStatus.RESOLVED.value,
        TicketStatus.CLOSED.value,
    ],
    TicketStatus.RESOLVED.value: [
        TicketStatus.CLOSED.value,
        TicketStatus.REOPENED.value,
    ],
    TicketStatus.REOPENED.value: [
        TicketStatus.IN_PROGRESS.value,
        TicketStatus.AWAITING_CUSTOMER.value,
        TicketStatus.RESOLVED.value,
        TicketStatus.CLOSED.value,
    ],
    TicketStatus.CLOSED.value: [
        TicketStatus.REOPENED.value,  # Allowed within 7 days of closure
    ],
}


# =============================================================================
# 2. Pydantic Schemas for Engine Input & Output
# =============================================================================

class TicketCreationInputSchema(BaseModel):
    """Payload to create a new support ticket."""
    model_config = ConfigDict(extra="ignore")

    subscriber_id: str
    category: str
    subject: str
    description: str
    ticket_type: Optional[str] = None
    case_id: Optional[str] = None
    priority: Optional[str] = None
    created_at: Optional[datetime] = None


class TicketCreationResultSchema(BaseModel):
    """Result of newly initialized support ticket."""
    model_config = ConfigDict(extra="ignore")

    ticket_number: str
    category: str
    priority: str
    ticket_status: str = "OPEN"
    sla_deadline: datetime
    is_dispute_ticket: bool = False
    dispute_freeze_info: Optional[Dict[str, Any]] = None
    auto_triage_note: str


class TicketTransitionInputSchema(BaseModel):
    """Payload to transition ticket lifecycle state."""
    model_config = ConfigDict(extra="ignore")

    current_status: str
    target_status: str
    actor_role: str  # 'PARENT', 'SUPPORT_AGENT', 'ADMIN', 'SYSTEM'
    resolution_notes: Optional[str] = None
    reopen_reason: Optional[str] = None
    current_reopen_count: int = 0
    closed_at: Optional[datetime] = None


class TicketTransitionResultSchema(BaseModel):
    """Result of state transition validation."""
    model_config = ConfigDict(extra="ignore")

    is_allowed: bool
    previous_status: str
    new_status: str
    transition_timestamp: datetime
    increment_reopen_count: bool = False
    escalated_priority: Optional[str] = None
    message: str


# =============================================================================
# 3. Production Support Ticket Engine Implementation
# =============================================================================

class SupportTicketEngine(BaseEngine):
    """
    Section 14 & 27 Support Ticket Lifecycle Engine.
    Handles sequential numbering, legal state transitions, automated priority triage,
    and 48-hour evaluation dispute escrow freeze.
    """

    MAX_REOPENS_ALLOWED: int = 3
    REOPEN_WINDOW_DAYS: int = 7
    HARD_SLA_HOURS: int = 48

    def __init__(self, failure_threshold: int = 5):
        super().__init__(name="SupportTicketEngine", failure_threshold=failure_threshold)

    # -------------------------------------------------------------------------
    # BaseEngine Lifecycle Hooks
    # -------------------------------------------------------------------------

    def validate_input(self, input_data: Any) -> Dict[str, Any]:
        """Validates incoming ticket operation payload."""
        if not isinstance(input_data, dict):
            raise ValueError("Input to SupportTicketEngine must be a dictionary")

        action = str(input_data.get("action", "CREATE")).upper()
        if action not in ["CREATE", "TRANSITION", "EVALUATE_DISPUTE"]:
            raise ValueError(f"Unknown action '{action}' for SupportTicketEngine")

        return {"action": action, "payload": input_data}

    def execute_core(self, validated_data: Dict[str, Any]) -> Any:
        """Dispatches to specific support ticket domain logic."""
        action = validated_data["action"]
        payload = validated_data["payload"]

        if action == "CREATE":
            seq = int(payload.get("sequence_number", 1))
            return self.process_ticket_creation(payload, sequence_number=seq)
        elif action == "TRANSITION":
            return self.process_status_transition(payload)
        elif action == "EVALUATE_DISPUTE":
            return self.evaluate_evaluation_dispute(
                case_id=payload["case_id"],
                case_status=payload["case_status"],
                completed_at=payload.get("completed_at"),
            )

    def fallback(self, error: Exception, input_data: Any) -> Any:
        """Safe fallback response preventing API failure."""
        self.logger.warning("SupportTicketEngine fallback invoked: %s", error)
        now = datetime.now(timezone.utc)
        return TicketCreationResultSchema(
            ticket_number="TKT-FALLBACK-00000",
            category=SupportTicketCategory.GUIDANCE.value,
            priority=SupportTicketPriority.NORMAL.value,
            ticket_status=TicketStatus.OPEN.value,
            sla_deadline=now + timedelta(hours=48),
            is_dispute_ticket=False,
            auto_triage_note=f"Degraded fallback: {str(error)[:100]}"
        )

    # -------------------------------------------------------------------------
    # Core Domain Logic: Ticket Creation & Triage
    # -------------------------------------------------------------------------

    @classmethod
    def format_ticket_number(cls, sequence_number: int, created_at: Optional[datetime] = None) -> str:
        """
        Formats collision-proof, human-readable ticket numbers:
        Format: TKT-YYYY-NNNNN (e.g., TKT-2026-00042)
        """
        dt = created_at or datetime.now(timezone.utc)
        year = dt.year
        return f"TKT-{year}-{sequence_number:05d}"

    @classmethod
    def calculate_sla_deadline(cls, created_at: Optional[datetime] = None) -> datetime:
        """
        Continuous 48-Hour Hard SLA clock (Section 27).
        Calculates exact deadline 48 hours after ticket creation (includes weekends).
        """
        base_time = created_at or datetime.now(timezone.utc)
        return base_time + timedelta(hours=cls.HARD_SLA_HOURS)

    def evaluate_priority_and_triage(
        self,
        category: str,
        subject: str,
        description: str,
        ticket_type: Optional[str] = None
    ) -> Tuple[str, str]:
        """
        Deterministic auto-prioritizer for support tickets.
        Returns: (priority, triage_note)
        """
        combined = f"{subject} {description}".lower()
        t_type = (ticket_type or "").upper()
        cat = category.upper()

        # 1. URGENT: Financial & Evaluation Dispute Breaches
        if t_type == TicketType.CORRECTION_DISPUTE.value or "dispute" in combined:
            return SupportTicketPriority.URGENT.value, "48h Marketplace evaluation dispute flagged. Escrow payout held."

        if (
            t_type == TicketType.PAYMENT_ISSUE.value
            or "double deduction" in combined
            or "charged twice" in combined
            or "double charged" in combined
            or "double charge" in combined
        ):
            return SupportTicketPriority.URGENT.value, "Payment failure or duplicate transaction reported."

        # 2. HIGH: Turnaround Delays & Plan Access Lockouts
        if t_type == TicketType.EXPERT_DELAY.value or "delay" in combined or "overdue" in combined:
            return SupportTicketPriority.HIGH.value, "Expert 48h turnaround delay reported."

        if cat == SupportTicketCategory.BILLING_REFUND.value or "refund" in combined:
            return SupportTicketPriority.HIGH.value, "Refund or subscription cancellation requested."

        if cat == SupportTicketCategory.LOGIN_ACCOUNT.value and ("locked" in combined or "otp" in combined):
            return SupportTicketPriority.HIGH.value, "Account access or OTP delivery blocked."

        # 3. LOW: Suggestions & Feedback
        if "feedback" in combined or "suggestion" in combined or "enhancement" in combined:
            return SupportTicketPriority.LOW.value, "General product feedback or non-blocking inquiry."

        # 4. NORMAL: Standard Support Flow
        return SupportTicketPriority.NORMAL.value, "Standard user support inquiry routed to general queue."

    @staticmethod
    def _parse_datetime(dt_val: Any) -> Optional[datetime]:
        """Safely parses datetime string or object to timezone-aware UTC datetime."""
        if not dt_val:
            return None
        if isinstance(dt_val, datetime):
            if dt_val.tzinfo is None:
                return dt_val.replace(tzinfo=timezone.utc)
            return dt_val
        if isinstance(dt_val, str):
            try:
                cleaned = dt_val.replace("Z", "+00:00")
                parsed = datetime.fromisoformat(cleaned)
                if parsed.tzinfo is None:
                    return parsed.replace(tzinfo=timezone.utc)
                return parsed
            except Exception:
                return None
        return None

    def process_ticket_creation(
        self,
        payload: Dict[str, Any],
        sequence_number: int = 1
    ) -> TicketCreationResultSchema:
        """Processes and enriches a new support ticket creation payload."""
        now = self._parse_datetime(payload.get("created_at")) or datetime.now(timezone.utc)

        ticket_number = self.format_ticket_number(sequence_number, created_at=now)
        sla_deadline = self.calculate_sla_deadline(created_at=now)

        category = str(payload.get("category", SupportTicketCategory.GUIDANCE.value)).upper()
        subject = str(payload.get("subject", "Support Request"))
        description = str(payload.get("description", ""))
        ticket_type = payload.get("ticket_type")
        case_id = payload.get("case_id")

        # Auto-evaluate priority unless explicitly overridden
        auto_prio, triage_note = self.evaluate_priority_and_triage(
            category=category,
            subject=subject,
            description=description,
            ticket_type=ticket_type
        )
        final_priority = str(payload.get("priority") or auto_prio).upper()

        # Dispute Escrow Freeze check
        is_dispute = False
        dispute_freeze = None
        if case_id and (ticket_type == TicketType.CORRECTION_DISPUTE.value or "dispute" in subject.lower()):
            is_dispute = True
            dispute_freeze = {
                "case_id": case_id,
                "freeze_escrow": True,
                "flagged_at": now.isoformat(),
                "reason": f"Dispute ticket {ticket_number} created by subscriber.",
                "target_case_status": CaseStatus.DISPUTED.value,
            }

        return TicketCreationResultSchema(
            ticket_number=ticket_number,
            category=category,
            priority=final_priority,
            ticket_status=TicketStatus.OPEN.value,
            sla_deadline=sla_deadline,
            is_dispute_ticket=is_dispute,
            dispute_freeze_info=dispute_freeze,
            auto_triage_note=triage_note
        )

    # -------------------------------------------------------------------------
    # Core Domain Logic: State Machine Transitions
    # -------------------------------------------------------------------------

    def process_status_transition(
        self,
        payload: Dict[str, Any]
    ) -> TicketTransitionResultSchema:
        """
        Validates and executes lifecycle state transition for a ticket.
        Enforces strict role permissions and transition legality.
        """
        curr = str(payload.get("current_status", "")).upper()
        target = str(payload.get("target_status", "")).upper()
        role = str(payload.get("actor_role", "SUPPORT_AGENT")).upper()
        reopen_count = int(payload.get("current_reopen_count", 0))
        closed_at = payload.get("closed_at")
        now = datetime.now(timezone.utc)

        # 1. Validate Legal Target in State Graph
        legal_targets = LEGAL_TICKET_TRANSITIONS.get(curr, [])
        if target not in legal_targets:
            raise TicketStateTransitionError(current_status=curr, attempted_status=target)

        # 2. Reopen Rules & Boundaries
        increment_reopen = False
        escalated_prio = None

        if target == TicketStatus.REOPENED.value:
            if reopen_count >= self.MAX_REOPENS_ALLOWED:
                raise ValueError(
                    f"Ticket has reached the maximum allowed reopen limit ({self.MAX_REOPENS_ALLOWED}). "
                    "Please create a new ticket or request an administrative escalation."
                )

            # Check 7-day reopen window if closing timestamp is provided
            parsed_closed = self._parse_datetime(closed_at)
            if parsed_closed:
                elapsed_days = (now - parsed_closed).total_seconds() / 86400.0
                if elapsed_days > self.REOPEN_WINDOW_DAYS:
                    raise ValueError(
                        f"Ticket cannot be reopened after {self.REOPEN_WINDOW_DAYS} days of closure. "
                        "Please open a fresh support ticket."
                    )

            increment_reopen = True
            # If reopened 2+ times, automatically escalate to URGENT for senior intervention
            if reopen_count >= 1:
                escalated_prio = SupportTicketPriority.URGENT.value

        # 3. Role-Based Permissions
        if role == "PARENT":
            # Parents can only transition to REOPENED or mark their own ticket as CLOSED/RESOLVED
            if target not in [TicketStatus.REOPENED.value, TicketStatus.CLOSED.value, TicketStatus.RESOLVED.value]:
                raise ValueError(f"Parents cannot transition ticket directly to '{target}'.")

        return TicketTransitionResultSchema(
            is_allowed=True,
            previous_status=curr,
            new_status=target,
            transition_timestamp=now,
            increment_reopen_count=increment_reopen,
            escalated_priority=escalated_prio,
            message=f"Ticket successfully transitioned from {curr} to {target}."
        )

    # -------------------------------------------------------------------------
    # Core Domain Logic: Evaluation Dispute Escrow Freeze
    # -------------------------------------------------------------------------

    @classmethod
    def evaluate_evaluation_dispute(
        cls,
        case_id: str,
        case_status: Union[CaseStatus, str],
        completed_at: Optional[Union[datetime, str]] = None
    ) -> Dict[str, Any]:
        """
        Section 14 & 21 Dispute Freeze Rule:
        If a parent flags an evaluation dispute within the 48-hour escrow window,
        the 80% expert payout is frozen pending administrative review.
        """
        now = datetime.now(timezone.utc)
        status_str = case_status.value if isinstance(case_status, CaseStatus) else str(case_status).upper()

        if status_str != CaseStatus.COMPLETED.value:
            return {
                "case_id": case_id,
                "dispute_eligible": False,
                "freeze_escrow": False,
                "reason": f"Disputes can only be raised for COMPLETED evaluations. Current status is {status_str}."
            }

        parsed_completed = cls._parse_datetime(completed_at)
        if parsed_completed:
            hours_elapsed = (now - parsed_completed).total_seconds() / 3600.0
            if hours_elapsed > ESCROW_DISPUTE_WINDOW_HOURS:
                return {
                    "case_id": case_id,
                    "dispute_eligible": False,
                    "freeze_escrow": False,
                    "hours_elapsed": round(hours_elapsed, 1),
                    "reason": f"The 48-hour dispute window has closed ({hours_elapsed:.1f} hours elapsed since completion). Escrow payout already released."
                }

        return {
            "case_id": case_id,
            "dispute_eligible": True,
            "freeze_escrow": True,
            "target_case_status": CaseStatus.DISPUTED.value,
            "reason": "Dispute raised within 48-hour escrow window. Expert payout frozen pending administrative review."
        }
