"""
STUDIQS® SmartParent™ - Curriculum Repository Gap Report Engine
=============================================================================
Module: src.smartparent.engines.section_03_qp_intelligence.repository_gap_report

Monitors and detects gaps in the 8,034-topic curriculum repository:
  1. Identifies novel concepts extracted from real test papers.
  2. Aggregates unmapped clusters to highlight syllabus additions.
=============================================================================
"""

import logging
from typing import Any, Dict, List
from src.smartparent.engines.section_00_core.base_engine import (
    BaseEngine,
    resilient_engine_step,
)

logger = logging.getLogger("STUDIQS_RepoGapReport")


class RepositoryGapReportEngine(BaseEngine):
    """
    Detects potential missing topics or coverage holes in curriculum taxonomy.
    """

    def __init__(self):
        super().__init__(name="RepositoryGapReportEngine")

    def pre_check(self, input_data: Any) -> bool:
        return isinstance(input_data, dict)

    def validate_input(self, input_data: Any) -> Dict[str, Any]:
        return input_data or {}

    @resilient_engine_step(engine_name="RepositoryGapReportEngine")
    def execute_core(self, data: Dict[str, Any]) -> Dict[str, Any]:
        unmapped_items = data.get("unmapped_questions", [])
        subject = data.get("subject", "General")

        candidate_gaps: List[Dict[str, Any]] = []
        for q in unmapped_items:
            candidate_gaps.append({
                "question_stem": str(q.get("question_stem", ""))[:100],
                "subject": subject,
                "confidence": float(q.get("confidence", 0.0)),
                "suggested_action": "EXPAND_CURRICULUM_SYNONYM",
            })

        return {
            "subject": subject,
            "detected_gap_candidates_count": len(candidate_gaps),
            "candidates": candidate_gaps,
        }

    def post_process(self, result: Dict[str, Any]) -> Dict[str, Any]:
        return result

    def fallback(self, error: Exception, input_data: Any) -> Dict[str, Any]:
        return {"subject": "Unknown", "detected_gap_candidates_count": 0, "candidates": [], "error": str(error)}
