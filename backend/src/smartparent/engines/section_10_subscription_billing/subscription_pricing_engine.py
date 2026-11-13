"""
STUDIQS® SmartParent™ - Section 10 & 24: Subscription Pricing & GST Engine
=============================================================================
Module: src.smartparent.engines.section_10_subscription_billing.subscription_pricing_engine

Implements Netflix-style subscription pricing across:
  - Plans: BASIC, ADVANCED, PRO
  - Durations: 1 Month, 3 Months, 6 Months, 12 Months (Annual)
  - Proposed GST-inclusive pricing matrix & fallback v6.2 base pricing matrix.
  - Indian GST 18% calculation (Intra-state: CGST 9% + SGST 9%; Inter-state: IGST 18%).
  - Multi-month savings & percentage discount calculations.
=============================================================================
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict
from src.smartparent.engines.section_00_core.base_engine import BaseEngine


# =============================================================================
# 1. Enums & Pricing Matrices
# =============================================================================

class SubscriptionPlanTier(str, Enum):
    BASIC = "BASIC"
    ADVANCED = "ADVANCED"
    PRO = "PRO"


class BillingDuration(int, Enum):
    MONTH_1 = 1
    MONTHS_3 = 3
    MONTHS_6 = 6
    MONTHS_12 = 12


class DurationLabel(str, Enum):
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    HALF_YEARLY = "HALF_YEARLY"
    ANNUAL = "ANNUAL"


DURATION_MONTHS_TO_LABEL: Dict[int, str] = {
    1: DurationLabel.MONTHLY.value,
    3: DurationLabel.QUARTERLY.value,
    6: DurationLabel.HALF_YEARLY.value,
    12: DurationLabel.ANNUAL.value,
}


# Proposed Studiqs SmartParent Pricing Matrix (All prices in INR, GST-inclusive)
PROPOSED_PRICING_MATRIX: Dict[str, Dict[int, float]] = {
    SubscriptionPlanTier.BASIC.value: {
        1: 199.0,
        3: 399.0,
        6: 699.0,
        12: 1199.0,
    },
    SubscriptionPlanTier.ADVANCED.value: {
        1: 399.0,
        3: 799.0,
        6: 1399.0,
        12: 2399.0,
    },
    SubscriptionPlanTier.PRO.value: {
        1: 599.0,
        3: 1199.0,
        6: 2099.0,
        12: 3599.0,
    },
}

# Base v6.2 Multiplied Pricing Matrix (Pre-tax Base Multiplier)
BASE_V62_PRICING_MATRIX: Dict[str, Dict[int, float]] = {
    SubscriptionPlanTier.BASIC.value: {
        1: 200.0,
        3: 600.0,
        6: 1200.0,
        12: 2400.0,
    },
    SubscriptionPlanTier.ADVANCED.value: {
        1: 400.0,
        3: 1200.0,
        6: 2400.0,
        12: 4800.0,
    },
    SubscriptionPlanTier.PRO.value: {
        1: 600.0,
        3: 1800.0,
        6: 3600.0,
        12: 7200.0,
    },
}


# =============================================================================
# 2. Pydantic Response Schemas
# =============================================================================

class GSTBreakdownSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")
    total_tax_rate: float = 18.0
    is_interstate: bool = False
    cgst_rate: float = 9.0
    cgst_amount: float = 0.0
    sgst_rate: float = 9.0
    sgst_amount: float = 0.0
    igst_rate: float = 0.0
    igst_amount: float = 0.0
    total_tax_amount: float = 0.0


class CheckoutQuoteSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")
    plan_id: str
    plan_name: str
    duration_months: int
    duration_label: str
    currency: str = "INR"
    # Pricing Breakdown
    gross_payable_amount: float = Field(description="Final total price payable by parent (GST-inclusive)")
    taxable_base_amount: float = Field(description="Base taxable amount before GST")
    gst_breakdown: GSTBreakdownSchema
    # Normalized & Savings Metrics
    monthly_equivalent_amount: float = Field(description="Cost broken down per month for transparency")
    savings_vs_monthly: float = Field(default=0.0, description="Rupees saved compared to 1-month recurring payment")
    discount_percentage: float = Field(default=0.0, description="Effective discount percentage")
    is_gst_inclusive: bool = True
    pricing_model: str = "PROPOSED"


class PlanDurationPricingSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")
    duration_months: int
    duration_label: str
    gross_price: float
    monthly_equivalent: float
    savings_amount: float
    discount_percentage: float


class PlanCatalogSummarySchema(BaseModel):
    model_config = ConfigDict(extra="ignore")
    plan_id: str
    plan_name: str
    tagline: str
    features: List[str]
    pricings: List[PlanDurationPricingSchema]
    is_recommended: bool = False


# =============================================================================
# 3. Production Subscription Pricing Engine
# =============================================================================

class SubscriptionPricingEngine(BaseEngine):
    """
    Section 10 & 24 Subscription Pricing & GST Computation Engine.
    Handles exact quote calculation, Indian GST 18% separation, multi-month savings,
    and plan catalog comparison.
    """

    HOME_STATE: str = "Tamil Nadu"
    GST_RATE: float = 0.18  # 18% standard rate for SaaS / EdTech in India

    def __init__(self, failure_threshold: int = 5):
        super().__init__(name="SubscriptionPricingEngine", failure_threshold=failure_threshold)

    # -------------------------------------------------------------------------
    # BaseEngine Lifecycle Hooks
    # -------------------------------------------------------------------------

    def validate_input(self, input_data: Any) -> Dict[str, Any]:
        """Validates incoming quote request parameters."""
        if not isinstance(input_data, dict):
            raise ValueError("Input to SubscriptionPricingEngine must be a dictionary")

        plan_id = str(input_data.get("plan_id", "")).upper()
        if plan_id not in [p.value for p in SubscriptionPlanTier]:
            raise ValueError(f"Invalid plan_id '{plan_id}'. Must be one of {[p.value for p in SubscriptionPlanTier]}")

        duration = int(input_data.get("duration_months", 1))
        if duration not in [d.value for d in BillingDuration]:
            raise ValueError(f"Invalid duration_months '{duration}'. Must be one of {[d.value for d in BillingDuration]}")

        state = str(input_data.get("state", self.HOME_STATE)).strip()
        pricing_model = str(input_data.get("pricing_model", "PROPOSED")).upper()

        return {
            "plan_id": plan_id,
            "duration_months": duration,
            "state": state,
            "pricing_model": pricing_model,
        }

    def execute_core(self, validated_data: Dict[str, Any]) -> CheckoutQuoteSchema:
        """Executes core pricing and GST calculation."""
        return self.calculate_checkout_quote(
            plan_id=validated_data["plan_id"],
            duration_months=validated_data["duration_months"],
            state=validated_data["state"],
            pricing_model=validated_data["pricing_model"],
        )

    def fallback(self, error: Exception, input_data: Any) -> CheckoutQuoteSchema:
        """Safe fallback defaulting to Basic 1-Month quote."""
        self.logger.warning("SubscriptionPricingEngine fallback invoked due to: %s", error)
        return self.calculate_checkout_quote(
            plan_id=SubscriptionPlanTier.BASIC.value,
            duration_months=1,
            state=self.HOME_STATE,
            pricing_model="PROPOSED",
        )

    # -------------------------------------------------------------------------
    # Core Domain Logic
    # -------------------------------------------------------------------------

    def get_price(self, plan_id: str, duration_months: int, pricing_model: str = "PROPOSED") -> float:
        """Retrieves raw price for given plan and duration."""
        matrix = PROPOSED_PRICING_MATRIX if pricing_model == "PROPOSED" else BASE_V62_PRICING_MATRIX
        plan_dict = matrix.get(plan_id.upper(), PROPOSED_PRICING_MATRIX[SubscriptionPlanTier.BASIC.value])
        return plan_dict.get(duration_months, plan_dict[1])

    def calculate_gst_breakdown(self, gross_amount: float, state: str) -> GSTBreakdownSchema:
        """
        Calculates backwards GST 18% from GST-inclusive gross amount.
        Formula:
          taxable_base = gross_amount / (1 + 0.18)
          total_gst = gross_amount - taxable_base
        """
        taxable_base = round(gross_amount / (1.0 + self.GST_RATE), 2)
        total_gst = round(gross_amount - taxable_base, 2)

        is_interstate = (state.strip().lower() != self.HOME_STATE.lower())

        if is_interstate:
            return GSTBreakdownSchema(
                total_tax_rate=18.0,
                is_interstate=True,
                cgst_rate=0.0,
                cgst_amount=0.0,
                sgst_rate=0.0,
                sgst_amount=0.0,
                igst_rate=18.0,
                igst_amount=total_gst,
                total_tax_amount=total_gst,
            )
        else:
            half_gst = round(total_gst / 2.0, 2)
            # Account for 1 paisa rounding difference if any
            remainder = round(total_gst - (half_gst * 2), 2)
            cgst = half_gst + remainder
            sgst = half_gst

            return GSTBreakdownSchema(
                total_tax_rate=18.0,
                is_interstate=False,
                cgst_rate=9.0,
                cgst_amount=cgst,
                sgst_rate=9.0,
                sgst_amount=sgst,
                igst_rate=0.0,
                igst_amount=0.0,
                total_tax_amount=total_gst,
            )

    def calculate_checkout_quote(
        self,
        plan_id: str,
        duration_months: int,
        state: str = "Tamil Nadu",
        pricing_model: str = "PROPOSED",
    ) -> CheckoutQuoteSchema:
        """
        Generates full checkout quote with tax and multi-month discount details.
        """
        norm_plan = plan_id.upper()
        gross_price = self.get_price(norm_plan, duration_months, pricing_model=pricing_model)
        single_month_price = self.get_price(norm_plan, 1, pricing_model=pricing_model)

        # Base 1-month equivalent if bought month-by-month
        full_recurring_amount = single_month_price * duration_months
        savings_amount = max(0.0, round(full_recurring_amount - gross_price, 2))
        discount_pct = round((savings_amount / full_recurring_amount) * 100.0, 1) if full_recurring_amount > 0 else 0.0

        monthly_equivalent = round(gross_price / duration_months, 2)
        gst = self.calculate_gst_breakdown(gross_price, state=state)
        taxable_base = round(gross_price - gst.total_tax_amount, 2)

        duration_label = DURATION_MONTHS_TO_LABEL.get(duration_months, f"{duration_months}_MONTHS")

        plan_display_names = {
            "BASIC": "Studiqs SmartParent Basic",
            "ADVANCED": "Studiqs SmartParent Advanced",
            "PRO": "Studiqs SmartParent Pro (with Voice AI)",
        }

        return CheckoutQuoteSchema(
            plan_id=norm_plan,
            plan_name=plan_display_names.get(norm_plan, norm_plan.capitalize()),
            duration_months=duration_months,
            duration_label=duration_label,
            currency="INR",
            gross_payable_amount=gross_price,
            taxable_base_amount=taxable_base,
            gst_breakdown=gst,
            monthly_equivalent_amount=monthly_equivalent,
            savings_vs_monthly=savings_amount,
            discount_percentage=discount_pct,
            is_gst_inclusive=True,
            pricing_model=pricing_model,
        )

    def get_plan_catalog(self, pricing_model: str = "PROPOSED") -> List[PlanCatalogSummarySchema]:
        """
        Returns complete customer-facing plan catalog with features and duration pricing.
        """
        plans_meta = [
            {
                "plan_id": "BASIC",
                "plan_name": "Basic",
                "tagline": "Essential Learning Intelligence for 1 Child",
                "is_recommended": False,
                "features": [
                    "4 Question Paper / Marksheet Uploads / month",
                    "1 Topic Gap Recheck / month",
                    "1 Diagnostic Quick Check / month",
                    "1 Active Subject Expert Evaluation",
                    "Subject Monthly Consistency Tracking",
                    "Monthly Parent Pulse (1 Improvement, 1 Watch, 1 Action)",
                    "Digital Report Card PDF",
                ],
            },
            {
                "plan_id": "ADVANCED",
                "plan_name": "Advanced",
                "tagline": "Deeper Insights & Accelerated Gap Resolution",
                "is_recommended": True,
                "features": [
                    "12 Question Paper / Marksheet Uploads / month",
                    "3 Topic Gap Rechecks / month",
                    "3 Diagnostic Quick Checks / month",
                    "3 Active Subject Expert Evaluations",
                    "All Basic Plan Features",
                    "Bloom's Mastery Matrix Breakdown",
                    "PTM & Tuition Prep Handoff Packs",
                    "WhatsApp One-Click Sharing Cards",
                    "Supports up to 2 Children",
                ],
            },
            {
                "plan_id": "PRO",
                "plan_name": "Pro (Voice AI)",
                "tagline": "Complete Academic Intelligence + AI Voice Assistant",
                "is_recommended": False,
                "features": [
                    "30 Question Paper / Marksheet Uploads / month",
                    "6 Topic Gap Rechecks / month",
                    "6 Diagnostic Quick Checks / month",
                    "6 Active Subject Expert Evaluations",
                    "All Advanced Plan Features",
                    "Board Readiness Index (Classes 10 & 12)",
                    "Projected Score & Cutoff Corridors (Engineering/Medical)",
                    "Stream & Career Pathway Recommendation",
                    "SmartParent RAG Voice Assistant (Tamil & English Q&A)",
                    "Priority 48-Hour Expert Turnaround SLA",
                    "Supports up to 4 Children",
                ],
            },
        ]

        catalog: List[PlanCatalogSummarySchema] = []
        for meta in plans_meta:
            pid = meta["plan_id"]
            pricing_options: List[PlanDurationPricingSchema] = []
            for d in [1, 3, 6, 12]:
                quote = self.calculate_checkout_quote(pid, d, pricing_model=pricing_model)
                pricing_options.append(
                    PlanDurationPricingSchema(
                        duration_months=d,
                        duration_label=quote.duration_label,
                        gross_price=quote.gross_payable_amount,
                        monthly_equivalent=quote.monthly_equivalent_amount,
                        savings_amount=quote.savings_vs_monthly,
                        discount_percentage=quote.discount_percentage,
                    )
                )

            catalog.append(
                PlanCatalogSummarySchema(
                    plan_id=pid,
                    plan_name=meta["plan_name"],
                    tagline=meta["tagline"],
                    features=meta["features"],
                    pricings=pricing_options,
                    is_recommended=meta["is_recommended"],
                )
            )

        return catalog
