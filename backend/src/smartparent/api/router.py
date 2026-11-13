"""
STUDIQS® SmartParent™ (v6.2 & v6.3 Extension) - Central API Router
=============================================================================
Module: src.smartparent.api.router
Aggregates all API v1 domain routers under the /api/v1 prefix:
  - Section 14 & 27: Support Centre, Ticketing & Admin SLA Triage
  - Section 7 & 9: Parent Actions & Academic Handoff
  - Section 11 & 12: Subject Expert Marketplace & Case Workflows
  - Section 6: Monthly Parent Pulse & Learning Cycle
  - Section 5: Performance Intelligence, Consistency & Topic Gaps
  - Section 8: Board Exam Readiness & Academic Share Mode
  - Section 4: Mandatory Student Consolidated Reports & Student 360
  - Section 10: Netflix-Style Subscriptions & Invoicing
=============================================================================
"""

from fastapi import APIRouter

from src.smartparent.api.v1.support import router as support_router
from src.smartparent.api.v1.admin.support import router as admin_support_router
from src.smartparent.api.v1.actions import router as actions_router
from src.smartparent.api.v1.handoff import router as handoff_router
from src.smartparent.api.v1.marketplace import router as marketplace_router
from src.smartparent.api.v1.parent_pulse import router as parent_pulse_router
from src.smartparent.api.v1.performance import router as performance_router
from src.smartparent.api.v1.readiness import router as readiness_router
from src.smartparent.api.v1.reports import router as reports_router
from src.smartparent.api.v1.subscriptions import router as subscriptions_router
from src.smartparent.api.v1.notification import router as notification_router
from src.smartparent.api.v1.auth import router as auth_router
from src.smartparent.api.v1.security_isolation import router as isolation_router
from src.smartparent.api.v1.analytics_ai import router as analytics_router
from src.smartparent.api.v1.webhooks import router as webhooks_router
from src.smartparent.api.v1.admin.dashboard import router as admin_dashboard_router
from src.smartparent.api.v1.admin.subscribers import admin_subscribers_router
from src.smartparent.api.v1.voice import router as voice_router
from src.smartparent.api.v1.intake import router as intake_router
from src.smartparent.api.v1.tutorials import router as tutorials_router
from src.smartparent.api.v1.curriculum import curriculum_router
from src.smartparent.api.v1.diagnostic import diagnostic_router
from src.smartparent.api.v1.legal import router as legal_router
from src.smartparent.api.v1.sandbox import router as sandbox_router
from src.smartparent.api.v1.public_preview import router as public_preview_router
from src.smartparent.api.v1.attribution import router as attribution_router
from src.smartparent.api.v1.ecosystem import router as ecosystem_router

api_router = APIRouter(prefix="/api/v1")

# Mount Section 2 Authentication & Ultra-Simple Onboarding router
api_router.include_router(auth_router)

# Mount Section 14 & 27 Support routers
api_router.include_router(support_router)
api_router.include_router(admin_support_router)

# Mount Section 24 Gateway Webhooks & Section 25 Admin Revenue Dashboard & Directory
api_router.include_router(webhooks_router)
api_router.include_router(admin_dashboard_router)
api_router.include_router(admin_subscribers_router)

# Mount Core SmartParent v6.2 / v6.3 functional routers
api_router.include_router(actions_router)
api_router.include_router(handoff_router)
api_router.include_router(marketplace_router)
api_router.include_router(parent_pulse_router)
api_router.include_router(performance_router)
api_router.include_router(readiness_router)
api_router.include_router(reports_router)
api_router.include_router(subscriptions_router)
api_router.include_router(notification_router)
api_router.include_router(isolation_router)
api_router.include_router(analytics_router)
api_router.include_router(voice_router)
api_router.include_router(intake_router)
api_router.include_router(tutorials_router)
api_router.include_router(curriculum_router)
api_router.include_router(diagnostic_router)
api_router.include_router(legal_router)
api_router.include_router(sandbox_router)
api_router.include_router(public_preview_router)
api_router.include_router(attribution_router)
api_router.include_router(ecosystem_router)
