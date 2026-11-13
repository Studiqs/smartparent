"""
Unit Tests for STUDIQS® SmartParent™ Parent Pulse Engine (Engine 10)
Verifies:
  - 3-Card digest structure (Green: Improvement, Amber: Watch, Blue: Action)
  - 'Praise First, Nudge Second' pedagogical standard
  - Dynamic trajectory telemetry mapping
  - Critical conceptual gap pinpointing
  - High-ROI next immediate action synthesis
  - Overall health indicator transitions (EXCELLENT, PROGRESSING, ATTENTION_NEEDED)
  - English-only narrative enforcement (no bilingual/Tamil text)
  - Safe degraded fallback and CircuitBreaker stability
"""

import pytest
from datetime import datetime
from src.smartparent.engines.parent_pulse_engine import (
    ParentPulseEngine,
    ParentPulseDigestResult,
    ParentPulseCardSchema
)
from src.smartparent.engines.consistency_engine import (
    ConsistencyEngine,
    AssessmentRecordSchema
)


@pytest.fixture
def pulse_engine():
    return ParentPulseEngine()


def test_parent_pulse_3_card_digest_structure(pulse_engine):
    """Verifies that the engine produces all 3 mandatory pulse cards with valid schemas."""
    payload = {
        "student_name": "Aarav Sharma",
        "subject_trajectories": {
            "Mathematics": {
                "direction_delta_60d": 5.4,
                "latest_percentage": 82.5,
                "trajectory_status": "IMPROVING"
            },
            "Science": {
                "direction_delta_60d": -4.2,
                "latest_percentage": 68.0,
                "trajectory_status": "DECLINING"
            }
        },
        "critical_topics": ["Light Reflection and Refraction"],
        "weak_topics": ["Light Reflection and Refraction"],
        "strong_topics": ["Quadratic Equations"]
    }

    result = pulse_engine.execute(payload)

    assert isinstance(result, ParentPulseDigestResult)
    assert result.student_name == "Aarav Sharma"
    assert result.improvement_area.card_type == "IMPROVEMENT"
    assert result.watch_area.card_type == "WATCH_AREA"
    assert result.next_immediate_action.card_type == "NEXT_ACTION"

    # Card fields check
    for card in [result.improvement_area, result.watch_area, result.next_immediate_action]:
        assert len(card.title) > 0
        assert len(card.headline) > 0
        assert len(card.description) > 0
        assert card.metric_badge is not None


def test_praise_first_nudge_second_principle(pulse_engine):
    """Verifies that the improvement card acknowledges success before any watch area nudge."""
    payload = {
        "student_name": "Diya Patel",
        "subject_trajectories": {
            "Social Science": {
                "direction_delta_60d": 6.8,
                "latest_percentage": 89.0,
                "trajectory_status": "IMPROVING"
            },
            "Mathematics": {
                "direction_delta_60d": -6.5,
                "latest_percentage": 58.0,
                "trajectory_status": "DECLINING"
            }
        },
        "critical_topics": ["Trigonometric Identities"],
        "strong_topics": ["Nationalism in India"]
    }

    result = pulse_engine.execute(payload)

    # Improvement card should praise Social Science growth
    assert "Social Science" in result.improvement_area.headline
    assert "Diya Patel" in result.improvement_area.description
    assert result.improvement_area.metric_badge is not None

    # Watch card should gently pinpoint Mathematics / Trigonometric Identities
    assert "Trigonometric Identities" in result.watch_area.headline or "Mathematics" in result.watch_area.headline
    assert result.watch_area.priority_level == "HIGH"


def test_parent_pulse_critical_topic_pinpoint(pulse_engine):
    """Verifies that critical gap topics elevate watch area priority to HIGH."""
    payload = {
        "student_name": "Rohan Verma",
        "subject_trajectories": {
            "Physics": {
                "direction_delta_60d": -7.5,
                "latest_percentage": 52.0,
                "trajectory_status": "DECLINING"
            }
        },
        "critical_topics": ["Electricity and Circuits"]
    }

    result = pulse_engine.execute(payload)

    assert result.watch_area.priority_level == "HIGH"
    assert "Electricity and Circuits" in result.watch_area.headline
    assert result.overall_health_indicator == "ATTENTION_NEEDED"


def test_parent_pulse_action_card_alignment(pulse_engine):
    """Verifies that the action card generates high-payoff home guidance for the identified gap."""
    payload = {
        "student_name": "Ananya Sen",
        "subject_trajectories": {
            "Chemistry": {
                "direction_delta_60d": -5.0,
                "latest_percentage": 64.0,
                "trajectory_status": "DECLINING"
            }
        },
        "critical_topics": ["Chemical Reactions and Equations"]
    }

    result = pulse_engine.execute(payload)

    assert "Chemical Reactions and Equations" in result.next_immediate_action.headline
    assert "Ananya Sen" in result.next_immediate_action.description
    assert "foundational problems" in result.next_immediate_action.description
    assert result.next_immediate_action.metric_badge == "High Payoff"


def test_parent_pulse_overall_health_indicators(pulse_engine):
    """Verifies state machine transitions for overall health badge."""
    # 1. Excellent: Upward momentum and no high priority watch areas
    exc_payload = {
        "student_name": "Student A",
        "subject_trajectories": {
            "Mathematics": {
                "direction_delta_60d": 8.0,
                "latest_percentage": 92.0,
                "trajectory_status": "IMPROVING"
            }
        },
        "critical_topics": []
    }
    exc_result = pulse_engine.execute(exc_payload)
    assert exc_result.overall_health_indicator == "EXCELLENT"

    # 2. Attention Needed: Critical gaps present
    att_payload = {
        "student_name": "Student B",
        "subject_trajectories": {
            "Science": {
                "direction_delta_60d": -8.0,
                "latest_percentage": 54.0,
                "trajectory_status": "DECLINING"
            }
        },
        "critical_topics": ["Optics"]
    }
    att_result = pulse_engine.execute(att_payload)
    assert att_result.overall_health_indicator == "ATTENTION_NEEDED"

    # 3. Progressing: Stable baseline
    prog_payload = {
        "student_name": "Student C",
        "subject_trajectories": {
            "English": {
                "direction_delta_60d": 0.5,
                "latest_percentage": 76.0,
                "trajectory_status": "STABLE"
            }
        },
        "critical_topics": []
    }
    prog_result = pulse_engine.execute(prog_payload)
    assert prog_result.overall_health_indicator == "PROGRESSING"


def test_parent_pulse_supports_nested_consistency_result(pulse_engine):
    """Verifies seamless compatibility when feeding ConsistencyEngine output directly."""
    consistency_engine = ConsistencyEngine()
    test_records = [
        AssessmentRecordSchema(
            assessment_id="T1", subject="Mathematics", test_date=datetime(2026, 1, 10),
            total_scored_marks=65.0, total_max_marks=100.0
        ),
        AssessmentRecordSchema(
            assessment_id="T2", subject="Mathematics", test_date=datetime(2026, 2, 10),
            total_scored_marks=75.0, total_max_marks=100.0
        ),
        AssessmentRecordSchema(
            assessment_id="T3", subject="Mathematics", test_date=datetime(2026, 3, 10),
            total_scored_marks=85.0, total_max_marks=100.0
        ),
        AssessmentRecordSchema(
            assessment_id="T4", subject="Science", test_date=datetime(2026, 1, 10),
            total_scored_marks=80.0, total_max_marks=100.0
        ),
        AssessmentRecordSchema(
            assessment_id="T5", subject="Science", test_date=datetime(2026, 3, 10),
            total_scored_marks=68.0, total_max_marks=100.0
        ),
    ]

    consistency_res = consistency_engine.execute(test_records)

    pulse_input = {
        "student_name": "Kavya Sundaram",
        "consistency_result": consistency_res,
        "critical_topics": ["Magnetic Effects of Current"],
        "strong_topics": ["Arithmetic Progressions"]
    }

    result = pulse_engine.execute(pulse_input)

    assert result.student_name == "Kavya Sundaram"
    assert result.supporting_metrics["total_subjects_evaluated"] == 2
    assert "Mathematics" in result.supporting_metrics["pillar_subjects"]
    assert "Science" in result.supporting_metrics["risk_subjects"]
    assert "Mathematics" in result.improvement_area.headline
    assert "Magnetic Effects of Current" in result.watch_area.headline


def test_parent_pulse_english_only_narratives(pulse_engine):
    """Verifies strict English-only text enforcement (no Tamil/bilingual characters)."""
    payload = {
        "student_name": "Rahul Raman",
        "subject_trajectories": {
            "Mathematics": {
                "direction_delta_60d": 4.5,
                "latest_percentage": 78.0,
                "trajectory_status": "IMPROVING"
            },
            "Tamil": {
                "direction_delta_60d": -2.0,
                "latest_percentage": 82.0,
                "trajectory_status": "STABLE"
            }
        },
        "critical_topics": ["Grammar Syntax"],
        "strong_topics": ["Coordinate Geometry"]
    }

    result = pulse_engine.execute(payload)

    for card in [result.improvement_area, result.watch_area, result.next_immediate_action]:
        text_content = f"{card.title} {card.headline} {card.description} {card.metric_badge or ''}"
        # Verify no Tamil unicode range (\u0b80 - \u0bff)
        assert not any('\u0b80' <= char <= '\u0bff' for char in text_content), (
            f"Tamil characters detected in card narrative: {text_content}"
        )


def test_parent_pulse_fallback_on_corrupt_data(pulse_engine):
    """Verifies non-crashing graceful degradation when corrupt or empty data is received."""
    result = pulse_engine.execute({})

    assert isinstance(result, ParentPulseDigestResult)
    assert result.improvement_area.card_type == "IMPROVEMENT"
    assert result.watch_area.card_type == "WATCH_AREA"
    assert result.next_immediate_action.card_type == "NEXT_ACTION"
    assert result.supporting_metrics.get("degraded") is True


def test_parent_pulse_circuit_breaker(pulse_engine):
    """Verifies CircuitBreaker transitions upon repeated catastrophic failures."""
    pulse_engine.circuit_breaker.failure_threshold = 2

    # Simulate catastrophic failure in validate_input
    class CrashingPayload:
        def __bool__(self):
            return True
        def __getattr__(self, name):
            raise RuntimeError("Catastrophic payload failure")

    # Trip breaker
    pulse_engine.execute(CrashingPayload())
    pulse_engine.execute(CrashingPayload())

    assert pulse_engine.circuit_breaker.is_open()

    # Reset
    pulse_engine.reset_circuit()
    assert pulse_engine.circuit_breaker.is_closed()
