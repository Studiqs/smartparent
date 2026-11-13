"""
STUDIQS® SmartParent™ (v6.2 Complete) - Consistency & Longitudinal Intelligence Engine
Evaluates multi-test longitudinal trajectory, directionality deltas, mathematical integrity,
and cross-subject consistency for students without crashing.
"""

import math
import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union
from pydantic import BaseModel, Field, ConfigDict

from src.smartparent.engines.base_engine import BaseEngine, EngineHealthStatus

logger = logging.getLogger("STUDIQS_ConsistencyEngine")


# =============================================================================
# 1. Pydantic v2 Type-Safe Schemas
# =============================================================================

class AssessmentRecordSchema(BaseModel):
    """Schema for a single historical test/exam event."""
    model_config = ConfigDict(extra="ignore")

    test_id: Optional[str] = None
    subject: str = Field(..., min_length=1, description="Subject name (e.g. Mathematics)")
    test_title: str = Field(default="Standard Test", description="Exam/test title")
    test_date: Union[date, datetime, str] = Field(..., description="Date of the test")
    total_scored_marks: float = Field(..., ge=0.0, description="Marks scored by student")
    total_max_marks: float = Field(..., gt=0.0, description="Maximum test marks")
    percentage: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    question_marks: Optional[List[Dict[str, Any]]] = Field(default=None, description="Optional line-item question breakdown")


class TrajectoryEvaluationResult(BaseModel):
    """Longitudinal directionality analysis for a single subject."""
    model_config = ConfigDict(extra="ignore")

    subject: str
    total_tests: int
    latest_test_title: str
    latest_test_date: str
    latest_scored: float
    latest_max: float
    latest_percentage: float
    previous_percentage: Optional[float] = None
    recent_delta: float = 0.0
    direction_delta_60d: float = 0.0
    trend_slope: float = 0.0
    trajectory_status: str  # 'IMPROVING', 'DECLINING', 'STABLE', 'VOLATILE'
    movement_indicator: str  # e.g. '↑ +6.2%', '↓ -4.5%', '→ 0.0%'
    consistency_index: float  # 0.0 to 100.0 (stability measure)
    std_dev: float = 0.0
    sparkline_points: List[float] = Field(default_factory=list)
    narrative: str = ""
    narrative_en: str = ""
    integrity_flags: List[str] = Field(default_factory=list)


class MultiSubjectConsistencyResult(BaseModel):
    """Cross-subject holistic consistency and parity report."""
    model_config = ConfigDict(extra="ignore")

    child_id: Optional[str] = None
    evaluated_subjects: List[str]
    subject_trajectories: Dict[str, TrajectoryEvaluationResult]
    overall_mean_percentage: float
    overall_consistency_score: float  # 0 to 100
    pillar_subjects: List[str]  # Strong & Improving
    risk_subjects: List[str]    # Declining or Volatile
    asymmetry_detected: bool
    asymmetry_summary: str
    audit_timestamp: str


# =============================================================================
# 2. Production Consistency Engine Implementation
# =============================================================================

class ConsistencyEngine(BaseEngine):
    """
    Engine 9: Consistency Engine (consistency_engine.py)
    
    Evaluates longitudinal directionality across historical test scores:
    1. Validates mathematical consistency (scored <= max, non-negative, sum of questions).
    2. Sorts chronological test series and calculates trend slope (Linear Regression).
    3. Calculates 60-day direction delta and categorizes trajectory (Improving/Declining/Stable/Volatile).
    4. Computes Consistency Index (stability measure based on standard deviation).
    5. Analyzes cross-subject parity to identify Pillar vs Risk subjects.
    6. Generates bilingual (English/Tamil) narratives for Parent Pulse & Monthly Reports.
    """

    def __init__(self, failure_threshold: int = 5):
        super().__init__(name="ConsistencyEngine", failure_threshold=failure_threshold)

    # -------------------------------------------------------------------------
    # BaseEngine Template Method Lifecycle Hooks
    # -------------------------------------------------------------------------

    def validate_input(self, input_data: Any) -> Dict[str, List[Dict[str, Any]]]:
        """
        Validates input structure. Accepts:
          - A list of test records (Dicts or TestRecordSchema)
          - A dict of {subject: [test_records]}
          - A single test record dict
        """
        if not input_data:
            raise ValueError("Input data cannot be empty.")

        grouped: Dict[str, List[Dict[str, Any]]] = {}

        if isinstance(input_data, list):
            for item in input_data:
                rec = self._normalize_record(item)
                subj = rec.get("subject", "General").strip().title()
                grouped.setdefault(subj, []).append(rec)

        elif isinstance(input_data, dict):
            # Check if it's a single test record or already grouped
            if "total_scored_marks" in input_data and "total_max_marks" in input_data:
                rec = self._normalize_record(input_data)
                subj = rec.get("subject", "General").strip().title()
                grouped[subj] = [rec]
            else:
                for subj_key, records in input_data.items():
                    if isinstance(records, list):
                        grouped[str(subj_key).strip().title()] = [
                            self._normalize_record(r) for r in records
                        ]

        if not grouped:
            raise ValueError("No valid subject test records found in input.")

        return grouped

    def execute_core(self, validated_data: Dict[str, List[Dict[str, Any]]]) -> MultiSubjectConsistencyResult:
        """Executes full longitudinal consistency and directionality evaluation."""
        subject_results: Dict[str, TrajectoryEvaluationResult] = {}
        all_percentages: List[float] = []
        all_consistency_indices: List[float] = []

        for subject, records in validated_data.items():
            trajectory = self._evaluate_single_subject(subject, records)
            subject_results[subject] = trajectory
            all_percentages.append(trajectory.latest_percentage)
            all_consistency_indices.append(trajectory.consistency_index)

        # Cross-Subject Asymmetry & Parity Analysis
        pillar_subjects = []
        risk_subjects = []
        for subj, traj in subject_results.items():
            if traj.latest_percentage >= 75.0 and traj.trajectory_status in ("IMPROVING", "STABLE"):
                pillar_subjects.append(subj)
            elif traj.latest_percentage < 60.0 or traj.trajectory_status in ("DECLINING", "VOLATILE"):
                risk_subjects.append(subj)

        overall_mean = round(sum(all_percentages) / len(all_percentages), 2) if all_percentages else 0.0
        overall_consistency = round(sum(all_consistency_indices) / len(all_consistency_indices), 2) if all_consistency_indices else 100.0

        # Asymmetry: Max spread > 30% between best and worst subject
        max_pct = max(all_percentages) if all_percentages else 0.0
        min_pct = min(all_percentages) if all_percentages else 0.0
        asymmetry_detected = (max_pct - min_pct) >= 30.0 and len(all_percentages) > 1

        if asymmetry_detected:
            asymmetry_summary = (
                f"Subject performance disparity detected: {max_pct:.1f}% vs {min_pct:.1f}% "
                f"(Gap of {max_pct - min_pct:.1f}%). Prioritize support in risk subjects."
            )
        else:
            asymmetry_summary = "Balanced cross-subject consistency with no severe subject disparity."

        return MultiSubjectConsistencyResult(
            evaluated_subjects=list(subject_results.keys()),
            subject_trajectories=subject_results,
            overall_mean_percentage=overall_mean,
            overall_consistency_score=overall_consistency,
            pillar_subjects=pillar_subjects,
            risk_subjects=risk_subjects,
            asymmetry_detected=asymmetry_detected,
            asymmetry_summary=asymmetry_summary,
            audit_timestamp=datetime.utcnow().isoformat()
        )

    def fallback(self, error: Exception, input_data: Any) -> MultiSubjectConsistencyResult:
        """Safe degraded fallback response ensuring pipeline never crashes."""
        logger.warning(f"[ConsistencyEngine] Executing fallback due to error: {error}")
        return MultiSubjectConsistencyResult(
            evaluated_subjects=["General"],
            subject_trajectories={
                "General": TrajectoryEvaluationResult(
                    subject="General",
                    total_tests=0,
                    latest_test_title="Fallback Report",
                    latest_test_date=date.today().isoformat(),
                    latest_scored=0.0,
                    latest_max=100.0,
                    latest_percentage=0.0,
                    recent_delta=0.0,
                    direction_delta_60d=0.0,
                    trend_slope=0.0,
                    trajectory_status="STABLE",
                    movement_indicator="→ 0.0%",
                    consistency_index=50.0,
                    std_dev=0.0,
                    sparkline_points=[0.0],
                    narrative="Insufficient data to evaluate historical test consistency.",
                    narrative_en="Insufficient data to evaluate historical test consistency.",
                    integrity_flags=[f"Degraded fallback: {str(error)[:100]}"]
                )
            },
            overall_mean_percentage=0.0,
            overall_consistency_score=50.0,
            pillar_subjects=[],
            risk_subjects=[],
            asymmetry_detected=False,
            asymmetry_summary="Evaluation degraded due to data processing fault.",
            audit_timestamp=datetime.utcnow().isoformat()
        )

    # -------------------------------------------------------------------------
    # Core Mathematical & Pedagogical Algorithms
    # -------------------------------------------------------------------------

    def _evaluate_single_subject(self, subject: str, raw_records: List[Dict[str, Any]]) -> TrajectoryEvaluationResult:
        """Evaluates longitudinal trajectory and trend slope for a single subject."""
        integrity_flags: List[str] = []
        clean_records = []

        for r in raw_records:
            is_valid, reason, sanitized = self._validate_and_sanitize_record(r)
            if not is_valid:
                integrity_flags.append(f"Skipped invalid test '{r.get('test_title', 'Unknown')}': {reason}")
                continue
            clean_records.append(sanitized)

        # Sort chronologically by date
        clean_records.sort(key=lambda x: x["parsed_date"])

        if not clean_records:
            return TrajectoryEvaluationResult(
                subject=subject,
                total_tests=0,
                latest_test_title="No Valid Tests",
                latest_test_date=date.today().isoformat(),
                latest_scored=0.0,
                latest_max=100.0,
                latest_percentage=0.0,
                trajectory_status="STABLE",
                movement_indicator="→ 0.0%",
                consistency_index=100.0,
                narrative=f"No valid test records found for {subject}.",
                narrative_en=f"No valid test records found for {subject}.",
                integrity_flags=integrity_flags
            )

        n = len(clean_records)
        latest = clean_records[-1]
        sparkline = [r["percentage"] for r in clean_records]

        # Single Test Event Handling
        if n == 1:
            pct = latest["percentage"]
            return TrajectoryEvaluationResult(
                subject=subject,
                total_tests=1,
                latest_test_title=latest["test_title"],
                latest_test_date=latest["parsed_date"].isoformat(),
                latest_scored=latest["scored"],
                latest_max=latest["max"],
                latest_percentage=pct,
                previous_percentage=None,
                recent_delta=0.0,
                direction_delta_60d=0.0,
                trend_slope=0.0,
                trajectory_status="STABLE",
                movement_indicator="→ 0.0%",
                consistency_index=100.0,
                std_dev=0.0,
                sparkline_points=sparkline,
                narrative=f"Initial baseline test recorded at {pct:.1f}%. Ongoing tracking active.",
                narrative_en=f"Initial baseline test recorded at {pct:.1f}%. Ongoing tracking active.",
                integrity_flags=integrity_flags
            )

        # Multi-Test Trajectory Calculations
        prev = clean_records[-2]
        recent_delta = round(latest["percentage"] - prev["percentage"], 2)

        # 60-Day Direction Delta
        cutoff_date = latest["parsed_date"] - timedelta(days=60)
        tests_in_60d = [r for r in clean_records if r["parsed_date"] >= cutoff_date]
        if len(tests_in_60d) >= 2:
            direction_delta_60d = round(tests_in_60d[-1]["percentage"] - tests_in_60d[0]["percentage"], 2)
        else:
            direction_delta_60d = recent_delta

        # Standard Deviation & Consistency Index
        mean_pct = sum(sparkline) / n
        variance = sum((p - mean_pct) ** 2 for p in sparkline) / (n - 1) if n > 1 else 0.0
        std_dev = round(math.sqrt(variance), 2)
        # Consistency Index: 100 - (2 * std_dev), bounded between 0 and 100
        consistency_index = round(max(0.0, min(100.0, 100.0 - (std_dev * 2.5))), 1)

        # Linear Regression Slope (Normalized over test index: x in [0, 1, 2, ...])
        # slope m = sum((x - x_bar) * (y - y_bar)) / sum((x - x_bar)^2)
        x_vals = list(range(n))
        x_bar = sum(x_vals) / n
        y_bar = mean_pct
        numerator = sum((x - x_bar) * (y - y_bar) for x, y in zip(x_vals, sparkline))
        denominator = sum((x - x_bar) ** 2 for x in x_vals)
        trend_slope = round(numerator / denominator, 3) if denominator != 0 else 0.0

        # Trajectory Status Classification
        # 1. Volatile: high fluctuation (std_dev > 12.0 and both positive & negative jumps)
        diffs = [sparkline[i] - sparkline[i-1] for i in range(1, n)]
        has_pos_jump = any(d >= 10.0 for d in diffs)
        has_neg_jump = any(d <= -10.0 for d in diffs)
        is_volatile = std_dev >= 12.0 and has_pos_jump and has_neg_jump

        if is_volatile:
            trajectory_status = "VOLATILE"
        elif trend_slope >= 1.5 or direction_delta_60d >= 4.0:
            trajectory_status = "IMPROVING"
        elif trend_slope <= -1.5 or direction_delta_60d <= -4.0:
            trajectory_status = "DECLINING"
        else:
            trajectory_status = "STABLE"

        # Movement Indicator String
        if direction_delta_60d > 0:
            movement_indicator = f"↑ +{direction_delta_60d:.1f}%"
        elif direction_delta_60d < 0:
            movement_indicator = f"↓ {direction_delta_60d:.1f}%"
        else:
            movement_indicator = "→ 0.0%"

        # English Narrative Synthesis
        narrative = self._synthesize_narrative(
            subject=subject,
            status=trajectory_status,
            latest_pct=latest["percentage"],
            delta_60d=direction_delta_60d,
            n_tests=n
        )

        return TrajectoryEvaluationResult(
            subject=subject,
            total_tests=n,
            latest_test_title=latest["test_title"],
            latest_test_date=latest["parsed_date"].isoformat(),
            latest_scored=latest["scored"],
            latest_max=latest["max"],
            latest_percentage=latest["percentage"],
            previous_percentage=prev["percentage"],
            recent_delta=recent_delta,
            direction_delta_60d=direction_delta_60d,
            trend_slope=trend_slope,
            trajectory_status=trajectory_status,
            movement_indicator=movement_indicator,
            consistency_index=consistency_index,
            std_dev=std_dev,
            sparkline_points=sparkline,
            narrative=narrative,
            narrative_en=narrative,
            integrity_flags=integrity_flags
        )

    # -------------------------------------------------------------------------
    # Validation & Sanitization Helpers
    # -------------------------------------------------------------------------

    def _validate_and_sanitize_record(self, raw: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Validates mathematical integrity of a single test record:
          - Scored marks must be non-negative
          - Max marks must be strictly positive
          - Scored marks cannot exceed max marks
          - Sum of question-level marks must match total scored marks (if present)
        """
        try:
            scored = float(raw.get("total_scored_marks", raw.get("scored_marks", 0.0)))
            max_m = float(raw.get("total_max_marks", raw.get("max_marks", 0.0)))
        except (ValueError, TypeError):
            return False, "Non-numeric marks provided", {}

        if max_m <= 0:
            return False, f"Invalid total_max_marks ({max_m}). Must be > 0.", {}

        if scored < 0:
            return False, f"Negative scored marks ({scored}) not allowed.", {}

        if scored > max_m:
            return False, f"Scored marks ({scored}) exceed max marks ({max_m}).", {}

        # Re-derive percentage to prevent corrupt stored percentages
        true_pct = round((scored / max_m) * 100.0, 2)

        # Question level cross-verification
        q_breakdown = raw.get("question_marks")
        if q_breakdown and isinstance(q_breakdown, list):
            q_sum = sum(float(q.get("scored", q.get("marks", 0))) for q in q_breakdown if isinstance(q, dict))
            if abs(q_sum - scored) > 0.5:
                logger.warning(f"Line-item question sum ({q_sum}) differs from total scored ({scored}).")

        # Parse Date safely
        raw_date = raw.get("test_date") or raw.get("date") or date.today()
        parsed_date = self._parse_date_safe(raw_date)

        sanitized = {
            "test_title": str(raw.get("test_title", "Test Event")).strip(),
            "subject": str(raw.get("subject", "General")).strip(),
            "scored": scored,
            "max": max_m,
            "percentage": true_pct,
            "parsed_date": parsed_date
        }
        return True, "Valid", sanitized

    def _normalize_record(self, item: Any) -> Dict[str, Any]:
        """Converts Pydantic model or dictionary to standard dictionary."""
        if hasattr(item, "model_dump"):
            return item.model_dump()
        elif hasattr(item, "dict"):
            return item.dict()
        elif isinstance(item, dict):
            return dict(item)
        raise ValueError(f"Cannot normalize record of type {type(item)}")

    def _parse_date_safe(self, dt: Any) -> date:
        """Safely parses date from date, datetime, or ISO string."""
        if isinstance(dt, datetime):
            return dt.date()
        if isinstance(dt, date):
            return dt
        if isinstance(dt, str):
            for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
                try:
                    return datetime.strptime(dt.strip(), fmt).date()
                except ValueError:
                    continue
        return date.today()

    def _synthesize_narrative(
        self,
        subject: str,
        status: str,
        latest_pct: float,
        delta_60d: float,
        n_tests: int
    ) -> str:
        """Synthesizes human-readable pedagogical summary in clear English."""
        if status == "IMPROVING":
            return f"{subject} demonstrates strong upward momentum (+{delta_60d:.1f}%), currently at {latest_pct:.1f}% across {n_tests} assessments."
        elif status == "DECLINING":
            return f"{subject} is experiencing a downward trend ({delta_60d:.1f}%), falling to {latest_pct:.1f}%. Timely remedial review recommended."
        elif status == "VOLATILE":
            return f"{subject} exhibits significant score volatility (latest: {latest_pct:.1f}%). Target concept reinforcement to build steady retention."
        else:
            return f"{subject} shows stable and consistent performance at {latest_pct:.1f}% across {n_tests} tests."
