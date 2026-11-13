"""
STUDIQS® SmartParent™ (v6.3 Complete) - Subscription & Billing API Endpoints
=============================================================================
Module: src.smartparent.api.v1.subscriptions
Section 24: Subscription, Invoicing & Gateway Webhooks
Section 24.7: Payment Failure, Retry Reconciliation & Idempotent Handling

Exposes production REST API endpoints:
  - GET  /catalog         : Plan catalog, feature comparison & 4 duration prices.
  - POST /quote           : Checkout quote calculation with GST 18% breakdown.
  - POST /upgrade-quote   : Mid-term prorated upgrade credit calculation.
  - POST /check-quota     : Pre-flight entitlement check with soft warnings.
  - GET  /alerts/banner   : Dynamic renewal and expiry alert banner.
  - POST /retry-payment   : Idempotent payment retry order.
  - POST /expired-renew   : Seamless renewal preserving child profiles.
  - GET  /grace-period-status : 3-day grace period evaluation.
  - GET  /checkout-config : 12 Nov 2026 payment mode discovery (Net Banking excluded).
  - POST /create-order    : Authoritative order / recurring mandate creation with DPDP consent.
  - POST /verify-payment  : Polymorphic HMAC-SHA256 signature verification & activation.
  - POST /cancel-auto-renew : Graceful mandate cancellation preserving paid access.
  - GET  /me              : Parent subscription dashboard per child with invoice history.
=============================================================================
"""

import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from src.smartparent.api.deps import get_current_subscriber_id, get_db
from src.smartparent.services.subscription_service import SubscriptionService
from src.smartparent.services.renewal_alert_service import renewal_alert_service
from src.smartparent.services.payment_failure_service import payment_failure_service
from src.smartparent.services.checkout_service import checkout_service
from src.smartparent.schemas.renewal_alerts import ParentRenewalAlertBannerResponse
from src.smartparent.schemas.payment_failure import (
    RetryPaymentRequest,
    RetryPaymentResponse,
    ExpiredRenewalRequest,
    ExpiredRenewalResponse,
    GracePeriodStatusResponse,
)
from src.smartparent.schemas.subscription import (
    CheckoutQuoteRequestSchema,
    CheckoutQuoteSchema,
    PlanCatalogSummarySchema,
    PlanUpgradeQuoteRequestSchema,
    UpgradeProrationQuoteSchema,
    EntitlementCheckRequestSchema,
    EntitlementDecisionSchema,
    CheckoutConfigResponse,
    SubscriptionCreateOrderRequest,
    SubscriptionCreateOrderResponse,
    SubscriptionVerifyPaymentRequest,
    SubscriptionVerifyPaymentResponse,
    CancelAutoRenewRequest,
    CancelAutoRenewResponse,
    ParentSubscriptionDashboardResponse,
)

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions & Billing"])
_service = SubscriptionService()


@router.get(
    "/catalog",
    response_model=List[PlanCatalogSummarySchema],
    summary="Get Subscription Plan Catalog",
    description="Returns Basic, Advanced, and Pro plans across 1M, 3M, 6M, and 12M durations with savings.",
)
def get_catalog(pricing_model: str = Query("PROPOSED", description="PROPOSED or BASE_V62")):
    try:
        return _service.get_plan_catalog(pricing_model=pricing_model)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch subscription catalog: {str(e)}",
        )


@router.post(
    "/quote",
    response_model=CheckoutQuoteSchema,
    summary="Calculate Checkout Quote",
    description="Calculates gross amount, base taxable amount, and GST 18% (CGST/SGST or IGST) breakdown.",
)
def calculate_quote(request: CheckoutQuoteRequestSchema):
    try:
        return _service.calculate_checkout_quote(
            plan_id=request.plan_id,
            duration_months=request.duration_months,
            state=request.state,
            pricing_model=request.pricing_model,
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/upgrade-quote",
    response_model=UpgradeProrationQuoteSchema,
    summary="Calculate Plan Upgrade Proration Quote",
    description="Calculates daily-prorated unused credit from active plan applied to target upgrade plan.",
)
def calculate_upgrade_quote(request: PlanUpgradeQuoteRequestSchema):
    try:
        return _service.calculate_upgrade_proration(
            current_plan_id=request.current_plan_id,
            current_price_paid=request.current_price_paid,
            start_date=request.start_date,
            expiry_date=request.expiry_date,
            target_plan_id=request.target_plan_id,
            target_duration_months=request.target_duration_months,
            pricing_model=request.pricing_model,
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/check-quota",
    response_model=EntitlementDecisionSchema,
    summary="Check Action Entitlement Quota",
    description="Pre-flight verification for uploads, rechecks, diagnostics, voice queries, etc.",
)
def check_quota(request: EntitlementCheckRequestSchema):
    try:
        return _service.check_entitlement(
            action_type=request.action_type,
            plan_id=request.plan_id,
            current_usage=request.current_usage,
            is_active=request.is_active,
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/alerts/banner",
    response_model=ParentRenewalAlertBannerResponse,
    summary="Get Parent Renewal & Expiry Alert Banner",
    description="Calculates dynamic expiry banner and urgent action CTA for parent dashboard.",
)
def get_parent_renewal_banner(
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
    db: Session = Depends(get_db),
):
    try:
        return renewal_alert_service.get_parent_renewal_banner(
            db=db,
            subscriber_id=subscriber_id,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch renewal banner: {str(e)}",
        )


@router.post(
    "/retry-payment",
    response_model=RetryPaymentResponse,
    summary="Retry Unsuccessful Subscription Payment",
    description="Section 24.7: Generates idempotent payment retry order using existing invoice audit trail.",
)
def retry_payment(
    request: RetryPaymentRequest,
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
    db: Session = Depends(get_db),
):
    try:
        return payment_failure_service.initiate_retry_payment(
            db=db,
            subscriber_id=subscriber_id,
            invoice_id=request.invoice_id,
            subscription_id=request.subscription_id,
            state=request.state,
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/expired-renew",
    response_model=ExpiredRenewalResponse,
    summary="Seamless Renewal for Expired Subscribers",
    description="Section 24.7: Re-activates subscription while strictly preserving existing child profiles and academic history.",
)
def renew_expired_subscription(
    request: ExpiredRenewalRequest,
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
    db: Session = Depends(get_db),
):
    try:
        return payment_failure_service.process_expired_renewal(
            db=db,
            subscriber_id=subscriber_id,
            plan_id=request.plan_id,
            duration_months=request.duration_months,
            state=request.state,
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/grace-period-status",
    response_model=GracePeriodStatusResponse,
    summary="Get 3-Day Grace Period & Gating Status",
    description="Section 24.7: Evaluates whether subscriber is in 3-day grace period, with academic data retention guaranteed.",
)
def get_grace_period_status(
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
    db: Session = Depends(get_db),
):
    try:
        return payment_failure_service.get_grace_period_status(
            db=db,
            subscriber_id=subscriber_id,
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# =============================================================================
# 12 Nov 2026 Payment Integration & Mandate Lifecycle Endpoints
# =============================================================================

@router.get(
    "/checkout-config",
    response_model=CheckoutConfigResponse,
    summary="Get Checkout Configuration & Payment Modes",
    description="Returns enabled payment methods (Net Banking excluded), baseline plan pricing, and mandatory DPDP legal consent texts.",
)
def get_checkout_config(
    child_id: Optional[uuid.UUID] = Query(None, description="Optional target child UUID"),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
    db: Session = Depends(get_db),
):
    try:
        return checkout_service.get_checkout_config(
            db=db,
            subscriber_id=subscriber_id,
            child_id=child_id,
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/create-order",
    response_model=SubscriptionCreateOrderResponse,
    summary="Create Authoritative Subscription Order / Mandate",
    description="Validates child ownership, records affirmative DPDP consents, and creates a Razorpay Order or Recurring Mandate with contextual metadata.",
)
def create_subscription_order(
    request: SubscriptionCreateOrderRequest,
    req: Request,
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
    db: Session = Depends(get_db),
):
    try:
        client_ip = req.client.host if req.client else None
        user_agent = req.headers.get("user-agent")
        return checkout_service.create_subscription_order(
            db=db,
            subscriber_id=subscriber_id,
            request=request,
            client_ip=client_ip,
            user_agent=user_agent,
        )
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/verify-payment",
    response_model=SubscriptionVerifyPaymentResponse,
    summary="Verify Payment & Authoritatively Activate Subscription",
    description="Polymorphically verifies HMAC-SHA256 signature for one-time orders or recurring mandates, generates sequential GST invoice, and provisions quota.",
)
def verify_payment(
    request: SubscriptionVerifyPaymentRequest,
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
    db: Session = Depends(get_db),
):
    try:
        return checkout_service.verify_and_fulfill_subscription_payment(
            db=db,
            subscriber_id=subscriber_id,
            request=request,
        )
    except ValueError as ve:
        err_msg = str(ve)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err_msg)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/cancel-auto-renew",
    response_model=CancelAutoRenewResponse,
    summary="Cancel Auto-Renewal Mandate Gracefully",
    description="Cancels future recurring debits with Razorpay while preserving paid access until the current paid-through date.",
)
def cancel_auto_renewal(
    request: CancelAutoRenewRequest,
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
    db: Session = Depends(get_db),
):
    try:
        return checkout_service.cancel_auto_renewal(
            db=db,
            subscriber_id=subscriber_id,
            request=request,
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/me",
    response_model=ParentSubscriptionDashboardResponse,
    summary="Parent Subscription Dashboard & Billing Overview",
    description="Returns active subscriptions per child, paid-through dates, mandate flags, and downloadable invoice list.",
)
def get_parent_subscription_dashboard(
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
    db: Session = Depends(get_db),
):
    try:
        return checkout_service.get_parent_subscription_dashboard(
            db=db,
            subscriber_id=subscriber_id,
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
