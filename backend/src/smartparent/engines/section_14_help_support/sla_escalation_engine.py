"""
STUDIQS® SmartParent™ (v6.3 Extension) - 48-Hour Support SLA Escalation Engine
=============================================================================
Module: src.smartparent.engines.section_14_help_support.sla_escalation_engine
Section 27: 48-Hour Hard SLA Support Operating Model with Continuous Escalation

Core Capabilities:
  1. Continuous 48-Hour Hard SLA Countdown Calculator (Includes weekends).
  2. 4 Automated Escalation Milestones:
     - 12h: First Human Response Overdue (FIRST_RESPONSE_12H)
     - 24h: Assigned Agent Operational Reminder (REMINDER_24H)
     - 36h: Senior Support Lead Escalation Alert (LEAD_ALERT_36H)
     - 48h: Hard SLA Breach with is_sla_breached Flag (SLA_BREACHED_48H)
  3. Real-Time Ticket Urgency Classification (CALM, ATTENTION_NEEDED, CRITICAL_WARNING, BREACHED).
  4. Batch SLA Health Audit Scanner for Operational Dashboard & Triage.
=============================================================================
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Union
from pydantic import BaseModel, Field, ConfigDict

from src.smartparent.engines.section_00_core.base_engine import BaseEngine
from src.smartparent.core.constants import (
    SLAEscalationLevel,
    TicketStatus,
    SUPPORT_SLA_TOTAL_HOURS,
    SUPPORT_SLA_FIRST_RESPONSE_HOURS,
    SUPPORT_SLA_REMINDER_HOURS,
    SUPPORT_SLA_LEAD_ALERT_HOURS,
)

logger = logging.getLogger("STUDIQS_SLAEscalationEngine")


# =============================================================================
# 1. Pydantic v2 Schemas for SLA Telemetry
# =============================================================================

class TicketSLATelemetry(BaseModel):
    """Detailed SLA calculation metrics for a single support ticket."""
    model_config = ConfigDict(extra="ignore")

    ticket_id: str
    ticket_number: str
    ticket_status: str
    priority: str
    created_at: datetime
    sla_deadline: datetime
    elapsed_hours: float
    remaining_hours: float
    progress_percentage: float
    is_first_response_pending: bool
    is_first_response_overdue: bool
    first_response_at: Optional[datetime] = None
    is_sla_breached: bool
    urgency_level: str  # 'CALM', 'ATTENTION_NEEDED', 'CRITICAL_WARNING', 'BREACHED'
    new_milestone_events: List[str] = Field(default_factory=list)


class SLABatchAuditSummary(BaseModel):
    """Aggregate SLA health telemetry across all active support tickets."""
    model_config = ConfigDict(extra="ignore")

    total_active_tickets: int
    sla_compliant_count: int
    first_response_overdue_count: int
    at_risk_count: int
    breached_count: int
    overall_compliance_rate_pct: float
    audit_timestamp: str
    escalations_to_dispatch: List[Dict[str, Any]] = Field(default_factory=list)


# =============================================================================
# 2. Production SLA Escalation Engine Implementation
# =============================================================================

class SLAEscalationEngine(BaseEngine):
    """
    Section 27 Continuous 48-Hour Support SLA Engine.
    Evaluates real-time countdowns, milestone thresholds, and automated escalations.
    """

    TOTAL_SLA_HOURS: float = float(SUPPORT_SLA_TOTAL_HOURS)              # 48.0 Hours
    FIRST_RESPONSE_HOURS: float = float(SUPPORT_SLA_FIRST_RESPONSE_HOURS) # 12.0 Hours
    REMINDER_HOURS: float = float(SUPPORT_SLA_REMINDER_HOURS)            # 24.0 Hours
    LEAD_ALERT_HOURS: float = float(SUPPORT_SLA_LEAD_ALERT_HOURS)        # 36.0 Hours

    TERMINAL_STATUSES: Set[str] = {
        TicketStatus.RESOLVED.value,
        TicketStatus.CLOSED.value,
    }

    def __init__(self, failure_threshold: int = 5):
        super().__init__(name="SLAEscalationEngine", failure_threshold=failure_threshold)

    # -------------------------------------------------------------------------
    # BaseEngine Lifecycle Hooks
    # -------------------------------------------------------------------------

    def validate_input(self, input_data: Any) -> Dict[str, Any]:
        """Validates SLA calculation request payload."""
        if not isinstance(input_data, dict):
            raise ValueError("Input to SLAEscalationEngine must be a dictionary")

        action = str(input_data.get("action", "EVALUATE_SINGLE")).upper()
        return {"action": action, "payload": input_data}

    def execute_core(self, validated_data: Dict[str, Any]) -> Any:
        """Dispatches single ticket evaluation or batch audit sweep."""
        action = validated_data["action"]
        payload = validated_data["payload"]

        if action == "EVALUATE_SINGLE":
            return self.evaluate_ticket_sla(
                ticket_data=payload["ticket"],
                existing_milestones=set(payload.get("existing_milestones", [])),
                current_time=payload.get("current_time"),
            )
        elif action == "BATCH_AUDIT":
            return self.run_batch_sla_audit(
                tickets=payload.get("tickets", []),
                existing_events_by_ticket=payload.get("existing_events_by_ticket", {}),
                current_time=payload.get("current_time"),
            )
        else:
            raise ValueError(f"Unsupported action: {action}")

    def fallback(self, error: Exception, input_data: Any) -> Any:
        """Safe fallback response preventing operational lockup."""
        self.logger.warning("SLAEscalationEngine fallback invoked: %s", error)
        now = datetime.now(timezone.utc)
        return TicketSLATelemetry(
            ticket_id="UNKNOWN",
            ticket_number="TKT-00000",
            ticket_status="OPEN",
            priority="NORMAL",
            created_at=now,
            sla_deadline=now,
            elapsed_hours=0.0,
            remaining_hours=48.0,
            progress_percentage=0.0,
            is_first_response_pending=False,
            is_first_response_overdue=False,
            is_sla_breached=False,
            urgency_level="CALM"
        )

    # -------------------------------------------------------------------------
    # Core Domain Logic: Single Ticket Evaluation
    # -------------------------------------------------------------------------

    def evaluate_ticket_sla(
        self,
        ticket_data: Dict[str, Any],
        existing_milestones: Optional[Set[str]] = None,
        current_time: Optional[datetime] = None
    ) -> TicketSLATelemetry:
        """
        Computes accurate continuous SLA telemetry for a single support ticket.
        Detects newly triggered milestone escalation events.
        """
        now = current_time or datetime.now(timezone.utc)
        triggered_events = existing_milestones or set()

        created_at = self._parse_datetime(ticket_data.get("created_at") or now)
        parsed_deadline = self._parse_datetime(ticket_data.get("sla_deadline"))
        sla_deadline = parsed_deadline if parsed_deadline else (created_at + timedelta(hours=self.TOTAL_SLA_HOURS))
        first_resp = self._parse_datetime(ticket_data.get("first_response_at"))

        status = str(ticket_data.get("ticket_status", TicketStatus.OPEN.value)).upper()
        prio = str(ticket_data.get("priority", "NORMAL")).upper()
        is_terminal = status in self.TERMINAL_STATUSES

        # 1. Elapsed & Remaining Time Math
        elapsed_seconds = max(0.0, (now - created_at).total_seconds())
        elapsed_hours = round(elapsed_seconds / 3600.0, 2)
        remaining_hours = max(0.0, round(self.TOTAL_SLA_HOURS - elapsed_hours, 2))
        progress_pct = min(100.0, round((elapsed_hours / self.TOTAL_SLA_HOURS) * 100.0, 1))

        # 2. First Human Response Tracking
        is_first_resp_pending = (first_resp is None) and not is_terminal
        is_first_resp_overdue = is_first_resp_pending and (elapsed_hours >= self.FIRST_RESPONSE_HOURS)

        # 3. Breach Calculation
        is_breached = bool(ticket_data.get("is_sla_breached", False))
        if not is_terminal and elapsed_hours >= self.TOTAL_SLA_HOURS:
            is_breached = True

        # 4. Urgency Classification
        if is_breached:
            urgency = "BREACHED"
        elif not is_terminal and elapsed_hours >= self.LEAD_ALERT_HOURS:
            urgency = "CRITICAL_WARNING"
        elif not is_terminal and (elapsed_hours >= self.REMINDER_HOURS or is_first_resp_overdue):
            urgency = "ATTENTION_NEEDED"
        else:
            urgency = "CALM"

        # 5. Milestone Trigger Detection
        new_events: List[str] = []
        if not is_terminal:
            # 12h First Response
            if is_first_resp_overdue and SLAEscalationLevel.FIRST_RESPONSE_12H.value not in triggered_events:
                new_events.append(SLAEscalationLevel.FIRST_RESPONSE_12H.value)

            # 24h Reminder
            if elapsed_hours >= self.REMINDER_HOURS and SLAEscalationLevel.REMINDER_24H.value not in triggered_events:
                new_events.append(SLAEscalationLevel.REMINDER_24H.value)

            # 36h Lead Alert
            if elapsed_hours >= self.LEAD_ALERT_HOURS and SLAEscalationLevel.LEAD_ALERT_36H.value not in triggered_events:
                new_events.append(SLAEscalationLevel.LEAD_ALERT_36H.value)

            # 48h Breach
            if elapsed_hours >= self.TOTAL_SLA_HOURS and SLAEscalationLevel.SLA_BREACHED_48H.value not in triggered_events:
                new_events.append(SLAEscalationLevel.SLA_BREACHED_48H.value)

        return TicketSLATelemetry(
            ticket_id=str(ticket_data.get("ticket_id", "")),
            ticket_number=str(ticket_data.get("ticket_number", "")),
            ticket_status=status,
            priority=prio,
            created_at=created_at,
            sla_deadline=sla_deadline,
            elapsed_hours=elapsed_hours,
            remaining_hours=remaining_hours,
            progress_percentage=progress_pct,
            is_first_response_pending=is_first_resp_pending,
            is_first_response_overdue=is_first_resp_overdue,
            first_response_at=first_resp,
            is_sla_breached=is_breached,
            urgency_level=urgency,
            new_milestone_events=new_events
        )

    # -------------------------------------------------------------------------
    # Core Domain Logic: Batch SLA Audit
    # -------------------------------------------------------------------------

    def run_batch_sla_audit(
        self,
        tickets: List[Dict[str, Any]],
        existing_events_by_ticket: Optional[Dict[str, List[str]]] = None,
        current_time: Optional[datetime] = None
    ) -> SLABatchAuditSummary:
        """
        Scans all active support tickets and generates an operational triage summary
        with newly triggered escalation alerts.
        """
        now = current_time or datetime.now(timezone.utc)
        events_map = existing_events_by_ticket or {}

        total_active = 0
        first_resp_overdue_count = 0
        at_risk_count = 0
        breached_count = 0
        compliant_count = 0
        escalations_to_dispatch: List[Dict[str, Any]] = []

        for t in tickets:
            status = str(t.get("ticket_status", TicketStatus.OPEN.value)).upper()
            if status in self.TERMINAL_STATUSES:
                continue

            total_active += 1
            t_id = str(t.get("ticket_id", ""))
            existing_m = set(events_map.get(t_id, []))

            telemetry = self.evaluate_ticket_sla(
                ticket_data=t,
                existing_milestones=existing_m,
                current_time=now
            )

            if telemetry.is_sla_breached:
                breached_count += 1
            elif telemetry.urgency_level == "CRITICAL_WARNING":
                at_risk_count += 1
            else:
                compliant_count += 1

            if telemetry.is_first_response_overdue:
                first_resp_overdue_count += 1

            for ev in telemetry.new_milestone_events:
                escalations_to_dispatch.append({
                    "ticket_id": t_id,
                    "ticket_number": telemetry.ticket_number,
                    "escalation_level": ev,
                    "elapsed_hours": telemetry.elapsed_hours,
                    "triggered_at": now.isoformat(),
                    "priority": telemetry.priority,
                    "assigned_to": t.get("assigned_to"),
                    "note": self._format_milestone_note(ev, telemetry)
                })

        compliance_rate = 100.0
        if total_active > 0:
            compliance_rate = round(((total_active - breached_count) / total_active) * 100.0, 1)

        return SLABatchAuditSummary(
            total_active_tickets=total_active,
            sla_compliant_count=compliant_count,
            first_response_overdue_count=first_resp_overdue_count,
            at_risk_count=at_risk_count,
            breached_count=breached_count,
            overall_compliance_rate_pct=compliance_rate,
            audit_timestamp=now.isoformat(),
            escalations_to_dispatch=escalations_to_dispatch
        )

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

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

    @staticmethod
    def _format_milestone_note(milestone: str, tele: TicketSLATelemetry) -> str:
        """Formats human-readable operational alert note for SLA milestone."""
        if milestone == SLAEscalationLevel.FIRST_RESPONSE_12H.value:
            return f"12H First Response SLA Overdue: Ticket {tele.ticket_number} has had no agent reply for {tele.elapsed_hours}h."
        elif milestone == SLAEscalationLevel.REMINDER_24H.value:
            return f"24H Reminder: Ticket {tele.ticket_number} is in progress with {tele.remaining_hours}h remaining."
        elif milestone == SLAEscalationLevel.LEAD_ALERT_36H.value:
            return f"36H Lead Alert: Ticket {tele.ticket_number} requires immediate attention ({tele.remaining_hours}h before hard breach)."
        elif milestone == SLAEscalationLevel.SLA_BREACHED_48H.value:
            return f"CRITICAL SLA BREACH: Ticket {tele.ticket_number} has exceeded 48 hours unresolved. Immediate intervention required."
        return f"SLA Event: {milestone}"
