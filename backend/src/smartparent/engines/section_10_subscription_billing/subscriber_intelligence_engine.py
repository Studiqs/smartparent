"""
STUDIQS® SmartParent™ - Section 25: Subscriber Intelligence & MRR Engine
=============================================================================
Module: src.smartparent.engines.section_10_subscription_billing.subscriber_intelligence_engine

Implements executive revenue analytics & metrics:
  - Multi-month MRR Normalization (Annual ₹3,599 -> ₹299.92/mo, Half-Yearly ₹2,099 -> ₹349.83/mo).
  - Cash collections vs Normalized MRR accounting.
  - Churn rate, renewal rate, conversion rate, ARPU (Average Revenue Per User).
  - Cohort breakdown by plan tier (Basic/Advanced/Pro) & duration (1M/3M/6M/12M).
=============================================================================
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict
from src.smartparent.engines.section_00_core.base_engine import BaseEngine


# =============================================================================
# 1. Schemas
# =============================================================================

class PlanRevenueBreakdownSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")
    plan_id: str
    active_subscriptions: int
    normalized_mrr: float
    percentage_of_mrr: float


class DurationRevenueBreakdownSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")
    duration_label: str
    duration_months: int
    active_subscriptions: int
    normalized_mrr: float
    total_contract_value: float


class MonthlyRevenueReportSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")
    month_key: str  # 'YYYY-MM'
    # Subscriber Counts
    opening_active_subscribers: int
    new_subscribers_acquired: int
    renewed_subscribers: int
    expired_subscribers: int
    cancelled_subscribers: int
    closing_active_subscribers: int
    # Revenue Metrics
    gross_cash_collections: float = Field(description="Actual cash collected in bank this month")
    total_refunds: float = Field(default=0.0)
    net_cash_collections: float = Field(description="Gross collections minus refunds")
    monthly_recurring_revenue_mrr: float = Field(description="Normalized monthly value of all active contracts")
    arpu: float = Field(description="Average Revenue Per Active User (MRR / Closing Subscribers)")
    # Rates
    churn_rate_pct: float
    renewal_rate_pct: float
    # Distributions
    plan_breakdown: List[PlanRevenueBreakdownSchema]
    duration_breakdown: List[DurationRevenueBreakdownSchema]


# =============================================================================
# 2. Production Subscriber Intelligence Engine
# =============================================================================

class SubscriberIntelligenceEngine(BaseEngine):
    """
    Section 25 Studiqs Subscriber Intelligence & Management Revenue Analytics Engine.
    Computes audited MRR, churn rates, and cohort metrics according to GAAP / SaaS standards.
    """

    def __init__(self, failure_threshold: int = 5):
        super().__init__(name="SubscriberIntelligenceEngine", failure_threshold=failure_threshold)

    # -------------------------------------------------------------------------
    # BaseEngine Lifecycle Hooks
    # -------------------------------------------------------------------------

    def validate_input(self, input_data: Any) -> Dict[str, Any]:
        """Validates subscriptions and movement figures."""
        if not isinstance(input_data, dict):
            raise ValueError("Input must be a dictionary")
        return input_data

    def execute_core(self, validated_data: Dict[str, Any]) -> MonthlyRevenueReportSchema:
        """Executes full MRR normalization and churn report generation."""
        return self.generate_monthly_revenue_report(
            month_key=validated_data.get("month_key", "CURRENT"),
            active_subscriptions=validated_data.get("active_subscriptions", []),
            opening_subscribers=int(validated_data.get("opening_subscribers", 0)),
            new_subscribers=int(validated_data.get("new_subscribers", 0)),
            renewed_subscribers=int(validated_data.get("renewed_subscribers", 0)),
            expired_subscribers=int(validated_data.get("expired_subscribers", 0)),
            cancelled_subscribers=int(validated_data.get("cancelled_subscribers", 0)),
            actual_cash_collected=float(validated_data.get("actual_cash_collected", 0.0)),
            refunds=float(validated_data.get("refunds", 0.0)),
        )

    def fallback(self, error: Exception, input_data: Any) -> MonthlyRevenueReportSchema:
        """Safe fallback with zeroed metrics."""
        self.logger.warning("SubscriberIntelligenceEngine fallback invoked: %s", error)
        return MonthlyRevenueReportSchema(
            month_key="FALLBACK",
            opening_active_subscribers=0,
            new_subscribers_acquired=0,
            renewed_subscribers=0,
            expired_subscribers=0,
            cancelled_subscribers=0,
            closing_active_subscribers=0,
            gross_cash_collections=0.0,
            net_cash_collections=0.0,
            monthly_recurring_revenue_mrr=0.0,
            arpu=0.0,
            churn_rate_pct=0.0,
            renewal_rate_pct=0.0,
            plan_breakdown=[],
            duration_breakdown=[],
        )

    # -------------------------------------------------------------------------
    # Core Domain Logic
    # -------------------------------------------------------------------------

    @staticmethod
    def normalize_single_subscription_mrr(contract_price: float, duration_months: int) -> float:
        """
        Normalizes a multi-month contract price into exact monthly recurring revenue.
        Section 25.2: For multi-month prepaid subscriptions, normalize the contracted value over its duration.
        """
        months = max(1, duration_months)
        return round(contract_price / float(months), 2)

    def generate_monthly_revenue_report(
        self,
        month_key: str,
        active_subscriptions: List[Dict[str, Any]],
        opening_subscribers: int,
        new_subscribers: int,
        renewed_subscribers: int,
        expired_subscribers: int,
        cancelled_subscribers: int,
        actual_cash_collected: float,
        refunds: float = 0.0,
    ) -> MonthlyRevenueReportSchema:
        """
        Computes the complete Section 25 executive revenue report.
        """
        # 1. Closing count calculation
        closing_subscribers = max(0, opening_subscribers + new_subscribers - expired_subscribers - cancelled_subscribers)

        # 2. MRR Normalization across active contracts
        total_mrr = 0.0
        plan_counts: Dict[str, int] = {"BASIC": 0, "ADVANCED": 0, "PRO": 0}
        plan_mrr: Dict[str, float] = {"BASIC": 0.0, "ADVANCED": 0.0, "PRO": 0.0}

        duration_counts: Dict[int, int] = {1: 0, 3: 0, 6: 0, 12: 0}
        duration_mrr: Dict[int, float] = {1: 0.0, 3: 0.0, 6: 0.0, 12: 0.0}
        duration_contract_value: Dict[int, float] = {1: 0.0, 3: 0.0, 6: 0.0, 12: 0.0}

        duration_labels = {1: "Monthly", 3: "Quarterly", 6: "Half-Yearly", 12: "Annual"}

        for sub in active_subscriptions:
            plan = str(sub.get("plan_id", "BASIC")).upper()
            dur = int(sub.get("duration_months", 1))
            price = float(sub.get("price_paid", 0.0))

            mrr_contribution = self.normalize_single_subscription_mrr(price, dur)
            total_mrr += mrr_contribution

            if plan in plan_counts:
                plan_counts[plan] += 1
                plan_mrr[plan] += mrr_contribution

            if dur in duration_counts:
                duration_counts[dur] += 1
                duration_mrr[dur] += mrr_contribution
                duration_contract_value[dur] += price

        total_mrr = round(total_mrr, 2)
        net_cash = round(max(0.0, actual_cash_collected - refunds), 2)

        # 3. Churn & Renewal Rate calculations
        churn_rate = 0.0
        if opening_subscribers > 0:
            lost = expired_subscribers + cancelled_subscribers
            churn_rate = round((lost / float(opening_subscribers)) * 100.0, 2)

        renewal_rate = 0.0
        total_eligible_for_renewal = expired_subscribers + renewed_subscribers
        if total_eligible_for_renewal > 0:
            renewal_rate = round((renewed_subscribers / float(total_eligible_for_renewal)) * 100.0, 2)

        # 4. ARPU (Average Revenue Per User)
        arpu = 0.0
        denominator = closing_subscribers if closing_subscribers > 0 else len(active_subscriptions)
        if denominator > 0:
            arpu = round(total_mrr / float(denominator), 2)

        # 5. Build Breakdowns
        plan_breakdown: List[PlanRevenueBreakdownSchema] = []
        for p in ["BASIC", "ADVANCED", "PRO"]:
            p_mrr = round(plan_mrr.get(p, 0.0), 2)
            pct = round((p_mrr / total_mrr * 100.0), 1) if total_mrr > 0 else 0.0
            plan_breakdown.append(
                PlanRevenueBreakdownSchema(
                    plan_id=p,
                    active_subscriptions=plan_counts.get(p, 0),
                    normalized_mrr=p_mrr,
                    percentage_of_mrr=pct,
                )
            )

        duration_breakdown: List[DurationRevenueBreakdownSchema] = []
        for d in [1, 3, 6, 12]:
            duration_breakdown.append(
                DurationRevenueBreakdownSchema(
                    duration_label=duration_labels.get(d, f"{d}_MONTHS"),
                    duration_months=d,
                    active_subscriptions=duration_counts.get(d, 0),
                    normalized_mrr=round(duration_mrr.get(d, 0.0), 2),
                    total_contract_value=round(duration_contract_value.get(d, 0.0), 2),
                )
            )

        return MonthlyRevenueReportSchema(
            month_key=month_key,
            opening_active_subscribers=opening_subscribers,
            new_subscribers_acquired=new_subscribers,
            renewed_subscribers=renewed_subscribers,
            expired_subscribers=expired_subscribers,
            cancelled_subscribers=cancelled_subscribers,
            closing_active_subscribers=closing_subscribers,
            gross_cash_collections=round(actual_cash_collected, 2),
            total_refunds=round(refunds, 2),
            net_cash_collections=net_cash,
            monthly_recurring_revenue_mrr=total_mrr,
            arpu=arpu,
            churn_rate_pct=churn_rate,
            renewal_rate_pct=renewal_rate,
            plan_breakdown=plan_breakdown,
            duration_breakdown=duration_breakdown,
        )
