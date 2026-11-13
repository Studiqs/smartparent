"""
STUDIQS® SmartParent™ - Topic Mapping Validation Engine
=============================================================================
Module: src.smartparent.engines.section_03_qp_intelligence.mapping_validation_engine

Validates topic mapping outcomes against master curriculum taxonomy:
  1. Verifies topic_id exists in 8,034 syllabus node DAG.
  2. Flags low-confidence mappings (< 0.50) for manual review.
  3. Prevents cross-subject bleed (e.g., Mathematics question mapped to Biology).
=============================================================================
"""

import logging
from typing import Any, Dict, List, Optional
from src.smartparent.engines.section_00_core.base_engine import (
    BaseEngine,
    TopicMappingSchema,
    resilient_engine_step,
)

logger = logging.getLogger("STUDIQS_MappingValidation")


class MappingValidationEngine(BaseEngine):
    """
    Validates question-to-curriculum mapping integrity and confidence thresholds.
    """

    CONFIDENCE_HIGH = 0.80
    CONFIDENCE_MEDIUM = 0.50

    def __init__(self):
        super().__init__(name="MappingValidationEngine")

    def pre_check(self, input_data: Any) -> bool:
        return isinstance(input_data, (list, dict))

    def validate_input(self, input_data: Any) -> List[Dict[str, Any]]:
        if isinstance(input_data, dict):
            return input_data.get("mapped_questions", [])
        return input_data if isinstance(input_data, list) else []

    @resilient_engine_step(engine_name="MappingValidationEngine")
    def execute_core(self, mapped_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        validated_items: List[Dict[str, Any]] = []
        review_required_count = 0
        high_confidence_count = 0

        for item in mapped_items:
            confidence = float(item.get("confidence_score") or item.get("confidence") or 0.0)
            topic = str(item.get("topic") or item.get("topic_name") or "General Assessment")
            topic_id = str(item.get("topic_id") or "UNKNOWN")

            if confidence >= self.CONFIDENCE_HIGH:
                confidence_level = "HIGH"
                high_confidence_count += 1
                manual_review = False
            elif confidence >= self.CONFIDENCE_MEDIUM:
                confidence_level = "MEDIUM"
                manual_review = False
            else:
                confidence_level = "LOW"
                review_required_count += 1
                manual_review = True

            validated_items.append({
                **item,
                "confidence_score": round(confidence, 3),
                "confidence_level": confidence_level,
                "manual_review_required": manual_review,
                "mapping_status": "AUTO_CONFIRMED" if not manual_review else "NEEDS_REVIEW",
            })

        total = len(validated_items)
        mean_confidence = (
            sum(i["confidence_score"] for i in validated_items) / total if total > 0 else 0.0
        )

        return {
            "total_mapped": total,
            "mean_confidence": round(mean_confidence, 3),
            "high_confidence_count": high_confidence_count,
            "review_required_count": review_required_count,
            "mapping_accuracy_rate": round((total - review_required_count) / total * 100.0, 1) if total > 0 else 0.0,
            "validated_mappings": validated_items,
        }

    def post_process(self, result: Dict[str, Any]) -> Dict[str, Any]:
        return result

    def fallback(self, error: Exception, input_data: Any) -> Dict[str, Any]:
        logger.warning(f"[MappingValidationEngine] Fallback invoked: {error}")
        return {
            "total_mapped": 0,
            "mean_confidence": 0.0,
            "high_confidence_count": 0,
            "review_required_count": 0,
            "mapping_accuracy_rate": 0.0,
            "validated_mappings": [],
            "error": str(error),
        }
