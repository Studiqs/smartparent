"""
STUDIQS® SmartParent™ (v6.2 & v6.3 Extension) - Support Service
=============================================================================
Module: src.smartparent.services.support_service
Section 14: Help Centre, Ticketing and Support Operating Models
Section 27: 48-Hour Hard SLA Support Operating Model with Continuous Escalation

Orchestrates:
  1. Self-Service Knowledge Base Search & Issue Deflection
  2. Support Ticket Creation with Sequential 'TKT-YYYY-NNNNN' Numbers
  3. 48-Hour Hard SLA Continuous Countdown & Milestone Escalation (12h, 24h, 36h, 48h)
  4. Marketplace 48-Hour Evaluation Dispute Escrow Freeze Automation
  5. Multi-Party Asynchronous Threaded Messaging with Hidden Internal Notes
  6. Reopen Policy & Guardrails (Max 3 reopens with auto-escalation)
  7. Row-Level Security & Least-Privilege Role Isolation
=============================================================================
"""

import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union

from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.orm import Session

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
    SLABreachError,
    TicketStateTransitionError,
)
from src.smartparent.db.models.support_ticket import (
    SupportTicket,
    SupportMessage,
    SupportSLAEvent,
)
from src.smartparent.db.models.marketplace import (
    EvaluationCase,
    CommissionLedger,
)
from src.smartparent.engines.section_14_help_support.support_ticket_engine import (
    SupportTicketEngine,
)
from src.smartparent.engines.section_14_help_support.sla_escalation_engine import (
    SLAEscalationEngine,
    TicketSLATelemetry,
)
from src.smartparent.engines.section_14_help_support.self_service_faq_engine import (
    SelfServiceFAQEngine,
)
from src.smartparent.schemas.support import (
    FAQArticleSchema,
    FAQSearchResultItemSchema,
    FAQSearchRequest,
    FAQSearchResponse,
    TicketCreateRequest,
    TicketUpdateRequest,
    TicketAssignRequest,
    TicketResolveRequest,
    TicketReopenRequest,
    SupportTicketResponse,
    SupportTicketDetailResponse,
    SupportTicketListResponse,
    SupportMessageCreateRequest,
    SupportMessageResponse,
    SupportSLAEventResponse,
    TicketSLAStatusResponse,
    AdminSLABatchAuditResponse,
    AdminSupportMetricsResponse,
)

logger = logging.getLogger("STUDIQS_SupportService")


class SupportService:
    """
    Production-grade business service for Help Centre, Ticketing, and 48-Hour SLA.
    """

    def __init__(self, db: Session):
        self.db = db
        self.ticket_engine = SupportTicketEngine()
        self.sla_engine = SLAEscalationEngine()
        self.faq_engine = SelfServiceFAQEngine()

    # =========================================================================
    # 1. Self-Service FAQ & Knowledge Base
    # =========================================================================

    def search_knowledge_base(self, request: FAQSearchRequest) -> FAQSearchResponse:
        """Searches curated FAQ articles with relevance scoring to resolve issues instantly."""
        engine_res = self.faq_engine.execute_core({
            "query": request.query,
            "category": request.category,
            "limit": request.limit,
        })

        results = [
            FAQSearchResultItemSchema(
                article=FAQArticleSchema(
                    article_id=r.article.article_id,
                    category=r.article.category,
                    title=r.article.title,
                    summary=r.article.summary,
                    content=r.article.content,
                    tags=r.article.tags,
                    action_label=r.article.action_label,
                    action_deep_link=r.article.action_deep_link,
                    helpful_count=r.article.helpful_count,
                ),
                relevance_score=r.relevance_score,
                matched_terms=r.matched_terms,
            )
            for r in engine_res.results
        ]

        return FAQSearchResponse(
            query=engine_res.query,
            total_found=engine_res.total_found,
            results=results,
            suggested_ticket_category=engine_res.suggested_ticket_category,
            fallback_message=engine_res.fallback_message,
        )

    # =========================================================================
    # 2. Support Ticket Lifecycle Management
    # =========================================================================

    def create_ticket(
        self,
        subscriber_id: uuid.UUID,
        payload: TicketCreateRequest,
    ) -> SupportTicketResponse:
        """
        Creates a new support ticket:
          - Generates sequential ticket number: TKT-YYYY-NNNNN
          - Sets 48-hour continuous SLA deadline
          - Evaluates auto-triage priority
          - Freezes expert commission escrow if marketplace dispute
          - Attaches initial message/screenshot
        """
        now = datetime.now(timezone.utc)

        # 1. Compute next sequential number for current year
        year_prefix = f"TKT-{now.year}-"
        max_query = select(func.max(SupportTicket.ticket_number)).where(
            SupportTicket.ticket_number.like(f"{year_prefix}%")
        )
        max_ticket = self.db.execute(max_query).scalar()
        if max_ticket:
            try:
                seq_num = int(max_ticket.split("-")[-1]) + 1
            except Exception:
                seq_num = 1
        else:
            seq_num = 1

        # 2. Process through SupportTicketEngine
        ticket_input = {
            "subscriber_id": str(subscriber_id),
            "category": payload.category,
            "subject": payload.subject,
            "description": payload.description,
            "ticket_type": payload.ticket_type,
            "case_id": payload.case_id,
            "priority": payload.priority,
            "created_at": now,
        }
        res = self.ticket_engine.process_ticket_creation(ticket_input, sequence_number=seq_num)

        # 3. Marketplace Evaluation Dispute Handling (Section 14 & 21)
        parsed_case_id = None
        if payload.case_id:
            try:
                parsed_case_id = uuid.UUID(payload.case_id)
            except ValueError:
                pass

        if res.is_dispute_ticket and parsed_case_id:
            self._handle_marketplace_dispute_freeze(
                case_id=parsed_case_id,
                subscriber_id=subscriber_id,
                ticket_number=res.ticket_number,
                now=now,
            )

        # 4. Persist SupportTicket entity
        ticket = SupportTicket(
            ticket_id=uuid.uuid4(),
            ticket_number=res.ticket_number,
            subscriber_id=subscriber_id,
            case_id=parsed_case_id,
            category=res.category,
            ticket_type=payload.ticket_type,
            subject=payload.subject,
            description=payload.description,
            ticket_status=TicketStatus.OPEN.value,
            priority=res.priority,
            sla_deadline=res.sla_deadline,
            is_sla_breached=False,
            reopen_count=0,
        )
        self.db.add(ticket)
        self.db.flush()

        # 5. Add initial message to thread
        initial_msg = SupportMessage(
            message_id=uuid.uuid4(),
            ticket_id=ticket.ticket_id,
            sender_id=subscriber_id,
            sender_role=SupportSenderRole.PARENT.value,
            message_text=payload.description,
            attachment_url=payload.attachment_url,
            attachment_filename=payload.attachment_filename,
            is_internal_note=False,
            created_at=now,
        )
        self.db.add(initial_msg)
        self.db.commit()
        self.db.refresh(ticket)

        return self._build_ticket_response(ticket, current_time=now)

    def get_subscriber_tickets(
        self,
        subscriber_id: uuid.UUID,
        status: Optional[str] = None,
        category: Optional[str] = None,
        page: int = 1,
        limit: int = 20,
    ) -> SupportTicketListResponse:
        """Returns paginated tickets owned by subscriber (enforces RLS)."""
        offset = (max(1, page) - 1) * limit
        filters = [SupportTicket.subscriber_id == subscriber_id]

        if status:
            filters.append(SupportTicket.ticket_status == status.strip().upper())
        if category:
            filters.append(SupportTicket.category == category.strip().upper())

        # Total count
        total_q = select(func.count(SupportTicket.ticket_id)).where(and_(*filters))
        total = self.db.execute(total_q).scalar() or 0

        # Query items
        q = (
            select(SupportTicket)
            .where(and_(*filters))
            .order_by(desc(SupportTicket.created_at))
            .offset(offset)
            .limit(limit)
        )
        tickets = self.db.execute(q).scalars().all()
        now = datetime.now(timezone.utc)

        responses = [self._build_ticket_response(t, current_time=now) for t in tickets]

        return SupportTicketListResponse(
            tickets=responses,
            total=total,
            page=page,
            limit=limit,
        )

    def get_ticket_detail(
        self,
        ticket_id: uuid.UUID,
        requesting_user_id: uuid.UUID,
        user_role: str = "PARENT",
    ) -> SupportTicketDetailResponse:
        """
        Retrieves ticket detail with threaded messages.
        Filters out internal notes for parents (Least-Privilege Security).
        """
        ticket = self.db.get(SupportTicket, ticket_id)
        if not ticket:
            raise SmartParentException(
                message=f"Support ticket {ticket_id} not found.",
                status_code=404,
                error_code="TICKET_NOT_FOUND",
            )

        # Enforce multi-tenant parent isolation
        if user_role.upper() == "PARENT" and ticket.subscriber_id != requesting_user_id:
            raise SmartParentException(
                message="Access denied. You do not own this support ticket.",
                status_code=403,
                error_code="ACCESS_DENIED",
            )

        now = datetime.now(timezone.utc)
        base_resp = self._build_ticket_response(ticket, current_time=now)

        # Fetch messages
        msg_filters = [SupportMessage.ticket_id == ticket_id]
        if user_role.upper() == "PARENT":
            # Parents CANNOT see internal agent notes
            msg_filters.append(SupportMessage.is_internal_note == False)

        msg_q = select(SupportMessage).where(and_(*msg_filters)).order_by(SupportMessage.created_at)
        messages = self.db.execute(msg_q).scalars().all()

        message_responses = [
            SupportMessageResponse(
                message_id=str(m.message_id),
                ticket_id=str(m.ticket_id),
                sender_id=str(m.sender_id),
                sender_role=m.sender_role,
                message_text=m.message_text,
                attachment_url=m.attachment_url,
                attachment_filename=m.attachment_filename,
                is_internal_note=m.is_internal_note,
                created_at=m.created_at,
            )
            for m in messages
        ]

        # Fetch SLA audit events
        sla_q = select(SupportSLAEvent).where(SupportSLAEvent.ticket_id == ticket_id).order_by(SupportSLAEvent.triggered_at)
        sla_events = self.db.execute(sla_q).scalars().all()

        sla_responses = [
            SupportSLAEventResponse(
                event_id=str(e.event_id),
                ticket_id=str(e.ticket_id),
                escalation_level=e.escalation_level,
                triggered_at=e.triggered_at,
                notified_to=str(e.notified_to) if e.notified_to else None,
                notes=e.notes,
            )
            for e in sla_events
        ]

        return SupportTicketDetailResponse(
            **base_resp.model_dump(),
            messages=message_responses,
            sla_events=sla_responses,
        )

    def add_message(
        self,
        ticket_id: uuid.UUID,
        sender_id: uuid.UUID,
        sender_role: str,
        payload: SupportMessageCreateRequest,
    ) -> SupportMessageResponse:
        """
        Adds a message to the ticket thread:
          - Automatically stamps first_response_at on first agent reply.
          - Transitions AWAITING_CUSTOMER back to IN_PROGRESS on parent reply.
          - Enforces internal note boundaries.
        """
        ticket = self.db.get(SupportTicket, ticket_id)
        if not ticket:
            raise SmartParentException(message="Ticket not found.", status_code=404, error_code="TICKET_NOT_FOUND")

        now = datetime.now(timezone.utc)
        role = sender_role.upper()

        # Authorization & Role Boundaries
        if role == "PARENT":
            if ticket.subscriber_id != sender_id:
                raise SmartParentException(message="Access denied.", status_code=403, error_code="ACCESS_DENIED")
            # Parents cannot create internal notes
            is_internal = False

            # If ticket was waiting for customer info, move back to IN_PROGRESS
            if ticket.ticket_status == TicketStatus.AWAITING_CUSTOMER.value:
                ticket.ticket_status = TicketStatus.IN_PROGRESS.value
        else:
            is_internal = payload.is_internal_note
            # If agent/admin sends public reply and first_response_at is not set:
            if not is_internal and ticket.first_response_at is None:
                ticket.first_response_at = now

            if ticket.ticket_status == TicketStatus.OPEN.value:
                ticket.ticket_status = TicketStatus.IN_PROGRESS.value

        msg = SupportMessage(
            message_id=uuid.uuid4(),
            ticket_id=ticket_id,
            sender_id=sender_id,
            sender_role=role,
            message_text=payload.message_text,
            attachment_url=payload.attachment_url,
            attachment_filename=payload.attachment_filename,
            is_internal_note=is_internal,
            created_at=now,
        )
        self.db.add(msg)
        self.db.commit()
        self.db.refresh(msg)

        return SupportMessageResponse(
            message_id=str(msg.message_id),
            ticket_id=str(msg.ticket_id),
            sender_id=str(msg.sender_id),
            sender_role=msg.sender_role,
            message_text=msg.message_text,
            attachment_url=msg.attachment_url,
            attachment_filename=msg.attachment_filename,
            is_internal_note=msg.is_internal_note,
            created_at=msg.created_at,
        )

    def assign_ticket(
        self,
        ticket_id: uuid.UUID,
        agent_id: uuid.UUID,
        admin_id: Optional[uuid.UUID] = None,
    ) -> SupportTicketResponse:
        """Assigns ticket to a support agent and advances status to IN_PROGRESS."""
        ticket = self.db.get(SupportTicket, ticket_id)
        if not ticket:
            raise SmartParentException(message="Ticket not found.", status_code=404, error_code="TICKET_NOT_FOUND")

        now = datetime.now(timezone.utc)
        ticket.assigned_to = agent_id
        ticket.assigned_at = now

        if ticket.ticket_status == TicketStatus.OPEN.value:
            ticket.ticket_status = TicketStatus.IN_PROGRESS.value

        # Log system message in thread
        sys_msg = SupportMessage(
            message_id=uuid.uuid4(),
            ticket_id=ticket_id,
            sender_id=admin_id or agent_id,
            sender_role=SupportSenderRole.SYSTEM.value,
            message_text=f"Ticket assigned to support specialist for review.",
            is_internal_note=True,
            created_at=now,
        )
        self.db.add(sys_msg)
        self.db.commit()
        self.db.refresh(ticket)

        return self._build_ticket_response(ticket, current_time=now)

    def resolve_ticket(
        self,
        ticket_id: uuid.UUID,
        payload: TicketResolveRequest,
        agent_id: uuid.UUID,
    ) -> SupportTicketResponse:
        """Marks support ticket as RESOLVED with required resolution notes."""
        ticket = self.db.get(SupportTicket, ticket_id)
        if not ticket:
            raise SmartParentException(message="Ticket not found.", status_code=404, error_code="TICKET_NOT_FOUND")

        now = datetime.now(timezone.utc)

        # Validate transition using engine
        self.ticket_engine.process_status_transition({
            "current_status": ticket.ticket_status,
            "target_status": TicketStatus.RESOLVED.value,
            "actor_role": "SUPPORT_AGENT",
        })

        ticket.ticket_status = TicketStatus.RESOLVED.value
        ticket.resolved_at = now
        ticket.resolution_notes = payload.resolution_notes

        # Post resolution notification message in thread
        res_msg = SupportMessage(
            message_id=uuid.uuid4(),
            ticket_id=ticket_id,
            sender_id=agent_id,
            sender_role=SupportSenderRole.SUPPORT_AGENT.value,
            message_text=f"Resolution: {payload.resolution_notes}",
            is_internal_note=False,
            created_at=now,
        )
        self.db.add(res_msg)
        self.db.commit()
        self.db.refresh(ticket)

        return self._build_ticket_response(ticket, current_time=now)

    def close_ticket(
        self,
        ticket_id: uuid.UUID,
        user_id: uuid.UUID,
        role: str = "PARENT",
    ) -> SupportTicketResponse:
        """Transitions ticket to CLOSED state."""
        ticket = self.db.get(SupportTicket, ticket_id)
        if not ticket:
            raise SmartParentException(message="Ticket not found.", status_code=404, error_code="TICKET_NOT_FOUND")

        if role.upper() == "PARENT" and ticket.subscriber_id != user_id:
            raise SmartParentException(message="Access denied.", status_code=403, error_code="ACCESS_DENIED")

        now = datetime.now(timezone.utc)

        self.ticket_engine.process_status_transition({
            "current_status": ticket.ticket_status,
            "target_status": TicketStatus.CLOSED.value,
            "actor_role": role,
        })

        ticket.ticket_status = TicketStatus.CLOSED.value
        self.db.commit()
        self.db.refresh(ticket)

        return self._build_ticket_response(ticket, current_time=now)

    def reopen_ticket(
        self,
        ticket_id: uuid.UUID,
        subscriber_id: uuid.UUID,
        payload: TicketReopenRequest,
    ) -> SupportTicketResponse:
        """
        Reopens a resolved or closed ticket:
          - Enforces max 3 reopens limit
          - Checks 7-day reopen window
          - Automatically escalates to URGENT priority on multiple reopens
        """
        ticket = self.db.get(SupportTicket, ticket_id)
        if not ticket:
            raise SmartParentException(message="Ticket not found.", status_code=404, error_code="TICKET_NOT_FOUND")

        if ticket.subscriber_id != subscriber_id:
            raise SmartParentException(message="Access denied.", status_code=403, error_code="ACCESS_DENIED")

        now = datetime.now(timezone.utc)

        transition_res = self.ticket_engine.process_status_transition({
            "current_status": ticket.ticket_status,
            "target_status": TicketStatus.REOPENED.value,
            "actor_role": "PARENT",
            "current_reopen_count": ticket.reopen_count,
            "closed_at": ticket.resolved_at or ticket.updated_at,
        })

        ticket.ticket_status = TicketStatus.REOPENED.value
        ticket.reopened_at = now
        ticket.reopen_count += 1

        if transition_res.escalated_priority:
            ticket.priority = transition_res.escalated_priority

        # Post parent reopening explanation
        msg = SupportMessage(
            message_id=uuid.uuid4(),
            ticket_id=ticket_id,
            sender_id=subscriber_id,
            sender_role=SupportSenderRole.PARENT.value,
            message_text=f"Ticket Reopened: {payload.reopen_reason}",
            is_internal_note=False,
            created_at=now,
        )
        self.db.add(msg)
        self.db.commit()
        self.db.refresh(ticket)

        return self._build_ticket_response(ticket, current_time=now)

    # =========================================================================
    # 3. 48-Hour Hard SLA Escalation Sweep & Operational Telemetry
    # =========================================================================

    def run_sla_escalation_sweep(self) -> AdminSLABatchAuditResponse:
        """
        Batch operational sweep across all active support tickets:
          - Calculates real-time countdown progress.
          - Detects 12h First Response, 24h Reminder, 36h Lead Alert, 48h Breach.
          - Emits and stores SupportSLAEvent audit records.
          - Flips is_sla_breached flag when SLA expires.
        """
        now = datetime.now(timezone.utc)

        # Fetch non-terminal tickets
        q = select(SupportTicket).where(
            SupportTicket.ticket_status.not_in([TicketStatus.RESOLVED.value, TicketStatus.CLOSED.value])
        )
        active_tickets = self.db.execute(q).scalars().all()

        ticket_dicts = [
            {
                "ticket_id": str(t.ticket_id),
                "ticket_number": t.ticket_number,
                "ticket_status": t.ticket_status,
                "priority": t.priority,
                "created_at": t.created_at,
                "sla_deadline": t.sla_deadline,
                "first_response_at": t.first_response_at,
                "is_sla_breached": t.is_sla_breached,
                "assigned_to": str(t.assigned_to) if t.assigned_to else None,
            }
            for t in active_tickets
        ]

        # Fetch already triggered events
        ticket_ids = [t.ticket_id for t in active_tickets]
        events_q = select(SupportSLAEvent).where(SupportSLAEvent.ticket_id.in_(ticket_ids)) if ticket_ids else []
        existing_events = self.db.execute(events_q).scalars().all() if ticket_ids else []

        events_map: Dict[str, List[str]] = {}
        for ev in existing_events:
            events_map.setdefault(str(ev.ticket_id), []).append(ev.escalation_level)

        # Execute batch SLA evaluation via engine
        audit_summary = self.sla_engine.run_batch_sla_audit(
            tickets=ticket_dicts,
            existing_events_by_ticket=events_map,
            current_time=now,
        )

        # Dispatch and persist new SLA events
        ticket_lookup = {str(t.ticket_id): t for t in active_tickets}
        for item in audit_summary.escalations_to_dispatch:
            t_obj = ticket_lookup.get(item["ticket_id"])
            if t_obj:
                # Create audit event
                event_entity = SupportSLAEvent(
                    event_id=uuid.uuid4(),
                    ticket_id=t_obj.ticket_id,
                    escalation_level=item["escalation_level"],
                    triggered_at=now,
                    notified_to=uuid.UUID(item["assigned_to"]) if item.get("assigned_to") else None,
                    notes=item["note"],
                )
                self.db.add(event_entity)

                # Set breach flag on 48h breach
                if item["escalation_level"] == SLAEscalationLevel.SLA_BREACHED_48H.value:
                    t_obj.is_sla_breached = True

        self.db.commit()

        return AdminSLABatchAuditResponse(
            total_active_tickets=audit_summary.total_active_tickets,
            sla_compliant_count=audit_summary.sla_compliant_count,
            first_response_overdue_count=audit_summary.first_response_overdue_count,
            at_risk_count=audit_summary.at_risk_count,
            breached_count=audit_summary.breached_count,
            overall_compliance_rate_pct=audit_summary.overall_compliance_rate_pct,
            audit_timestamp=audit_summary.audit_timestamp,
            escalations_to_dispatch=audit_summary.escalations_to_dispatch,
        )

    def get_admin_metrics(self) -> AdminSupportMetricsResponse:
        """Computes comprehensive operational metrics for the support leadership dashboard."""
        all_q = select(SupportTicket)
        tickets = self.db.execute(all_q).scalars().all()
        now = datetime.now(timezone.utc)

        total = len(tickets)
        status_counts: Dict[str, int] = {}
        category_counts: Dict[str, int] = {}
        priority_counts: Dict[str, int] = {}
        breached_count = 0

        resolution_times_hours: List[float] = []
        first_resp_times_hours: List[float] = []

        for t in tickets:
            st = t.ticket_status
            cat = t.category
            prio = t.priority

            status_counts[st] = status_counts.get(st, 0) + 1
            category_counts[cat] = category_counts.get(cat, 0) + 1
            priority_counts[prio] = priority_counts.get(prio, 0) + 1

            if t.is_sla_breached:
                breached_count += 1

            if t.resolved_at and t.created_at:
                res_hrs = (t.resolved_at - t.created_at).total_seconds() / 3600.0
                resolution_times_hours.append(res_hrs)

            if t.first_response_at and t.created_at:
                fr_hrs = (t.first_response_at - t.created_at).total_seconds() / 3600.0
                first_resp_times_hours.append(fr_hrs)

        avg_res = round(sum(resolution_times_hours) / len(resolution_times_hours), 1) if resolution_times_hours else 0.0
        avg_fr = round(sum(first_resp_times_hours) / len(first_resp_times_hours), 1) if first_resp_times_hours else 0.0
        compliance = round(((total - breached_count) / total) * 100.0, 1) if total > 0 else 100.0

        return AdminSupportMetricsResponse(
            total_tickets=total,
            open_tickets=status_counts.get(TicketStatus.OPEN.value, 0),
            in_progress_tickets=status_counts.get(TicketStatus.IN_PROGRESS.value, 0),
            awaiting_customer_tickets=status_counts.get(TicketStatus.AWAITING_CUSTOMER.value, 0),
            resolved_tickets=status_counts.get(TicketStatus.RESOLVED.value, 0),
            closed_tickets=status_counts.get(TicketStatus.CLOSED.value, 0),
            breached_tickets=breached_count,
            overall_sla_compliance_pct=compliance,
            average_resolution_hours=avg_res,
            average_first_response_hours=avg_fr,
            category_breakdown=category_counts,
            priority_breakdown=priority_counts,
        )

    # =========================================================================
    # Helpers
    # =========================================================================

    def _handle_marketplace_dispute_freeze(
        self,
        case_id: uuid.UUID,
        subscriber_id: uuid.UUID,
        ticket_number: str,
        now: datetime,
    ) -> None:
        """
        Executes marketplace dispute freeze:
          - Verifies evaluation case belongs to subscriber.
          - Transitions case to DISPUTED status.
          - Holds 80% expert escrow payout disbursement pending review.
        """
        case = self.db.get(EvaluationCase, case_id)
        if not case or case.subscriber_id != subscriber_id:
            return

        # Check if case is completed and within 48h dispute window
        eval_res = self.ticket_engine.evaluate_evaluation_dispute(
            case_id=str(case_id),
            case_status=case.case_status,
            completed_at=case.completed_at,
        )

        if eval_res.get("dispute_eligible"):
            case.case_status = CaseStatus.DISPUTED.value
            if hasattr(case, "disputed_at"):
                setattr(case, "disputed_at", now)
            if hasattr(case, "dispute_reason"):
                setattr(case, "dispute_reason", f"Support Dispute Ticket {ticket_number} raised by parent.")

            # Find ledger and freeze payout
            ledger_q = select(CommissionLedger).where(CommissionLedger.case_id == case_id)
            ledger = self.db.execute(ledger_q).scalars().first()
            if ledger:
                ledger.payout_status = "HELD_DISPUTE"
                logger.info(f"[SupportService] Expert escrow payout frozen for case {case_id} via ticket {ticket_number}.")

    def _build_ticket_response(
        self,
        ticket: SupportTicket,
        current_time: Optional[datetime] = None,
    ) -> SupportTicketResponse:
        """Constructs enriched SupportTicketResponse with live SLA metrics."""
        now = current_time or datetime.now(timezone.utc)

        telemetry = self.sla_engine.evaluate_ticket_sla(
            ticket_data={
                "ticket_id": str(ticket.ticket_id),
                "ticket_number": ticket.ticket_number,
                "ticket_status": ticket.ticket_status,
                "priority": ticket.priority,
                "created_at": ticket.created_at,
                "sla_deadline": ticket.sla_deadline,
                "first_response_at": ticket.first_response_at,
                "is_sla_breached": ticket.is_sla_breached,
            },
            current_time=now,
        )

        return SupportTicketResponse(
            ticket_id=str(ticket.ticket_id),
            ticket_number=ticket.ticket_number,
            subscriber_id=str(ticket.subscriber_id),
            case_id=str(ticket.case_id) if ticket.case_id else None,
            category=ticket.category,
            ticket_type=ticket.ticket_type,
            subject=ticket.subject,
            description=ticket.description,
            ticket_status=ticket.ticket_status,
            priority=ticket.priority,
            assigned_to=str(ticket.assigned_to) if ticket.assigned_to else None,
            assigned_at=ticket.assigned_at,
            sla_deadline=ticket.sla_deadline,
            first_response_at=ticket.first_response_at,
            resolved_at=ticket.resolved_at,
            is_sla_breached=ticket.is_sla_breached,
            resolution_notes=ticket.resolution_notes,
            reopen_count=ticket.reopen_count,
            created_at=ticket.created_at,
            updated_at=ticket.updated_at,
            elapsed_hours=telemetry.elapsed_hours,
            remaining_hours=telemetry.remaining_hours,
            urgency_level=telemetry.urgency_level,
        )
