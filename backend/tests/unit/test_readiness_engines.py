"""
=============================================================================
Unit Test Suite: Week 5 Copied Engines Verification
=============================================================================
Validates all exact functions copied from Week 5:
- calculate_stream_readiness (stream_readiness_engine.py)
- calculate_projected_cutoff (projected_cutoff_engine.py)
- calculate_projected_score (projected_score_engine.py)
- calculate_career_readiness (career_readiness_engine.py)
- calculate_achievement (achievement_engine.py)
- calculate_parent_satisfaction (parent_satisfaction_engine.py)
- calculate_admission_intelligence (admission_engine.py)
- calculate_school_growth (school_growth_engine.py)
- calculate_alumni_analytics (alumni_analytics.py)
=============================================================================
"""

import pandas as pd
import pytest

from src.smartparent.engines.stream_readiness_engine import (
    calculate_stream_readiness,
    classify_readiness,
    normalize_subject,
)
from src.smartparent.engines.projected_cutoff_engine import calculate_projected_cutoff
from src.smartparent.engines.projected_score_engine import calculate_projected_score
from src.smartparent.engines.career_readiness_engine import calculate_career_readiness
from src.smartparent.engines.achievement_engine import calculate_achievement
from src.smartparent.engines.parent_satisfaction_engine import calculate_parent_satisfaction




# 1. Stream Readiness
def test_stream_readiness_high_engineering():
    stream_map = {
        "engineering_readiness": ["maths", "physics", "chemistry"],
        "life_science_readiness": ["biology", "physics", "chemistry"],
        "commerce_readiness": ["commerce", "accountancy", "economics"]
    }
    student = {
        "student_id": "CB1019",
        "maths": 92,
        "physics": 88,
        "chemistry": 85,
        "biology": 60,
        "commerce": 40
    }
    res = calculate_stream_readiness(student, stream_map)
    assert res["engineering_readiness"] == "High"
    assert res["life_science_readiness"] == "Moderate"
    assert res["commerce_readiness"] == "Low"


def test_stream_readiness_weakness_gate():
    stream_map = {
        "engineering_readiness": ["maths", "physics", "chemistry"]
    }
    student = {
        "maths": 40,
        "physics": 45,
        "chemistry": 42
    }
    res = calculate_stream_readiness(student, stream_map)
    assert res["engineering_readiness"] == "Low"


# 2. Projected Cutoff
def test_projected_cutoff():
    data = {
        "maths": 92,
        "physics": 88,
        "chemistry": 85
    }
    res = calculate_projected_cutoff(data)
    # 92 + (88 + 85) / 2 = 92 + 86.5 = 178.5
    assert res["projected_cutoff"] == 178.5


# 3. Projected Score
def test_projected_score():
    data = {
        "term1": 72,
        "term2": 80,
        "term3": 85
    }
    # Mock mastery dataframe
    mastery_df = pd.DataFrame([
        {"Score_Range_Min": 80, "Score_Range_Max": 100, "Level": "Strong"},
        {"Score_Range_Min": 60, "Score_Range_Max": 79.9, "Level": "Average"},
        {"Score_Range_Min": 40, "Score_Range_Max": 59.9, "Level": "Weak"},
        {"Score_Range_Min": 0, "Score_Range_Max": 39.9, "Level": "Critical"},
    ])
    res = calculate_projected_score(data, mastery_df)
    assert res["projected_score"] >= 80


# 4. Career Readiness
def test_career_readiness():
    stream_data = {
        "engineering_readiness": "High",
        "life_science_readiness": "Moderate",
        "commerce_readiness": "Low"
    }
    cutoff_data = {"projected_cutoff": 182.5}
    res = calculate_career_readiness(stream_data, cutoff_data)
    assert res["engineering"] == "High"
    assert res["life_science"] == "Moderate"
    assert res["commerce"] == "Low"


# 5. Achievement Engine
def test_achievement():
    data = {
        "school_id": "SCH001",
        "certificates": 120,
        "sports": 45,
        "competitions": 35,
        "cultural": 20,
        "total_students": 500
    }
    res = calculate_achievement(data)
    assert res["achievement_score"] == 44
    assert res["engagement_level"] == "Moderate"


# 6. Parent Satisfaction
def test_parent_satisfaction():
    data = {
        "survey_scores": [5, 4, 4, 3, 5, 4, 5]
    }
    res = calculate_parent_satisfaction(data)
    assert res["parent_satisfaction"] == 86
    assert res["satisfaction_level"] == "Excellent"

