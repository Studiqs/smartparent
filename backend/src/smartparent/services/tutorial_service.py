"""
STUDIQS® SmartParent™ (v6.3 Complete) - Protected Video Tutorial Service
=============================================================================
Module: src.smartparent.services.tutorial_service
Section 26: Customer-Only Video Tutorials & Usage Guidance

Implements:
  1. 11 Canonical Tutorial Videos Catalog with auto-seeding.
  2. Plan-Tier Access Firewall (Pro-only vs Basic/Advanced).
  3. Short-lived HMAC Signed Streaming URLs (15-minute expiration).
  4. Watch progress telemetry and 90% completion logic.
  5. Contextual in-product ? Help Icon resolution.
  6. First-time subscriber onboarding walkthrough tracking.
=============================================================================
"""

import hashlib
import hmac
import logging
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, or_

from src.smartparent.core.constants import SubscriptionPlan
from src.smartparent.db.models.auth import Subscriber
from src.smartparent.db.models.tutorial import TutorialVideo, TutorialProgress
from src.smartparent.schemas.tutorial import (
    TutorialCategory,
    TutorialVideoItemSchema,
    TutorialListResponse,
    TutorialPlaybackResponse,
    TutorialProgressUpdateResponse,
    ContextualHelpResponse,
    OnboardingWalkthroughStatusResponse,
)

logger = logging.getLogger("STUDIQS_TutorialService")

# Plan tier weights for hierarchical access gating
PLAN_LEVELS: Dict[str, int] = {
    SubscriptionPlan.BASIC.value: 1,
    SubscriptionPlan.ADVANCED.value: 2,
    SubscriptionPlan.PRO.value: 3,
}

# The 11 Canonical Section 26 Tutorial Specifications
CANONICAL_TUTORIALS = [
    {
        "video_id": 1,
        "title": "Welcome to Studiqs SmartParent",
        "description": "An introduction to your independent B2C learning intelligence dashboard and how it empowers your child's academic journey.",
        "video_duration_seconds": 120,
        "min_required_plan": SubscriptionPlan.BASIC.value,
        "storage_path": "storage/tutorials/01_welcome.mp4",
        "thumbnail_url": "/assets/thumbnails/tutorial_01_welcome.png",
        "category": TutorialCategory.ONBOARDING.value,
        "sort_order": 1,
        "contextual_help_pages": "DASHBOARD,WELCOME,HOME",
    },
    {
        "video_id": 2,
        "title": "How to Add Your Child",
        "description": "Step-by-step guidance on setting up student profiles, selecting boards (CBSE/State Board), and grade standards (Classes 1-12).",
        "video_duration_seconds": 150,
        "min_required_plan": SubscriptionPlan.BASIC.value,
        "storage_path": "storage/tutorials/02_add_child.mp4",
        "thumbnail_url": "/assets/thumbnails/tutorial_02_add_child.png",
        "category": TutorialCategory.ONBOARDING.value,
        "sort_order": 2,
        "contextual_help_pages": "ONBOARDING,ADD_CHILD,PROFILE",
    },
    {
        "video_id": 3,
        "title": "How to Enter Marks",
        "description": "Learn the fast route: record exam scores in under one minute using our parent-friendly Quick Marks entry grid.",
        "video_duration_seconds": 180,
        "min_required_plan": SubscriptionPlan.BASIC.value,
        "storage_path": "storage/tutorials/03_enter_marks.mp4",
        "thumbnail_url": "/assets/thumbnails/tutorial_03_enter_marks.png",
        "category": TutorialCategory.ACADEMIC.value,
        "sort_order": 3,
        "contextual_help_pages": "ADD_MARKS,QUICK_MARKS,EVIDENCE",
    },
    {
        "video_id": 4,
        "title": "How to Upload Question Papers",
        "description": "Discover Document AI: upload question papers (PDF/Images) to extract questions, map topics, and confirm line-item marks.",
        "video_duration_seconds": 210,
        "min_required_plan": SubscriptionPlan.BASIC.value,
        "storage_path": "storage/tutorials/04_upload_qp.mp4",
        "thumbnail_url": "/assets/thumbnails/tutorial_04_upload_qp.png",
        "category": TutorialCategory.ACADEMIC.value,
        "sort_order": 4,
        "contextual_help_pages": "UPLOAD_PAPER,DOCUMENT_AI,QP",
    },
    {
        "video_id": 5,
        "title": "Understanding Topic Intelligence",
        "description": "Explore the 4 mastery tiers (Strong, Average, Weak, Critical) across 8,034 topics and monitor the persistent learning gap watchlist.",
        "video_duration_seconds": 240,
        "min_required_plan": SubscriptionPlan.BASIC.value,
        "storage_path": "storage/tutorials/05_topic_intelligence.mp4",
        "thumbnail_url": "/assets/thumbnails/tutorial_05_topic_intel.png",
        "category": TutorialCategory.ACADEMIC.value,
        "sort_order": 5,
        "contextual_help_pages": "TOPIC_INTELLIGENCE,MASTERY,GAPS",
    },
    {
        "video_id": 6,
        "title": "Understanding Student 360",
        "description": "Interpret holistic diagnostic telemetry, longitudinal performance trajectories, and topic-level strengths.",
        "video_duration_seconds": 200,
        "min_required_plan": SubscriptionPlan.BASIC.value,
        "storage_path": "storage/tutorials/06_student_360.mp4",
        "thumbnail_url": "/assets/thumbnails/tutorial_06_student_360.png",
        "category": TutorialCategory.ACADEMIC.value,
        "sort_order": 6,
        "contextual_help_pages": "STUDENT_360,DIAGNOSTICS,PROFILE",
    },
    {
        "video_id": 7,
        "title": "Monthly, Term and Yearly Reports",
        "description": "Master the Report Lifecycle: browse automatically compiled monthly diagnostic digests and term progress evaluations.",
        "video_duration_seconds": 190,
        "min_required_plan": SubscriptionPlan.BASIC.value,
        "storage_path": "storage/tutorials/07_reports_overview.mp4",
        "thumbnail_url": "/assets/thumbnails/tutorial_07_reports.png",
        "category": TutorialCategory.REPORTS.value,
        "sort_order": 7,
        "contextual_help_pages": "REPORT_CENTRE,REPORTS,PULSE",
    },
    {
        "video_id": 8,
        "title": "How to Download and Print Reports",
        "description": "Download 12-page deterministic vector PDFs with school/tuition academic handoff summary sheets.",
        "video_duration_seconds": 130,
        "min_required_plan": SubscriptionPlan.BASIC.value,
        "storage_path": "storage/tutorials/08_download_print_reports.mp4",
        "thumbnail_url": "/assets/thumbnails/tutorial_08_download.png",
        "category": TutorialCategory.REPORTS.value,
        "sort_order": 8,
        "contextual_help_pages": "DOWNLOAD_REPORT,PRINT_REPORT",
    },
    {
        "video_id": 9,
        "title": "How to Manage Your Subscription",
        "description": "View active plans (Basic/Advanced/Pro), payment receipts, billing history, and manage automatic renewals with Razorpay.",
        "video_duration_seconds": 160,
        "min_required_plan": SubscriptionPlan.BASIC.value,
        "storage_path": "storage/tutorials/09_manage_subscription.mp4",
        "thumbnail_url": "/assets/thumbnails/tutorial_09_subscription.png",
        "category": TutorialCategory.SUBSCRIPTION.value,
        "sort_order": 9,
        "contextual_help_pages": "SUBSCRIPTION,BILLING,RENEWAL",
    },
    {
        "video_id": 10,
        "title": "How to Raise a Support Ticket",
        "description": "Contact our academic operations team through our in-platform support desk backed by a strict 48-hour hard SLA.",
        "video_duration_seconds": 140,
        "min_required_plan": SubscriptionPlan.BASIC.value,
        "storage_path": "storage/tutorials/10_raise_support_ticket.mp4",
        "thumbnail_url": "/assets/thumbnails/tutorial_10_support.png",
        "category": TutorialCategory.SUPPORT.value,
        "sort_order": 10,
        "contextual_help_pages": "SUPPORT_CENTRE,HELP,TICKET",
    },
    {
        "video_id": 11,
        "title": "How to Use AI Voice / RAG (Pro Only)",
        "description": "Voice Pro demonstration: conversational queries ('Ask Studiqs') with strict tenant isolation, 6-pillar topic filtering, and no hallucination.",
        "video_duration_seconds": 300,
        "min_required_plan": SubscriptionPlan.PRO.value,
        "storage_path": "storage/tutorials/11_ai_voice_pro.mp4",
        "thumbnail_url": "/assets/thumbnails/tutorial_11_voice_pro.png",
        "category": TutorialCategory.PRO_FEATURES.value,
        "sort_order": 11,
        "contextual_help_pages": "ASK_STUDIQS,VOICE_PRO,AI_VOICE",
    },
]

CONTEXTUAL_TIPS: Dict[str, Tuple[str, str]] = {
    "ADD_MARKS": (
        "Entering Marks",
        "Tip: Use Quick Marks to input total scores in seconds, or upload a Question Paper PDF for automatic line-item question breakdown.",
    ),
    "TOPIC_INTELLIGENCE": (
        "Topic Intelligence & Gaps",
        "Tip: Topics scored below 40% are flagged as CRITICAL. They are automatically added to the child's learning gap watchlist until resolved.",
    ),
    "REPORT_CENTRE": (
        "Report Centre",
        "Tip: Monthly digests are compiled on the 1st of each month. Download the handoff summary for parent-teacher conferences.",
    ),
    "SUBSCRIPTION": (
        "Subscription & Billing",
        "Tip: Upgrading to Pro unlocks the AI Voice Assistant ('Ask Studiqs') with real-time multi-child diagnostic querying.",
    ),
    "SUPPORT_CENTRE": (
        "Help Centre",
        "Tip: All tickets are guaranteed a response within 48 hours by our senior academic support specialists.",
    ),
    "ASK_STUDIQS": (
        "AI Voice Assistant (Pro)",
        "Tip: Ask questions like 'Which math topics does my child struggle with?' to retrieve isolated diagnostic insights instantly.",
    ),
}


class TutorialService:
    """
    Enterprise Video Tutorial Service enforcing Section 26 requirements.
    """

    def __init__(self, signing_secret: Optional[str] = None):
        self.signing_secret = signing_secret or os.getenv(
            "TUTORIAL_STREAMING_SECRET", "studiqs_prod_tutorial_signing_key_2026"
        )

    def _ensure_catalog_seeded(self, db: Session) -> None:
        """Auto-seeds the 11 canonical tutorial videos if the table is currently empty."""
        count = db.execute(select(TutorialVideo)).scalars().first()
        if not count:
            logger.info("[TutorialService] Seeding 11 canonical tutorial videos...")
            for spec in CANONICAL_TUTORIALS:
                video = TutorialVideo(
                    video_id=spec["video_id"],
                    title=spec["title"],
                    description=spec["description"],
                    video_duration_seconds=spec["video_duration_seconds"],
                    min_required_plan=spec["min_required_plan"],
                    storage_path=spec["storage_path"],
                    thumbnail_url=spec["thumbnail_url"],
                    category=spec["category"],
                    sort_order=spec["sort_order"],
                    contextual_help_pages=spec["contextual_help_pages"],
                    is_published=True,
                )
                db.add(video)
            db.commit()
            logger.info("[TutorialService] Canonical tutorial videos seeded successfully.")

    def _is_plan_entitled(self, subscriber_plan: str, min_required_plan: str) -> bool:
        """Evaluates hierarchical plan tier entitlement (BASIC < ADVANCED < PRO)."""
        user_weight = PLAN_LEVELS.get(subscriber_plan.upper(), 1)
        required_weight = PLAN_LEVELS.get(min_required_plan.upper(), 1)
        return user_weight >= required_weight

    def generate_signed_token(self, video_id: int, subscriber_id: uuid.UUID, expires_at_timestamp: int) -> str:
        """Computes HMAC-SHA256 signature for short-lived authorized playback."""
        message = f"video:{video_id}:sub:{subscriber_id}:exp:{expires_at_timestamp}".encode("utf-8")
        return hmac.new(self.signing_secret.encode("utf-8"), message, hashlib.sha256).hexdigest()

    def verify_signed_token(self, video_id: int, subscriber_id: uuid.UUID, expires_at_timestamp: int, token: str) -> bool:
        """Validates playback token authenticity and expiration window."""
        current_ts = int(time.time())
        if current_ts > expires_at_timestamp:
            return False
        expected_token = self.generate_signed_token(video_id, subscriber_id, expires_at_timestamp)
        return hmac.compare_digest(expected_token, token)

    def list_tutorials(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        category: Optional[str] = None,
    ) -> TutorialListResponse:
        """
        Lists all published tutorial videos with personalized lock status and watch progress.
        """
        self._ensure_catalog_seeded(db)

        sub_stmt = select(Subscriber).where(Subscriber.subscriber_id == subscriber_id)
        subscriber = db.execute(sub_stmt).scalar_one_or_none()
        user_plan = subscriber.subscription_plan if subscriber else SubscriptionPlan.BASIC.value

        # Fetch all progress records for subscriber
        prog_stmt = select(TutorialProgress).where(TutorialProgress.subscriber_id == subscriber_id)
        prog_map = {p.video_id: p for p in db.execute(prog_stmt).scalars().all()}

        # Fetch published videos
        conditions = [TutorialVideo.is_published == True]
        if category:
            conditions.append(TutorialVideo.category.ilike(category))

        query = select(TutorialVideo).where(and_(*conditions)).order_by(TutorialVideo.sort_order)
        videos = db.execute(query).scalars().all()

        results: List[TutorialVideoItemSchema] = []
        categories_set = set()

        for v in videos:
            if v.category:
                categories_set.add(v.category)

            is_locked = not self._is_plan_entitled(user_plan, v.min_required_plan)
            progress = prog_map.get(v.video_id)

            watch_sec = progress.watch_progress_seconds if progress else 0
            watch_pct = float(progress.watch_progress_percent) if progress else 0.0
            is_comp = bool(progress.is_completed) if progress else False

            results.append(
                TutorialVideoItemSchema(
                    video_id=v.video_id,
                    title=v.title,
                    description=v.description,
                    video_duration_seconds=v.video_duration_seconds,
                    min_required_plan=v.min_required_plan,
                    thumbnail_url=v.thumbnail_url,
                    category=v.category or "ACADEMIC",
                    sort_order=v.sort_order,
                    contextual_help_pages=v.contextual_help_pages,
                    is_published=v.is_published,
                    is_locked=is_locked,
                    watch_progress_seconds=watch_sec,
                    watch_progress_percent=watch_pct,
                    is_completed=is_comp,
                )
            )

        return TutorialListResponse(
            total_videos=len(results),
            categories=sorted(list(categories_set)),
            tutorials=results,
        )

    def get_tutorial_playback_session(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        video_id: int,
    ) -> TutorialPlaybackResponse:
        """
        Authorizes video streaming and produces a 15-minute signed playback session.
        Enforces plan gating: Blocks Basic/Advanced users from Pro-only tutorials.
        """
        self._ensure_catalog_seeded(db)

        # 1. Fetch video
        v_stmt = select(TutorialVideo).where(
            and_(TutorialVideo.video_id == video_id, TutorialVideo.is_published == True)
        )
        video = db.execute(v_stmt).scalar_one_or_none()
        if not video:
            raise KeyError(f"Tutorial video #{video_id} not found or unpublished.")

        # 2. Check subscriber plan
        sub_stmt = select(Subscriber).where(Subscriber.subscriber_id == subscriber_id)
        subscriber = db.execute(sub_stmt).scalar_one_or_none()
        if not subscriber:
            raise PermissionError("Authenticated subscriber profile required.")

        user_plan = subscriber.subscription_plan
        if not self._is_plan_entitled(user_plan, video.min_required_plan):
            raise PermissionError(
                f"Access Denied: Tutorial '{video.title}' requires a {video.min_required_plan} subscription tier. "
                f"Your current plan is {user_plan}."
            )

        # 3. Retrieve watch progress bookmark
        prog_stmt = select(TutorialProgress).where(
            and_(
                TutorialProgress.subscriber_id == subscriber_id,
                TutorialProgress.video_id == video_id,
            )
        )
        progress = db.execute(prog_stmt).scalar_one_or_none()
        last_pos = progress.watch_progress_seconds if progress else 0

        # 4. Generate 15-minute signed token
        now_dt = datetime.now(timezone.utc)
        expires_dt = now_dt + timedelta(minutes=15)
        exp_ts = int(expires_dt.timestamp())
        token = self.generate_signed_token(video_id, subscriber_id, exp_ts)

        signed_url = f"/api/v1/tutorials/{video_id}/stream?token={token}&sub={subscriber_id}&exp={exp_ts}"

        return TutorialPlaybackResponse(
            video_id=video.video_id,
            title=video.title,
            signed_streaming_url=signed_url,
            expires_at=expires_dt,
            video_duration_seconds=video.video_duration_seconds,
            last_watch_position_seconds=last_pos,
            supported_languages=["English", "Tamil"],
            playback_token=token,
        )

    def record_watch_progress(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        video_id: int,
        watch_seconds: int,
    ) -> TutorialProgressUpdateResponse:
        """
        Updates watch telemetry. If watch progress reaches >= 90%, marks tutorial as COMPLETED.
        """
        self._ensure_catalog_seeded(db)

        v_stmt = select(TutorialVideo).where(TutorialVideo.video_id == video_id)
        video = db.execute(v_stmt).scalar_one_or_none()
        if not video:
            raise KeyError(f"Tutorial video #{video_id} not found.")

        duration = video.video_duration_seconds or 180
        clamped_seconds = min(watch_seconds, duration)
        pct = round((clamped_seconds / duration) * 100.0, 2)
        is_completed = pct >= 90.0

        prog_stmt = select(TutorialProgress).where(
            and_(
                TutorialProgress.subscriber_id == subscriber_id,
                TutorialProgress.video_id == video_id,
            )
        )
        progress = db.execute(prog_stmt).scalar_one_or_none()

        now_utc = datetime.now(timezone.utc)
        if not progress:
            progress = TutorialProgress(
                progress_id=uuid.uuid4(),
                subscriber_id=subscriber_id,
                video_id=video_id,
                watch_progress_seconds=clamped_seconds,
                watch_progress_percent=pct,
                is_completed=is_completed,
                last_watched_at=now_utc,
                completed_at=now_utc if is_completed else None,
            )
            db.add(progress)
        else:
            progress.watch_progress_seconds = max(progress.watch_progress_seconds, clamped_seconds)
            progress.watch_progress_percent = max(float(progress.watch_progress_percent), pct)
            if is_completed and not progress.is_completed:
                progress.is_completed = True
                progress.completed_at = now_utc
            progress.last_watched_at = now_utc

        db.commit()
        db.refresh(progress)

        return TutorialProgressUpdateResponse(
            progress_id=progress.progress_id,
            video_id=video_id,
            subscriber_id=subscriber_id,
            watch_progress_seconds=progress.watch_progress_seconds,
            watch_progress_percent=float(progress.watch_progress_percent),
            is_completed=progress.is_completed,
            completed_at=progress.completed_at,
            message="Progress recorded successfully.",
        )

    def get_contextual_help(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        context_key: str,
    ) -> ContextualHelpResponse:
        """
        Resolves the small ? help icon on specific dashboard pages (e.g. ADD_MARKS, REPORT_CENTRE).
        Returns contextual tip and associated short tutorial video.
        """
        self._ensure_catalog_seeded(db)

        clean_key = context_key.strip().upper()
        screen_title, tip = CONTEXTUAL_TIPS.get(
            clean_key,
            (
                "Help & Tutorials",
                "Tip: Browse the full video library in the Help Centre to learn more about SmartParent.",
            ),
        )

        sub_stmt = select(Subscriber).where(Subscriber.subscriber_id == subscriber_id)
        subscriber = db.execute(sub_stmt).scalar_one_or_none()
        user_plan = subscriber.subscription_plan if subscriber else SubscriptionPlan.BASIC.value

        # Search video associated with page
        stmt = select(TutorialVideo).where(
            and_(
                TutorialVideo.is_published == True,
                TutorialVideo.contextual_help_pages.ilike(f"%{clean_key}%"),
            )
        )
        video = db.execute(stmt).scalars().first()

        video_schema = None
        if video:
            prog_stmt = select(TutorialProgress).where(
                and_(
                    TutorialProgress.subscriber_id == subscriber_id,
                    TutorialProgress.video_id == video.video_id,
                )
            )
            progress = db.execute(prog_stmt).scalar_one_or_none()

            video_schema = TutorialVideoItemSchema(
                video_id=video.video_id,
                title=video.title,
                description=video.description,
                video_duration_seconds=video.video_duration_seconds,
                min_required_plan=video.min_required_plan,
                thumbnail_url=video.thumbnail_url,
                category=video.category or "ACADEMIC",
                sort_order=video.sort_order,
                contextual_help_pages=video.contextual_help_pages,
                is_published=video.is_published,
                is_locked=not self._is_plan_entitled(user_plan, video.min_required_plan),
                watch_progress_seconds=progress.watch_progress_seconds if progress else 0,
                watch_progress_percent=float(progress.watch_progress_percent) if progress else 0.0,
                is_completed=bool(progress.is_completed) if progress else False,
            )

        return ContextualHelpResponse(
            context_key=clean_key,
            screen_title=screen_title,
            quick_guidance_tip=tip,
            has_video=video_schema is not None,
            tutorial=video_schema,
        )

    def get_onboarding_walkthrough_status(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
    ) -> OnboardingWalkthroughStatusResponse:
        """Returns lightweight first-time subscriber onboarding progression."""
        # Check tutorial #1 and #2 watch completion as onboarding markers
        prog_stmt = select(TutorialProgress).where(
            and_(
                TutorialProgress.subscriber_id == subscriber_id,
                TutorialProgress.video_id.in_([1, 2]),
                TutorialProgress.is_completed == True,
            )
        )
        completed_records = db.execute(prog_stmt).scalars().all()
        is_done = len(completed_records) >= 1

        completed_steps = ["ADD_CHILD", "SELECT_BOARD_CLASS"] if is_done else []
        next_step = "CONFIRM_SUBJECTS" if is_done else "ADD_CHILD"

        return OnboardingWalkthroughStatusResponse(
            subscriber_id=subscriber_id,
            has_completed_walkthrough=is_done,
            completed_steps=completed_steps,
            next_step=next_step if not is_done else None,
        )


tutorial_service = TutorialService()
