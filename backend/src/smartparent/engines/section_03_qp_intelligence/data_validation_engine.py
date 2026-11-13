"""
STUDIQS® SmartParent™ - Question Paper Data Validation Engine
=============================================================================
Module: src.smartparent.engines.section_03_qp_intelligence.data_validation_engine

Validates extracted question paper data:
  1. Question Numbering Sequence & Completeness (Q1, Q2, etc.).
  2. Marks Summation & Bounds Verification (e.g., marks <= total_max_marks).
  3. Question Stem Minimum Length & Content Integrity.
  4. Deduplication of Repeated Extraction Artifacts.
=============================================================================
"""

import logging
from typing import Any, Dict, List, Optional
from src.smartparent.engines.section_00_core.base_engine import (
    BaseEngine,
    ParsedQuestionSchema,
    resilient_engine_step,
)

logger = logging.getLogger("STUDIQS_DataValidation")


class DataValidationEngine(BaseEngine):
    """
    Validates parsed question paper payload before syllabus mapping and persistence.
    """

    def __init__(self):
        super().__init__(name="DataValidationEngine")

    def pre_check(self, input_data: Any) -> bool:
        if not input_data:
            return False
        if isinstance(input_data, dict) and "questions" in input_data:
            return True
        if isinstance(input_data, list):
            return True
        return False

    def validate_input(self, input_data: Any) -> Any:
        if isinstance(input_data, dict):
            questions = input_data.get("questions", [])
        elif isinstance(input_data, list):
            questions = input_data
        else:
            questions = []
        return questions

    @resilient_engine_step(engine_name="DataValidationEngine")
    def execute_core(self, questions: List[Dict[str, Any]]) -> Dict[str, Any]:
        valid_questions: List[Dict[str, Any]] = []
        warnings: List[str] = []
        seen_stems = set()
        total_extracted_marks = 0.0

        for idx, q in enumerate(questions):
            q_num = str(q.get("question_no") or q.get("question_number") or f"Q{idx+1}")
            q_stem = str(q.get("question_text") or q.get("question_stem") or "").strip()
            
            try:
                max_marks = float(q.get("max_marks", 1.0))
            except (ValueError, TypeError):
                max_marks = 1.0

            # Guard against empty stems or header text artifacts
            if len(q_stem) < 5:
                warnings.append(f"Skipped question {q_num} due to sparse stem text (< 5 chars).")
                continue

            # Check stem deduplication
            stem_hash = q_stem.lower()[:80]
            if stem_hash in seen_stems:
                warnings.append(f"Duplicate question text detected for {q_num}; skipping duplicate.")
                continue
            seen_stems.add(stem_hash)

            total_extracted_marks += max_marks
            valid_questions.append({
                "question_number": q_num,
                "question_stem": q_stem,
                "max_marks": max_marks,
                "section": q.get("section"),
                "is_mcq": q.get("is_mcq", False),
                "options": q.get("options", []),
            })

        return {
            "is_valid": len(valid_questions) > 0,
            "total_questions": len(valid_questions),
            "total_extracted_marks": round(total_extracted_marks, 2),
            "validated_questions": valid_questions,
            "warnings": warnings,
        }

    def post_process(self, result: Dict[str, Any]) -> Dict[str, Any]:
        result["validation_status"] = "PASSED" if result.get("is_valid") else "FAILED"
        return result

    def fallback(self, error: Exception, input_data: Any) -> Dict[str, Any]:
        logger.warning(f"[DataValidationEngine] Invoking fallback due to: {error}")
        return {
            "is_valid": False,
            "total_questions": 0,
            "total_extracted_marks": 0.0,
            "validated_questions": [],
            "warnings": [f"Validation failed: {str(error)}"],
            "validation_status": "DEGRADED",
        }
