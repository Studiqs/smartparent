"""
STUDIQS® SmartParent™ (v6.3 Complete) - Renewal & Expiry Alert Service
=============================================================================
Module: src.smartparent.services.renewal_alert_service
Section 24.6: Automatic Renewal and Expiry Alerts

Implements:
  1. 4-Stage Renewal Reminder Sweeper (T-7d, T-3d, T-1d, On-Expiry).
  2. Auto-renew differentiation (informs upcoming debit vs requesting payment).
  3. Absolute deduplication (prevents duplicate alerts per stage window).
  4. Real-time parent banner telemetry with action CTA.
  5. Multi-channel delivery: In-App Notification + Email/SMS readiness.
=============================================================================
"""

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, or_, desc

from src.smartparent.core.constants import SubscriptionPlan
from src.smartparent.db.models.auth import Subscriber
from src.smartparent.db.models.subscription import (
    Subscription,
    SubscriptionRenewalReminder,
)
from src.smartparent.db.models.notification import InAppNotification
from src.smartparent.schemas.renewal_alerts import (
    AlertStageEnum,
    RenewalAlertItemSchema,
    ParentRenewalAlertBannerResponse,
    AlertSweepSummaryResponse,
)

logger = logging.getLogger("STUDIQS_RenewalAlertService")

# Reminder windows in days
SCHEDULE_STAGES = [
    (7, AlertStageEnum.REMINDER_7_DAYS.value, "7-Day Renewal Reminder"),
    (3, AlertStageEnum.REMINDER_3_DAYS.value, "3-Day Renewal Reminder"),
    (1, AlertStageEnum.REMINDER_1_DAY.value, "Final Renewal Reminder"),
    (0, AlertStageEnum.EXPIRED_NOTICE.value, "Subscription Expired Notification"),
]


class RenewalAlertService:
    """
    Automated Renewal & Expiry Reminder Engine (Section 24.6).
    """

    def generate_alert_content(
        self,
        plan_id: str,
        expiry_date: datetime,
        days_remaining: int,
        auto_renew: bool,
    ) -> Dict[str, str]:
        """
        Produces clear, non-confusing messaging based on auto-renew flag.
        """
        exp_str = expiry_date.strftime("%d %B %Y")

        if auto_renew:
            if days_remaining > 0:
                title = f"SmartParent {plan_id} Renewal Notice"
                message = (
                    f"Notice: Your SmartParent {plan_id} subscription will automatically renew on "
                    f"{exp_str} via your saved payment method on Razorpay. No manual action is required."
                )
                cta = "Manage Subscription"
            else:
                title = f"SmartParent {plan_id} Auto-Renewal Processing"
                message = (
                    f"Your subscription is scheduled for automatic renewal today ({exp_str}). "
                    f"Your child's learning insights will continue without interruption."
                )
                cta = "View Billing"
        else:
            if days_remaining == 7:
                title = f"SmartParent {plan_id}: 7 Days Until Expiry"
                message = (
                    f"Friendly Reminder: Your SmartParent {plan_id} subscription expires on {exp_str}. "
                    f"Renew now to maintain uninterrupted access to Topic Intelligence and diagnostic reports."
                )
                cta = "Renew Now"
            elif days_remaining == 3:
                title = f"Important: 3 Days Left on SmartParent {plan_id}"
                message = (
                    f"Your subscription expires in 3 days on {exp_str}. "
                    f"Renew today to ensure your child's learning gap tracker remains active."
                )
                cta = "Renew Today"
            elif days_remaining == 1:
                title = f"Urgent: Final Day of SmartParent {plan_id}"
                message = (
                    f"Your subscription expires tomorrow ({exp_str}). "
                    f"Renew immediately to prevent pausing of automated monthly diagnostic compilations."
                )
                cta = "Renew Immediately"
            else:
                title = f"Subscription Expired: SmartParent {plan_id}"
                message = (
                    f"Your SmartParent {plan_id} subscription expired on {exp_str}. "
                    f"Active telemetry and voice features are currently paused. Reactivate anytime to resume."
                )
                cta = "Reactivate Subscription"

        return {
            "title": title,
            "message": message,
            "cta": cta,
            "checkout_url": f"/subscription/checkout?plan={plan_id.upper()}",
        }

    def get_parent_renewal_banner(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
    ) -> ParentRenewalAlertBannerResponse:
        """
        Computes dynamic header banner for parent dashboard and mobile app.
        """
        # Fetch latest active or expired subscription
        stmt = (
            select(Subscription)
            .where(Subscription.subscriber_id == subscriber_id)
            .order_by(desc(Subscription.created_at))
        )
        subscription = db.execute(stmt).scalars().first()

        if not subscription:
            return ParentRenewalAlertBannerResponse(
                subscriber_id=subscriber_id,
                has_active_alert=False,
                alert_severity="INFO",
                plan_id=SubscriptionPlan.BASIC.value,
                auto_renew=False,
                banner_headline="Welcome to SmartParent",
                banner_message="Select a subscription plan to unlock full Topic Intelligence.",
                quick_action_cta="View Plans",
                checkout_url="/subscription/catalog",
            )

        today = datetime.now(timezone.utc).date()
        days_rem = (subscription.expiry_date.date() - today).days
        content = self.generate_alert_content(
            plan_id=subscription.plan_id,
            expiry_date=subscription.expiry_date,
            days_remaining=days_rem,
            auto_renew=subscription.auto_renew,
        )

        has_alert = days_rem <= 7 or subscription.status in ("EXPIRING_SOON", "EXPIRED")
        if days_rem <= 0:
            severity = "EXPIRED"
        elif days_rem <= 1:
            severity = "CRITICAL"
        elif days_rem <= 3:
            severity = "WARNING"
        else:
            severity = "INFO"

        return ParentRenewalAlertBannerResponse(
            subscriber_id=subscriber_id,
            has_active_alert=has_alert,
            alert_severity=severity,
            days_remaining=days_rem,
            expiry_date=subscription.expiry_date,
            plan_id=subscription.plan_id,
            auto_renew=subscription.auto_renew,
            banner_headline=content["title"],
            banner_message=content["message"],
            quick_action_cta=content["cta"],
            checkout_url=content["checkout_url"],
        )

    def run_alert_sweep(
        self,
        db: Session,
        target_date: Optional[date] = None,
        dry_run: bool = False,
    ) -> AlertSweepSummaryResponse:
        """
        Scans all active subscriptions, matches expiry windows (7d, 3d, 1d, 0d),
        and dispatches deduplicated alerts with audit records.
        """
        sweep_date = target_date or datetime.now(timezone.utc).date()
        now_utc = datetime.now(timezone.utc)

        # Query all active or expiring subscriptions
        stmt = select(Subscription).where(
            Subscription.status.in_(["ACTIVE", "EXPIRING_SOON", "EXPIRED"])
        )
        subscriptions = db.execute(stmt).scalars().all()

        scanned_count = len(subscriptions)
        dispatched_count = 0
        skipped_count = 0
        stage_breakdown: Dict[str, int] = {
            AlertStageEnum.REMINDER_7_DAYS.value: 0,
            AlertStageEnum.REMINDER_3_DAYS.value: 0,
            AlertStageEnum.REMINDER_1_DAY.value: 0,
            AlertStageEnum.EXPIRED_NOTICE.value: 0,
        }
        dispatched_details: List[Dict[str, Any]] = []

        for sub in subscriptions:
            exp_date = sub.expiry_date.date()
            days_diff = (exp_date - sweep_date).days

            # Determine matching stage
            matched_stage: Optional[str] = None
            if days_diff == 7:
                matched_stage = AlertStageEnum.REMINDER_7_DAYS.value
            elif days_diff == 3:
                matched_stage = AlertStageEnum.REMINDER_3_DAYS.value
            elif days_diff == 1:
                matched_stage = AlertStageEnum.REMINDER_1_DAY.value
            elif days_diff <= 0:
                matched_stage = AlertStageEnum.EXPIRED_NOTICE.value

            if not matched_stage:
                continue

            # Deduplication: Check if reminder of this stage was already sent for this subscription
            check_stmt = select(SubscriptionRenewalReminder).where(
                and_(
                    SubscriptionRenewalReminder.subscription_id == sub.subscription_id,
                    SubscriptionRenewalReminder.reminder_type == matched_stage,
                )
            )
            existing = db.execute(check_stmt).scalar_one_or_none()
            if existing:
                skipped_count += 1
                continue

            content = self.generate_alert_content(
                plan_id=sub.plan_id,
                expiry_date=sub.expiry_date,
                days_remaining=days_diff,
                auto_renew=sub.auto_renew,
            )

            if not dry_run:
                # 1. Record SubscriptionRenewalReminder audit entity
                reminder = SubscriptionRenewalReminder(
                    reminder_id=uuid.uuid4(),
                    subscription_id=sub.subscription_id,
                    reminder_type=matched_stage,
                    scheduled_at=now_utc,
                    sent_at=now_utc,
                    is_sent=True,
                    notification_channel="IN_APP",
                )
                db.add(reminder)

                # 2. Emit InAppNotification for the parent
                notif = InAppNotification(
                    notification_id=uuid.uuid4(),
                    subscriber_id=sub.subscriber_id,
                    event_type=f"SUBSCRIPTION_{matched_stage}",
                    title=content["title"],
                    message=content["message"],
                    is_read=False,
                )
                db.add(notif)

                # If expired, update subscription status
                if matched_stage == AlertStageEnum.EXPIRED_NOTICE.value and sub.status != "EXPIRED":
                    sub.status = "EXPIRED"

                db.commit()

            dispatched_count += 1
            stage_breakdown[matched_stage] = stage_breakdown.get(matched_stage, 0) + 1
            dispatched_details.append({
                "subscription_id": str(sub.subscription_id),
                "subscriber_id": str(sub.subscriber_id),
                "plan_id": sub.plan_id,
                "stage": matched_stage,
                "days_diff": days_diff,
                "auto_renew": sub.auto_renew,
                "title": content["title"],
            })

        logger.info(
            f"[RenewalAlertService] Sweep completed: {scanned_count} scanned, "
            f"{dispatched_count} dispatched, {skipped_count} skipped (deduped)."
        )

        return AlertSweepSummaryResponse(
            sweep_timestamp=now_utc,
            total_subscriptions_scanned=scanned_count,
            alerts_dispatched_count=dispatched_count,
            alerts_skipped_already_sent_count=skipped_count,
            stage_breakdown=stage_breakdown,
            dispatched_alerts=dispatched_details,
        )

    def list_dispatched_reminders(
        self,
        db: Session,
        subscriber_id: Optional[uuid.UUID] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Lists audit history of dispatched renewal reminders."""
        stmt = (
            select(SubscriptionRenewalReminder, Subscription)
            .join(Subscription, SubscriptionRenewalReminder.subscription_id == Subscription.subscription_id)
        )
        if subscriber_id:
            stmt = stmt.where(Subscription.subscriber_id == subscriber_id)

        stmt = stmt.order_by(desc(SubscriptionRenewalReminder.created_at)).limit(limit)
        results = db.execute(stmt).all()

        out = []
        for rem, sub in results:
            out.append({
                "reminder_id": str(rem.reminder_id),
                "subscription_id": str(rem.subscription_id),
                "subscriber_id": str(sub.subscriber_id),
                "reminder_type": rem.reminder_type,
                "scheduled_at": rem.scheduled_at.isoformat(),
                "sent_at": rem.sent_at.isoformat() if rem.sent_at else None,
                "is_sent": rem.is_sent,
                "notification_channel": rem.notification_channel,
                "created_at": rem.created_at.isoformat(),
            })
        return out


renewal_alert_service = RenewalAlertService()
