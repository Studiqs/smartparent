"""
STUDIQS® SmartParent™ (v6.2 Complete) - Section 6 Parent Pulse & Learning Cycle Schemas
=============================================================================
Defines Pydantic v2 type-safe schemas for Section 6:
1. Monthly Parent Pulse: 1 Improvement + 1 Watch Area + 1 Next Action
2. Monthly Action List: Max 3 Grounded Actions
3. Progress Since Last Update: What changed
4. 30-Day Closed-Loop Learning Cycle Response
=============================================================================
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class PulseCardSchema(BaseModel):
    """Individual Parent Pulse Card (Improvement, Watch Area, or Action)."""
    model_config = ConfigDict(extra="ignore")

    card_type: str = Field(..., description="'IMPROVEMENT', 'WATCH_AREA', or 'NEXT_ACTION'")
    title: str
    headline: str
    description: str
    metric_badge: Optional[str] = None
    subject: Optional[str] = None
    priority_level: str = "NORMAL"  # 'NORMAL', 'HIGH', 'URGENT'
    color_theme: str = Field(..., description="'GREEN', 'AMBER', or 'BLUE'")


class GroundedActionItemSchema(BaseModel):
    """One of the maximum 3 grounded parent actions for the active month."""
    model_config = ConfigDict(extra="ignore")

    action_id: str
    action_type: str = Field(..., description="'REVISION', 'PRACTICE', 'DIAGNOSTIC_RECHECK', 'ASK_EXPERT'")
    title: str
    description: str
    subject: str
    topic_name: Optional[str] = None
    is_completed: bool = False
    action_url: Optional[str] = None  # e.g., '/marketplace/experts?subject=Mathematics'


class ProgressSinceLastUpdateSchema(BaseModel):
    """
    Progress Since Last Update (What Changed):
    Tracks movement delta, new assessments logged, and gaps closed.
    """
    model_config = ConfigDict(extra="ignore")

    prior_period: Optional[str] = None
    current_period: str
    overall_movement_delta: float = 0.0
    movement_direction: str = "STABLE"  # 'IMPROVING', 'DECLINING', 'STABLE'
    new_evidence_count: int = 0
    gaps_closed_count: int = 0
    active_gaps_count: int = 0
    has_meaningful_change: bool = False
    narrative_summary: str = Field(..., description="Summary of changes since last month")


class MonthlyParentPulseResponse(BaseModel):
    """
    Section 6: Complete 30-Day Closed-Loop Monthly Learning Cycle Response.
    Enforces 'No new evidence = no fabricated change'.
    """
    model_config = ConfigDict(extra="ignore")

    pulse_id: str
    child_id: str
    student_name: str
    standard_class: str
    month_key: str  # 'YYYY-MM'
    pulse_period: str  # 'October 2026'
    overall_health_indicator: str  # 'EXCELLENT', 'PROGRESSING', 'ATTENTION_NEEDED'
    improvement_area: PulseCardSchema
    watch_area: PulseCardSchema
    next_immediate_action: PulseCardSchema
    grounded_actions: List[GroundedActionItemSchema] = Field(
        default_factory=list,
        max_length=3,
        description="Strictly no more than 3 grounded actions on Home screen"
    )
    progress_since_last_update: ProgressSinceLastUpdateSchema
    is_fabricated: bool = False
    evidence_status: str = "CONFIRMED_EVIDENCE_PRESENT"
    generated_at: str


class GeneratePulseRequest(BaseModel):
    """Request payload to synthesize or retrieve monthly parent pulse."""
    model_config = ConfigDict(extra="ignore")

    child_id: uuid.UUID
    month_key: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "2026-10"},
        description="Target month (defaults to current month YYYY-MM)"
    )
    force_refresh: bool = Field(
        default=False,
        description="If False, respects 'no new evidence = no fabricated change'"
    )
