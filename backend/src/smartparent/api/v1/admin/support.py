"""
STUDIQS® SmartParent™ (v6.3) - Admin Support & SLA Monitoring API
=============================================================================
Module: src.smartparent.api.v1.admin.support
Section 27: 48-Hour Hard SLA Support Operating Model with Continuous Escalation

Endpoints:
  1. GET  /api/v1/admin/support/tickets           -> Triage all tickets across platform
  2. GET  /api/v1/admin/support/tickets/{id}      -> Full ticket detail with internal notes & SLA logs
  3. POST /api/v1/admin/support/tickets/{id}/assign -> Assign ticket to support specialist
  4. POST /api/v1/admin/support/tickets/{id}/messages -> Agent response or hidden internal note
  5. POST /api/v1/admin/support/tickets/{id}/resolve -> Resolve ticket with resolution notes
  6. POST /api/v1/admin/support/tickets/{id}/close  -> Administratively close ticket
  7. POST /api/v1/admin/support/sla/scan          -> Trigger 12h/24h/36h/48h SLA escalation sweep
  8. GET  /api/v1/admin/support/metrics           -> SLA operational dashboard metrics
=============================================================================
"""

import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, and_, desc
from sqlalchemy.orm import Session

from src.smartparent.db.models.support_ticket import SupportTicket
from src.smartparent.schemas.support import (
    TicketAssignRequest,
    TicketResolveRequest,
    SupportTicketResponse,
    SupportTicketDetailResponse,
    SupportTicketListResponse,
    SupportMessageCreateRequest,
    SupportMessageResponse,
    AdminSLABatchAuditResponse,
    AdminSupportMetricsResponse,
)
from src.smartparent.services.support_service import SupportService
from src.smartparent.core.exceptions import SmartParentException

router = APIRouter(prefix="/admin/support", tags=["Section 27: Admin Support & SLA Triage"])


# Dependency injection hooks imported from central deps module
from src.smartparent.api.deps import get_db, get_current_admin_id


@router.get(
    "/tickets",
    response_model=SupportTicketListResponse,
    summary="Triage All Support Tickets (Admin)",
    description="Lists all support tickets across the platform with filters for SLA breach, urgency, priority, and category.",
)
def list_all_tickets(
    status: Optional[str] = Query(None, description="Filter by status: OPEN, IN_PROGRESS, RESOLVED, etc."),
    is_breached: Optional[bool] = Query(None, description="Filter by SLA breach flag"),
    priority: Optional[str] = Query(None, description="Filter by priority: URGENT, HIGH, NORMAL, LOW"),
    category: Optional[str] = Query(None, description="Filter by category"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    admin_id: uuid.UUID = Depends(get_current_admin_id),
):
    offset = (max(1, page) - 1) * limit
    filters = []

    if status:
        filters.append(SupportTicket.ticket_status == status.strip().upper())
    if is_breached is not None:
        filters.append(SupportTicket.is_sla_breached == is_breached)
    if priority:
        filters.append(SupportTicket.priority == priority.strip().upper())
    if category:
        filters.append(SupportTicket.category == category.strip().upper())

    total_q = select(func.count(SupportTicket.ticket_id))
    if filters:
        total_q = total_q.where(and_(*filters))
    total = db.execute(total_q).scalar() or 0

    q = select(SupportTicket)
    if filters:
        q = q.where(and_(*filters))
    q = q.order_by(desc(SupportTicket.created_at)).offset(offset).limit(limit)
    tickets = db.execute(q).scalars().all()

    service = SupportService(db)
    responses = [service._build_ticket_response(t) for t in tickets]

    return SupportTicketListResponse(
        tickets=responses,
        total=total,
        page=page,
        limit=limit,
    )


@router.get(
    "/tickets/{ticket_id}",
    response_model=SupportTicketDetailResponse,
    summary="Get Full Ticket Detail (Admin)",
    description="Returns complete ticket details, full threaded conversation (including internal notes), and complete SLA audit trail.",
)
def get_admin_ticket_detail(
    ticket_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin_id: uuid.UUID = Depends(get_current_admin_id),
):
    service = SupportService(db)
    try:
        return service.get_ticket_detail(
            ticket_id=ticket_id,
            requesting_user_id=admin_id,
            user_role="ADMIN",
        )
    except SmartParentException as spe:
        raise HTTPException(status_code=spe.status_code, detail=spe.message)


@router.post(
    "/tickets/{ticket_id}/assign",
    response_model=SupportTicketResponse,
    summary="Assign Ticket to Support Specialist",
    description="Assigns ticket to an agent, updates assigned_at, and transitions OPEN tickets to IN_PROGRESS.",
)
def assign_ticket(
    ticket_id: uuid.UUID,
    payload: TicketAssignRequest,
    db: Session = Depends(get_db),
    admin_id: uuid.UUID = Depends(get_current_admin_id),
):
    service = SupportService(db)
    try:
        agent_uuid = uuid.UUID(payload.assigned_to)
        return service.assign_ticket(ticket_id=ticket_id, agent_id=agent_uuid, admin_id=admin_id)
    except SmartParentException as spe:
        raise HTTPException(status_code=spe.status_code, detail=spe.message)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid agent UUID.")


@router.post(
    "/tickets/{ticket_id}/messages",
    response_model=SupportMessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Post Agent Reply or Internal Note",
    description="Posts an official response to the parent or a hidden internal note (visible only to staff). Automatically stamps first_response_at.",
)
def post_admin_message(
    ticket_id: uuid.UUID,
    payload: SupportMessageCreateRequest,
    db: Session = Depends(get_db),
    admin_id: uuid.UUID = Depends(get_current_admin_id),
):
    service = SupportService(db)
    try:
        return service.add_message(
            ticket_id=ticket_id,
            sender_id=admin_id,
            sender_role="SUPPORT_AGENT",
            payload=payload,
        )
    except SmartParentException as spe:
        raise HTTPException(status_code=spe.status_code, detail=spe.message)


@router.post(
    "/tickets/{ticket_id}/resolve",
    response_model=SupportTicketResponse,
    summary="Resolve Ticket",
    description="Marks ticket as RESOLVED with mandatory resolution notes.",
)
def resolve_ticket(
    ticket_id: uuid.UUID,
    payload: TicketResolveRequest,
    db: Session = Depends(get_db),
    admin_id: uuid.UUID = Depends(get_current_admin_id),
):
    service = SupportService(db)
    try:
        return service.resolve_ticket(
            ticket_id=ticket_id,
            payload=payload,
            agent_id=admin_id,
        )
    except SmartParentException as spe:
        raise HTTPException(status_code=spe.status_code, detail=spe.message)


@router.post(
    "/tickets/{ticket_id}/close",
    response_model=SupportTicketResponse,
    summary="Administratively Close Ticket",
)
def admin_close_ticket(
    ticket_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin_id: uuid.UUID = Depends(get_current_admin_id),
):
    service = SupportService(db)
    try:
        return service.close_ticket(
            ticket_id=ticket_id,
            user_id=admin_id,
            role="ADMIN",
        )
    except SmartParentException as spe:
        raise HTTPException(status_code=spe.status_code, detail=spe.message)


@router.post(
    "/sla/scan",
    response_model=AdminSLABatchAuditResponse,
    summary="Trigger Continuous 48H SLA Escalation Sweep",
    description="Evaluates all active tickets against 12h, 24h, 36h, and 48h milestone escalation thresholds and writes audit events.",
)
def run_sla_escalation_sweep(
    db: Session = Depends(get_db),
    admin_id: uuid.UUID = Depends(get_current_admin_id),
):
    service = SupportService(db)
    return service.run_sla_escalation_sweep()


@router.get(
    "/metrics",
    response_model=AdminSupportMetricsResponse,
    summary="Support Operational Dashboard Metrics",
    description="Returns aggregate KPI metrics: resolution times, first response averages, breach counts, and category breakdowns.",
)
def get_support_metrics(
    db: Session = Depends(get_db),
    admin_id: uuid.UUID = Depends(get_current_admin_id),
):
    service = SupportService(db)
    return service.get_admin_metrics()
