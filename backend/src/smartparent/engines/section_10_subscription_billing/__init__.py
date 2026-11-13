"""
STUDIQS® SmartParent™ - Section 10 & 24/25: Subscription, Billing & Entitlement Quota Package
=============================================================================
Module Package: src.smartparent.engines.section_10_subscription_billing

Engines included:
  - subscription_pricing_engine:
      * SubscriptionPricingEngine
      * Proposed & v6.2 Base Pricing Matrices
      * Indian GST 18% (CGST 9% + SGST 9% or IGST 18%)
      * Multi-month savings & discount calculator
  - calendar_validity_engine:
      * CalendarValidityEngine
      * Non-drifting calendar-month validity arithmetic (Jan 31 -> Feb 28/29)
      * Subscription status evaluation (ACTIVE, EXPIRING_SOON, EXPIRED, etc.)
      * 4-Stage Renewal reminder schedule builder (7d, 3d, 1d, on-expiry)
  - entitlement_quota_engine:
      * EntitlementQuotaEngine
      * Tier limits: Basic (4/1/1/1), Advanced (12/3/3/3), Pro (30/6/6/6)
      * Pre-flight entitlement checks with 80% soft warnings
      * Daily-prorated upgrade credit calculation
  - subscriber_intelligence_engine:
      * SubscriberIntelligenceEngine
      * Multi-month MRR Normalization
      * Churn rate, renewal rate, ARPU
  - invoice_generator_engine:
      * InvoiceGeneratorEngine
      * Sequential GST Tax Invoice numbering (INV-STQ-YYYY-NNNNN)
      * SAC Code 998431 line items
=============================================================================
"""

from .subscription_pricing_engine import (
    SubscriptionPlanTier,
    BillingDuration,
    DurationLabel,
    PROPOSED_PRICING_MATRIX,
    BASE_V62_PRICING_MATRIX,
    GSTBreakdownSchema,
    CheckoutQuoteSchema,
    PlanDurationPricingSchema,
    PlanCatalogSummarySchema,
    SubscriptionPricingEngine,
)

from .calendar_validity_engine import (
    SubscriptionLifecycleStatus,
    ReminderTypeEnum,
    RenewalReminderScheduleItem,
    SubscriptionStatusEvaluationSchema,
    CalendarValidityEngine,
)

from .entitlement_quota_engine import (
    QuotaActionType,
    TIER_LIMITS,
    EntitlementDecisionSchema,
    QuotaUsageOverviewSchema,
    UpgradeProrationQuoteSchema,
    EntitlementQuotaEngine,
)

from .subscriber_intelligence_engine import (
    PlanRevenueBreakdownSchema,
    DurationRevenueBreakdownSchema,
    MonthlyRevenueReportSchema,
    SubscriberIntelligenceEngine,
)

from .invoice_generator_engine import (
    STUDIQS_COMPANY_INFO,
    InvoiceItemSchema,
    TaxInvoiceSchema,
    InvoiceGeneratorEngine,
)

__all__ = [
    # Pricing
    "SubscriptionPlanTier",
    "BillingDuration",
    "DurationLabel",
    "PROPOSED_PRICING_MATRIX",
    "BASE_V62_PRICING_MATRIX",
    "GSTBreakdownSchema",
    "CheckoutQuoteSchema",
    "PlanDurationPricingSchema",
    "PlanCatalogSummarySchema",
    "SubscriptionPricingEngine",
    # Calendar Validity
    "SubscriptionLifecycleStatus",
    "ReminderTypeEnum",
    "RenewalReminderScheduleItem",
    "SubscriptionStatusEvaluationSchema",
    "CalendarValidityEngine",
    # Entitlement & Quotas
    "QuotaActionType",
    "TIER_LIMITS",
    "EntitlementDecisionSchema",
    "QuotaUsageOverviewSchema",
    "UpgradeProrationQuoteSchema",
    "EntitlementQuotaEngine",
    # Management Analytics
    "PlanRevenueBreakdownSchema",
    "DurationRevenueBreakdownSchema",
    "MonthlyRevenueReportSchema",
    "SubscriberIntelligenceEngine",
    # Invoice Generation
    "STUDIQS_COMPANY_INFO",
    "InvoiceItemSchema",
    "TaxInvoiceSchema",
    "InvoiceGeneratorEngine",
]
