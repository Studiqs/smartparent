"""
STUDIQS® SmartParent™ (v6.2 Complete) - Section 5 Performance & Consistency Schemas
=============================================================================
Defines Pydantic v2 type-safe schemas for Section 5:
1. Subject Monthly Consistency (e.g. Maths 72 → 78 → 81 | Improving)
2. Overall Monthly Movement (e.g. +4% vs last comparable result)
3. Term Consistency (Term 1 → Term 2 direction with sufficiency check)
4. Topic Movement (Needs Attention → Needs Practice → Mastered)
5. Gap Closure Lifecycle (e.g. 2 of 3 gaps improved / closed)
6. Expert Feedback Status (Submitted → Under Review → Completed)
=============================================================================
"""

import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class SubjectMonthlyConsistencySchema(BaseModel):
    """Subject Monthly Consistency Progression (e.g. Maths 72 → 78 → 81 | Improving)."""
    model_config = ConfigDict(extra="ignore")

    subject: str = Field(..., description="Subject name (e.g. Mathematics)")
    progression: List[float] = Field(default_factory=list, description="Chronological monthly percentages")
    months: List[str] = Field(default_factory=list, description="Month labels, e.g. ['2026-08', '2026-09', '2026-10']")
    current_percentage: float = Field(..., description="Latest month percentage")
    previous_percentage: Optional[float] = Field(default=None, description="Previous comparable month percentage")
    delta: float = Field(default=0.0, description="Percentage change from previous comparable month")
    trend_direction: str = Field(..., description="IMPROVING, DECLINING, STABLE, or FLUCTUATING")
    directional_symbol: str = Field(..., description="Arrow indicator: ↗, ↘, →, or ∿")
    consistency_tier: str = Field(..., description="Improving, Stable, Declining, or Fluctuating")
    display_narrative: str = Field(..., description="Formatted string: Maths 72 → 78 → 81 | Improving")
    tests_count: int = Field(default=0, description="Number of confirmed assessments evaluated")


class OverallMonthlyMovementSchema(BaseModel):
    """
    Overall Monthly Movement (+4% vs last comparable result).
    Strict Rule: Never silently compare incompatible evidence!
    """
    model_config = ConfigDict(extra="ignore")

    current_month: str = Field(..., description="Current evaluated month, e.g. '2026-10'")
    prior_month: Optional[str] = Field(default=None, description="Prior comparison month, e.g. '2026-09'")
    current_mean: float = Field(..., description="Current month weighted/mean percentage")
    prior_mean: Optional[float] = Field(default=None, description="Prior month comparable mean percentage")
    movement_percentage: float = Field(default=0.0, description="Percentage movement (+/- %)")
    movement_symbol: str = Field(default="→", description="Arrow or prefix, e.g. +4.0%")
    display_badge: str = Field(..., description="e.g. '+4% vs last comparable result'")
    is_comparable: bool = Field(default=True, description="False if evidence scopes or subjects are incompatible")
    compatibility_note: Optional[str] = Field(
        default=None,
        description="Reason if evidence cannot be compared (e.g. 'Only disjoint subjects available')"
    )


class TermConsistencySchema(BaseModel):
    """
    Term Consistency (Term 1 → Term 2 direction).
    Rule: Only with sufficient evidence (>= 2 assessments per term or major term exam).
    """
    model_config = ConfigDict(extra="ignore")

    terms_evaluated: List[str] = Field(default_factory=list, description="Evaluated terms, e.g. ['Term 1', 'Term 2']")
    term_scores: Dict[str, float] = Field(default_factory=dict, description="Term averages, e.g. {'Term 1': 74.0, 'Term 2': 80.0}")
    has_sufficient_evidence: bool = Field(..., description="Whether minimum evidence threshold was met")
    term_direction: str = Field(..., description="IMPROVING, DECLINING, STABLE, or INSUFFICIENT_EVIDENCE")
    display_narrative: str = Field(..., description="e.g. 'Term 1 (74%) → Term 2 (80%) | Improving'")
    evidence_breakdown: Dict[str, int] = Field(default_factory=dict, description="Test count per term")


class TopicMovementSchema(BaseModel):
    """
    Topic Movement (Needs Attention → Needs Practice → Mastered).
    Rule: Topic-level evidence required. Aggregate marks alone never create fake mastery.
    """
    model_config = ConfigDict(extra="ignore")

    node_id: str
    topic_name: str
    subject: str
    previous_tier: Optional[str] = None  # Critical, Weak, Average, Strong
    current_tier: str                    # Critical, Weak, Average, Strong
    previous_score: Optional[float] = None
    current_score: float
    movement_label: str  # e.g. 'Needs Attention → Needs Practice'
    is_improved: bool = False


class GapClosureSummarySchema(BaseModel):
    """
    Gap Closure Tracking (e.g. 2 of 3 gaps improved / closed).
    Rule: Actual recheck/new evidence only.
    """
    model_config = ConfigDict(extra="ignore")

    total_identified_gaps: int = 0
    active_gaps_count: int = 0
    in_recheck_count: int = 0
    resolved_gaps_count: int = 0
    closure_rate_percent: float = 0.0
    display_badge: str = Field(..., description="e.g. '2 of 3 gaps improved / closed (66.7%)'")
    active_gaps: List[Dict[str, Any]] = Field(default_factory=list)
    recently_closed_gaps: List[Dict[str, Any]] = Field(default_factory=list)


class ExpertFeedbackStatusSchema(BaseModel):
    """
    Expert Feedback Status (Submitted → Under Review → Completed).
    Rule: Only assigned expert can evaluate. Completed feedback integrates as confirmed evidence.
    """
    model_config = ConfigDict(extra="ignore")

    case_id: str
    subject: str
    test_title: str
    expert_name: str = "Subject Expert"
    case_status: str  # ASSIGNED, AWAITING_UPLOAD, SUBMITTED, UNDER_REVIEW, COMPLETED, DISPUTED
    submitted_at: Optional[str] = None
    completed_at: Optional[str] = None
    sla_hours_remaining: Optional[float] = None  # 48h SLA countdown
    is_sla_breached: bool = False
    is_confirmed_evidence: bool = False
    evaluated_pdf_path: Optional[str] = None
    expert_feedback_summary: Optional[str] = None


class GapRecheckRequestSchema(BaseModel):
    """Request payload to record a diagnostic recheck for a specific topic gap."""
    model_config = ConfigDict(extra="ignore")

    child_id: uuid.UUID
    gap_id: uuid.UUID
    recheck_scored_marks: float = Field(..., ge=0.0)
    recheck_max_marks: float = Field(..., gt=0.0)
    recheck_title: str = Field(default="Diagnostic Gap Recheck")
    test_date: Optional[date] = None


class GapRecheckResponseSchema(BaseModel):
    """Result of a diagnostic gap recheck evaluation."""
    model_config = ConfigDict(extra="ignore")

    gap_id: str
    node_id: str
    topic_name: str
    subject: str
    prior_score: float
    recheck_score: float
    delta: float
    prior_status: str
    new_status: str  # ACTIVE or RESOLVED
    is_gap_closed: bool
    transition_narrative: str
    evaluated_at: str


class Section5PerformanceResponse(BaseModel):
    """Complete Section 5 Performance & Consistency Intelligence Response."""
    model_config = ConfigDict(extra="ignore")

    child_id: str
    student_name: str
    standard_class: str
    academic_year: str
    overall_monthly_movement: OverallMonthlyMovementSchema
    subject_consistencies: List[SubjectMonthlyConsistencySchema] = Field(default_factory=list)
    term_consistency: TermConsistencySchema
    topic_movements: List[TopicMovementSchema] = Field(default_factory=list)
    gap_closure_summary: GapClosureSummarySchema
    expert_feedback_cases: List[ExpertFeedbackStatusSchema] = Field(default_factory=list)
    generated_at: str
