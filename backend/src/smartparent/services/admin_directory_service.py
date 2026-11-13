"""
STUDIQS® SmartParent™ (v6.3 Complete) - Admin Subscriber Directory Service
=============================================================================
Module: src.smartparent.services.admin_directory_service
Section 25.4: Administrative Searchable Subscriber Directory & Manual Overrides

Implements:
  1. Multi-criteria searchable subscriber directory with pagination.
  2. Deep 360 subscriber overview (Children, Invoices, Tickets, Audits).
  3. Authorized manual subscription adjustments with mandatory audit trail.
=============================================================================
"""

import logging
import math
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, or_, func, desc

from src.smartparent.db.models.auth import Subscriber, Child
from src.smartparent.db.models.subscription import (
    Subscription,
    BillingInvoice,
    SubscriptionAdjustmentAudit,
)
from src.smartparent.db.models.support_ticket import SupportTicket
from src.smartparent.schemas.admin_directory import (
    AdminSubscriberDirectoryItemSchema,
    AdminSubscriberDirectoryResponse,
    AdminChildDetailItem,
    AdminSubscriberDetailResponse,
    ManualSubscriptionAdjustmentRequest,
    ManualSubscriptionAdjustmentResponse,
)

logger = logging.getLogger("STUDIQS_AdminDirectoryService")


class AdminDirectoryService:
    """
    Administrative Subscriber Directory & Account Management Service.
    """

    def list_subscribers(
        self,
        db: Session,
        plan: Optional[str] = None,
        duration_months: Optional[int] = None,
        status: Optional[str] = None,
        search_query: Optional[str] = None,
        expiry_before: Optional[date] = None,
        expiry_after: Optional[date] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> AdminSubscriberDirectoryResponse:
        """
        Retrieves paginated, filtered administrative subscriber directory.
        """
        # Base subscriber query
        sub_query = select(Subscriber)

        # Apply search query (Parent name, Mobile, Email)
        if search_query and search_query.strip():
            sq = f"%{search_query.strip()}%"
            sub_query = sub_query.where(
                or_(
                    Subscriber.parent_name.ilike(sq),
                    Subscriber.mobile_number.ilike(sq),
                    Subscriber.email.ilike(sq),
                )
            )

        if plan and plan.strip():
            sub_query = sub_query.where(Subscriber.subscription_plan == plan.strip().upper())

        # Fetch matching subscribers
        total_count = db.execute(select(func.count()).select_from(sub_query.subquery())).scalar_one()

        offset = (page - 1) * page_size
        paged_query = sub_query.order_by(desc(Subscriber.created_at)).offset(offset).limit(page_size)
        subscribers = db.execute(paged_query).scalars().all()

        today = datetime.now(timezone.utc).date()
        items: List[AdminSubscriberDirectoryItemSchema] = []

        for sub in subscribers:
            # Fetch latest subscription
            latest_sub_stmt = (
                select(Subscription)
                .where(Subscription.subscriber_id == sub.subscriber_id)
                .order_by(desc(Subscription.created_at))
            )
            latest_sub = db.execute(latest_sub_stmt).scalars().first()

            # Filter by duration or status or expiry if specified
            if duration_months and latest_sub and latest_sub.duration_months != duration_months:
                continue
            if status and latest_sub and latest_sub.status != status:
                continue
            if expiry_before and latest_sub and latest_sub.expiry_date.date() > expiry_before:
                continue
            if expiry_after and latest_sub and latest_sub.expiry_date.date() < expiry_after:
                continue

            # Fetch children
            children_stmt = select(Child).where(Child.subscriber_id == sub.subscriber_id)
            children = db.execute(children_stmt).scalars().all()
            children_names = [c.student_name for c in children]

            # Fetch total revenue collected and last payment
            paid_inv_stmt = (
                select(BillingInvoice)
                .where(
                    and_(
                        BillingInvoice.subscriber_id == sub.subscriber_id,
                        BillingInvoice.payment_status == "PAID",
                    )
                )
                .order_by(desc(BillingInvoice.created_at))
            )
            paid_invoices = db.execute(paid_inv_stmt).scalars().all()
            total_rev = sum(float(inv.total_amount or 0.0) for inv in paid_invoices)
            last_inv = paid_invoices[0] if paid_invoices else None

            # Fetch support tickets count
            ticket_count_stmt = (
                select(func.count())
                .select_from(SupportTicket)
                .where(SupportTicket.subscriber_id == sub.subscriber_id)
            )
            ticket_count = db.execute(ticket_count_stmt).scalar_one() or 0

            days_remaining = None
            if latest_sub and latest_sub.expiry_date:
                days_remaining = (latest_sub.expiry_date.date() - today).days

            sub_status = latest_sub.status if latest_sub else "PENDING"
            if days_remaining is not None and days_remaining <= 0 and sub_status == "ACTIVE":
                sub_status = "EXPIRED"

            items.append(
                AdminSubscriberDirectoryItemSchema(
                    subscriber_id=sub.subscriber_id,
                    parent_name=sub.parent_name,
                    mobile_number=sub.mobile_number,
                    email=sub.email,
                    subscription_plan=sub.subscription_plan,
                    duration_months=latest_sub.duration_months if latest_sub else 1,
                    subscribed_children_count=len(children),
                    children_names=children_names,
                    subscription_start_date=latest_sub.start_date if latest_sub else None,
                    subscription_end_date=latest_sub.expiry_date if latest_sub else None,
                    subscription_status=sub_status,
                    days_until_expiry=days_remaining,
                    auto_renew=latest_sub.auto_renew if latest_sub else False,
                    last_successful_payment_date=last_inv.created_at if last_inv else None,
                    last_successful_payment_amount=float(last_inv.total_amount) if last_inv else None,
                    total_revenue_collected=round(total_rev, 2),
                    support_ticket_count=ticket_count,
                    created_at=sub.created_at,
                )
            )

        total_pages = math.ceil(total_count / page_size) if total_count > 0 else 1

        return AdminSubscriberDirectoryResponse(
            total_subscribers=total_count,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            subscribers=items,
        )

    def get_subscriber_detail(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
    ) -> AdminSubscriberDetailResponse:
        """
        Compiles exhaustive 360-degree administrative dossier for a subscriber.
        """
        sub_stmt = select(Subscriber).where(Subscriber.subscriber_id == subscriber_id)
        sub = db.execute(sub_stmt).scalar_one_or_none()
        if not sub:
            raise KeyError(f"Subscriber {subscriber_id} not found in directory.")

        # Children
        children_stmt = select(Child).where(Child.subscriber_id == subscriber_id)
        children = db.execute(children_stmt).scalars().all()
        child_items = [
            AdminChildDetailItem(
                child_id=c.child_id,
                student_name=c.student_name,
                standard_class=c.standard_class,
                board=c.board,
                academic_year=c.academic_year or "2025-2026",
            )
            for c in children
        ]

        # Subscriptions history
        sub_hist_stmt = (
            select(Subscription)
            .where(Subscription.subscriber_id == subscriber_id)
            .order_by(desc(Subscription.created_at))
        )
        subscriptions = db.execute(sub_hist_stmt).scalars().all()
        sub_hist = [
            {
                "subscription_id": str(s.subscription_id),
                "plan_id": s.plan_id,
                "duration_months": s.duration_months,
                "start_date": s.start_date.isoformat(),
                "expiry_date": s.expiry_date.isoformat(),
                "status": s.status,
                "auto_renew": s.auto_renew,
                "created_at": s.created_at.isoformat(),
            }
            for s in subscriptions
        ]

        # Payment Invoices
        inv_stmt = (
            select(BillingInvoice)
            .where(BillingInvoice.subscriber_id == subscriber_id)
            .order_by(desc(BillingInvoice.created_at))
        )
        invoices = db.execute(inv_stmt).scalars().all()
        inv_hist = [
            {
                "invoice_id": str(inv.invoice_id),
                "invoice_number": inv.invoice_number,
                "taxable_amount": float(inv.taxable_amount or 0.0),
                "total_amount": float(inv.total_amount or 0.0),
                "payment_status": inv.payment_status,
                "razorpay_payment_id": inv.razorpay_payment_id,
                "created_at": inv.created_at.isoformat(),
            }
            for inv in invoices
        ]

        # Support Tickets
        ticket_stmt = (
            select(SupportTicket)
            .where(SupportTicket.subscriber_id == subscriber_id)
            .order_by(desc(SupportTicket.created_at))
        )
        tickets = db.execute(ticket_stmt).scalars().all()
        ticket_hist = [
            {
                "ticket_id": str(t.ticket_id),
                "ticket_number": t.ticket_number,
                "category": t.category,
                "status": t.status,
                "subject": t.subject,
                "priority": t.priority,
                "created_at": t.created_at.isoformat(),
            }
            for t in tickets
        ]

        # Adjustment Audits
        audit_stmt = (
            select(SubscriptionAdjustmentAudit)
            .where(SubscriptionAdjustmentAudit.subscriber_id == subscriber_id)
            .order_by(desc(SubscriptionAdjustmentAudit.created_at))
        )
        audits = db.execute(audit_stmt).scalars().all()
        audit_hist = [
            {
                "audit_id": str(a.audit_id),
                "admin_user": a.admin_user,
                "action_type": a.action_type,
                "previous_state": a.previous_state,
                "new_state": a.new_state,
                "reason": a.reason,
                "created_at": a.created_at.isoformat(),
            }
            for a in audits
        ]

        latest_sub = subscriptions[0] if subscriptions else None
        today = datetime.now(timezone.utc).date()
        days_rem = (latest_sub.expiry_date.date() - today).days if latest_sub else None

        paid_invoices = [inv for inv in invoices if inv.payment_status == "PAID"]
        total_rev = sum(float(inv.total_amount or 0.0) for inv in paid_invoices)
        last_inv = paid_invoices[0] if paid_invoices else None

        directory_item = AdminSubscriberDirectoryItemSchema(
            subscriber_id=sub.subscriber_id,
            parent_name=sub.parent_name,
            mobile_number=sub.mobile_number,
            email=sub.email,
            subscription_plan=sub.subscription_plan,
            duration_months=latest_sub.duration_months if latest_sub else 1,
            subscribed_children_count=len(children),
            children_names=[c.student_name for c in children],
            subscription_start_date=latest_sub.start_date if latest_sub else None,
            subscription_end_date=latest_sub.expiry_date if latest_sub else None,
            subscription_status=latest_sub.status if latest_sub else "PENDING",
            days_until_expiry=days_rem,
            auto_renew=latest_sub.auto_renew if latest_sub else False,
            last_successful_payment_date=last_inv.created_at if last_inv else None,
            last_successful_payment_amount=float(last_inv.total_amount) if last_inv else None,
            total_revenue_collected=round(total_rev, 2),
            support_ticket_count=len(tickets),
            created_at=sub.created_at,
        )

        return AdminSubscriberDetailResponse(
            subscriber=directory_item,
            children=child_items,
            subscriptions_history=sub_hist,
            payment_invoices=inv_hist,
            support_tickets=ticket_hist,
            adjustment_audits=audit_hist,
        )

    def adjust_subscription(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        payload: ManualSubscriptionAdjustmentRequest,
    ) -> ManualSubscriptionAdjustmentResponse:
        """
        Executes administrative manual adjustment with mandatory audit entry (Section 25.4).
        """
        sub_stmt = select(Subscriber).where(Subscriber.subscriber_id == subscriber_id)
        sub = db.execute(sub_stmt).scalar_one_or_none()
        if not sub:
            raise KeyError(f"Subscriber {subscriber_id} not found.")

        # Latest subscription
        sub_query = (
            select(Subscription)
            .where(Subscription.subscriber_id == subscriber_id)
            .order_by(desc(Subscription.created_at))
        )
        subscription = db.execute(sub_query).scalars().first()
        if not subscription:
            raise KeyError(f"No subscription found for subscriber {subscriber_id} to adjust.")

        prev_state = {
            "plan_id": subscription.plan_id,
            "status": subscription.status,
            "expiry_date": subscription.expiry_date.isoformat(),
            "duration_months": subscription.duration_months,
            "subscriber_plan": sub.subscription_plan,
        }

        # Apply action
        if payload.action_type == "EXTEND_VALIDITY":
            if not payload.extend_days:
                raise ValueError("extend_days is required for EXTEND_VALIDITY.")
            # If already expired, extend from now; otherwise extend from expiry_date
            now_utc = datetime.now(timezone.utc)
            base_date = subscription.expiry_date
            if base_date.tzinfo is None:
                base_date = base_date.replace(tzinfo=timezone.utc)
            effective_base = max(base_date, now_utc)
            subscription.expiry_date = effective_base + timedelta(days=payload.extend_days)
            subscription.status = "ACTIVE"
        elif payload.action_type == "CHANGE_PLAN":
            if not payload.new_plan_id:
                raise ValueError("new_plan_id is required for CHANGE_PLAN.")
            subscription.plan_id = payload.new_plan_id.upper()
            sub.subscription_plan = payload.new_plan_id.upper()
        elif payload.action_type == "OVERRIDE_STATUS":
            if not payload.new_status:
                raise ValueError("new_status is required for OVERRIDE_STATUS.")
            subscription.status = payload.new_status.upper()

        new_state = {
            "plan_id": subscription.plan_id,
            "status": subscription.status,
            "expiry_date": subscription.expiry_date.isoformat(),
            "duration_months": subscription.duration_months,
            "subscriber_plan": sub.subscription_plan,
        }

        # Create mandatory audit log entry
        audit_entry = SubscriptionAdjustmentAudit(
            audit_id=uuid.uuid4(),
            subscriber_id=subscriber_id,
            subscription_id=subscription.subscription_id,
            admin_user=payload.admin_user,
            action_type=payload.action_type,
            previous_state=prev_state,
            new_state=new_state,
            reason=payload.reason,
        )
        db.add(audit_entry)
        db.commit()
        db.refresh(audit_entry)

        logger.info(
            f"[AdminDirectoryService] Subscriber {subscriber_id} adjusted by {payload.admin_user}: "
            f"{payload.action_type} - Reason: {payload.reason}"
        )

        return ManualSubscriptionAdjustmentResponse(
            audit_id=audit_entry.audit_id,
            subscriber_id=subscriber_id,
            subscription_id=subscription.subscription_id,
            admin_user=payload.admin_user,
            action_type=payload.action_type,
            previous_state=prev_state,
            new_state=new_state,
            reason=payload.reason,
            adjusted_at=audit_entry.created_at,
            message="Subscription successfully adjusted with audit entry.",
        )


admin_directory_service = AdminDirectoryService()
