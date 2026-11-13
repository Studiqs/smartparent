"""
STUDIQS® SmartParent™ (v6.2 Complete) - API v1 Module
Exposes Section 4 (Reports), Section 5 (Performance), and Section 6 (Parent Pulse) routers
"""

from src.smartparent.api.v1.intake import router as intake_router
from src.smartparent.api.v1.curriculum import curriculum_router
from src.smartparent.api.v1.diagnostic import diagnostic_router
from src.smartparent.api.v1.reports import router as reports_router
from src.smartparent.api.v1.performance import router as performance_router
from src.smartparent.api.v1.parent_pulse import router as parent_pulse_router
from src.smartparent.api.v1.actions import router as actions_router
from src.smartparent.api.v1.readiness import router as readiness_router
from src.smartparent.api.v1.handoff import router as handoff_router
from src.smartparent.api.v1.marketplace import router as marketplace_router
from src.smartparent.api.v1.subscriptions import router as subscriptions_router
from src.smartparent.api.v1.tutorials import router as tutorials_router
from src.smartparent.api.v1.support import router as support_router
from src.smartparent.api.v1.admin.support import router as admin_support_router
from src.smartparent.api.v1.admin.subscribers import admin_subscribers_router

__all__ = [
    "intake_router",
    "curriculum_router",
    "diagnostic_router",
    "reports_router",
    "performance_router",
    "parent_pulse_router",
    "actions_router",
    "readiness_router",
    "handoff_router",
    "marketplace_router",
    "subscriptions_router",
    "tutorials_router",
    "support_router",
    "admin_support_router",
    "admin_subscribers_router",
]

