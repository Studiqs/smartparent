"""
STUDIQS® SmartParent™ (v6.3 Complete) - Protected Video Tutorial Schemas
=============================================================================
Module: src.smartparent.schemas.tutorial
Section 26: Customer-Only Video Tutorials & In-Product Guidance

Defines strict Pydantic v2 schemas for the 11-video tutorial academy,
signed streaming URL generation, contextual in-app help, and watch progress.
=============================================================================
"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class TutorialCategory(StrEnum):
    """Pedagogical classification categories for the Tutorial Library."""
    ONBOARDING = "ONBOARDING"
    ACADEMIC = "ACADEMIC"
    REPORTS = "REPORTS"
    SUBSCRIPTION = "SUBSCRIPTION"
    SUPPORT = "SUPPORT"
    PRO_FEATURES = "PRO_FEATURES"


class TutorialVideoItemSchema(BaseModel):
    """Public metadata representation of a tutorial video."""
    model_config = ConfigDict(from_attributes=True)

    video_id: int
    title: str
    description: Optional[str] = None
    video_duration_seconds: Optional[int] = None
    min_required_plan: str
    thumbnail_url: Optional[str] = None
    category: str
    sort_order: int
    contextual_help_pages: Optional[str] = None
    is_published: bool
    is_locked: bool = Field(default=False, description="True if subscriber plan does not meet min_required_plan")
    watch_progress_seconds: int = Field(default=0, description="Subscriber's current playback position")
    watch_progress_percent: float = Field(default=0.0, description="Percentage of video watched")
    is_completed: bool = Field(default=False, description="True if subscriber watched >= 90% of the tutorial")


class TutorialListResponse(BaseModel):
    """Response containing grouped or filtered tutorial videos for authenticated subscribers."""
    total_videos: int
    categories: List[str]
    tutorials: List[TutorialVideoItemSchema]


class TutorialPlaybackResponse(BaseModel):
    """
    Authorized streaming session response.
    Returns short-lived signed playback URL with an expiration window.
    Never exposes raw persistent storage paths or credentials.
    """
    video_id: int
    title: str
    signed_streaming_url: str
    expires_at: datetime
    video_duration_seconds: Optional[int] = None
    last_watch_position_seconds: int = 0
    supported_languages: List[str] = Field(
        default=["English", "Tamil"],
        description="Available audio narration or subtitle tracks",
    )
    playback_token: str


class TutorialProgressUpdateRequest(BaseModel):
    """Progress telemetry beacon sent from the video player."""
    watch_progress_seconds: int = Field(..., ge=0, description="Current timestamp in seconds")


class TutorialProgressUpdateResponse(BaseModel):
    """Confirmation of recorded watch progress."""
    progress_id: uuid.UUID
    video_id: int
    subscriber_id: uuid.UUID
    watch_progress_seconds: int
    watch_progress_percent: float
    is_completed: bool
    completed_at: Optional[datetime] = None
    message: str


class ContextualHelpResponse(BaseModel):
    """Contextual in-app help icon (? popup) response for specific dashboard screens."""
    context_key: str
    screen_title: str
    quick_guidance_tip: str
    has_video: bool
    tutorial: Optional[TutorialVideoItemSchema] = None


class OnboardingWalkthroughStatusResponse(BaseModel):
    """Lightweight first-time subscriber walkthrough tracking."""
    subscriber_id: uuid.UUID
    has_completed_walkthrough: bool
    completed_steps: List[str]
    next_step: Optional[str] = None
    all_steps: List[str] = Field(
        default=[
            "ADD_CHILD",
            "SELECT_BOARD_CLASS",
            "CONFIRM_SUBJECTS",
            "ENTER_FIRST_MARKS",
            "EXPLORE_STUDENT_360",
        ]
    )


class CompleteOnboardingStepRequest(BaseModel):
    """Advance or complete an onboarding walkthrough step."""
    step_name: str = Field(..., min_length=2, max_length=50)
    skip_remaining: bool = Field(default=False, description="Allows subscriber to skip remaining onboarding steps")
