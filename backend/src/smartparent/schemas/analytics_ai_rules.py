"""
STUDIQS® SmartParent™ (v6.2 Complete) - Section 17 Analytics, AI & Topic-Repository Rules Schemas
=============================================================================
Defines Pydantic v2 type-safe schemas for Section 17 (Working Specification v6.0 / v6.1):
1. Deterministic calculations (strictly server-owned math)
2. AI explains grounded changes only ("No new evidence means no fabricated change")
3. 'Subject Expert Feedback' vs 'AI Feedback' strict visual badging and origin separation
4. Immutable Source Provenance tracking for expert evaluations mapped into Student 360
5. Topic-Repository taxonomy & Gate 2 zero-fake mastery validation
=============================================================================
"""

import uuid
from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class FeedbackOriginEnum(str, Enum):
    """Source provenance origin for feedback and narratives."""
    HUMAN_EXPERT = "HUMAN_EXPERT"                    # Certified Subject Teacher
    AUTOMATED_AI_NARRATIVE = "AUTOMATED_AI_NARRATIVE"# Interpretive LLM / AI Engine
    DETERMINISTIC_RULE = "DETERMINISTIC_RULE"        # Pure Server-Calculated Metric


class MasteryTierEnum(str, Enum):
    """Deterministic mathematical topic mastery tiers."""
    STRONG = "STRONG"       # Score >= 80%
    AVERAGE = "AVERAGE"     # 60% <= Score < 80%
    WEAK = "WEAK"           # 40% <= Score < 60%
    CRITICAL = "CRITICAL"   # Score < 40%


class MovementDirectionEnum(str, Enum):
    """Longitudinal score trajectory delta direction."""
    IMPROVING = "IMPROVING" # Delta > +1.5%
    STABLE = "STABLE"       # -1.5% <= Delta <= +1.5%
    DECLINING = "DECLINING" # Delta < -1.5%


class DeterministicScorePoint(BaseModel):
    """A single raw evidence score point."""
    model_config = ConfigDict(extra="ignore")

    score: float = Field(..., ge=0.0)
    max_marks: float = Field(default=100.0, gt=0.0)
    test_date: Optional[str] = None


class DeterministicCalculationRequest(BaseModel):
    """Input payload for server-owned mathematical calculation."""
    model_config = ConfigDict(extra="ignore")

    subject: str
    scores: List[DeterministicScorePoint] = Field(..., min_length=1)


class DeterministicCalculationResponse(BaseModel):
    """
    Pure server-owned deterministic mathematical metrics.
    Guarantees zero math hallucination.
    """
    model_config = ConfigDict(extra="ignore")

    subject: str
    latest_score_pct: float
    prior_score_pct: Optional[float] = None
    movement_delta: float
    movement_direction: MovementDirectionEnum
    rolling_average_pct: float
    mastery_tier: MasteryTierEnum
    is_server_deterministic: bool = True
    calculated_at: str


class GroundedAiExplanationRequest(BaseModel):
    """Input payload for interpretive AI narrative generation."""
    model_config = ConfigDict(extra="ignore")

    student_name: str
    subject: str
    latest_score_pct: float
    prior_score_pct: Optional[float] = None
    movement_delta: float
    movement_direction: MovementDirectionEnum
    active_gaps: List[str] = Field(default_factory=list)
    has_new_evidence: bool = True
    language: str = Field(default="en", description="'en' or 'ta'")


class GroundedAiExplanationResponse(BaseModel):
    """
    AI pedagogical explanation grounded strictly in server-calculated deltas.
    Prevents fabricated changes when evidence is absent.
    """
    model_config = ConfigDict(extra="ignore")

    headline: str
    narrative_explanation: str
    feedback_badge: str
    feedback_origin: FeedbackOriginEnum = FeedbackOriginEnum.AUTOMATED_AI_NARRATIVE
    has_fabricated_change: bool = False
    generated_at: str


class ExpertProvenanceMetadata(BaseModel):
    """
    Immutable source provenance bundle for expert marks & feedback
    mapped into Student 360 Topic Intelligence.
    """
    model_config = ConfigDict(extra="ignore")

    expert_id: str
    evaluation_id: str
    completion_date: str
    evidence_type: str = "EXPERT_EVALUATION"
    marks_awarded: float
    total_max_marks: float
    percentage: float
    topic_node_ids: List[str] = Field(default_factory=list)
    audit_hash: str


class MapExpertEvaluationToIntelligenceRequest(BaseModel):
    """Payload to map a completed human expert evaluation into Student 360."""
    model_config = ConfigDict(extra="ignore")

    child_id: str
    evaluation_id: str
    expert_id: str
    subject: str
    marks_awarded: float
    total_max_marks: float = 100.0
    topic_ratings: Dict[str, float] = Field(default_factory=dict, description="node_id -> percentage (0-100)")
    expert_feedback_text: str
    completion_date: Optional[str] = None


class MapExpertEvaluationToIntelligenceResponse(BaseModel):
    """Result of mapping expert evaluation into Student 360 with full provenance."""
    model_config = ConfigDict(extra="ignore")

    success: bool
    child_id: str
    subject: str
    provenance: ExpertProvenanceMetadata
    updated_topic_scores_count: int
    resolved_gaps_count: int
    feedback_origin: FeedbackOriginEnum = FeedbackOriginEnum.HUMAN_EXPERT
    feedback_badge: str = "Subject Expert Feedback"
    intelligence_status: str


class TopicNodeValidationRequest(BaseModel):
    """Taxonomy validation request for a curriculum repository topic node."""
    model_config = ConfigDict(extra="ignore")

    node_id: str
    board: str
    standard_class: str
    subject: str
    chapter_name: str
    topic_name: str


class TopicNodeValidationResponse(BaseModel):
    """Curriculum topic repository validation result."""
    model_config = ConfigDict(extra="ignore")

    is_valid: bool
    canonical_node_id: str
    hierarchy_path: str
    validation_errors: List[str] = Field(default_factory=list)


class Gate2TopicIntelligenceCheckRequest(BaseModel):
    """Request to verify if an evidence type is permitted to unlock topic-level mastery."""
    model_config = ConfigDict(extra="ignore")

    evidence_type: str
    requested_topic_mastery: bool


class Gate2TopicIntelligenceCheckResponse(BaseModel):
    """Gate 2 Zero-Fake-Mastery enforcement result."""
    model_config = ConfigDict(extra="ignore")

    is_topic_intelligence_eligible: bool
    evidence_type: str
    status_code: str
    enforcement_message: str

