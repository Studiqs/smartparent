"""
STUDIQS® SmartParent™ (v6.3) - Subscription & Billing Pydantic Schemas
=============================================================================
Module: src.smartparent.schemas.subscription

Defines API request/response contracts for subscription management:
  - Plan Catalog & Pricing Quotes
  - Checkout & Payment Verification
  - Live Status & Expiry Alerts
  - Entitlement & Quota Dashboards
  - Plan Upgrades & Prorated Quotes
  - Invoices & Billing History
  - Management MRR Analytics
=============================================================================
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict

from src.smartparent.engines.section_10_subscription_billing import (
    GSTBreakdownSchema,
    CheckoutQuoteSchema,
    PlanDurationPricingSchema,
    PlanCatalogSummarySchema,
    RenewalReminderScheduleItem,
    SubscriptionStatusEvaluationSchema,
    EntitlementDecisionSchema,
    QuotaUsageOverviewSchema,
    UpgradeProrationQuoteSchema,
    PlanRevenueBreakdownSchema,
    DurationRevenueBreakdownSchema,
    MonthlyRevenueReportSchema,
    InvoiceItemSchema,
    TaxInvoiceSchema,
)


# =============================================================================
# Request Schemas
# =============================================================================

class CheckoutQuoteRequestSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")
    plan_id: str = Field(..., description="BASIC, ADVANCED, or PRO")
    duration_months: int = Field(..., description="1, 3, 6, or 12")
    state: str = Field(default="Tamil Nadu", description="State for GST tax determination")
    pricing_model: str = Field(default="PROPOSED", description="PROPOSED or BASE_V62")


class PlanUpgradeQuoteRequestSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")
    current_plan_id: str
    current_price_paid: float
    start_date: datetime
    expiry_date: datetime
    target_plan_id: str
    target_duration_months: int = 1
    pricing_model: str = "PROPOSED"


class EntitlementCheckRequestSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")
    action_type: str = Field(..., description="DOCUMENT_UPLOAD, GAP_RECHECK, DIAGNOSTIC, EXPERT_CASE, VOICE_QUERY")
    plan_id: str = "BASIC"
    current_usage: int = 0
    is_active: bool = True


class BillingHistoryItemSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")
    invoice_id: str
    invoice_number: str
    payment_date: datetime
    plan_id: str
    duration_label: str
    billing_period: str
    amount_paid: float
    tax_amount: float
    payment_status: str
    payment_reference: Optional[str] = None
    invoice_pdf_url: Optional[str] = None


# =============================================================================
# 12 Nov 2026 Payment Integration & DPDP Consent Schemas
# =============================================================================

class ConsentItemSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")
    consent_type: str = Field(..., description="TERMS_AND_REFUND, CHILD_DATA_DPDP, AUTO_RENEWAL_MANDATE, EXPERT_COMMISSION_AND_TERMS")
    policy_version: str = Field(..., description="Version of presented policy, e.g. v1.0-20261112")
    accepted: bool = Field(..., description="Whether user affirmatively accepted")


class PlanPricingMeta(BaseModel):
    model_config = ConfigDict(extra="ignore")
    monthly_price: float
    currency: str = "INR"
    gst_pct: float = 18.0


class CheckoutConfigResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    subscriber_id: str
    child_id: Optional[str] = None
    child_name: Optional[str] = None
    plan_pricing: Dict[str, PlanPricingMeta]
    allowed_payment_methods: List[str]
    allowed_recurring_methods: List[str]
    disallowed_methods: List[str]
    consent_policies: Dict[str, str]


class SubscriptionCreateOrderRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    plan_id: str = Field(..., description="BASIC, ADVANCED, or PRO")
    child_id: str = Field(..., description="UUID of target child")
    duration_months: int = Field(default=1, description="1, 3, 6, or 12")
    state: str = Field(default="Tamil Nadu", description="Billing state for GST")
    opt_in_auto_renewal: bool = Field(default=False, description="Explicit opt-in for recurring mandate")
    consents: List[ConsentItemSchema] = Field(..., description="Mandatory affirmative consents")


class SubscriptionCreateOrderResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    checkout_type: str  # 'ONE_TIME' or 'RECURRING'
    gateway_order_id: Optional[str] = None
    gateway_subscription_id: Optional[str] = None
    amount_paise: int
    key_id: str
    currency: str = "INR"
    child_id: str
    plan_id: str
    tax_breakdown: Dict[str, float]


class SubscriptionVerifyPaymentRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    razorpay_payment_id: str = Field(..., description="Payment ID from Razorpay")
    razorpay_order_id: Optional[str] = Field(None, description="Order ID (for one-time checkout)")
    razorpay_subscription_id: Optional[str] = Field(None, description="Subscription ID (for recurring mandate)")
    razorpay_signature: str = Field(..., description="HMAC SHA-256 signature")
    child_id: str = Field(..., description="Target child UUID")
    plan_id: str = Field(..., description="BASIC, ADVANCED, or PRO")


class SubscriptionVerifyPaymentResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    status: str = "SUCCESS"
    subscription_id: str
    child_id: str
    plan_id: str
    period_start: datetime
    period_end: datetime
    auto_renew: bool
    invoice_number: str
    invoice_pdf_url: Optional[str] = None


class CancelAutoRenewRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    subscription_id: str
    child_id: str
    reason: Optional[str] = None


class CancelAutoRenewResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    status: str = "CANCELLED_RENEWAL"
    subscription_id: str
    child_id: str
    auto_renew: bool = False
    active_until: datetime
    message: str


class ChildSubscriptionItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    subscription_id: str
    child_id: str
    child_name: str
    plan_id: str
    status: str
    auto_renew: bool
    mandate_status: str
    period_start: datetime
    period_end: datetime
    cancellation_requested_at: Optional[datetime] = None


class ParentSubscriptionDashboardResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    subscriber_id: str
    subscriptions: List[ChildSubscriptionItem]
    invoices: List[BillingHistoryItemSchema]


# Re-exports for clean API usage
__all__ = [
    "CheckoutQuoteRequestSchema",
    "PlanUpgradeQuoteRequestSchema",
    "EntitlementCheckRequestSchema",
    "BillingHistoryItemSchema",
    "ConsentItemSchema",
    "PlanPricingMeta",
    "CheckoutConfigResponse",
    "SubscriptionCreateOrderRequest",
    "SubscriptionCreateOrderResponse",
    "SubscriptionVerifyPaymentRequest",
    "SubscriptionVerifyPaymentResponse",
    "CancelAutoRenewRequest",
    "CancelAutoRenewResponse",
    "ChildSubscriptionItem",
    "ParentSubscriptionDashboardResponse",
    "GSTBreakdownSchema",
    "CheckoutQuoteSchema",
    "PlanDurationPricingSchema",
    "PlanCatalogSummarySchema",
    "RenewalReminderScheduleItem",
    "SubscriptionStatusEvaluationSchema",
    "EntitlementDecisionSchema",
    "QuotaUsageOverviewSchema",
    "UpgradeProrationQuoteSchema",
    "PlanRevenueBreakdownSchema",
    "DurationRevenueBreakdownSchema",
    "MonthlyRevenueReportSchema",
    "InvoiceItemSchema",
    "TaxInvoiceSchema",
]
