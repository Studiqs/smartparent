"""
STUDIQS® SmartParent™ (v6.2 Complete) - Quick Marks Engine
=============================================================================
Fast Aggregate Evidence Intake (Section 3: Zero-Friction Data Feed)
Pedagogical Rule (Section 5):
"Aggregate marks alone never create fake topic mastery.
 Topic-level evidence required for topic movement."
=============================================================================
"""

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, model_validator, ConfigDict

logger = logging.getLogger("STUDIQS_QuickMarks")


# =============================================================================
# 1. Pydantic Type-Safe Schemas for Quick Marks
# =============================================================================

class SubjectMarkInput(BaseModel):
    """Input payload for a single subject mark."""
    model_config = ConfigDict(extra="ignore")

    subject: str = Field(..., min_length=1, description="Official curriculum subject name")
    marks_obtained: float = Field(..., ge=0.0, description="Marks scored by the student")
    max_marks: float = Field(..., gt=0.0, description="Maximum total marks for the test")

    @model_validator(mode="after")
    def validate_marks_within_max(self) -> "SubjectMarkInput":
        if self.marks_obtained > self.max_marks:
            raise ValueError(f"Marks obtained ({self.marks_obtained}) cannot exceed maximum marks ({self.max_marks})")
        return self


class QuickMarksBatchInput(BaseModel):
    """Input payload for a complete test/exam quick marks entry."""
    model_config = ConfigDict(extra="ignore")

    student_id: str = Field(..., min_length=1, description="Unique child/student identifier")
    test_title: str = Field(..., min_length=1, description="Title of the assessment (e.g. Unit Test 1)")
    test_date: Union[date, str] = Field(default_factory=date.today, description="Date of the test")
    subjects: List[SubjectMarkInput] = Field(..., min_length=1, description="List of subject marks")
    grade: Optional[str] = None
    board: Optional[str] = None


class SubjectTelemetry(BaseModel):
    """Processed diagnostic telemetry for a single subject."""
    subject: str
    marks_obtained: float
    max_marks: float
    score_percent: float
    score_band: str
    band_code: int
    movement_delta: Optional[float] = None
    consistency_direction: str  # "Improving", "Stable", "Declining", "Baseline"
    movement_label: str


class QuickMarksResult(BaseModel):
    """Output contract produced by the Quick Marks Engine."""
    student_id: str
    test_title: str
    test_date: str
    total_marks_obtained: float
    total_max_marks: float
    overall_percentage: float
    overall_score_band: str
    overall_band_code: int
    overall_movement_delta: Optional[float] = None
    overall_movement_label: str
    subject_count: int
    subjects_telemetry: List[SubjectTelemetry]

    # Non-Negotiable Gate 2 Zero-Hallucination Integrity Guardrails
    evidence_type: str = "QUICK_MARKS"
    is_topic_intelligence_eligible: bool = False
    topic_intelligence_status: str = "LOCKED_AGGREGATE_ONLY"
    guardrail_note: str = "Aggregate marks alone never create fake topic mastery. Upload question paper for line-item topic diagnostics."


# =============================================================================
# 2. QuickMarksEngine Implementation
# =============================================================================

class QuickMarksEngine:
    """
    Production-Grade Quick Marks Processing Engine.
    Converts raw subject marks into diagnostic movement and consistency slopes
    while strictly refusing to synthesize fake topic mastery.
    """

    def __init__(self):
        logger.info("[QuickMarksEngine] Initialized with Zero Fake Topic Mastery guardrails.")

    @staticmethod
    def get_score_band(score_percent: float) -> tuple[str, int]:
        """
        Maps score percentage to canonical SmartParent 4-tier score bands:
          Band 1 (Strong):   80.0% - 100.0%
          Band 2 (Average):  60.0% - 79.99%
          Band 3 (Weak):     40.0% - 59.99%
          Band 4 (Critical): 0.0%  - 39.99%
        """
        pct = round(score_percent, 2)
        if pct >= 80.0:
            return "Band 1: Strong", 1
        elif pct >= 60.0:
            return "Band 2: Average", 2
        elif pct >= 40.0:
            return "Band 3: Weak", 3
        else:
            return "Band 4: Critical", 4

    @staticmethod
    def calculate_consistency_slope(
        current_pct: float,
        previous_pct: Optional[float]
    ) -> tuple[Optional[float], str, str]:
        """
        Calculates month-on-month trajectory slope:
          delta >= +2.0% -> "Improving"
          -2.0% <= delta <= +2.0% -> "Stable"
          delta < -2.0% -> "Declining"
        """
        if previous_pct is None:
            return None, "Baseline", "Baseline assessment (No previous comparable record)"

        delta = round(current_pct - previous_pct, 2)
        if delta >= 2.0:
            direction = "Improving"
            label = f"+{delta:.1f}% vs last test (Improving)"
        elif delta <= -2.0:
            direction = "Declining"
            label = f"{delta:.1f}% vs last test (Declining)"
        else:
            direction = "Stable"
            sign = "+" if delta > 0 else ""
            label = f"{sign}{delta:.1f}% vs last test (Stable)"

        return delta, direction, label

    def process(
        self,
        batch_input: Union[QuickMarksBatchInput, Dict[str, Any]],
        historical_subject_averages: Optional[Dict[str, float]] = None,
        previous_overall_percentage: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Processes a quick marks intake payload.
        Args:
            batch_input: Pydantic schema or dict containing student test marks.
            historical_subject_averages: Dict mapping subject -> previous comparable % score.
            previous_overall_percentage: Float representing previous overall test % score.
        Returns:
            Structured dictionary compliant with QuickMarksResult schema.
        """
        if isinstance(batch_input, dict):
            validated_batch = QuickMarksBatchInput(**batch_input)
        else:
            validated_batch = batch_input

        history = historical_subject_averages or {}
        subject_telemetry_list: List[SubjectTelemetry] = []
        total_obtained = 0.0
        total_max = 0.0

        for item in validated_batch.subjects:
            obtained = float(item.marks_obtained)
            max_m = float(item.max_marks)
            pct = round((obtained / max_m) * 100.0, 2)

            total_obtained += obtained
            total_max += max_m

            band_name, band_code = self.get_score_band(pct)
            prev_pct = history.get(item.subject)
            delta, direction, mov_label = self.calculate_consistency_slope(pct, prev_pct)

            telemetry = SubjectTelemetry(
                subject=item.subject,
                marks_obtained=obtained,
                max_marks=max_m,
                score_percent=pct,
                score_band=band_name,
                band_code=band_code,
                movement_delta=delta,
                consistency_direction=direction,
                movement_label=mov_label
            )
            subject_telemetry_list.append(telemetry)

        # Overall aggregate calculations
        overall_pct = round((total_obtained / total_max) * 100.0, 2) if total_max > 0 else 0.0
        ov_band_name, ov_band_code = self.get_score_band(overall_pct)
        ov_delta, _, ov_mov_label = self.calculate_consistency_slope(overall_pct, previous_overall_percentage)

        # Ensure date string
        t_date = validated_batch.test_date
        t_date_str = t_date.isoformat() if isinstance(t_date, (date, datetime)) else str(t_date)

        result = QuickMarksResult(
            student_id=validated_batch.student_id,
            test_title=validated_batch.test_title,
            test_date=t_date_str,
            total_marks_obtained=round(total_obtained, 2),
            total_max_marks=round(total_max, 2),
            overall_percentage=overall_pct,
            overall_score_band=ov_band_name,
            overall_band_code=ov_band_code,
            overall_movement_delta=ov_delta,
            overall_movement_label=ov_mov_label,
            subject_count=len(subject_telemetry_list),
            subjects_telemetry=subject_telemetry_list
        )

        return result.model_dump()

    def execute_core(
        self,
        batch_input: Union[QuickMarksBatchInput, Dict[str, Any]],
        historical_subject_averages: Optional[Dict[str, float]] = None,
        previous_overall_percentage: Optional[float] = None
    ) -> QuickMarksResult:
        """Standard engine execution returning typed QuickMarksResult contract."""
        res_dict = self.process(
            batch_input,
            historical_subject_averages=historical_subject_averages,
            previous_overall_percentage=previous_overall_percentage
        )
        return QuickMarksResult(**res_dict)
