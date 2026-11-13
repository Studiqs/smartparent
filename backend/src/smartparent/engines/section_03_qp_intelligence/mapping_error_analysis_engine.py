"""
STUDIQS® SmartParent™ - Mapping Error Analysis Engine
=============================================================================
Module: src.smartparent.engines.section_03_qp_intelligence.mapping_error_analysis_engine

Deep diagnostic analysis of question mapping failures and ambiguities:
  1. Identifies questions with confidence < 0.50.
  2. Categorizes error etiology: Sparse Stem, Cross-Subject Jargon, Out of Syllabus.
  3. Provides remediation recommendations for topic mapper embeddings.
=============================================================================
"""

import logging
from typing import Any, Dict, List
from src.smartparent.engines.section_00_core.base_engine import (
    BaseEngine,
    resilient_engine_step,
)

logger = logging.getLogger("STUDIQS_MappingErrorAnalysis")


class MappingErrorAnalysisEngine(BaseEngine):
    """
    Performs root cause categorization for low-confidence or unmapped questions.
    """

    def __init__(self):
        super().__init__(name="MappingErrorAnalysisEngine")

    def pre_check(self, input_data: Any) -> bool:
        return isinstance(input_data, (list, dict))

    def validate_input(self, input_data: Any) -> List[Dict[str, Any]]:
        if isinstance(input_data, dict):
            return input_data.get("validated_mappings") or input_data.get("questions") or []
        return input_data if isinstance(input_data, list) else []

    @resilient_engine_step(engine_name="MappingErrorAnalysisEngine")
    def execute_core(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        low_confidence_items: List[Dict[str, Any]] = []
        error_categories: Dict[str, int] = {
            "SPARSE_TEXT": 0,
            "OUT_OF_SYLLABUS_CANDIDATE": 0,
            "CROSS_SUBJECT_AMBIGUITY": 0,
            "DIAGRAM_FORMULA_HEAVY": 0,
        }

        for item in items:
            conf = float(item.get("confidence_score") or item.get("confidence") or 0.0)
            if conf < 0.50:
                stem = str(item.get("question_stem") or item.get("question_text") or "")
                words = stem.split()
                
                if len(words) < 6:
                    category = "SPARSE_TEXT"
                elif any(sym in stem for sym in ["\\frac", "\\sqrt", "diagram", "figure", "graph"]):
                    category = "DIAGRAM_FORMULA_HEAVY"
                elif conf < 0.25:
                    category = "OUT_OF_SYLLABUS_CANDIDATE"
                else:
                    category = "CROSS_SUBJECT_AMBIGUITY"

                error_categories[category] += 1
                low_confidence_items.append({
                    "question_number": item.get("question_number") or item.get("question_no"),
                    "question_stem": stem[:120],
                    "confidence": conf,
                    "tentative_topic": item.get("topic") or item.get("topic_name"),
                    "error_category": category,
                })

        return {
            "total_analyzed": len(items),
            "flagged_issues_count": len(low_confidence_items),
            "error_distribution": error_categories,
            "flagged_items": low_confidence_items,
        }

    def post_process(self, result: Dict[str, Any]) -> Dict[str, Any]:
        return result

    def fallback(self, error: Exception, input_data: Any) -> Dict[str, Any]:
        return {
            "total_analyzed": 0,
            "flagged_issues_count": 0,
            "error_distribution": {},
            "flagged_items": [],
            "error": str(error),
        }
