"""Unit tests for ConsistencyEngine in smartparent-backend."""

import os
import sys
from datetime import date, timedelta
import pytest

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.smartparent.engines.consistency_engine import (
    ConsistencyEngine,
    AssessmentRecordSchema,
    TrajectoryEvaluationResult,
    MultiSubjectConsistencyResult
)


@pytest.fixture
def engine():
    return ConsistencyEngine()


# =============================================================================
# 1. Single Test & Baseline Tests
# =============================================================================

def test_single_test_baseline(engine):
    """A single test should establish a baseline with STABLE trajectory and 0 delta."""
    records = [
        {
            "subject": "Mathematics",
            "test_title": "Unit Test 1",
            "test_date": "2026-08-01",
            "total_scored_marks": 75.0,
            "total_max_marks": 100.0
        }
    ]
    result: MultiSubjectConsistencyResult = engine.run(records)
    assert "Mathematics" in result.subject_trajectories
    traj = result.subject_trajectories["Mathematics"]
    assert traj.total_tests == 1
    assert traj.latest_percentage == 75.0
    assert traj.trajectory_status == "STABLE"
    assert traj.direction_delta_60d == 0.0
    assert traj.movement_indicator == "→ 0.0%"
    assert traj.consistency_index == 100.0
    assert "75.0%" in traj.narrative
    assert "Initial baseline test" in traj.narrative


# =============================================================================
# 2. Longitudinal Trajectory Tests
# =============================================================================

def test_improving_trajectory(engine):
    """Sequential upward tests should produce IMPROVING status and positive slope."""
    records = [
        {"subject": "Physics", "test_title": "T1", "test_date": "2026-08-01", "total_scored_marks": 50.0, "total_max_marks": 100.0},
        {"subject": "Physics", "test_title": "T2", "test_date": "2026-08-20", "total_scored_marks": 65.0, "total_max_marks": 100.0},
        {"subject": "Physics", "test_title": "T3", "test_date": "2026-09-10", "total_scored_marks": 82.0, "total_max_marks": 100.0},
    ]
    result = engine.run(records)
    traj = result.subject_trajectories["Physics"]
    assert traj.total_tests == 3
    assert traj.latest_percentage == 82.0
    assert traj.trajectory_status == "IMPROVING"
    assert traj.trend_slope > 0
    assert traj.direction_delta_60d == 32.0
    assert traj.movement_indicator.startswith("↑")
    assert "upward momentum" in traj.narrative


def test_declining_trajectory(engine):
    """Sequential downward tests should produce DECLINING status and negative slope."""
    records = [
        {"subject": "Chemistry", "test_title": "T1", "test_date": "2026-08-01", "total_scored_marks": 85.0, "total_max_marks": 100.0},
        {"subject": "Chemistry", "test_title": "T2", "test_date": "2026-08-25", "total_scored_marks": 70.0, "total_max_marks": 100.0},
        {"subject": "Chemistry", "test_title": "T3", "test_date": "2026-09-15", "total_scored_marks": 55.0, "total_max_marks": 100.0},
    ]
    result = engine.run(records)
    traj = result.subject_trajectories["Chemistry"]
    assert traj.total_tests == 3
    assert traj.latest_percentage == 55.0
    assert traj.trajectory_status == "DECLINING"
    assert traj.trend_slope < 0
    assert traj.direction_delta_60d == -30.0
    assert traj.movement_indicator.startswith("↓")
    assert "downward trend" in traj.narrative


def test_volatile_trajectory(engine):
    """Erratic jumps (both positive and negative) with high variance should be VOLATILE."""
    records = [
        {"subject": "Biology", "test_title": "T1", "test_date": "2026-07-01", "total_scored_marks": 85.0, "total_max_marks": 100.0},
        {"subject": "Biology", "test_title": "T2", "test_date": "2026-07-20", "total_scored_marks": 35.0, "total_max_marks": 100.0},
        {"subject": "Biology", "test_title": "T3", "test_date": "2026-08-10", "total_scored_marks": 90.0, "total_max_marks": 100.0},
        {"subject": "Biology", "test_title": "T4", "test_date": "2026-08-30", "total_scored_marks": 40.0, "total_max_marks": 100.0},
    ]
    result = engine.run(records)
    traj = result.subject_trajectories["Biology"]
    assert traj.total_tests == 4
    assert traj.trajectory_status == "VOLATILE"
    assert traj.std_dev > 12.0
    assert "score volatility" in traj.narrative


def test_stable_trajectory(engine):
    """Consistent tight scores within +/- 3% should remain STABLE."""
    records = [
        {"subject": "English", "test_title": "T1", "test_date": "2026-08-01", "total_scored_marks": 78.0, "total_max_marks": 100.0},
        {"subject": "English", "test_title": "T2", "test_date": "2026-08-20", "total_scored_marks": 80.0, "total_max_marks": 100.0},
        {"subject": "English", "test_title": "T3", "test_date": "2026-09-10", "total_scored_marks": 79.0, "total_max_marks": 100.0},
    ]
    result = engine.run(records)
    traj = result.subject_trajectories["English"]
    assert traj.total_tests == 3
    assert traj.trajectory_status == "STABLE"
    assert abs(traj.direction_delta_60d) <= 3.0
    assert "stable and consistent" in traj.narrative


# =============================================================================
# 3. Mathematical Integrity & Sanity Verification
# =============================================================================

def test_data_integrity_rejects_scored_greater_than_max(engine):
    """Tests where scored > max must be flagged and skipped gracefully without crashing."""
    records = [
        {"subject": "Maths", "test_title": "Corrupt Test", "test_date": "2026-08-01", "total_scored_marks": 120.0, "total_max_marks": 100.0},
        {"subject": "Maths", "test_title": "Valid Test", "test_date": "2026-08-15", "total_scored_marks": 80.0, "total_max_marks": 100.0},
    ]
    result = engine.run(records)
    traj = result.subject_trajectories["Maths"]
    assert traj.total_tests == 1  # Only valid test counted
    assert len(traj.integrity_flags) >= 1
    assert "exceed max marks" in traj.integrity_flags[0]


def test_data_integrity_rejects_negative_marks(engine):
    """Negative marks must be flagged as invalid."""
    records = [
        {"subject": "Science", "test_title": "Negative Test", "test_date": "2026-08-01", "total_scored_marks": -10.0, "total_max_marks": 50.0},
        {"subject": "Science", "test_title": "Good Test", "test_date": "2026-08-10", "total_scored_marks": 40.0, "total_max_marks": 50.0},
    ]
    result = engine.run(records)
    traj = result.subject_trajectories["Science"]
    assert traj.total_tests == 1
    assert traj.latest_percentage == 80.0
    assert any("Negative scored marks" in flag for flag in traj.integrity_flags)


def test_recomputed_percentage_prevents_corruption(engine):
    """Even if an erroneous percentage is passed in input, engine recalculates true percentage."""
    records = [
        {
            "subject": "Social",
            "test_title": "Test 1",
            "test_date": "2026-08-01",
            "total_scored_marks": 40.0,
            "total_max_marks": 80.0,
            "percentage": 99.0  # Corrupt reported percentage!
        }
    ]
    result = engine.run(records)
    traj = result.subject_trajectories["Social"]
    assert traj.latest_percentage == 50.0  # 40/80 * 100 == 50.0%


# =============================================================================
# 4. Multi-Subject Parity & Asymmetry Analysis
# =============================================================================

def test_multi_subject_asymmetry_and_pillar_vs_risk(engine):
    """Cross-subject analysis should identify pillar subjects, risk subjects, and asymmetry."""
    input_data = {
        "Mathematics": [
            {"test_title": "M1", "test_date": "2026-08-01", "total_scored_marks": 88.0, "total_max_marks": 100.0},
            {"test_title": "M2", "test_date": "2026-08-20", "total_scored_marks": 94.0, "total_max_marks": 100.0},
        ],
        "Science": [
            {"test_title": "S1", "test_date": "2026-08-01", "total_scored_marks": 65.0, "total_max_marks": 100.0},
            {"test_title": "S2", "test_date": "2026-08-20", "total_scored_marks": 45.0, "total_max_marks": 100.0},
        ],
        "English": [
            {"test_title": "E1", "test_date": "2026-08-01", "total_scored_marks": 78.0, "total_max_marks": 100.0},
            {"test_title": "E2", "test_date": "2026-08-20", "total_scored_marks": 80.0, "total_max_marks": 100.0},
        ]
    }
    result: MultiSubjectConsistencyResult = engine.run(input_data)
    assert len(result.evaluated_subjects) == 3
    assert "Mathematics" in result.pillar_subjects
    assert "Science" in result.risk_subjects
    # Asymmetry: 94.0% vs 45.0% -> gap of 49.0% >= 30.0%
    assert result.asymmetry_detected is True
    assert "Subject performance disparity detected" in result.asymmetry_summary


# =============================================================================
# 5. Fallback & Resilience Tests
# =============================================================================

def test_fallback_on_corrupt_input(engine):
    """Completely invalid input should trigger graceful fallback without crashing."""
    result = engine.run({"invalid_key": "not a list"})
    assert result is not None
    assert isinstance(result, MultiSubjectConsistencyResult)
    assert result.overall_consistency_score == 50.0
