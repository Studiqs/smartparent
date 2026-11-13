"""
STUDIQS® SmartParent™ (v6.2 & v6.3 Extension) - Support Centre API Router
=============================================================================
Module: src.smartparent.api.v1.support
Section 14: Help Centre, Ticketing and Support Operating Models (Parent Tier)
Section 27: 48-Hour Hard SLA Support Operating Model

Endpoints:
  1. GET  /api/v1/support/faq                   -> Search self-service FAQ & instant resolution
  2. POST /api/v1/support/tickets               -> Create new support ticket (generates TKT-YYYY-NNNNN)
  3. GET  /api/v1/support/tickets               -> List parent's tickets (RLS isolated)
  4. GET  /api/v1/support/tickets/{ticket_id}   -> Ticket thread detail (internal notes masked)
  5. POST /api/v1/support/tickets/{ticket_id}/messages -> Reply in ticket conversation
  6. POST /api/v1/support/tickets/{ticket_id}/reopen   -> Reopen ticket (max 3 times, 7d window)
  7. POST /api/v1/support/tickets/{ticket_id}/close    -> Mark ticket as closed
=============================================================================
"""

import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.smartparent.schemas.support import (
    FAQSearchRequest,
    FAQSearchResponse,
    TicketCreateRequest,
    TicketReopenRequest,
    SupportTicketResponse,
    SupportTicketDetailResponse,
    SupportTicketListResponse,
    SupportMessageCreateRequest,
    SupportMessageResponse,
)
from src.smartparent.services.support_service import SupportService
from src.smartparent.core.exceptions import SmartParentException

router = APIRouter(prefix="/support", tags=["Section 14: Support Centre & Ticketing"])


# Dependency injection hooks imported from central deps module
from src.smartparent.api.deps import get_db, get_current_subscriber_id


# =============================================================================
# 1. Self-Service FAQ & Knowledge Base
# =============================================================================

@router.get(
    "/faq",
    response_model=FAQSearchResponse,
    summary="Search Self-Service FAQ Knowledge Base",
    description="Instant automated resolution engine for billing, OCR, topic mastery, PTM brief, and expert SLA questions.",
)
def search_faq(
    query: str = Query("", description="Keywords, question, or problem description"),
    category: Optional[str] = Query(None, description="Optional category filter from SupportTicketCategory"),
    limit: int = Query(5, ge=1, le=20, description="Max results to return"),
    db: Session = Depends(get_db),
):
    service = SupportService(db)
    return service.search_knowledge_base(
        FAQSearchRequest(query=query, category=category, limit=limit)
    )


# =============================================================================
# 2. Support Ticket Lifecycle (Parent Facing)
# =============================================================================

@router.post(
    "/tickets",
    response_model=SupportTicketResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Support Ticket",
    description="Creates a new support ticket with sequential TKT-YYYY-NNNNN numbering and 48-hour continuous SLA clock.",
)
def create_ticket(
    payload: TicketCreateRequest,
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    service = SupportService(db)
    try:
        return service.create_ticket(subscriber_id=subscriber_id, payload=payload)
    except SmartParentException as spe:
        raise HTTPException(status_code=spe.status_code, detail=spe.message)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create support ticket: {str(e)}",
        )


@router.get(
    "/tickets",
    response_model=SupportTicketListResponse,
    summary="List Parent Support Tickets",
    description="Retrieves paginated tickets owned by the authenticated subscriber (enforcing RLS isolation).",
)
def list_subscriber_tickets(
    status: Optional[str] = Query(None, description="Filter by status: OPEN, IN_PROGRESS, RESOLVED, CLOSED, etc."),
    category: Optional[str] = Query(None, description="Filter by category"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    service = SupportService(db)
    return service.get_subscriber_tickets(
        subscriber_id=subscriber_id,
        status=status,
        category=category,
        page=page,
        limit=limit,
    )


@router.get(
    "/tickets/{ticket_id}",
    response_model=SupportTicketDetailResponse,
    summary="Get Ticket Conversation Detail",
    description="Returns ticket status, SLA timer, and message thread. Internal agent notes are masked from parents.",
)
def get_ticket_detail(
    ticket_id: uuid.UUID,
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    service = SupportService(db)
    try:
        return service.get_ticket_detail(
            ticket_id=ticket_id,
            requesting_user_id=subscriber_id,
            user_role="PARENT",
        )
    except SmartParentException as spe:
        raise HTTPException(status_code=spe.status_code, detail=spe.message)


@router.post(
    "/tickets/{ticket_id}/messages",
    response_model=SupportMessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Reply in Ticket Thread",
    description="Posts a reply message with optional screenshot. Moves AWAITING_CUSTOMER tickets back to IN_PROGRESS.",
)
def post_ticket_message(
    ticket_id: uuid.UUID,
    payload: SupportMessageCreateRequest,
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    service = SupportService(db)
    try:
        return service.add_message(
            ticket_id=ticket_id,
            sender_id=subscriber_id,
            sender_role="PARENT",
            payload=payload,
        )
    except SmartParentException as spe:
        raise HTTPException(status_code=spe.status_code, detail=spe.message)


@router.post(
    "/tickets/{ticket_id}/reopen",
    response_model=SupportTicketResponse,
    summary="Reopen Ticket",
    description="Reopens a resolved or closed ticket if issue persists (Max 3 reopens; within 7 days).",
)
def reopen_ticket(
    ticket_id: uuid.UUID,
    payload: TicketReopenRequest,
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    service = SupportService(db)
    try:
        return service.reopen_ticket(
            ticket_id=ticket_id,
            subscriber_id=subscriber_id,
            payload=payload,
        )
    except SmartParentException as spe:
        raise HTTPException(status_code=spe.status_code, detail=spe.message)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))


@router.post(
    "/tickets/{ticket_id}/close",
    response_model=SupportTicketResponse,
    summary="Close Ticket",
    description="Subscriber confirms issue is resolved and closes the support ticket.",
)
def close_ticket(
    ticket_id: uuid.UUID,
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    service = SupportService(db)
    try:
        return service.close_ticket(
            ticket_id=ticket_id,
            user_id=subscriber_id,
            role="PARENT",
        )
    except SmartParentException as spe:
        raise HTTPException(status_code=spe.status_code, detail=spe.message)
