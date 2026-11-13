"""
STUDIQS® SmartParent™ (v6.2 Complete) - Section 7 Parent Actions, Gap Recheck & Handoff Schemas
=============================================================================
Defines Pydantic v2 type-safe schemas for Section 7:
1. Home Screen Action List (Strictly Max 3 Grounded Actions)
2. Diagnostic Gap Recheck Quiz & Resolution Workflow
3. Academic Handoff Brief for PTM / School Teachers / Home Tutors
=============================================================================
"""

import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ActionCardSchema(BaseModel):
    """Grounded Parent Action Card for the Home Screen / Cockpit."""
    model_config = ConfigDict(extra="ignore")

    action_id: str
    action_type: str = Field(..., description="'ASK_EXPERT', 'DIAGNOSTIC_RECHECK', 'PRACTICE', 'REVISION'")
    priority: str = Field(..., description="'HIGH', 'MEDIUM', 'ROUTINE'")
    title: str
    description: str
    subject: str
    topic_name: Optional[str] = None
    node_id: Optional[str] = None
    gap_id: Optional[str] = None
    action_url: Optional[str] = None
    is_completed: bool = False
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class ParentActionsListResponse(BaseModel):
    """
    Home screen action cockpit response.
    Enforces the non-negotiable Section 7 rule: strictly <= 3 actions!
    """
    model_config = ConfigDict(extra="ignore")

    child_id: str
    student_name: str
    actions: List[ActionCardSchema] = Field(
        default_factory=list,
        max_length=3,
        description="Strictly max 3 actions on Home screen to prevent cognitive overload"
    )
    total_actions_available: int = 0
    active_gaps_count: int = 0
    generated_at: str


class RecheckQuizQuestionSchema(BaseModel):
    """A targeted practice/recheck question for a curriculum gap."""
    model_config = ConfigDict(extra="ignore")

    question_id: str
    question_no: int
    question_text: str
    marks: float = 1.0
    options: Optional[List[str]] = None
    correct_answer: Optional[str] = None
    explanation: Optional[str] = None
    bloom_level: str = "Apply"


class RecheckQuizGenerateResponse(BaseModel):
    """5-Question Targeted Diagnostic Recheck Quiz generated for a weak topic."""
    model_config = ConfigDict(extra="ignore")

    quiz_id: str
    gap_id: str
    node_id: str
    topic_name: str
    subject: str
    standard_class: str
    total_questions: int = 5
    total_max_marks: float = 10.0
    questions: List[RecheckQuizQuestionSchema]
    passing_threshold_pct: float = 80.0
    instructions: str = "Score >= 80% to close this learning gap and mark it RESOLVED."


class RecheckQuizSubmitRequest(BaseModel):
    """Submission payload for targeted diagnostic recheck quiz."""
    model_config = ConfigDict(extra="ignore")

    child_id: uuid.UUID
    gap_id: uuid.UUID
    quiz_id: Optional[str] = None
    scored_marks: float = Field(..., ge=0.0)
    max_marks: float = Field(..., gt=0.0)
    recheck_title: str = Field(default="Diagnostic Gap Recheck Quiz")


class RecheckQuizSubmitResponse(BaseModel):
    """Result of recheck quiz evaluation with dynamic state transition."""
    model_config = ConfigDict(extra="ignore")

    gap_id: str
    node_id: str
    topic_name: str
    subject: str
    scored_marks: float
    max_marks: float
    score_percentage: float
    prior_score: float
    delta_percentage: float
    prior_status: str
    new_status: str  # ACTIVE or RESOLVED
    is_gap_closed: bool
    transition_narrative: str  # e.g. 'Needs Attention (<40%) → Mastered (>=80%)'
    pedagogical_badge: str
    evaluated_at: str


class StrengthItemSchema(BaseModel):
    """Confirmed subject/topic strength to celebrate."""
    model_config = ConfigDict(extra="ignore")

    subject: str
    topic_name: str
    mastery_percentage: float
    status: str = "Mastered"


class GapItemSchema(BaseModel):
    """Pinpointed topic gap requiring classroom/tuition attention."""
    model_config = ConfigDict(extra="ignore")

    subject: str
    chapter_name: str
    topic_name: str
    node_id: str
    current_percentage: float
    severity: str  # Critical (<40%) or Weak (40-59%)
    tutor_guidance: str


class AcademicHandoffBriefResponse(BaseModel):
    """
    Section 7 & 9: Diagnostic Academic Handoff Brief for PTM / School Teachers / Tutors.
    Bridges parent-teacher dialogue with precise diagnostic telemetry.
    """
    model_config = ConfigDict(extra="ignore")

    brief_id: str
    child_id: str
    student_name: str
    standard_class: str
    board: str
    academic_year: str
    praise_points: List[StrengthItemSchema] = Field(default_factory=list)
    remedial_gaps: List[GapItemSchema] = Field(default_factory=list)
    recommended_focus_next_2_weeks: str
    tutor_talking_points: List[str] = Field(default_factory=list)
    formatted_printable_text: str
    generated_at: str
