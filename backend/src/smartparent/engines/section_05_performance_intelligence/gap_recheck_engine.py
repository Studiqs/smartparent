"""
STUDIQS® SmartParent™ (v6.2 Complete) - Diagnostic Gap Recheck Engine
=============================================================================
Engine: gap_recheck_engine.py (Section 5 & Section 7)
Rule: Actual recheck/new evidence only!
Evaluates whether remedial learning, teacher feedback, or home revision
successfully resolved a historical topic gap.
When student scores >= 80% on recheck, gap transitions from ACTIVE to RESOLVED.
=============================================================================
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field

from src.smartparent.engines.base_engine import BaseEngine, EngineHealthStatus

logger = logging.getLogger("STUDIQS_GapRecheckEngine")

# Non-negotiable mastery threshold to resolve a persistent gap (Section 5 & 7)
GAP_RESOLUTION_THRESHOLD_PCT: float = 80.0


class GapRecheckInputSchema(BaseModel):
    """Input payload for a diagnostic gap recheck evaluation."""
    model_config = ConfigDict(extra="ignore")

    gap_id: str
    node_id: str
    topic_name: str
    subject: str = "General"
    scored_marks: float = Field(..., ge=0.0)
    max_marks: float = Field(..., gt=0.0)
    prior_score_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    prior_status: str = Field(default="ACTIVE")


class GapRecheckResultSchema(BaseModel):
    """Outcome of a diagnostic gap recheck."""
    model_config = ConfigDict(extra="ignore")

    gap_id: str
    node_id: str
    topic_name: str
    subject: str
    prior_score_pct: float
    recheck_score_pct: float
    delta_pct: float
    prior_status: str
    new_status: str  # ACTIVE or RESOLVED
    is_gap_closed: bool
    transition_narrative: str
    pedagogical_badge: str
    evaluated_at: str


class GapRecheckEngine(BaseEngine):
    """
    Engine: Diagnostic Gap Recheck Engine (gap_recheck_engine.py)
    
    Verifies gap closure using confirmed recheck evidence:
    - Normalizes (scored / max) * 100
    - If score >= 80.0%: Gap status becomes RESOLVED (closure verified).
    - If score < 80.0%: Gap remains ACTIVE; improvement delta is tracked.
    - Produces grounded transition narratives (e.g. 'Needs Attention → Needs Practice').
    """

    def __init__(self, failure_threshold: int = 5):
        super().__init__(name="GapRecheckEngine", failure_threshold=failure_threshold)

    def validate_input(self, input_data: Any) -> Dict[str, Any]:
        """Validates recheck input payload against GapRecheckInputSchema."""
        if not input_data:
            raise ValueError("Gap recheck input payload cannot be empty.")

        if hasattr(input_data, "model_dump"):
            data = input_data.model_dump()
        elif hasattr(input_data, "dict"):
            data = input_data.dict()
        elif isinstance(input_data, dict):
            data = dict(input_data)
        else:
            raise ValueError(f"Unsupported payload type for GapRecheckEngine: {type(input_data)}")

        schema = GapRecheckInputSchema(**data)
        return schema.model_dump()

    def execute_core(self, validated_data: Dict[str, Any]) -> GapRecheckResultSchema:
        """Executes core recheck thresholding and pedagogical tier transition."""
        scored = float(validated_data["scored_marks"])
        max_m = float(validated_data["max_marks"])
        recheck_pct = round((scored / max_m) * 100.0, 1)

        prior_pct = round(float(validated_data.get("prior_score_pct", 0.0)), 1)
        delta = round(recheck_pct - prior_pct, 1)
        prior_status = validated_data.get("prior_status", "ACTIVE")

        # Map tiers
        def _get_tier_name(pct: float) -> str:
            if pct >= 80.0:
                return "Mastered"
            elif pct >= 60.0:
                return "Foundational"
            elif pct >= 40.0:
                return "Needs Practice"
            else:
                return "Needs Attention"

        prior_tier = _get_tier_name(prior_pct)
        new_tier = _get_tier_name(recheck_pct)

        is_closed = recheck_pct >= GAP_RESOLUTION_THRESHOLD_PCT
        new_status = "RESOLVED" if is_closed else "ACTIVE"

        if is_closed:
            narrative = f"{prior_tier} → {new_tier} (Gap Successfully Closed at {recheck_pct}%)"
            badge = "RESOLVED"
        elif delta > 5.0:
            narrative = f"{prior_tier} → {new_tier} (+{delta}% improvement; further revision recommended)"
            badge = "IMPROVING"
        elif delta < -5.0:
            narrative = f"{prior_tier} → {new_tier} ({delta}% decline; urgent intervention needed)"
            badge = "NEEDS_ATTENTION"
        else:
            narrative = f"{prior_tier} → {new_tier} (Stable at {recheck_pct}%)"
            badge = "STABLE"

        return GapRecheckResultSchema(
            gap_id=str(validated_data["gap_id"]),
            node_id=str(validated_data["node_id"]),
            topic_name=str(validated_data["topic_name"]),
            subject=str(validated_data.get("subject", "General")),
            prior_score_pct=prior_pct,
            recheck_score_pct=recheck_pct,
            delta_pct=delta,
            prior_status=prior_status,
            new_status=new_status,
            is_gap_closed=is_closed,
            transition_narrative=narrative,
            pedagogical_badge=badge,
            evaluated_at=datetime.utcnow().isoformat(),
        )

    def fallback(self, error: Exception, input_data: Any) -> GapRecheckResultSchema:
        """Safe fallback keeping gap ACTIVE to avoid false positive closure."""
        logger.warning(f"[GapRecheckEngine] Fallback triggered due to error: {error}")
        gap_id = "UNKNOWN"
        node_id = "UNKNOWN"
        topic_name = "Topic"
        subject = "General"

        if isinstance(input_data, dict):
            gap_id = str(input_data.get("gap_id", "UNKNOWN"))
            node_id = str(input_data.get("node_id", "UNKNOWN"))
            topic_name = str(input_data.get("topic_name", "Topic"))
            subject = str(input_data.get("subject", "General"))

        return GapRecheckResultSchema(
            gap_id=gap_id,
            node_id=node_id,
            topic_name=topic_name,
            subject=subject,
            prior_score_pct=0.0,
            recheck_score_pct=0.0,
            delta_pct=0.0,
            prior_status="ACTIVE",
            new_status="ACTIVE",
            is_gap_closed=False,
            transition_narrative="Recheck processing delayed; gap retained on active watchlist.",
            pedagogical_badge="FALLBACK",
            evaluated_at=datetime.utcnow().isoformat(),
        )
