"""
STUDIQS® SmartParent™ (v6.2 Complete) - Sub-3-Minute Consumer Onboarding Service
=================================================================================
Module: src.smartparent.services.onboarding_service
Section 2: Minimal-Friction Consumer Onboarding & Child Profile Setup

Enforces the sub-3-minute consumer onboarding SLA:
  Step 1: Mobile Phone Verification & Parent Registration
  Step 2: Minimal Student Academic Profile (Board + Class)
  Step 3: Initial Quota Provisioning & Baseline Assessment Ready
=================================================================================
"""

import re
import uuid
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from pydantic import BaseModel, Field, EmailStr
from sqlalchemy.orm import Session

from src.smartparent.db.models.auth import Subscriber, Child
from src.smartparent.db.models.usage_quota import SubscriberUsageQuota
from src.smartparent.core.security import create_access_token, create_refresh_token, get_password_hash

logger = logging.getLogger("STUDIQS_OnboardingService")


class QuickOnboardingRequest(BaseModel):
    """Sub-3-minute onboarding payload combining Parent & Child in 1 step."""
    mobile_number: str = Field(..., description="Indian 10-digit mobile number")
    parent_name: str = Field(..., min_length=2, max_length=100)
    email: Optional[EmailStr] = None
    child_name: str = Field(..., min_length=2, max_length=100)
    board: str = Field(..., description="Curriculum Board: CBSE, ICSE, TN_STATE_BOARD")
    standard_class: str = Field(..., description="Standard Class: Class 1 to Class 12")
    academic_year: Optional[str] = "2025-2026"


class OnboardingCompletionResponse(BaseModel):
    """Result of successful onboarding."""
    subscriber_id: str
    child_id: str
    parent_name: str
    student_name: str
    board: str
    standard_class: str
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    onboarding_status: str = "COMPLETED"
    onboarded_at: str


class OnboardingService:
    """
    Sub-3-Minute Onboarding Wizard Engine.
    """

    VALID_BOARDS = {"CBSE", "ICSE", "TN_STATE_BOARD", "STATE_BOARD"}
    VALID_CLASSES = {f"Class {i}" for i in range(1, 13)}

    @staticmethod
    def clean_phone_number(phone: str) -> str:
        """Normalizes phone to E.164 +91 format."""
        digits = re.sub(r"\D", "", phone)
        if len(digits) == 10:
            return f"+91{digits}"
        elif len(digits) == 12 and digits.startswith("91"):
            return f"+{digits}"
        raise ValueError(f"Invalid phone number format '{phone}'. Must be a 10-digit Indian mobile number.")

    def onboard_subscriber_and_child(
        self,
        db: Session,
        payload: QuickOnboardingRequest,
    ) -> OnboardingCompletionResponse:
        """
        Executes atomic sub-3-minute consumer onboarding.
        """
        clean_phone = self.clean_phone_number(payload.mobile_number)

        clean_board = payload.board.strip().upper()
        if clean_board not in self.VALID_BOARDS:
            raise ValueError(f"Invalid board '{payload.board}'. Allowed: {', '.join(sorted(self.VALID_BOARDS))}")

        clean_class = payload.standard_class.strip()
        if clean_class not in self.VALID_CLASSES:
            raise ValueError(f"Invalid standard class '{payload.standard_class}'. Allowed: Class 1 to Class 12")

        # 1. Create or retrieve Subscriber
        existing_sub = db.query(Subscriber).filter(Subscriber.mobile_number == clean_phone).first()
        if existing_sub:
            subscriber = existing_sub
        else:
            subscriber = Subscriber(
                subscriber_id=uuid.uuid4(),
                mobile_number=clean_phone,
                parent_name=payload.parent_name.strip(),
                email=payload.email,
                password_hash=get_password_hash(uuid.uuid4().hex[:12]),  # Secure random passwordless initial hash
            )
            db.add(subscriber)
            db.flush()

        # 2. Create Child
        child = Child(
            child_id=uuid.uuid4(),
            subscriber_id=subscriber.subscriber_id,
            student_name=payload.child_name.strip(),
            standard_class=clean_class,
            board=clean_board,
            academic_year=payload.academic_year or "2025-2026",
        )
        db.add(child)

        # 3. Provision Free Trial Monthly Usage Quota
        month_key = datetime.now(timezone.utc).strftime("%Y-%m")
        existing_quota = db.query(SubscriberUsageQuota).filter(
            SubscriberUsageQuota.subscriber_id == subscriber.subscriber_id,
            SubscriberUsageQuota.month_key == month_key,
        ).first()

        if not existing_quota:
            quota = SubscriberUsageQuota(
                quota_id=uuid.uuid4(),
                subscriber_id=subscriber.subscriber_id,
                month_key=month_key,
                document_uploads_used=0,
                gap_rechecks_used=0,
                diagnostics_used=0,
                active_expert_cases=0,
                voice_queries_used=0,
                typed_tokens_used=0,
            )
            db.add(quota)

        db.commit()
        db.refresh(subscriber)
        db.refresh(child)

        # 4. Generate Auth Tokens
        token_data = {"sub": str(subscriber.subscriber_id), "role": "subscriber"}
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)

        now_str = datetime.now(timezone.utc).isoformat()
        logger.info(f"[OnboardingService] Sub-3-min onboarding complete: {subscriber.parent_name} -> {child.student_name}")

        return OnboardingCompletionResponse(
            subscriber_id=str(subscriber.subscriber_id),
            child_id=str(child.child_id),
            parent_name=subscriber.parent_name,
            student_name=child.student_name,
            board=child.board,
            standard_class=child.standard_class,
            access_token=access_token,
            refresh_token=refresh_token,
            onboarding_status="COMPLETED",
            onboarded_at=now_str,
        )
