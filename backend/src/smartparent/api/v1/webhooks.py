"""
STUDIQS® SmartParent™ (v6.3 Complete) - Live Razorpay Webhook Ingestion API
============================================================================
Module: src.smartparent.api.v1.webhooks
Section 24: Subscription, Invoicing & Gateway Webhooks
Section 24.7: Payment Failure, Retry Reconciliation & Idempotent Handling

Processes:
  1. X-Razorpay-Signature HMAC-SHA256 signature verification.
  2. Strict event idempotency via `RazorpayWebhookEvent` log table.
  3. payment.captured & order.paid fulfillment:
     - Activates subscription & transitions status to ACTIVE.
     - Provisions monthly usage quota.
     - Fulfills Expert Marketplace case payment to AWAITING_UPLOAD.
     - Issues B2C GST Tax Invoice.
  4. payment.failed processing:
     - Sets invoice payment_status to FAILED.
     - Prevents duplicate subscription creation.
     - Sets past-due status for auto-renew failures (3-day grace period).
     - Dispatches parent retry alert notification.
  5. Idempotent HTTP 200 acknowledgment.
============================================================================
"""

import json
import hashlib
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict
from fastapi import APIRouter, Request, Header, HTTPException, status, Depends
from sqlalchemy.orm import Session

from src.smartparent.db.session import get_db
from src.smartparent.services.billing_service import BillingService
from src.smartparent.services.marketplace_service import MarketplaceService
from src.smartparent.services.subscription_service import SubscriptionService
from src.smartparent.services.payment_failure_service import payment_failure_service
from src.smartparent.core.constants import CaseStatus, PaymentStatus
from src.smartparent.db.models.marketplace import PaymentOrder, EvaluationCase
from src.smartparent.db.models.subscription import (
    Subscription,
    BillingInvoice,
    RazorpayWebhookEvent,
)
from src.smartparent.db.models.usage_quota import SubscriberUsageQuota
from src.smartparent.config import settings

logger = logging.getLogger("STUDIQS_Webhooks")

router = APIRouter(prefix="/webhooks", tags=["Payment Gateway Webhooks"])


@router.post(
    "/razorpay",
    status_code=status.HTTP_200_OK,
    summary="Razorpay Live Event Webhook Listener",
    description="Securely ingests, verifies, and fulfills live Razorpay payment, failure, and subscription lifecycle events.",
)
async def handle_razorpay_webhook(
    request: Request,
    x_razorpay_signature: str = Header(..., alias="X-Razorpay-Signature"),
    x_razorpay_event_id: str = Header(None, alias="X-Razorpay-Event-Id"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Ingests and fulfills Razorpay webhook events with strict idempotency:
    - payment.captured / order.paid
    - payment.failed
    - subscription.charged
    """
    raw_body = await request.body()

    # 1. Verify HMAC-SHA256 Webhook Signature
    is_valid = BillingService.verify_webhook_signature(
        raw_body=raw_body,
        signature=x_razorpay_signature,
        webhook_secret=getattr(settings, "RAZORPAY_WEBHOOK_SECRET", None),
    )
    if not is_valid:
        logger.warning("[Webhook] Invalid Razorpay webhook signature received.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid cryptographic webhook signature.",
        )

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception as e:
        logger.error(f"[Webhook] Malformed JSON in webhook payload: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed JSON.")

    event_type = payload.get("event", "")
    event_payload = payload.get("payload", {})
    logger.info(f"[Webhook] Received Razorpay event: {event_type}")

    # -------------------------------------------------------------------------
    # 2. STRICT IDEMPOTENCY CHECK (RazorpayWebhookEvent)
    # -------------------------------------------------------------------------
    event_id = x_razorpay_event_id or payload.get("event_id") or payload.get("id")
    if not event_id:
        # Fallback hash of event_type + raw_body
        event_id = f"evt_{hashlib.sha256(raw_body).hexdigest()[:24]}"

    existing_event = db.query(RazorpayWebhookEvent).filter_by(event_id=event_id).first()
    if existing_event and existing_event.processing_status == "PROCESSED":
        logger.info(f"[Webhook] Event {event_id} already processed. Returning idempotent HTTP 200.")
        return {
            "status": "already_processed",
            "event": event_type,
            "event_id": event_id,
            "processed": True,
        }

    if not existing_event:
        webhook_log = RazorpayWebhookEvent(
            event_id=event_id,
            event_type=event_type,
            payload=payload,
            processing_status="RECEIVED",
        )
        db.add(webhook_log)
        db.commit()
    else:
        webhook_log = existing_event

    try:
        # -------------------------------------------------------------------------
        # 3. EVENT: PAYMENT.FAILED (Section 24.7)
        # -------------------------------------------------------------------------
        if event_type in ["payment.failed"]:
            payment_entity = event_payload.get("payment", {}).get("entity", {})
            order_id = payment_entity.get("order_id", "")
            payment_id = payment_entity.get("id", "")
            error_code = payment_entity.get("error_code") or "PAYMENT_FAILED"
            error_desc = payment_entity.get("error_description") or "Payment transaction failed at gateway."
            notes = payment_entity.get("notes", {})
            sub_id_val = None
            if notes.get("subscriber_id"):
                try:
                    sub_id_val = uuid.UUID(notes.get("subscriber_id"))
                except ValueError:
                    pass

            payment_failure_service.handle_gateway_payment_failure(
                db=db,
                razorpay_order_id=order_id,
                error_code=error_code,
                error_description=error_desc,
                razorpay_payment_id=payment_id,
                subscriber_id=sub_id_val,
            )

        # -------------------------------------------------------------------------
        # 4. EVENT: PAYMENT.CAPTURED / ORDER.PAID (Section 24)
        # -------------------------------------------------------------------------
        elif event_type in ["payment.captured", "order.paid", "subscription.charged"]:
            payment_entity = event_payload.get("payment", {}).get("entity", {})
            order_id = payment_entity.get("order_id", "")
            payment_id = payment_entity.get("id", "")
            notes = payment_entity.get("notes", {})

            # Check if this payment belongs to an Expert Marketplace Evaluation Case
            case_id_str = notes.get("case_id")
            if case_id_str:
                try:
                    case_id = uuid.UUID(case_id_str)
                    case = db.query(EvaluationCase).filter(EvaluationCase.case_id == case_id).first()
                    if case and case.case_status == CaseStatus.ASSIGNED.value:
                        case.case_status = CaseStatus.AWAITING_UPLOAD.value
                        p_order = db.query(PaymentOrder).filter(PaymentOrder.case_id == case_id).first()
                        if p_order:
                            p_order.payment_status = PaymentStatus.PAID.value
                            p_order.gateway_payment_id = payment_id
                        db.commit()
                        logger.info(f"[Webhook] Case {case_id} moved to AWAITING_UPLOAD via payment {payment_id}")
                except Exception as e:
                    logger.error(f"[Webhook] Error processing case payment fulfillment: {e}")

            # Check if this payment belongs to a Subscription Plan checkout
            subscriber_id_str = notes.get("subscriber_id")
            plan_id = notes.get("plan_id")
            duration_months = int(notes.get("duration_months", 1))

            if subscriber_id_str and plan_id:
                try:
                    subscriber_id = uuid.UUID(subscriber_id_str)
                    sub_service = SubscriptionService()
                    billing_service = BillingService()

                    # Calculate quote
                    quote = sub_service.calculate_checkout_quote(
                        plan_id=plan_id,
                        duration_months=duration_months,
                        state=notes.get("state", "Tamil Nadu"),
                    )

                    # Activate or renew subscription in DB
                    now_utc = datetime.now(timezone.utc)
                    existing_sub = (
                        db.query(Subscription)
                        .filter(Subscription.subscriber_id == subscriber_id)
                        .order_by(Subscription.created_at.desc())
                        .first()
                    )

                    if existing_sub and existing_sub.status in ["PENDING_PAYMENT", "EXPIRED", "PAST_DUE"]:
                        existing_sub.status = "ACTIVE"
                        existing_sub.plan_id = plan_id
                        existing_sub.duration_months = duration_months
                        existing_sub.start_date = now_utc
                        existing_sub.expiry_date = now_utc + timedelta(days=duration_months * 30)
                        existing_sub.razorpay_order_id = order_id
                    elif not existing_sub:
                        new_sub = Subscription(
                            subscription_id=uuid.uuid4(),
                            subscriber_id=subscriber_id,
                            plan_id=plan_id,
                            duration_months=duration_months,
                            start_date=now_utc,
                            expiry_date=now_utc + timedelta(days=duration_months * 30),
                            status="ACTIVE",
                            razorpay_order_id=order_id,
                        )
                        db.add(new_sub)

                    # Provision usage quota
                    month_key = now_utc.strftime("%Y-%m")
                    quota = db.query(SubscriberUsageQuota).filter(
                        SubscriberUsageQuota.subscriber_id == subscriber_id,
                        SubscriberUsageQuota.month_key == month_key,
                    ).first()
                    if not quota:
                        quota = SubscriberUsageQuota(
                            quota_id=uuid.uuid4(),
                            subscriber_id=subscriber_id,
                            month_key=month_key,
                        )
                        db.add(quota)
                    db.commit()

                    # Issue B2C GST Tax Invoice
                    billing_service.create_subscription_invoice(
                        db=db,
                        subscriber_id=subscriber_id,
                        quote=quote,
                        razorpay_payment_id=payment_id,
                        razorpay_order_id=order_id,
                    )
                    logger.info(f"[Webhook] Subscription fulfilled and activated for subscriber {subscriber_id}")
                except Exception as e:
                    logger.error(f"[Webhook] Error fulfilling subscription invoice: {e}")

        # -------------------------------------------------------------------------
        # 4b. EVENT: SUBSCRIPTION.CANCELLED
        # -------------------------------------------------------------------------
        elif event_type in ["subscription.cancelled"]:
            sub_entity = event_payload.get("subscription", {}).get("entity", {})
            sub_id_str = sub_entity.get("id")
            if sub_id_str:
                target_sub = db.query(Subscription).filter(
                    Subscription.razorpay_subscription_id == sub_id_str
                ).first()
                if target_sub:
                    target_sub.auto_renew = False
                    target_sub.mandate_status = "CANCELLED"
                    target_sub.cancellation_requested_at = datetime.now(timezone.utc)
                    db.commit()
                    logger.info(f"[Webhook] Cancelled auto-renew for subscription {target_sub.subscription_id}")

        # -------------------------------------------------------------------------
        # 4c. EVENT: REFUND.PROCESSED
        # -------------------------------------------------------------------------
        elif event_type in ["refund.processed"]:
            refund_entity = event_payload.get("refund", {}).get("entity", {})
            pay_id = refund_entity.get("payment_id")
            ref_id = refund_entity.get("id")
            ref_amt = float(refund_entity.get("amount", 0)) / 100.0
            if pay_id:
                inv = db.query(BillingInvoice).filter(BillingInvoice.razorpay_payment_id == pay_id).first()
                if inv:
                    inv.payment_status = "REFUNDED"
                    inv.refund_amount = ref_amt
                    inv.refunded_at = datetime.now(timezone.utc)
                    db.commit()
                    logger.info(f"[Webhook] Processed refund {ref_id} for invoice {inv.invoice_number}")

        # Mark webhook event as PROCESSED
        webhook_log.processing_status = "PROCESSED"
        webhook_log.processed_at = datetime.now(timezone.utc)
        db.commit()

    except Exception as exc:
        logger.error(f"[Webhook] Exception processing event {event_id}: {exc}")
        webhook_log.processing_status = "FAILED"
        webhook_log.error_message = str(exc)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Webhook processing failure: {str(exc)}",
        )

    # -------------------------------------------------------------------------
    # 5. IDEMPOTENT HTTP 200 ACKNOWLEDGMENT
    # -------------------------------------------------------------------------
    return {
        "status": "success",
        "event": event_type,
        "event_id": event_id,
        "processed": True,
    }
