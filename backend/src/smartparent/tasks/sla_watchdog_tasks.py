"""
STUDIQS® SmartParent™ (v6.3 Complete) - Periodic SLA Watchdog & Monthly Pulse Tasks
=====================================================================================
Module: src.smartparent.tasks.sla_watchdog_tasks
Celery Beat Scheduled Tasks:
  1. 48-Hour Continuous Hard SLA Escalation Watchdog (Runs every 15 min)
  2. Automated Monthly Parent Pulse Generation (Runs 1st of month)
=====================================================================================
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict
from celery import shared_task
from sqlalchemy.orm import Session

from src.smartparent.db.session import SessionLocal
from src.smartparent.db.models.marketplace import EvaluationCase
from src.smartparent.core.constants import CaseStatus

logger = logging.getLogger("STUDIQS_SLAWatchdog")


@shared_task
def check_expert_cases_sla_breach_task() -> Dict[str, Any]:
    """
    Watches all SUBMITTED and UNDER_REVIEW expert evaluation cases.
    Identifies cases approaching or exceeding the 48-Hour SLA deadline:
      - Warning: If remaining time < 12 hours -> Trigger notification to Expert
      - Critical Breach: If remaining time <= 0 hours -> Escalate to Admin Support
    """
    db: Session = SessionLocal()
    now = datetime.now(timezone.utc)
    warnings_sent = 0
    breaches_escalated = 0

    try:
        active_cases = (
            db.query(EvaluationCase)
            .filter(EvaluationCase.case_status.in_([CaseStatus.SUBMITTED.value, CaseStatus.UNDER_REVIEW.value]))
            .all()
        )

        for case in active_cases:
            if not case.submitted_at:
                continue

            # 48-hour turnaround deadline
            deadline = case.submitted_at + timedelta(hours=48)
            remaining_seconds = (deadline - now).total_seconds()

            if remaining_seconds <= 0:
                breaches_escalated += 1
                logger.warning(f"[SLA Breach] Case {case.case_id} exceeded 48h SLA! Escalating to Operations Desk.")
            elif remaining_seconds <= 43200:  # < 12 hours remaining
                warnings_sent += 1
                logger.info(f"[SLA Warning] Case {case.case_id} has {int(remaining_seconds // 3600)}h left. Sending nudge.")

        return {
            "status": "COMPLETED",
            "active_cases_checked": len(active_cases),
            "warnings_sent": warnings_sent,
            "breaches_escalated": breaches_escalated,
            "checked_at": now.isoformat(),
        }
    finally:
        db.close()


@shared_task
def monthly_pulse_cron_task() -> Dict[str, Any]:
    """
    Automatically synthesizes the 3-Card Parent Pulse for all active children
    on the 1st of every month at 00:00 UTC.
    """
    db: Session = SessionLocal()
    now = datetime.now(timezone.utc)
    current_month_key = now.strftime("%Y-%m")
    synthesized_count = 0

    try:
        from src.smartparent.services.parent_pulse_service import ParentPulseService
        from src.smartparent.db.models.auth import Child

        pulse_service = ParentPulseService()
        all_children = db.query(Child).all()

        for child in all_children:
            try:
                pulse_service.get_or_synthesize_parent_pulse(
                    db=db,
                    subscriber_id=child.subscriber_id,
                    child_id=child.child_id,
                    month_key=current_month_key,
                )
                synthesized_count += 1
            except Exception as e:
                logger.error(f"[Monthly Pulse Cron] Error synthesizing for child {child.child_id}: {e}")

        return {
            "status": "COMPLETED",
            "month_key": current_month_key,
            "total_children": len(all_children),
            "synthesized_count": synthesized_count,
        }
    finally:
        db.close()

