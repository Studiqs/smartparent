"""
STUDIQS® SmartParent™ - Question Paper Error Analysis Report Engine
=============================================================================
Module: src.smartparent.engines.section_03_qp_intelligence.error_analysis_report

Assembles actionable error reports for teacher review and algorithm optimization:
  1. Summary metrics on manual review requirements.
  2. Section-by-section extraction health scores.
  3. JSON and text summaries for ingestion logs.
=============================================================================
"""

import logging
from typing import Any, Dict, List
from src.smartparent.engines.section_00_core.base_engine import (
    BaseEngine,
    resilient_engine_step,
)

logger = logging.getLogger("STUDIQS_ErrorReport")


class ErrorAnalysisReportEngine(BaseEngine):
    """
    Compiles comprehensive extraction & mapping diagnostic audit summaries.
    """

    def __init__(self):
        super().__init__(name="ErrorAnalysisReportEngine")

    def pre_check(self, input_data: Any) -> bool:
        return isinstance(input_data, dict)

    def validate_input(self, input_data: Any) -> Dict[str, Any]:
        return input_data or {}

    @resilient_engine_step(engine_name="ErrorAnalysisReportEngine")
    def execute_core(self, data: Dict[str, Any]) -> Dict[str, Any]:
        total_questions = data.get("total_questions", 0)
        review_count = data.get("review_required_count", 0)
        mean_conf = data.get("mean_confidence", 0.0)

        health_rating = "EXCELLENT" if mean_conf >= 0.85 else ("GOOD" if mean_conf >= 0.70 else "NEEDS_ATTENTION")

        return {
            "health_rating": health_rating,
            "overall_mapping_confidence": mean_conf,
            "total_questions_processed": total_questions,
            "auto_confirmed_count": max(0, total_questions - review_count),
            "manual_review_count": review_count,
            "requires_human_triage": review_count > 0,
            "recommendation": (
                "Paper mapped cleanly. Ready for immediate parent diagnosis."
                if review_count == 0
                else f"{review_count} questions have low confidence and should be confirmed by parent/evaluator."
            ),
        }

    def post_process(self, result: Dict[str, Any]) -> Dict[str, Any]:
        return result

    def fallback(self, error: Exception, input_data: Any) -> Dict[str, Any]:
        return {
            "health_rating": "DEGRADED",
            "overall_mapping_confidence": 0.0,
            "total_questions_processed": 0,
            "requires_human_triage": True,
            "error": str(error),
        }
