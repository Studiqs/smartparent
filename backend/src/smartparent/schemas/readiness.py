"""
STUDIQS® SmartParent™ (v6.2 Complete) - Section 8 Board Readiness & Share Mode Schemas
=============================================================================
Pydantic v2 schemas governing:
1. Board Exam Readiness Index & High-Weightage Risk Radar
2. Projected Score Corridor & Syllabus Coverage Gauge
3. Stream Alignment & Career Future Readiness
4. Student Milestone & Achievement Badges
5. Parent-Controlled 72-Hour Share Token Generation & Revocation
6. Public Zero-Leakage Tutor / Mentor Diagnostic Shared Report View
=============================================================================
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# =============================================================================
# 1. Board Readiness Schemas
# =============================================================================

class ScoreCorridorSchema(BaseModel):
    lower_bound_pct: float = Field(..., description="Conservative lower bound projected board score")
    most_likely_pct: float = Field(..., description="Most probable projected board score")
    upper_bound_pct: float = Field(..., description="Optimistic upper bound projected board score")
    corridor_spread_pct: Optional[float] = Field(None, description="Spread width between upper and lower bound")
    projection_confidence: str = Field(..., description="Confidence tier: HIGH, MODERATE, PRELIMINARY")
    confidence_score: float = Field(..., description="Numeric confidence level 0.0 to 1.0")


class SyllabusCoverageSchema(BaseModel):
    total_curriculum_topics: int = Field(..., description="Total official curriculum topics for standard/board")
    tested_topics_count: int = Field(..., description="Number of topics assessed via test evidence")
    mastered_topics_count: int = Field(..., description="Number of topics in Mastered tier (>=80%)")
    coverage_percentage: float = Field(..., description="Percentage of curriculum covered by tests")
    mastery_percentage: float = Field(..., description="Percentage of curriculum mastered")
    untested_topics_count: int = Field(..., description="Topics without test evidence")


class HighWeightageRiskTopicSchema(BaseModel):
    topic_name: str
    subject: str
    chapter: str
    weightage_marks: float
    student_score_pct: float
    mastery_tier: str
    has_active_gap: bool
    risk_severity: str  # CRITICAL, EMERGING
    remediation_action: str


class RiskRadarSchema(BaseModel):
    high_weightage_risk_count: int
    critical_risk_count: int
    risk_index: float  # 0 to 100
    risk_level: str  # HIGH, MODERATE, LOW
    risk_topics: List[HighWeightageRiskTopicSchema]


class SubjectReadinessDetailSchema(BaseModel):
    subject: str
    average_percentage: float
    latest_percentage: float
    total_assessments: int
    health_tier: str  # STRONG, AVERAGE, VULNERABLE, CRITICAL


class StreamAlignmentSchema(BaseModel):
    recommended_stream: str
    recommended_stream_display: Optional[str] = Field(None, description="Display name for recommended stream")
    best_stream_score: Optional[float] = Field(None, description="Best stream aptitude score")
    alignment_scores: Dict[str, float] = Field(default_factory=dict)
    rationale: str


class PriorityActionItemSchema(BaseModel):
    priority: str  # HIGH, MEDIUM, LOW
    title: str
    action: str
    target_subject: str


class BoardReadinessResponse(BaseModel):
    child_id: uuid.UUID
    student_name: str
    standard_class: str
    board: str
    readiness_status: str  # READY, ON_TRACK, NEEDS_ATTENTION, CRITICAL_RISK
    status_rationale: str
    is_board_appearing_grade: bool
    score_corridor: ScoreCorridorSchema
    syllabus_coverage: SyllabusCoverageSchema
    risk_radar: RiskRadarSchema
    subject_breakdown: Dict[str, SubjectReadinessDetailSchema]
    stream_alignment: StreamAlignmentSchema
    priority_action_checklist: List[PriorityActionItemSchema]
    evaluated_at: datetime


# =============================================================================
# 2. Achievement & Milestone Badges Schemas
# =============================================================================

class AchievementBadgeSchema(BaseModel):
    badge_code: str
    title: str
    category: str
    description: str
    icon: str
    is_unlocked: bool
    unlocked_at: Optional[str] = None
    evidence_highlight: Optional[str] = None
    current_progress: Optional[int] = None
    target_threshold: Optional[int] = None
    progress_percentage: float
    progress_label: Optional[str] = None


class StudentAchievementsResponse(BaseModel):
    child_id: uuid.UUID
    student_name: str
    total_badges_count: int
    unlocked_count: int
    in_progress_count: int
    completion_percentage: float
    unlocked_badges: List[AchievementBadgeSchema]
    in_progress_badges: List[AchievementBadgeSchema]


# =============================================================================
# 3. Share Mode (72-Hour Expiring Link) Schemas
# =============================================================================

class GenerateShareLinkRequest(BaseModel):
    child_id: uuid.UUID
    duration_hours: int = Field(default=72, ge=1, le=168, description="Validity duration in hours (default 72h)")
    notes: Optional[str] = Field(default=None, max_length=250, description="Optional parent note for tutor")


class ShareLinkResponse(BaseModel):
    token_id: uuid.UUID
    child_id: uuid.UUID
    share_token: str
    share_url: str
    expires_at: datetime
    hours_valid: int
    seconds_remaining: int
    time_remaining_display: str
    is_revoked: bool
    created_at: datetime


class ActiveShareTokenSchema(BaseModel):
    token_id: uuid.UUID
    share_token: str
    share_url: str
    expires_at: datetime
    is_revoked: bool
    is_expired: bool
    seconds_remaining: int
    time_remaining_display: str
    created_at: datetime


class ActiveShareTokensListResponse(BaseModel):
    child_id: uuid.UUID
    active_tokens_count: int
    tokens: List[ActiveShareTokenSchema]


class RevokeShareLinkResponse(BaseModel):
    token_id: uuid.UUID
    is_revoked: bool
    revoked_at: datetime
    message: str


# =============================================================================
# 4. Public Sanitized Shared Report (Zero Privacy Leakage) Schema
# =============================================================================

class PublicSharedReportResponse(BaseModel):
    """
    Strict zero-leakage read-only brief for verified home tutors and school teachers.
    Hides all subscriber credentials, family contacts, billing status, and sibling data.
    """
    is_valid: bool
    token_status: str  # ACTIVE, EXPIRED, REVOKED
    expires_at: datetime
    seconds_remaining: int
    time_remaining_display: str
    student_alias: str  # e.g. "Arun K." (first name + last initial only)
    standard_class: str
    board: str
    readiness_status: str
    status_rationale: str
    score_corridor: ScoreCorridorSchema
    subject_breakdown: Dict[str, SubjectReadinessDetailSchema]
    top_strengths: List[str]
    priority_remedial_gaps: List[str]
    pedagogical_notice: str = Field(
        default="This is an authorized, time-limited diagnostic brief generated by Studiqs SmartParent™. Subscriber identity, phone, and billing details are protected."
    )
