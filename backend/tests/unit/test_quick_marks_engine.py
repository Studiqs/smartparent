"""
Unit Tests for QuickMarksEngine (Task SP-02 / Section 3 & Section 5)
Verifies:
1. Aggregate score calculations & 5-tier score bands
2. Month-on-month consistency slopes (Improving, Stable, Declining)
3. Boundary error validations (marks > max_marks, negative marks)
4. Strict Gate 2 Zero Fake Topic Mastery guardrails
"""

import pytest
from src.smartparent.engines.quick_marks_engine import QuickMarksEngine, QuickMarksBatchInput, SubjectMarkInput


def test_quick_marks_successful_batch_processing():
    engine = QuickMarksEngine()
    
    payload = {
        "student_id": "STU_102",
        "test_title": "Term 1 Quarterly Exam",
        "test_date": "2026-10-15",
        "subjects": [
            {"subject": "Mathematics", "max_marks": 100, "marks_obtained": 94.0},
            {"subject": "Science", "max_marks": 100, "marks_obtained": 82.5},
            {"subject": "English", "max_marks": 100, "marks_obtained": 74.0},
            {"subject": "Social Science", "max_marks": 100, "marks_obtained": 65.0},
            {"subject": "Tamil", "max_marks": 100, "marks_obtained": 48.0}
        ]
    }
    
    history = {
        "Mathematics": 88.0,  # 94 - 88 = +6.0 -> Improving
        "Science": 83.0,      # 82.5 - 83.0 = -0.5 -> Stable
        "English": 80.0,      # 74.0 - 80.0 = -6.0 -> Declining
    }
    
    result = engine.process(payload, historical_subject_averages=history, previous_overall_percentage=70.0)
    
    # 1. Overall verification
    assert result["student_id"] == "STU_102"
    assert result["total_marks_obtained"] == 363.5
    assert result["total_max_marks"] == 500.0
    assert result["overall_percentage"] == 72.7
    assert result["overall_band_code"] == 2  # 72.7% is Band 2 (Average)
    assert result["overall_score_band"] == "Band 2: Average"
    assert result["overall_movement_delta"] == 2.7
    assert "Improving" in result["overall_movement_label"]
    
    # 2. Strict Gate 2 Zero Fake Topic Mastery verification
    assert result["evidence_type"] == "QUICK_MARKS"
    assert result["is_topic_intelligence_eligible"] is False
    assert result["topic_intelligence_status"] == "LOCKED_AGGREGATE_ONLY"
    assert "Aggregate marks alone never create fake topic mastery" in result["guardrail_note"]
    
    # 3. Individual Subject Telemetry verification (4 Bands: Strong, Average, Weak, Critical)
    subjs = {s["subject"]: s for s in result["subjects_telemetry"]}
    
    # Maths: 94% -> Band 1: Strong (>= 80%), Improving (+6.0%)
    assert subjs["Mathematics"]["band_code"] == 1
    assert subjs["Mathematics"]["score_band"] == "Band 1: Strong"
    assert subjs["Mathematics"]["consistency_direction"] == "Improving"
    assert subjs["Mathematics"]["movement_delta"] == 6.0
    
    # Science: 82.5% -> Band 1: Strong (>= 80%), Stable (-0.5%)
    assert subjs["Science"]["band_code"] == 1
    assert subjs["Science"]["score_band"] == "Band 1: Strong"
    assert subjs["Science"]["consistency_direction"] == "Stable"
    
    # English: 74% -> Band 2: Average (60% - 79.99%), Declining (-6.0%)
    assert subjs["English"]["band_code"] == 2
    assert subjs["English"]["score_band"] == "Band 2: Average"
    assert subjs["English"]["consistency_direction"] == "Declining"
    
    # Social Science: 65% -> Band 2: Average (60% - 79.99%), Baseline
    assert subjs["Social Science"]["band_code"] == 2
    assert subjs["Social Science"]["score_band"] == "Band 2: Average"
    assert subjs["Social Science"]["consistency_direction"] == "Baseline"
    
    # Tamil: 48% -> Band 3: Weak (40% - 59.99%), Baseline
    assert subjs["Tamil"]["band_code"] == 3
    assert subjs["Tamil"]["score_band"] == "Band 3: Weak"


def test_quick_marks_boundary_validation_exceeding_max_marks():
    with pytest.raises(ValueError, match="cannot exceed maximum marks"):
        SubjectMarkInput(subject="Mathematics", max_marks=50, marks_obtained=55)


def test_quick_marks_boundary_negative_marks():
    with pytest.raises(ValueError):
        SubjectMarkInput(subject="Science", max_marks=100, marks_obtained=-5)


def test_quick_marks_centum_and_zero():
    engine = QuickMarksEngine()
    
    # Centum (100 / 100) -> Band 1: Strong
    centum_res = engine.process({
        "student_id": "STU_CENTUM",
        "test_title": "Monthly Test",
        "subjects": [{"subject": "Maths", "max_marks": 100, "marks_obtained": 100}]
    })
    assert centum_res["overall_percentage"] == 100.0
    assert centum_res["overall_band_code"] == 1
    assert centum_res["overall_score_band"] == "Band 1: Strong"
    
    # Zero (0 / 50) -> Band 4: Critical
    zero_res = engine.process({
        "student_id": "STU_ZERO",
        "test_title": "Pop Quiz",
        "subjects": [{"subject": "Physics", "max_marks": 50, "marks_obtained": 0}]
    })
    assert zero_res["overall_percentage"] == 0.0
    assert zero_res["overall_band_code"] == 4
    assert zero_res["overall_score_band"] == "Band 4: Critical"
