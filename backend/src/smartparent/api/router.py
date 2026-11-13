"""
STUDIQS® SmartParent™ - Central API Router
=============================================================================
Module: src.smartparent.api.router
Feature Pack 1: Core Authentication, 3-Role RBAC & Child Onboarding
=============================================================================
"""

from fastapi import APIRouter

from src.smartparent.api.v1.auth import router as auth_router
from src.smartparent.api.v1.curriculum import curriculum_router

api_router = APIRouter(prefix="/api/v1")

# Mount Feature Pack 1: Section 2 Authentication & Ultra-Simple Onboarding
api_router.include_router(auth_router)
api_router.include_router(curriculum_router)
