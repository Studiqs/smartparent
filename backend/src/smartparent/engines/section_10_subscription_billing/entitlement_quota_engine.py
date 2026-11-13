"""
STUDIQS® SmartParent™ - Section 10: Entitlement Quota & Upgrade Proration Engine
=============================================================================
Module: src.smartparent.engines.section_10_subscription_billing.entitlement_quota_engine

Enforces tier quotas across:
  - Document uploads: Basic (4), Advanced (12), Pro (30)
  - Gap rechecks: Basic (1), Advanced (3), Pro (6)
  - Diagnostics: Basic (1), Advanced (3), Pro (6)
  - Active expert cases: Basic (1), Advanced (3), Pro (6)
  - AI Voice Pro RAG: Basic (Disabled), Advanced (Disabled), Pro (Enabled - 100 queries)
  - Max children: Basic (1), Advanced (2), Pro (4)
Includes:
  - Pre-flight entitlement checks with soft warnings at 80% usage.
  - Mid-term plan upgrade & duration change daily proration computation.
=============================================================================
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict
from src.smartparent.engines.section_00_core.base_engine import BaseEngine
from src.smartparent.engines.section_10_subscription_billing.subscription_pricing_engine import (
    PROPOSED_PRICING_MATRIX,
    SubscriptionPricingEngine,
)


# =============================================================================
# 1. Enums & Quota Definitions
# =============================================================================

class QuotaActionType(str, Enum):
    DOCUMENT_UPLOAD = "DOCUMENT_UPLOAD"
    GAP_RECHECK = "GAP_RECHECK"
    DIAGNOSTIC = "DIAGNOSTIC"
    EXPERT_CASE = "EXPERT_CASE"
    VOICE_QUERY = "VOICE_QUERY"
    DIAGNOSTIC_TOKENS = "DIAGNOSTIC_TOKENS"
    ADD_CHILD = "ADD_CHILD"


TIER_LIMITS: Dict[str, Dict[str, Any]] = {
    "BASIC": {
        QuotaActionType.DOCUMENT_UPLOAD.value: 4,
        QuotaActionType.GAP_RECHECK.value: 1,
        QuotaActionType.DIAGNOSTIC.value: 1,
        QuotaActionType.EXPERT_CASE.value: 1,
        QuotaActionType.VOICE_QUERY.value: 0,  # Locked
        QuotaActionType.DIAGNOSTIC_TOKENS.value: 5000,
        QuotaActionType.ADD_CHILD.value: 1,
        "voice_rag_enabled": False,
        "ptm_pack_enabled": True,
        "board_readiness_deep_enabled": False,
    },
    "ADVANCED": {
        QuotaActionType.DOCUMENT_UPLOAD.value: 12,
        QuotaActionType.GAP_RECHECK.value: 3,
        QuotaActionType.DIAGNOSTIC.value: 3,
        QuotaActionType.EXPERT_CASE.value: 3,
        QuotaActionType.VOICE_QUERY.value: 25,  # Unlocked (25 queries)
        QuotaActionType.DIAGNOSTIC_TOKENS.value: 25000,
        QuotaActionType.ADD_CHILD.value: 2,
        "voice_rag_enabled": True,
        "ptm_pack_enabled": True,
        "board_readiness_deep_enabled": True,
    },
    "PRO": {
        QuotaActionType.DOCUMENT_UPLOAD.value: 30,
        QuotaActionType.GAP_RECHECK.value: 6,
        QuotaActionType.DIAGNOSTIC.value: 6,
        QuotaActionType.EXPERT_CASE.value: 6,
        QuotaActionType.VOICE_QUERY.value: 100,  # Enabled (100 queries)
        QuotaActionType.DIAGNOSTIC_TOKENS.value: 100000,
        QuotaActionType.ADD_CHILD.value: 4,
        "voice_rag_enabled": True,
        "ptm_pack_enabled": True,
        "board_readiness_deep_enabled": True,
    },
}


# =============================================================================
# 2. Schemas
# =============================================================================

class EntitlementDecisionSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")
    action_type: str
    plan_id: str
    is_allowed: bool
    current_usage: int
    quota_limit: int
    remaining_quota: int
    usage_percentage: float
    is_soft_warning: bool = False
    message: str
    upgrade_prompt: Optional[str] = None
    suggested_target_plan: Optional[str] = None


class QuotaUsageOverviewSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")
    plan_id: str
    month_key: str  # 'YYYY-MM'
    document_uploads: Dict[str, Any]
    gap_rechecks: Dict[str, Any]
    diagnostics: Dict[str, Any]
    active_expert_cases: Dict[str, Any]
    voice_queries: Dict[str, Any]
    children_count: Dict[str, Any]


class UpgradeProrationQuoteSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")
    current_plan_id: str
    target_plan_id: str
    target_duration_months: int
    total_days_in_term: int
    days_used: int
    days_remaining: int
    current_plan_price_paid: float
    daily_rate: float
    unused_credit_amount: float
    target_plan_price: float
    net_payable_today: float
    effective_savings: float
    currency: str = "INR"
    message: str


# =============================================================================
# 3. Production Entitlement Quota Engine
# =============================================================================

class EntitlementQuotaEngine(BaseEngine):
    """
    Section 10 Entitlement Quota & Upgrade Proration Engine.
    Enforces subscription boundaries and calculates fair daily-prorated upgrade costs.
    """

    SOFT_WARNING_THRESHOLD: float = 0.80  # 80% usage triggers early warning

    def __init__(self, failure_threshold: int = 5):
        super().__init__(name="EntitlementQuotaEngine", failure_threshold=failure_threshold)
        self.pricing_engine = SubscriptionPricingEngine()

    # -------------------------------------------------------------------------
    # BaseEngine Lifecycle Hooks
    # -------------------------------------------------------------------------

    def validate_input(self, input_data: Any) -> Dict[str, Any]:
        """Validates incoming entitlement or proration request."""
        if not isinstance(input_data, dict):
            raise ValueError("Input must be a dictionary")

        req_type = input_data.get("request_type", "CHECK_ACTION")
        return {"request_type": req_type, "payload": input_data}

    def execute_core(self, validated_data: Dict[str, Any]) -> Any:
        """Executes entitlement check or proration quote."""
        payload = validated_data["payload"]
        if validated_data["request_type"] == "CHECK_ACTION":
            return self.check_entitlement(
                action_type=payload["action_type"],
                plan_id=payload.get("plan_id", "BASIC"),
                current_usage=int(payload.get("current_usage", 0)),
                is_active=bool(payload.get("is_active", True)),
            )
        elif validated_data["request_type"] == "PRORATION_QUOTE":
            return self.calculate_upgrade_proration(
                current_plan_id=payload["current_plan_id"],
                current_price_paid=float(payload["current_price_paid"]),
                start_date=payload["start_date"],
                expiry_date=payload["expiry_date"],
                target_plan_id=payload["target_plan_id"],
                target_duration_months=int(payload.get("target_duration_months", 1)),
                pricing_model=payload.get("pricing_model", "PROPOSED"),
            )
        else:
            raise ValueError(f"Unknown request_type: {validated_data['request_type']}")

    def fallback(self, error: Exception, input_data: Any) -> Any:
        """Safe fallback disallowing action to protect resource bounds."""
        self.logger.warning("EntitlementQuotaEngine fallback invoked: %s", error)
        return EntitlementDecisionSchema(
            action_type="UNKNOWN",
            plan_id="BASIC",
            is_allowed=False,
            current_usage=0,
            quota_limit=0,
            remaining_quota=0,
            usage_percentage=100.0,
            message="Unable to verify entitlement quota at this time. Please retry.",
        )

    # -------------------------------------------------------------------------
    # Core Domain Logic
    # -------------------------------------------------------------------------

    def get_tier_limits(self, plan_id: str) -> Dict[str, Any]:
        """Returns quota limits for specified plan."""
        return TIER_LIMITS.get(plan_id.upper(), TIER_LIMITS["BASIC"])

    def check_entitlement(
        self,
        action_type: str,
        plan_id: str,
        current_usage: int,
        is_active: bool = True,
    ) -> EntitlementDecisionSchema:
        """
        Pre-flight check before performing a metered action.
        """
        norm_plan = plan_id.upper()
        norm_action = action_type.upper()
        limits = self.get_tier_limits(norm_plan)

        if not is_active:
            return EntitlementDecisionSchema(
                action_type=norm_action,
                plan_id=norm_plan,
                is_allowed=False,
                current_usage=current_usage,
                quota_limit=0,
                remaining_quota=0,
                usage_percentage=100.0,
                is_soft_warning=False,
                message="Subscription is expired or inactive. Please renew to continue.",
                upgrade_prompt="Renew your subscription to unlock all features.",
                suggested_target_plan=norm_plan,
            )

        # Check for feature gating (e.g. AI Voice RAG)
        if norm_action == QuotaActionType.VOICE_QUERY.value:
            if not limits.get("voice_rag_enabled", False):
                return EntitlementDecisionSchema(
                    action_type=norm_action,
                    plan_id=norm_plan,
                    is_allowed=False,
                    current_usage=current_usage,
                    quota_limit=0,
                    remaining_quota=0,
                    usage_percentage=100.0,
                    is_soft_warning=False,
                    message="SmartParent RAG Voice Assistant is exclusive to Pro subscribers.",
                    upgrade_prompt="Upgrade to Pro (₹599/mo) to unlock real-time conversational Voice AI.",
                    suggested_target_plan="PRO",
                )

        quota_limit = limits.get(norm_action, 0)
        remaining = max(0, quota_limit - current_usage)
        usage_pct = round((current_usage / quota_limit) * 100.0, 1) if quota_limit > 0 else 100.0

        if current_usage >= quota_limit:
            target = "ADVANCED" if norm_plan == "BASIC" else "PRO"
            return EntitlementDecisionSchema(
                action_type=norm_action,
                plan_id=norm_plan,
                is_allowed=False,
                current_usage=current_usage,
                quota_limit=quota_limit,
                remaining_quota=0,
                usage_percentage=usage_pct,
                is_soft_warning=False,
                message=f"Monthly limit of {quota_limit} {norm_action.lower()}s reached on {norm_plan} plan.",
                upgrade_prompt=f"Upgrade to {target} plan for higher quotas and deeper analysis.",
                suggested_target_plan=target,
            )

        # Allow with optional soft warning
        is_soft = (usage_pct >= (self.SOFT_WARNING_THRESHOLD * 100.0))
        soft_msg = f"You have used {current_usage} of {quota_limit} {norm_action.lower()}s ({remaining} remaining)." if is_soft else "Action allowed."

        return EntitlementDecisionSchema(
            action_type=norm_action,
            plan_id=norm_plan,
            is_allowed=True,
            current_usage=current_usage,
            quota_limit=quota_limit,
            remaining_quota=remaining,
            usage_percentage=usage_pct,
            is_soft_warning=is_soft,
            message=soft_msg,
            suggested_target_plan="ADVANCED" if norm_plan == "BASIC" and is_soft else None,
        )

    def get_quota_overview(
        self,
        plan_id: str,
        month_key: str,
        usage_data: Dict[str, int],
    ) -> QuotaUsageOverviewSchema:
        """
        Builds complete dashboard overview of all 5 quota boundaries.
        """
        norm_plan = plan_id.upper()
        limits = self.get_tier_limits(norm_plan)

        def _build_metric(action_key: str) -> Dict[str, Any]:
            used = usage_data.get(action_key, 0)
            limit = limits.get(action_key, 0)
            remaining = max(0, limit - used)
            pct = round((used / limit) * 100.0, 1) if limit > 0 else 0.0
            return {
                "used": used,
                "limit": limit,
                "remaining": remaining,
                "percentage": pct,
                "is_locked": limit == 0,
            }

        return QuotaUsageOverviewSchema(
            plan_id=norm_plan,
            month_key=month_key,
            document_uploads=_build_metric(QuotaActionType.DOCUMENT_UPLOAD.value),
            gap_rechecks=_build_metric(QuotaActionType.GAP_RECHECK.value),
            diagnostics=_build_metric(QuotaActionType.DIAGNOSTIC.value),
            active_expert_cases=_build_metric(QuotaActionType.EXPERT_CASE.value),
            voice_queries=_build_metric(QuotaActionType.VOICE_QUERY.value),
            children_count=_build_metric(QuotaActionType.ADD_CHILD.value),
        )

    def calculate_upgrade_proration(
        self,
        current_plan_id: str,
        current_price_paid: float,
        start_date: datetime,
        expiry_date: datetime,
        target_plan_id: str,
        target_duration_months: int = 1,
        pricing_model: str = "PROPOSED",
        current_time: Optional[datetime] = None,
    ) -> UpgradeProrationQuoteSchema:
        """
        Calculates fair daily-prorated upgrade credit according to Section 24.4:
          unused_credit = (remaining_days / total_days) * current_price_paid
          net_payable = max(0, target_plan_price - unused_credit)
        """
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)
        if expiry_date.tzinfo is None:
            expiry_date = expiry_date.replace(tzinfo=timezone.utc)

        now = current_time or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        total_days = max(1, (expiry_date - start_date).days)
        days_used = max(0, min(total_days, (now - start_date).days))
        days_remaining = max(0, total_days - days_used)

        daily_rate = round(current_price_paid / total_days, 4)
        unused_credit = round(daily_rate * days_remaining, 2)

        target_quote = self.pricing_engine.calculate_checkout_quote(
            plan_id=target_plan_id,
            duration_months=target_duration_months,
            pricing_model=pricing_model,
        )
        target_price = target_quote.gross_payable_amount

        net_payable = max(0.0, round(target_price - unused_credit, 2))
        effective_savings = round(unused_credit, 2)

        msg = (
            f"Upgrade to {target_plan_id} ({target_duration_months} Month(s)). "
            f"Credited ₹{unused_credit} for {days_remaining} remaining days on {current_plan_id}. "
            f"Total payable today: ₹{net_payable}."
        )

        return UpgradeProrationQuoteSchema(
            current_plan_id=current_plan_id.upper(),
            target_plan_id=target_plan_id.upper(),
            target_duration_months=target_duration_months,
            total_days_in_term=total_days,
            days_used=days_used,
            days_remaining=days_remaining,
            current_plan_price_paid=current_price_paid,
            daily_rate=daily_rate,
            unused_credit_amount=unused_credit,
            target_plan_price=target_price,
            net_payable_today=net_payable,
            effective_savings=effective_savings,
            currency="INR",
            message=msg,
        )
