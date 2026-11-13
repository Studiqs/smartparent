"""
STUDIQS® SmartParent™ - Section 10 & 24: Calendar-Month Validity & Lifecycle Engine
=============================================================================
Module: src.smartparent.engines.section_10_subscription_billing.calendar_validity_engine

Implements Netflix-style subscription calendar validity:
  - Exact calendar-month addition (Jan 31 -> Feb 28/29, Jan 15 -> Apr 15).
  - Leap-year awareness (2028, 2032).
  - Real-time status evaluation (ACTIVE, EXPIRING_SOON, EXPIRED, CANCELLED_ACTIVE, etc.).
  - Automated reminder schedule builder (7 days, 3 days, 1 day, on-expiry).
=============================================================================
"""

import calendar
from datetime import datetime, date, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field, ConfigDict
from src.smartparent.engines.section_00_core.base_engine import BaseEngine


# =============================================================================
# 1. Enums & Schemas
# =============================================================================

class SubscriptionLifecycleStatus(str, Enum):
    PENDING_PAYMENT = "PENDING_PAYMENT"
    ACTIVE = "ACTIVE"
    EXPIRING_SOON = "EXPIRING_SOON"  # Within 7 days of expiry
    EXPIRED = "EXPIRED"
    CANCELLED_ACTIVE = "CANCELLED_ACTIVE"  # Cancelled auto-renew, but period paid
    CANCELLED = "CANCELLED"
    PAST_DUE = "PAST_DUE"
    TRIAL = "TRIAL"


class ReminderTypeEnum(str, Enum):
    REMINDER_7_DAYS = "REMINDER_7_DAYS"
    REMINDER_3_DAYS = "REMINDER_3_DAYS"
    REMINDER_1_DAY = "REMINDER_1_DAY"
    EXPIRED_NOTICE = "EXPIRED_NOTICE"


class RenewalReminderScheduleItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    reminder_type: str
    scheduled_at: datetime
    description: str
    urgency_tier: str  # 'INFO', 'WARNING', 'URGENT', 'CRITICAL'


class SubscriptionStatusEvaluationSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")
    status: str
    is_access_allowed: bool
    expiry_date: datetime
    days_remaining: int
    hours_remaining: int
    is_expiring_soon: bool
    renewal_alert_message: Optional[str] = None
    action_required: Optional[str] = None


# =============================================================================
# 2. Production Calendar Validity Engine
# =============================================================================

class CalendarValidityEngine(BaseEngine):
    """
    Section 10 & 24 Calendar-Month Validity & Renewal Engine.
    Handles non-drifting calendar month arithmetic, multi-tier expiry alerts,
    and access state resolution.
    """

    EXPIRING_SOON_THRESHOLD_DAYS: int = 7

    def __init__(self, failure_threshold: int = 5):
        super().__init__(name="CalendarValidityEngine", failure_threshold=failure_threshold)

    # -------------------------------------------------------------------------
    # BaseEngine Lifecycle Hooks
    # -------------------------------------------------------------------------

    def validate_input(self, input_data: Any) -> Dict[str, Any]:
        """Validates input payload for date arithmetic or status checks."""
        if not isinstance(input_data, dict):
            raise ValueError("Input to CalendarValidityEngine must be a dictionary")

        if "start_date" in input_data and "duration_months" in input_data:
            start_date = input_data["start_date"]
            if isinstance(start_date, str):
                start_date = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
            return {
                "operation": "CALCULATE_EXPIRY",
                "start_date": start_date,
                "duration_months": int(input_data["duration_months"]),
            }
        elif "expiry_date" in input_data:
            expiry_date = input_data["expiry_date"]
            if isinstance(expiry_date, str):
                expiry_date = datetime.fromisoformat(expiry_date.replace("Z", "+00:00"))
            return {
                "operation": "EVALUATE_STATUS",
                "expiry_date": expiry_date,
                "is_paid": bool(input_data.get("is_paid", True)),
                "is_trial": bool(input_data.get("is_trial", False)),
                "is_cancelled": bool(input_data.get("is_cancelled", False)),
                "current_time": input_data.get("current_time"),
            }
        else:
            raise ValueError("CalendarValidityEngine requires either start_date + duration_months or expiry_date")

    def execute_core(self, validated_data: Dict[str, Any]) -> Any:
        """Executes selected operation."""
        op = validated_data.get("operation")
        if op == "CALCULATE_EXPIRY":
            return self.calculate_calendar_expiry(
                start_date=validated_data["start_date"],
                duration_months=validated_data["duration_months"],
            )
        else:
            return self.evaluate_status(
                expiry_date=validated_data["expiry_date"],
                is_paid=validated_data["is_paid"],
                is_trial=validated_data["is_trial"],
                is_cancelled=validated_data["is_cancelled"],
                current_time=validated_data.get("current_time"),
            )

    def fallback(self, error: Exception, input_data: Any) -> Any:
        """Safe fallback defaulting to 30 days ahead."""
        self.logger.warning("CalendarValidityEngine fallback triggered: %s", error)
        now = datetime.now(timezone.utc)
        return now + timedelta(days=30)

    # -------------------------------------------------------------------------
    # Core Calendar Math & Business Logic
    # -------------------------------------------------------------------------

    @staticmethod
    def add_calendar_months(source_dt: datetime, months_to_add: int) -> datetime:
        """
        Adds exact calendar months to a datetime, handling varying month lengths
        and leap years without day drift.
        
        Rules:
          - Jan 15 + 3 months -> Apr 15
          - Jan 31 + 1 month (2026) -> Feb 28
          - Jan 31 + 1 month (2028 leap) -> Feb 29
          - Aug 31 + 1 month -> Sep 30
        """
        year = source_dt.year
        month = source_dt.month + months_to_add
        day = source_dt.day

        # Normalize year and month for values > 12
        while month > 12:
            year += 1
            month -= 12
        while month < 1:
            year -= 1
            month += 12

        # Clamp day to max days in target month
        max_days = calendar.monthrange(year, month)[1]
        clamped_day = min(day, max_days)

        return source_dt.replace(year=year, month=month, day=clamped_day)

    def calculate_calendar_expiry(self, start_date: datetime, duration_months: int) -> datetime:
        """
        Calculates exact expiry timestamp for a subscription starting at start_date.
        Ensures timezone preservation.
        """
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)

        return self.add_calendar_months(start_date, duration_months)

    def evaluate_status(
        self,
        expiry_date: datetime,
        is_paid: bool = True,
        is_trial: bool = False,
        is_cancelled: bool = False,
        current_time: Optional[datetime] = None,
    ) -> SubscriptionStatusEvaluationSchema:
        """
        Evaluates current real-time status of a subscription based on expiry date
        and payment conditions.
        """
        if expiry_date.tzinfo is None:
            expiry_date = expiry_date.replace(tzinfo=timezone.utc)

        now = current_time or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        if not is_paid and not is_trial:
            return SubscriptionStatusEvaluationSchema(
                status=SubscriptionLifecycleStatus.PENDING_PAYMENT.value,
                is_access_allowed=False,
                expiry_date=expiry_date,
                days_remaining=0,
                hours_remaining=0,
                is_expiring_soon=False,
                renewal_alert_message="Payment is pending. Please complete checkout to activate.",
                action_required="COMPLETE_PAYMENT",
            )

        time_delta = expiry_date - now
        total_seconds = int(time_delta.total_seconds())

        if total_seconds <= 0:
            return SubscriptionStatusEvaluationSchema(
                status=SubscriptionLifecycleStatus.EXPIRED.value,
                is_access_allowed=False,
                expiry_date=expiry_date,
                days_remaining=0,
                hours_remaining=0,
                is_expiring_soon=False,
                renewal_alert_message="Your subscription has expired. Renew now to restore intelligence reports.",
                action_required="RENEW_SUBSCRIPTION",
            )

        days_remaining = total_seconds // 86400
        hours_remaining = (total_seconds % 86400) // 3600

        # Check if within expiring soon window (7 days)
        is_expiring_soon = days_remaining <= self.EXPIRING_SOON_THRESHOLD_DAYS

        if is_trial:
            status = SubscriptionLifecycleStatus.TRIAL.value
            alert = f"Trial active. {days_remaining} days remaining."
            action = "UPGRADE_TO_PAID" if is_expiring_soon else None
        elif is_cancelled:
            # Cancelled auto-renewal, but period is already paid
            status = SubscriptionLifecycleStatus.CANCELLED_ACTIVE.value
            alert = f"Auto-renewal cancelled. Access continues until {expiry_date.strftime('%d %b %Y')}."
            action = "REACTIVATE_AUTO_RENEW"
        elif is_expiring_soon:
            status = SubscriptionLifecycleStatus.EXPIRING_SOON.value
            alert = f"Subscription expiring in {days_remaining} days ({hours_remaining} hours). Renew today to avoid interruption."
            action = "RENEW_SUBSCRIPTION"
        else:
            status = SubscriptionLifecycleStatus.ACTIVE.value
            alert = None
            action = None

        return SubscriptionStatusEvaluationSchema(
            status=status,
            is_access_allowed=True,
            expiry_date=expiry_date,
            days_remaining=days_remaining,
            hours_remaining=hours_remaining,
            is_expiring_soon=is_expiring_soon,
            renewal_alert_message=alert,
            action_required=action,
        )

    def generate_renewal_reminder_schedule(
        self,
        start_date: datetime,
        expiry_date: datetime,
    ) -> List[RenewalReminderScheduleItem]:
        """
        Builds the 4 mandatory renewal alert schedule items conforming to Section 24.6:
          - 7 days before expiry: First renewal reminder
          - 3 days before expiry: Second reminder
          - 1 day before expiry: Final reminder
          - On expiry: Subscription expired notice
        """
        if expiry_date.tzinfo is None:
            expiry_date = expiry_date.replace(tzinfo=timezone.utc)
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)

        total_duration = expiry_date - start_date
        reminders: List[RenewalReminderScheduleItem] = []

        # 7 Days reminder (Only if subscription duration is >= 14 days)
        if total_duration >= timedelta(days=14):
            rem_7 = expiry_date - timedelta(days=7)
            reminders.append(
                RenewalReminderScheduleItem(
                    reminder_type=ReminderTypeEnum.REMINDER_7_DAYS.value,
                    scheduled_at=rem_7,
                    description="1st Renewal Reminder: 7 days until subscription renewal.",
                    urgency_tier="INFO",
                )
            )

        # 3 Days reminder (Only if subscription duration >= 7 days)
        if total_duration >= timedelta(days=7):
            rem_3 = expiry_date - timedelta(days=3)
            reminders.append(
                RenewalReminderScheduleItem(
                    reminder_type=ReminderTypeEnum.REMINDER_3_DAYS.value,
                    scheduled_at=rem_3,
                    description="2nd Renewal Reminder: 3 days until subscription renewal.",
                    urgency_tier="WARNING",
                )
            )

        # 1 Day reminder
        rem_1 = expiry_date - timedelta(days=1)
        if rem_1 > start_date:
            reminders.append(
                RenewalReminderScheduleItem(
                    reminder_type=ReminderTypeEnum.REMINDER_1_DAY.value,
                    scheduled_at=rem_1,
                    description="Final Renewal Reminder: 24 hours left on your subscription.",
                    urgency_tier="URGENT",
                )
            )

        # On expiry
        reminders.append(
            RenewalReminderScheduleItem(
                reminder_type=ReminderTypeEnum.EXPIRED_NOTICE.value,
                scheduled_at=expiry_date,
                description="Subscription Expired: Intelligence reports paused. Click to renew.",
                urgency_tier="CRITICAL",
            )
        )

        return reminders
