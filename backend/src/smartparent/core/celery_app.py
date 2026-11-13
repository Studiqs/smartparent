"""
STUDIQS® SmartParent™ (v6.3 Complete) - Production Celery Application & Task Routing
====================================================================================
Module: src.smartparent.core.celery_app
Handles asynchronous background workers and periodic scheduled tasks (Celery Beat):
  1. Asynchronous Question Paper OCR & Spatial Parsing
  2. Asynchronous 12-Page Vector PDF Report Generation (ReportLab)
  3. 48-Hour Continuous Hard SLA Escalation Watchdog (Every 15 minutes)
  4. Monthly Parent Pulse Synthesis (Every 1st of month at 00:00 UTC)
====================================================================================
"""

import os
from celery import Celery
from celery.schedules import crontab

# Broker & Backend URLs
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "smartparent_tasks",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "src.smartparent.tasks.evidence_tasks",
        "src.smartparent.tasks.sla_watchdog_tasks",
    ],
)

# Celery Production Configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 min hard limit for PDF OCR
    task_soft_time_limit=240,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,  # Prevent memory leaks from PyMuPDF
    task_routes={
        "src.smartparent.tasks.evidence_tasks.*": {"queue": "evidence_queue"},
        "src.smartparent.tasks.sla_watchdog_tasks.*": {"queue": "scheduled_queue"},
    },
    beat_schedule={
        # Check for 48h SLA breaches every 15 minutes
        "check-expert-cases-sla-every-15-mins": {
            "task": "src.smartparent.tasks.sla_watchdog_tasks.check_expert_cases_sla_breach_task",
            "schedule": crontab(minute="*/15"),
        },
        # Synthesize Monthly Parent Pulse on the 1st of every month at midnight IST
        "synthesize-monthly-pulse-cron": {
            "task": "src.smartparent.tasks.sla_watchdog_tasks.monthly_pulse_cron_task",
            "schedule": crontab(minute="0", hour="0", day_of_month="1"),
        },
    },
)

