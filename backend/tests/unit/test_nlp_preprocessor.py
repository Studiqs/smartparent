"""
Unit Tests for STUDIQS® SmartParent™ NLP Preprocessor Engine (Engine 3)
Verifies:
  - Question number & Roman numeral prefix stripping
  - Marks notation bracket stripping ([5 Marks], (3M), [1x4=4])
  - Generic exam instruction clause removal (State true or false, Fill in blanks)
  - LaTeX fraction & math symbol normalization
  - Academic domain classification (Physics, Chemistry, Biology, Mathematics)
  - Cross-curriculum concept bridges (GCD -> HCF, Ray Optics -> Reflection)
  - Scenario context detection
  - Degraded fallback and CircuitBreaker stability
"""

import pytest
from src.smartparent.engines.nlp_preprocessor import (
    NLPPreprocessor,
    NLPPreprocessInputSchema,
    CleanedQuestionResultSchema,
)


@pytest.fixture
def preprocessor():
    return NLPPreprocessor()


# ==============================================================================
# 1. Stem Cleaning & Prefix Stripping
# ==============================================================================

def test_nlp_preprocessor_stem_cleaning_strips_q_prefixes(preprocessor):
    test_cases = [
        ("Q.14 (a): Why do stars twinkle at night?", "Why do stars twinkle at night?"),
        ("Question 5 - What is an electric circuit?", "What is an electric circuit?"),
        ("12. Explain the process of photosynthesis.", "Explain the process of photosynthesis."),
        ("(iv) Define electric power.", "Define electric power."),
        ("Section C - 25. Solve the quadratic equation.", "Solve the quadratic equation."),
    ]
    for raw_input, expected_core in test_cases:
        res = preprocessor.execute({"raw_text": raw_input})
        assert isinstance(res, CleanedQuestionResultSchema)
        assert expected_core.lower() in res.cleaned_stem.lower()
        assert not res.cleaned_stem.startswith("Q.14")
        assert not res.cleaned_stem.startswith("Section C")


def test_nlp_preprocessor_strips_marks_notations(preprocessor):
    raw = "Explain why copper does not displace hydrogen from dilute hydrochloric acid. [3 Marks]"
    res = preprocessor.execute({"raw_text": raw})

    assert "[3 Marks]" not in res.cleaned_stem
    assert "copper does not displace hydrogen" in res.cleaned_stem
    assert any("MARK: [3 Marks]" in m for m in res.stripped_tokens)


def test_nlp_preprocessor_strips_exam_instructions(preprocessor):
    test_cases = [
        ("State whether true or false: Mitochondria is the powerhouse of the cell.", "Mitochondria is the powerhouse of the cell."),
        ("Fill in the blanks: The SI unit of electric potential difference is volt.", "The SI unit of electric potential difference is volt."),
        ("Choose the correct option: Which of the following is a greenhouse gas?", "Which of the following is a greenhouse gas?"),
    ]
    for raw, expected in test_cases:
        res = preprocessor.execute({"raw_text": raw})
        assert expected.lower() in res.cleaned_stem.lower()
        assert not res.cleaned_stem.lower().startswith("state whether true or false")
        assert not res.cleaned_stem.lower().startswith("fill in the blanks")


# ==============================================================================
# 2. LaTeX and Math Normalization
# ==============================================================================

def test_nlp_preprocessor_latex_normalization(preprocessor):
    raw = r"Given that \frac{sin(x)}{cos(x)} = \tan(x), calculate \sqrt{16} \times 2."
    res = preprocessor.execute({"raw_text": raw})

    assert r"\frac" not in res.cleaned_stem
    assert "sin(x)/cos(x)" in res.cleaned_stem
    assert r"\sqrt" not in res.cleaned_stem
    assert "sqrt(16)" in res.cleaned_stem


# ==============================================================================
# 3. Domain Routing
# ==============================================================================

def test_nlp_preprocessor_domain_routing(preprocessor):
    physics_res = preprocessor.execute({"raw_text": "Calculate the equivalent resistance when three resistors of 2 ohm are in parallel."})
    assert physics_res.detected_domain == "Physics"
    assert physics_res.domain_confidence >= 0.5

    chem_res = preprocessor.execute({"raw_text": "Write the chemical equation for the esterification reaction of ethanoic acid."})
    assert chem_res.detected_domain == "Chemistry"
    assert chem_res.domain_confidence >= 0.5

    bio_res = preprocessor.execute({"raw_text": "Describe the structure and functioning of a nephron in the human kidney."})
    assert bio_res.detected_domain == "Biology"
    assert bio_res.domain_confidence >= 0.5

    math_res = preprocessor.execute({"raw_text": "Find the roots of the quadratic equation 2x^2 - 7x + 3 = 0 using the quadratic formula."})
    assert math_res.detected_domain == "Mathematics"
    assert math_res.domain_confidence >= 0.5


# ==============================================================================
# 4. Concept Bridges & Scenario Detection
# ==============================================================================

def test_nlp_preprocessor_concept_bridges(preprocessor):
    raw = "Find the GCD of two numbers using prime factorization method."
    res = preprocessor.execute({"raw_text": raw})

    assert any("gcd -> HCF and LCM" in b for b in res.applied_bridges)
    assert "HCF and LCM" in res.concept_query


def test_nlp_preprocessor_scenario_detection(preprocessor):
    scenario_text = "A student observed in an experiment that light bends when entering from air into water."
    res = preprocessor.execute({"raw_text": scenario_text})
    assert res.is_scenario_question is True

    pure_text = "State Snell's law of refraction."
    res_pure = preprocessor.execute({"raw_text": pure_text})
    assert res_pure.is_scenario_question is False


# ==============================================================================
# 5. Fallback and Circuit Breaker
# ==============================================================================

def test_nlp_preprocessor_safe_fallback(preprocessor):
    res = preprocessor.execute({})
    assert isinstance(res, CleanedQuestionResultSchema)
    assert res.detected_domain == "General"
    assert "FALLBACK_INVOKED" in res.stripped_tokens


def test_nlp_preprocessor_circuit_breaker(preprocessor):
    preprocessor.circuit_breaker.failure_threshold = 2

    class CrashingPayload:
        def __bool__(self):
            return True
        def __getattr__(self, name):
            raise RuntimeError("Preprocessor crash")

    preprocessor.execute(CrashingPayload())
    preprocessor.execute(CrashingPayload())

    assert preprocessor.circuit_breaker.is_open()
    preprocessor.reset_circuit()
    assert preprocessor.circuit_breaker.is_closed()
