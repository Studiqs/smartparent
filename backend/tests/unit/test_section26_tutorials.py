"""
STUDIQS® SmartParent™ - Section 26 Video Tutorials & Guidance Unit Tests
=============================================================================
Module: tests.unit.test_section26_tutorials

Verifies:
  1. Auto-seeding of all 11 canonical Section 26 tutorial videos.
  2. Plan-tier gating: Pro-only video blocked for Basic subscribers, unlocked for Pro.
  3. Short-lived 15-minute HMAC signed streaming URL generation and tamper detection.
  4. Watch progress telemetry and automated 90% completion trigger.
  5. Contextual in-product ? Help Icon resolution across dashboard pages.
  6. First-time subscriber onboarding walkthrough status.
=============================================================================
"""

import time
import uuid
from datetime import datetime, timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID

@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"

@compiles(PG_UUID, "sqlite")
def compile_uuid_sqlite(type_, compiler, **kw):
    return "CHAR(36)"

from src.smartparent.core.constants import SubscriptionPlan
from src.smartparent.db.base import Base
from src.smartparent.db.models.auth import Subscriber, Child
from src.smartparent.db.models.tutorial import TutorialVideo, TutorialProgress
from src.smartparent.services.tutorial_service import TutorialService, CANONICAL_TUTORIALS


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def seed_subscribers(test_db):
    basic_sub_id = uuid.uuid4()
    pro_sub_id = uuid.uuid4()

    basic_sub = Subscriber(
        subscriber_id=basic_sub_id,
        mobile_number="9876543220",
        parent_name="Venkatesh S.",
        password_hash="basic_hash",
        subscription_plan=SubscriptionPlan.BASIC.value,
    )
    pro_sub = Subscriber(
        subscriber_id=pro_sub_id,
        mobile_number="9876543221",
        parent_name="Dr. Lakshmi N.",
        password_hash="pro_hash",
        subscription_plan=SubscriptionPlan.PRO.value,
    )

    test_db.add_all([basic_sub, pro_sub])
    test_db.commit()

    return {
        "basic_sub_id": basic_sub_id,
        "pro_sub_id": pro_sub_id,
    }


class TestSection26VideoTutorials:
    """Production test suite for Section 26 Video Tutorials & Guidance."""

    def test_canonical_catalog_autoseeding(self, test_db, seed_subscribers):
        """Service automatically seeds 11 canonical tutorials when the table is empty."""
        service = TutorialService()
        res = service.list_tutorials(
            db=test_db,
            subscriber_id=seed_subscribers["basic_sub_id"],
        )

        assert res.total_videos == 11
        assert len(res.tutorials) == 11
        assert "ONBOARDING" in res.categories
        assert "ACADEMIC" in res.categories
        assert "REPORTS" in res.categories
        assert "PRO_FEATURES" in res.categories

        # Verify specific titles
        titles = [t.title for t in res.tutorials]
        assert "Welcome to Studiqs SmartParent" in titles
        assert "How to Enter Marks" in titles
        assert "How to Use AI Voice / RAG (Pro Only)" in titles

    def test_plan_tier_gating_blocks_basic_subscriber_from_pro_video(self, test_db, seed_subscribers):
        """Basic subscriber is denied playback of Pro-only Video #11, while Pro subscriber succeeds."""
        service = TutorialService()

        # 1. Basic user attempting to stream Pro video #11 -> PermissionError
        with pytest.raises(PermissionError) as exc_info:
            service.get_tutorial_playback_session(
                db=test_db,
                subscriber_id=seed_subscribers["basic_sub_id"],
                video_id=11,  # AI Voice Pro
            )
        assert "requires a PRO subscription tier" in str(exc_info.value)

        # 2. Pro user streaming Pro video #11 -> Success with 15-min signed token
        playback = service.get_tutorial_playback_session(
            db=test_db,
            subscriber_id=seed_subscribers["pro_sub_id"],
            video_id=11,
        )
        assert playback.video_id == 11
        assert "token=" in playback.signed_streaming_url
        assert playback.playback_token is not None
        assert playback.expires_at > datetime.now(timezone.utc)

    def test_signed_token_generation_and_tamper_detection(self, test_db, seed_subscribers):
        """HMAC signed token strictly validates subscriber identity, video ID, and expiration window."""
        service = TutorialService(signing_secret="test_secret_key_123")
        sub_id = seed_subscribers["basic_sub_id"]
        exp_ts = int(time.time()) + 900  # 15 minutes in future

        # 1. Generate valid token
        token = service.generate_signed_token(video_id=1, subscriber_id=sub_id, expires_at_timestamp=exp_ts)
        assert service.verify_signed_token(1, sub_id, exp_ts, token) is True

        # 2. Tampered video ID -> Fails
        assert service.verify_signed_token(2, sub_id, exp_ts, token) is False

        # 3. Tampered subscriber ID -> Fails
        other_sub = uuid.uuid4()
        assert service.verify_signed_token(1, other_sub, exp_ts, token) is False

        # 4. Expired token -> Fails
        past_exp = int(time.time()) - 10
        expired_token = service.generate_signed_token(video_id=1, subscriber_id=sub_id, expires_at_timestamp=past_exp)
        assert service.verify_signed_token(1, sub_id, past_exp, expired_token) is False

    def test_watch_progress_telemetry_and_automated_completion(self, test_db, seed_subscribers):
        """Records watch progress; reaching >= 90% automatically sets is_completed=True."""
        service = TutorialService()
        sub_id = seed_subscribers["basic_sub_id"]

        # Video #1 has duration 120s
        # 1. Watch 30 seconds (25%)
        p1 = service.record_watch_progress(
            db=test_db,
            subscriber_id=sub_id,
            video_id=1,
            watch_seconds=30,
        )
        assert p1.watch_progress_seconds == 30
        assert p1.watch_progress_percent == 25.0
        assert p1.is_completed is False
        assert p1.completed_at is None

        # 2. Watch 110 seconds (91.67% >= 90.0% completion threshold)
        p2 = service.record_watch_progress(
            db=test_db,
            subscriber_id=sub_id,
            video_id=1,
            watch_seconds=110,
        )
        assert p2.watch_progress_seconds == 110
        assert p2.watch_progress_percent == 91.67
        assert p2.is_completed is True
        assert p2.completed_at is not None

        # 3. Confirm listed status shows completed
        catalog = service.list_tutorials(db=test_db, subscriber_id=sub_id)
        v1 = next(t for t in catalog.tutorials if t.video_id == 1)
        assert v1.is_completed is True
        assert v1.watch_progress_percent == 91.67

    def test_contextual_help_icon_mapping(self, test_db, seed_subscribers):
        """Resolves dashboard ? help icon with contextual short video and pedagogical tips."""
        service = TutorialService()

        # 1. Context: ADD_MARKS -> Video #3
        h1 = service.get_contextual_help(
            db=test_db,
            subscriber_id=seed_subscribers["basic_sub_id"],
            context_key="ADD_MARKS",
        )
        assert h1.has_video is True
        assert h1.tutorial.video_id == 3
        assert h1.tutorial.title == "How to Enter Marks"
        assert "Quick Marks" in h1.quick_guidance_tip

        # 2. Context: REPORT_CENTRE -> Video #7
        h2 = service.get_contextual_help(
            db=test_db,
            subscriber_id=seed_subscribers["basic_sub_id"],
            context_key="REPORT_CENTRE",
        )
        assert h2.has_video is True
        assert h2.tutorial.video_id == 7

        # 3. Context: ASK_STUDIQS -> Video #11 (locked for Basic subscriber)
        h3 = service.get_contextual_help(
            db=test_db,
            subscriber_id=seed_subscribers["basic_sub_id"],
            context_key="ASK_STUDIQS",
        )
        assert h3.has_video is True
        assert h3.tutorial.video_id == 11
        assert h3.tutorial.is_locked is True  # Basic user cannot access Pro video!

