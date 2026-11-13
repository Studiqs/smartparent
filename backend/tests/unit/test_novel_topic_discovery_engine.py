"""
Unit Tests for STUDIQS® SmartParent™ Novel Topic Discovery Engine
Verifies:
  - Discovery of candidate novel topics from unmapped questions
  - Chapter clustering and nearest parent chapter matching
  - Noun-chunk salient candidate topic title extraction
  - Candidate Topic ID minting format
  - General scenario / word-problem filtering
  - Admin approval queue formatting and recommendation generation
  - Non-crashing fallback and CircuitBreaker stability
"""

import pytest
from src.smartparent.engines.novel_topic_discovery_engine import (
    NovelTopicDiscoveryEngine,
    UnmappedQuestionSchema,
    NovelTopicCandidateSchema,
    DiscoveryResultSchema,
)


@pytest.fixture
def discovery_engine():
    return NovelTopicDiscoveryEngine()


# ==============================================================================
# 1. Candidate Novel Topic Discovery
# ==============================================================================

def test_novel_topic_discovery_science_candidate(discovery_engine):
    questions = [
        {
            "question_no": 15,
            "question_text": "Explain the catenation property and tetravalency of carbon atoms resulting in millions of organic compounds.",
            "subject": "Science",
            "grade": "Class 10"
        }
    ]

    result = discovery_engine.execute(questions)

    assert isinstance(result, DiscoveryResultSchema)
    assert result.total_unmapped_analyzed == 1
    assert len(result.novel_topics_discovered) == 1

    cand = result.novel_topics_discovered[0]
    assert isinstance(cand, NovelTopicCandidateSchema)
    assert cand.suggested_chapter == "Carbon and its Compounds"
    assert cand.confidence_level == "HIGH"
    assert cand.similarity_score >= 0.60
    assert cand.review_status == "PENDING_ADMIN_REVIEW"
    assert "CBSE10SCI" in cand.candidate_topic_id
    assert len(cand.candidate_topic_name) > 3


def test_novel_topic_discovery_math_candidate(discovery_engine):
    questions = [
        {
            "question_no": 22,
            "question_text": "Determine the 20th term of an arithmetic progression where the common difference is 5 and first term is 2.",
            "subject": "Mathematics",
            "grade": "Class 10"
        }
    ]

    result = discovery_engine.execute(questions)

    assert len(result.novel_topics_discovered) == 1
    cand = result.novel_topics_discovered[0]
    assert cand.suggested_chapter == "Arithmetic Progressions"
    assert "CBSE10MTH" in cand.candidate_topic_id
    assert cand.confidence_level == "HIGH"


# ==============================================================================
# 2. General Scenario Filtering
# ==============================================================================

def test_novel_topic_discovery_general_scenario_filter(discovery_engine):
    questions = [
        {
            "question_no": 30,
            "question_text": "Suppose a student named Ramesh bought 5 pens in a village market and calculated the cost without receipts.",
            "subject": "Mathematics"
        }
    ]

    result = discovery_engine.execute(questions)

    assert len(result.general_scenarios_filtered) == 1
    assert len(result.novel_topics_discovered) == 0
    assert result.general_scenarios_filtered[0]["question_no"] == 30
    assert "General scenario" in result.general_scenarios_filtered[0]["reason"]


# ==============================================================================
# 3. Summary & Admin Review Queue
# ==============================================================================

def test_novel_topic_discovery_summary_generation(discovery_engine):
    questions = [
        {"question_no": 1, "question_text": "Describe the formation of a rainbow due to dispersion and internal reflection in raindrops.", "subject": "Science"},
        {"question_no": 2, "question_text": "Calculate the focal length of a concave mirror having radius of curvature 30 cm.", "subject": "Science"},
        {"question_no": 3, "question_text": "In a village school, Ramesh bought 10 balls during sports day.", "subject": "General"}
    ]

    result = discovery_engine.execute(questions)

    assert result.total_unmapped_analyzed == 3
    assert len(result.novel_topics_discovered) == 2
    assert len(result.general_scenarios_filtered) == 1

    summary = result.summary
    assert summary["novel_topics_proposed"] == 2
    assert summary["general_scenarios_filtered"] == 1
    assert len(summary["unique_chapters_impacted"]) >= 1


# ==============================================================================
# 4. Safe Fallback and Circuit Breaker
# ==============================================================================

def test_novel_topic_discovery_fallback(discovery_engine):
    result = discovery_engine.execute({})
    assert isinstance(result, DiscoveryResultSchema)
    assert result.total_unmapped_analyzed == 0
    assert len(result.novel_topics_discovered) == 0


def test_novel_topic_discovery_circuit_breaker(discovery_engine):
    discovery_engine.circuit_breaker.failure_threshold = 2

    class CrashingPayload:
        def __bool__(self):
            return True
        def __getattr__(self, name):
            raise RuntimeError("Discovery crash")

    discovery_engine.execute(CrashingPayload())
    discovery_engine.execute(CrashingPayload())

    assert discovery_engine.circuit_breaker.is_open()
    discovery_engine.reset_circuit()
    assert discovery_engine.circuit_breaker.is_closed()
