"""
STUDIQS® SmartParent™ - Section 24.7 Payment Failure & Expiry Handling Schemas
=============================================================================
Module: src.smartparent.schemas.payment_failure
Governs:
  1. Failed payment event payloads and retry triggers.
  2. Idempotent payment retry orders (retaining invoice history).
  3. Grace period telemetry and feature gating status.
  4. Seamless expired renewal retaining existing child academic profiles.
=============================================================================
"""

import uuid
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict


class PaymentFailureEventSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")

    razorpay_order_id: str = Field(..., description="Razorpay order ID that failed")
    razorpay_payment_id: Optional[str] = Field(None, description="Razorpay payment ID if assigned")
    error_code: str = Field(..., description="Gateway failure code (e.g. BAD_REQUEST_ERROR, PAYMENT_FAILED)")
    error_description: str = Field(..., description="Human-readable reason for payment failure")
    subscriber_id: Optional[uuid.UUID] = Field(None, description="Associated subscriber ID")


class RetryPaymentRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    invoice_id: Optional[uuid.UUID] = Field(None, description="Existing failed/pending invoice ID")
    subscription_id: Optional[uuid.UUID] = Field(None, description="Existing subscription ID")
    state: str = Field("Tamil Nadu", description="State for GST calculation")


class RetryPaymentResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    retry_order_id: str = Field(..., description="Fresh Razorpay order ID for retry")
    amount: float = Field(..., description="Exact payable amount including GST")
    currency: str = Field("INR", description="Currency code")
    key_id: str = Field(..., description="Public Razorpay key for checkout")
    invoice_id: uuid.UUID = Field(..., description="Existing invoice ID retained without duplication")
    subscription_id: Optional[uuid.UUID] = Field(None, description="Subscription ID linked")
    checkout_url: str = Field(..., description="Direct retry checkout URL")
    message: str = Field(..., description="Customer guidance message")


class ExpiredRenewalRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    plan_id: str = Field(..., description="Target renewal plan: BASIC, ADVANCED, PRO")
    duration_months: int = Field(..., description="Duration: 1, 3, 6, 12")
    state: str = Field("Tamil Nadu", description="State for GST calculation")


class ExpiredRenewalResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    subscriber_id: uuid.UUID = Field(..., description="Parent subscriber ID")
    plan_id: str = Field(..., description="Renewed plan ID")
    duration_months: int = Field(..., description="Renewed duration months")
    preserved_children_count: int = Field(..., description="Number of linked child profiles preserved")
    preserved_children_names: List[str] = Field(..., description="Names of preserved children profiles")
    new_order_id: str = Field(..., description="New Razorpay order ID")
    amount: float = Field(..., description="Gross amount payable including GST")
    checkout_url: str = Field(..., description="Checkout URL for re-activation")
    message: str = Field(..., description="Customer reassurance on data preservation")


class GracePeriodStatusResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    subscriber_id: uuid.UUID
    subscription_id: Optional[uuid.UUID]
    plan_id: str
    status: str  # ACTIVE, PAST_DUE, EXPIRED
    is_in_grace_period: bool
    days_past_due: int
    grace_period_days_remaining: int
    paid_features_locked: bool
    academic_data_preserved: bool
    cta: str
    checkout_url: str

