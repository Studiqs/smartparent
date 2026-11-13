"""
STUDIQS® SmartParent™ (v6.2 Complete) - Section 9 Parent Value & School/Tuition Handoff Schemas
=============================================================================
Defines Pydantic v2 type-safe schemas for Section 9 (Working Specification v6.0 / v6.1):
1. 'After Each Test': Instant marks/result update & baseline trajectory delta
2. 'When a Subject Needs Deeper Help': Persistent weakness diagnosis & expert evaluation trigger
3. 'Month End': Monthly Parent Pulse + Monthly Consolidated Report snapshot
4. 'Term End': Term-wise Consolidated Report & Consistency Rating
5. 'Year End': Final Yearly Consolidated Report & Permanent Archive
6. 'Next Academic Year': Prior Yearly Report Retention in history & Clean Baseline
7. 'PTM / Tuition': 1-Page Printable Brief, Misconception Patterns & WhatsApp Share
=============================================================================
"""

import uuid
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class PtmAudienceEnum(str, Enum):
    """Target recipient for the academic handoff brief."""
    TEACHER = "TEACHER"              # School Parent-Teacher Meeting (PTM)
    TUTOR = "TUTOR"                  # Private Home Tutor / Remedial Specialist
    COMPREHENSIVE = "COMPREHENSIVE"  # Dual-purpose Parent Reference Archive


class ParentValueMomentEnum(str, Enum):
    """The 7 Core Production Lifecycle Moments of Section 9."""
    AFTER_EACH_TEST = "AFTER_EACH_TEST"
    WHEN_SUBJECT_NEEDS_DEEPER_HELP = "WHEN_SUBJECT_NEEDS_DEEPER_HELP"
    MONTH_END = "MONTH_END"
    TERM_END = "TERM_END"
    YEAR_END = "YEAR_END"
    NEXT_ACADEMIC_YEAR = "NEXT_ACADEMIC_YEAR"
    PTM_TUITION = "PTM_TUITION"


# =============================================================================
# 1. AFTER EACH TEST SCHEMAS
# =============================================================================
class AfterEachTestSnapshotSchema(BaseModel):
    """Immediate post-test intelligence snapshot."""
    model_config = ConfigDict(extra="ignore")

    child_id: str
    test_id: Optional[str] = None
    subject: str
    test_title: str
    test_date: str
    score_percentage: float
    prior_score_percentage: Optional[float] = None
    delta_percentage: float = 0.0
    movement_badge: str
    confirmed_strengths_count: int = 0
    active_gaps_count: int = 0
    immediate_next_step: str
    timestamp: str


# =============================================================================
# 2. WHEN A SUBJECT NEEDS DEEPER HELP SCHEMAS
# =============================================================================
class DeeperHelpDiagnosticSchema(BaseModel):
    """Persistent weakness diagnosis and expert referral trigger."""
    model_config = ConfigDict(extra="ignore")

    child_id: str
    subject: str
    rolling_average_percentage: float
    is_persistent_weak: bool
    status_alert: str
    identified_weak_chapters: List[str] = Field(default_factory=list)
    critical_topic_gaps: List[str] = Field(default_factory=list)
    recommended_expert_action: str
    expert_marketplace_url: str
    expert_intake_brief: str
    timestamp: str


# =============================================================================
# 3. MONTH END SCHEMAS
# =============================================================================
class MonthEndDigestSchema(BaseModel):
    """Month-end learning cycle & consolidated report links."""
    model_config = ConfigDict(extra="ignore")

    child_id: str
    month_key: str
    has_parent_pulse: bool
    pulse_summary: Dict[str, str] = Field(default_factory=dict)
    monthly_report_available: bool
    monthly_report_pdf_url: Optional[str] = None
    unresolved_watchlist_count: int = 0
    timestamp: str


# =============================================================================
# 4. TERM END SCHEMAS
# =============================================================================
class TermEndReviewSchema(BaseModel):
    """Term-end multi-exam trajectory and consistency rating."""
    model_config = ConfigDict(extra="ignore")

    child_id: str
    term_name: str
    term_score_average: float
    term_consistency_rating: str
    term_syllabus_coverage_pct: float
    term_report_pdf_url: Optional[str] = None
    total_tests_in_term: int = 0
    timestamp: str


# =============================================================================
# 5. YEAR END SCHEMAS
# =============================================================================
class YearEndConsolidatedSchema(BaseModel):
    """Final Yearly Consolidated Report & permanent annual archive."""
    model_config = ConfigDict(extra="ignore")

    child_id: str
    academic_year: str
    annual_score_average: float
    overall_grade_tier: str
    total_tests_conducted: int = 0
    total_gaps_resolved: int = 0
    yearly_report_pdf_url: Optional[str] = None
    is_permanently_archived: bool = True
    timestamp: str


# =============================================================================
# 6. NEXT ACADEMIC YEAR SCHEMAS
# =============================================================================
class NextAcademicYearRolloverStatusSchema(BaseModel):
    """Next academic year transition: Only prior yearly report retained."""
    model_config = ConfigDict(extra="ignore")

    child_id: str
    previous_academic_year: str
    current_academic_year: str
    promoted_to_class: str
    prior_yearly_report_retained_in_history: bool = True
    intermediate_drafts_retired: bool = True
    fresh_diagnostic_baseline_ready: bool = True
    timestamp: str


# =============================================================================
# 7. PTM / TUITION SCHEMAS
# =============================================================================
class PtmExamTrajectoryItemSchema(BaseModel):
    """A historical exam data point on the student's trajectory."""
    model_config = ConfigDict(extra="ignore")

    test_title: str
    test_date: str
    score_percentage: float
    subject: str


class PtmSubjectTrendSchema(BaseModel):
    """Subject-wise longitudinal trajectory for the teacher/tutor."""
    model_config = ConfigDict(extra="ignore")

    subject: str
    current_percentage: float
    prior_percentage: Optional[float] = None
    delta_percentage: float = 0.0
    direction: str = Field(..., description="'IMPROVING', 'STABLE', 'DECLINING'")
    consistency_badge: str
    recent_exams: List[PtmExamTrajectoryItemSchema] = Field(default_factory=list)


class PtmStrugglingGapSchema(BaseModel):
    """Specific learning gap with concrete struggling question pattern."""
    model_config = ConfigDict(extra="ignore")

    subject: str
    chapter_name: str
    topic_name: str
    node_id: str
    current_percentage: float
    severity: str = Field(..., description="'CRITICAL' (<40%) or 'WEAK' (40-59%)")
    misconception_type: str
    struggling_question_example: str
    remedial_directive: str


class PtmPraisePointSchema(BaseModel):
    """Verified strength to celebrate ('Praise First')."""
    model_config = ConfigDict(extra="ignore")

    subject: str
    topic_name: str
    mastery_percentage: float
    status: str = Field(default="Mastered", description="'Mastered' (>=80%) or 'Solid' (70-79%)")
    celebration_narrative: str


class PtmPackResponse(BaseModel):
    """
    Section 9 Master PTM Prep Pack & Academic Handoff Brief.
    Arm parents with concrete diagnostic evidence to turn vague complaints
    into constructive, high-impact remedial dialogues.
    """
    model_config = ConfigDict(extra="ignore")

    brief_id: str
    child_id: str
    student_name: str
    standard_class: str
    board: str
    academic_year: str
    target_audience: PtmAudienceEnum = PtmAudienceEnum.TEACHER
    selected_subject: Optional[str] = None  # None indicates all subjects
    trends: List[PtmSubjectTrendSchema] = Field(default_factory=list)
    praise_points: List[PtmPraisePointSchema] = Field(default_factory=list)
    priority_gaps: List[PtmStrugglingGapSchema] = Field(default_factory=list)
    talking_points: List[str] = Field(default_factory=list)
    recommended_2_week_plan: str
    whatsapp_share_text: str
    formatted_printable_text: str
    generated_at: str


class WhatsAppShareResponse(BaseModel):
    """1-Click WhatsApp share payload for sending to teacher or tutor."""
    model_config = ConfigDict(extra="ignore")

    child_id: str
    student_name: str
    target_audience: PtmAudienceEnum
    whatsapp_text: str
    direct_whatsapp_url: str


# =============================================================================
# MASTER SECTION 9 RESPONSE (ALL 7 MOMENTS)
# =============================================================================
class Section9MasterValueLifecycleResponse(BaseModel):
    """Complete Section 9 Parent Value & School/Tuition Lifecycle."""
    model_config = ConfigDict(extra="ignore")

    child_id: str
    student_name: str
    standard_class: str
    board: str
    academic_year: str
    moments_summary: Dict[str, str] = Field(default_factory=dict)
    after_each_test: Optional[AfterEachTestSnapshotSchema] = None
    deeper_help: Optional[DeeperHelpDiagnosticSchema] = None
    month_end: Optional[MonthEndDigestSchema] = None
    term_end: Optional[TermEndReviewSchema] = None
    year_end: Optional[YearEndConsolidatedSchema] = None
    next_academic_year: Optional[NextAcademicYearRolloverStatusSchema] = None
    ptm_tuition: Optional[PtmPackResponse] = None
    generated_at: str
