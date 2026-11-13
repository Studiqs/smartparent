"""
STUDIQS® SmartParent™ (v6.3 Complete) - Diagnostic Intelligence Schemas
=============================================================================
Module: src.smartparent.schemas.diagnostic

Pydantic v2 schemas for Child Topic Mastery Scores, Learning Gap Watchlist,
and Student 360 Diagnostic Profiles.
=============================================================================
"""

import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class TopicScoreItemSchema(BaseModel):
    """Granular topic score and mastery status."""
    model_config = ConfigDict(from_attributes=True)

    score_id: uuid.UUID
    node_id: str
    topic_name: str
    chapter_name: str
    subject: str
    scored_marks: float
    max_marks: float
    percentage: float
    mastery_tier: str = Field(..., description="'STRONG', 'AVERAGE', 'WEAK', 'CRITICAL'")
    evaluated_at: datetime


class TopicGapItemSchema(BaseModel):
    """Learning gap in active monitoring watchlist."""
    model_config = ConfigDict(from_attributes=True)

    gap_id: uuid.UUID
    node_id: str
    topic_name: str
    chapter_name: str
    subject: str
    gap_status: str = Field(..., description="'ACTIVE', 'IN_RECHECK', 'RESOLVED'")
    first_identified_at: datetime
    resolved_at: Optional[datetime] = None


class StudentDiagnosticSummaryResponse(BaseModel):
    """Holistic Student 360 diagnostic overview."""
    child_id: uuid.UUID
    student_name: str
    standard_class: str
    board: str
    academic_year: str
    overall_mastery_percentage: float
    total_evaluated_topics: int
    strong_topics_count: int
    average_topics_count: int
    weak_topics_count: int
    critical_topics_count: int
    active_gaps_count: int
    recent_scores: List[TopicScoreItemSchema]
    critical_gaps: List[TopicGapItemSchema]


class ResolveGapRequest(BaseModel):
    """Request to resolve or update a learning gap status."""
    gap_status: str = Field(..., pattern="^(ACTIVE|IN_RECHECK|RESOLVED)$", description="New gap status")
    notes: Optional[str] = Field(None, max_length=500, description="Optional remediation notes")


class ResolveGapResponse(BaseModel):
    """Result of gap resolution."""
    gap_id: uuid.UUID
    child_id: uuid.UUID
    node_id: str
    new_status: str
    resolved_at: Optional[datetime] = None
    message: str

