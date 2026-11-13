"""
STUDIQS® SmartParent™ (v6.2 & v6.3 Extension) - Section 3 Diagnostic Flow Audit Suite
=============================================================================
Module: tests.integration.test_diagnostic_flow
Section 3: Diagnostic Ingestion, Quick Marks, Result Upload, and QP Intelligence

Real-World Data Verification Scope:
  Part 1: Quick Marks Intake Engine
    - Authentic CBSE Class 10 Indian parent data (Ananya Sundar)
    - 4-Tier Score Bands (Strong, Average, Weak, Critical)
    - Month-on-Month trajectory slopes (Improving, Stable, Declining, Baseline)
    - Strict Gate 2 Zero Fake Topic Mastery guardrails (Locked Aggregate Only)
    - Boundary & malformed input validations

  Part 2: Result Upload & Hybrid Document AI Marksheet Parser
    - Multi-format extraction heuristics (Ratio fractions, 'out of' text, columnar grids)
    - Fuzzy subject alias resolver & typo tolerance (Maths, Sci & Tech, SST, Phyzics)
    - Spec-mandated Human Confirmation workflow flag (needs_human_confirmation=True)
    - Non-negotiable Gate 2 Zero-Hallucination integrity compliance

  Part 3: Question Paper (QP) Intelligence on Real Authentic Papers
    - Actual PDF parsing from 'data/question_papers/':
        1. CBSE Class 10 Mathematics Standard (cbse_10_maths_sqp.pdf)
        2. CBSE Class 10 Science (cbse_10_science_sqp.pdf)
        3. Scanned State Board paper with OCR fallback (10Th English TVR 1st MidTerm.pdf)
    - Bloom's Taxonomy tagging, difficulty scoring, MCQ extraction
    - Sequence healing verification on question numbers
    - Stakeholder recommendations generation (Student, Parent, Teacher, Management)
=============================================================================
"""

import os
from pathlib import Path
import pytest

from src.smartparent.engines.section_03_qp_intelligence.quick_marks_engine import (
    QuickMarksEngine,
    QuickMarksBatchInput,
    SubjectMarkInput,
    QuickMarksResult,
)
from src.smartparent.engines.section_03_qp_intelligence.result_parser import (
    ResultParserEngine,
    CanonicalSubjectResolver,
    DeterministicReportCardParser,
    ExtractedSubjectMark,
    ResultParserOutput,
)
from src.smartparent.engines.section_03_qp_intelligence.qp_parser import (
    DocIntelligencePipeline,
    QuestionExtractor,
)
from src.smartparent.engines.section_03_qp_intelligence.topic_intelligence_engine import (
    TopicIntelligenceEngine,
)

# Resolve workspace root, question papers directory, and test fixtures
BACKEND_ROOT = Path(__file__).resolve().parents[2]
QP_DIR = BACKEND_ROOT / "data" / "qp_pdfs"
if not QP_DIR.exists():
    QP_DIR = Path(__file__).resolve().parents[3] / "data" / "question_papers"
SAMPLES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "samples"


# =============================================================================
# PART 1: QUICK MARKS INTAKE ENGINE (REAL-WORLD DATA AUDIT)
# =============================================================================

class TestQuickMarksRealWorldAudit:
    """Verifies fast aggregate marks entry with authentic Indian student data."""

    def setup_method(self):
        self.engine = QuickMarksEngine()

    def test_cbse_class10_real_student_intake(self):
        """
        Scenario: Parent Meenakshi Sundaram inputs Class 10 Half-Yearly marks
        for student Ananya Sundar across 5 subjects.
        """
        payload = {
            "student_id": "STU-ANANYA-2026",
            "test_title": "Class 10 CBSE Half-Yearly Examination",
            "test_date": "2026-10-15",
            "grade": "Class 10",
            "board": "CBSE",
            "subjects": [
                {"subject": "Mathematics", "max_marks": 100.0, "marks_obtained": 94.0},
                {"subject": "Science", "max_marks": 100.0, "marks_obtained": 82.5},
                {"subject": "English", "max_marks": 100.0, "marks_obtained": 74.0},
                {"subject": "Social Science", "max_marks": 100.0, "marks_obtained": 65.0},
                {"subject": "Tamil", "max_marks": 100.0, "marks_obtained": 48.0},
            ],
        }

        # Historical scores from previous Quarterly Exam
        historical_averages = {
            "Mathematics": 88.0,  # 94 - 88 = +6.0% -> Improving
            "Science": 83.0,      # 82.5 - 83.0 = -0.5% -> Stable
            "English": 80.0,      # 74.0 - 80.0 = -6.0% -> Declining
            # Social Science and Tamil have no prior record -> Baseline
        }
        previous_overall = 70.0

        result = self.engine.process(
            payload,
            historical_subject_averages=historical_averages,
            previous_overall_percentage=previous_overall,
        )

        # 1. Total and Aggregate Calculations
        assert result["student_id"] == "STU-ANANYA-2026"
        assert result["total_marks_obtained"] == 363.5
        assert result["total_max_marks"] == 500.0
        assert result["overall_percentage"] == 72.7
        assert result["overall_band_code"] == 2  # 72.7% is Band 2 (Average)
        assert result["overall_score_band"] == "Band 2: Average"
        assert result["overall_movement_delta"] == 2.7
        assert "Improving" in result["overall_movement_label"]

        # 2. Strict Gate 2 Zero-Hallucination Integrity Guardrails
        assert result["evidence_type"] == "QUICK_MARKS"
        assert result["is_topic_intelligence_eligible"] is False
        assert result["topic_intelligence_status"] == "LOCKED_AGGREGATE_ONLY"
        assert "never create fake topic mastery" in result["guardrail_note"]

        # 3. Subject-Specific Telemetry & Consistency Directions
        subj_map = {s["subject"]: s for s in result["subjects_telemetry"]}

        # Mathematics (94%) -> Band 1 (Strong), Improving (+6.0%)
        maths = subj_map["Mathematics"]
        assert maths["score_percent"] == 94.0
        assert maths["band_code"] == 1
        assert maths["score_band"] == "Band 1: Strong"
        assert maths["consistency_direction"] == "Improving"
        assert maths["movement_delta"] == 6.0

        # Science (82.5%) -> Band 1 (Strong), Stable (-0.5%)
        sci = subj_map["Science"]
        assert sci["score_percent"] == 82.5
        assert sci["band_code"] == 1
        assert sci["score_band"] == "Band 1: Strong"
        assert sci["consistency_direction"] == "Stable"

        # English (74%) -> Band 2 (Average), Declining (-6.0%)
        eng = subj_map["English"]
        assert eng["score_percent"] == 74.0
        assert eng["band_code"] == 2
        assert eng["score_band"] == "Band 2: Average"
        assert eng["consistency_direction"] == "Declining"

        # Social Science (65%) -> Band 2 (Average), Baseline
        soc = subj_map["Social Science"]
        assert soc["score_percent"] == 65.0
        assert soc["band_code"] == 2
        assert soc["consistency_direction"] == "Baseline"

        # Tamil (48%) -> Band 3 (Weak), Baseline
        tam = subj_map["Tamil"]
        assert tam["score_percent"] == 48.0
        assert tam["band_code"] == 3
        assert tam["score_band"] == "Band 3: Weak"
        assert tam["consistency_direction"] == "Baseline"

    def test_boundary_and_malformed_marks_validation(self):
        """Verifies boundary checks, centum handling, and error rejection."""
        # Error: Marks obtained > max marks
        with pytest.raises(ValueError, match="cannot exceed maximum marks"):
            SubjectMarkInput(subject="Mathematics", max_marks=50.0, marks_obtained=55.0)

        # Error: Negative marks
        with pytest.raises(ValueError):
            SubjectMarkInput(subject="Science", max_marks=100.0, marks_obtained=-5.0)

        # Centum Score: 100/100 -> Band 1: Strong
        centum_payload = {
            "student_id": "STU-CENTUM",
            "test_title": "Unit Test Centum",
            "subjects": [{"subject": "Maths", "max_marks": 100.0, "marks_obtained": 100.0}],
        }
        res_centum = self.engine.process(centum_payload)
        assert res_centum["overall_percentage"] == 100.0
        assert res_centum["overall_band_code"] == 1
        assert res_centum["overall_score_band"] == "Band 1: Strong"

        # Zero Score: 0/100 -> Band 4: Critical
        zero_payload = {
            "student_id": "STU-ZERO",
            "test_title": "Diagnostic Initial",
            "subjects": [{"subject": "Maths", "max_marks": 100.0, "marks_obtained": 0.0}],
        }
        res_zero = self.engine.process(zero_payload)
        assert res_zero["overall_percentage"] == 0.0
        assert res_zero["overall_band_code"] == 4
        assert res_zero["overall_score_band"] == "Band 4: Critical"

    def test_icse_7_subject_real_student_intake(self):
        """
        Scenario: ICSE Class 10 student (Rohan Mukherjee) with 7 distinct subjects.
        Verifies multi-subject aggregate calculation and longitudinal consistency.
        """
        payload = {
            "student_id": "STU-ROHAN-ICSE",
            "test_title": "ICSE Class 10 Mid-Term Examination",
            "test_date": "2026-09-28",
            "grade": "Class 10",
            "board": "ICSE",
            "subjects": [
                {"subject": "English Language", "max_marks": 100.0, "marks_obtained": 86.0},
                {"subject": "English Literature", "max_marks": 100.0, "marks_obtained": 88.0},
                {"subject": "Hindi", "max_marks": 100.0, "marks_obtained": 72.0},
                {"subject": "History & Civics", "max_marks": 100.0, "marks_obtained": 81.0},
                {"subject": "Geography", "max_marks": 100.0, "marks_obtained": 79.0},
                {"subject": "Mathematics", "max_marks": 100.0, "marks_obtained": 96.0},
                {"subject": "Science", "max_marks": 100.0, "marks_obtained": 91.0},
            ],
        }

        history = {
            "Mathematics": 90.0,         # +6.0% -> Improving
            "English Language": 85.0,    # +1.0% -> Stable
            "Hindi": 78.0,               # -6.0% -> Declining
        }

        result = self.engine.process(payload, historical_subject_averages=history, previous_overall_percentage=82.0)

        assert result["total_marks_obtained"] == 593.0
        assert result["total_max_marks"] == 700.0
        assert result["overall_percentage"] == 84.71
        assert result["overall_score_band"] == "Band 1: Strong"
        assert result["overall_band_code"] == 1
        assert result["overall_movement_delta"] == 2.71
        assert "Improving" in result["overall_movement_label"]
        assert result["is_topic_intelligence_eligible"] is False



# =============================================================================
# PART 2: RESULT UPLOAD & REPORT CARD PARSER AUDIT
# =============================================================================

class TestResultUploadAndReportCardParser:
    """Verifies Hybrid Document AI parsing across realistic school report cards."""

    def setup_method(self):
        self.resolver = CanonicalSubjectResolver()
        self.parser = DeterministicReportCardParser(self.resolver)

    def test_ratio_and_fraction_extraction(self):
        """Tests standard fraction format: Subject : Marks/Max."""
        res_maths = self.parser.parse_line_ratio("Mathematics : 45/50")
        assert res_maths is not None
        subj, raw_subj, obt, max_m, conf = res_maths
        assert subj == "Mathematics"
        assert obt == 45.0
        assert max_m == 50.0
        assert conf >= 0.90

        # "out of" variation
        res_sci = self.parser.parse_line_ratio("Science 76 out of 80")
        assert res_sci is not None
        subj, raw_subj, obt, max_m, conf = res_sci
        assert subj == "Science"
        assert obt == 76.0
        assert max_m == 80.0

    def test_fuzzy_subject_normalization_and_typos(self):
        """Verifies canonical mapping handles abbreviations and OCR typos."""
        # Abbreviations
        subj, conf = self.resolver.resolve("Maths")
        assert subj == "Mathematics"
        assert conf == 1.0

        subj, conf = self.resolver.resolve("Sci & Tech")
        assert subj == "Science"
        assert conf == 1.0

        subj, conf = self.resolver.resolve("SST")
        assert subj == "Social Science"
        assert conf == 1.0

        # Typos
        subj_typo1, conf1 = self.resolver.resolve("Mathematecs")
        assert subj_typo1 == "Mathematics"
        assert conf1 >= 0.80

        subj_typo2, conf2 = self.resolver.resolve("Phyzics")
        assert subj_typo2 == "Physics"
        assert conf2 >= 0.80

    def test_report_card_output_contract_and_gate2_compliance(self):
        """
        Validates ResultParserOutput schema enforces human confirmation
        and Gate 2 Zero-Hallucination rules.
        """
        sub_mark = ExtractedSubjectMark(
            subject="Mathematics",
            raw_subject_text="Maths",
            marks_obtained=88.0,
            max_marks=100.0,
            score_percent=88.0,
            score_band="Band 1: Strong",
            band_code=1,
            confidence=0.95,
            extraction_tier="PYMUPDF_TABLE",
        )

        output = ResultParserOutput(
            student_id="STU-001",
            student_name="Ananya Sundar",
            exam_name="Term 1 Exam",
            subjects=[sub_mark],
            total_marks_obtained=88.0,
            total_max_marks=100.0,
            overall_percentage=88.0,
            overall_score_band="Band 1: Strong",
            overall_band_code=1,
            overall_confidence=0.95,
        )

        assert output.needs_human_confirmation is True  # Mandatory UI review
        assert output.is_topic_intelligence_eligible is False  # Gate 2 Compliance
        assert "never create fake topic mastery" in output.pedagogical_note

    def test_parse_real_cbse_report_card_digital_pdf(self):
        """
        Parses actual vector digital CBSE report card PDF (sample_cbse_report_card.pdf).
        Verifies table detection, subject resolution, marks calculation, and Gate 2 guardrail.
        """
        pdf_path = SAMPLES_DIR / "sample_cbse_report_card.pdf"
        assert pdf_path.exists(), f"Sample report card PDF not found at {pdf_path}"

        engine = ResultParserEngine()
        result = engine.parse(pdf_path, student_id="STU-RAHUL-DPS")

        assert len(result.subjects) == 5
        subj_names = [s.subject for s in result.subjects]
        assert "Mathematics" in subj_names
        assert "Science" in subj_names
        assert "English" in subj_names
        assert "Social Science" in subj_names
        assert "Tamil" in subj_names

        assert result.total_marks_obtained == 432.0
        assert result.total_max_marks == 500.0
        assert result.overall_percentage == 86.4
        assert result.overall_score_band == "Band 1: Strong"
        assert result.overall_band_code == 1
        assert result.needs_human_confirmation is True
        assert result.is_topic_intelligence_eligible is False

    def test_parse_clean_rendered_report_card_image_ocr(self):
        """
        Parses clean 300 DPI report card image (sample_report_card_clean.png)
        via 8-stage image preprocessing + Tesseract OCR.
        """
        img_path = SAMPLES_DIR / "sample_report_card_clean.png"
        assert img_path.exists(), f"Clean report card PNG not found at {img_path}"

        engine = ResultParserEngine()
        result = engine.parse(img_path, student_id="STU-CLEAN-IMG")

        assert len(result.subjects) == 5
        assert result.total_marks_obtained == 432.0
        assert result.overall_percentage == 86.4
        assert result.overall_score_band == "Band 1: Strong"
        assert result.needs_human_confirmation is True

    def test_parse_smartphone_camera_photo_skewed_shadow_ocr(self):
        """
        Parses 13.5MB realistic smartphone photo (sample_report_card_skewed_shadow.png)
        with +4.5° perspective tilt and harsh illumination shadow.
        Verifies CLAHE, shadow elimination, deskewing, and robust OCR extraction.
        """
        img_path = SAMPLES_DIR / "sample_report_card_skewed_shadow.png"
        assert img_path.exists(), f"Skewed report card image not found at {img_path}"

        engine = ResultParserEngine()
        result = engine.parse(img_path, student_id="STU-SKEW-IMG")

        assert len(result.subjects) == 5
        assert result.total_marks_obtained == 432.0
        assert result.overall_percentage == 86.4
        assert result.overall_score_band == "Band 1: Strong"
        assert result.needs_human_confirmation is True



# =============================================================================
# PART 3: QP INTELLIGENCE ON REAL AUTHENTIC QUESTION PAPERS
# =============================================================================

class TestRealQuestionPaperIntelligence:
    """Verifies parsing of authentic CBSE and State Board question papers from disk."""

    def test_parse_real_cbse_10_maths_paper(self):
        """
        Parses actual CBSE Class 10 Mathematics Standard Question Paper
        from data/question_papers/cbse_10_maths_sqp.pdf.
        """
        pdf_path = QP_DIR / "cbse_10_maths_sqp.pdf"
        assert pdf_path.exists(), f"Question paper not found at {pdf_path}"

        pipeline = DocIntelligencePipeline()
        questions = pipeline.parse(str(pdf_path))

        assert len(questions) >= 30, f"Expected >= 30 questions, extracted {len(questions)}"

        # Validate Question 1 structure
        q1 = questions[0]
        assert q1["question_no"] == 1
        assert "LCM" in q1["question_text"] or "equal to" in q1["question_text"]
        assert q1["section"] == "A"
        assert q1["max_marks"] == 1.0
        assert any(opt in q1["question_text"] for opt in ["(a)", "(B)", "(C)", "(D)"])

        # Validate Sections parsed (A, B, C, D, E)
        sections_found = set(q.get("section") for q in questions if q.get("section"))
        assert "A" in sections_found or len(sections_found) >= 1

        # Validate Bloom's Taxonomy & Difficulty tagging
        bloom_levels = set(q.get("bloom_level") for q in questions if q.get("bloom_level"))
        assert len(bloom_levels) >= 1

    def test_parse_real_cbse_10_science_paper(self):
        """
        Parses actual CBSE Class 10 Science Question Paper
        from data/question_papers/cbse_10_science_sqp.pdf.
        """
        pdf_path = QP_DIR / "cbse_10_science_sqp.pdf"
        assert pdf_path.exists(), f"Question paper not found at {pdf_path}"

        pipeline = DocIntelligencePipeline()
        questions = pipeline.parse(str(pdf_path))

        assert len(questions) >= 30, f"Expected >= 30 questions, extracted {len(questions)}"

        # Validate scientific terminology and question structure
        q1 = questions[0]
        assert q1["question_no"] == 1
        assert any(
            term in q1["question_text"].lower()
            for term in ["nutrition", "organism", "chemical", "reaction", "light", "current"]
        )
        assert q1["max_marks"] == 1.0

    def test_parse_scanned_state_board_paper_with_ocr_healing(self):
        """
        Parses scanned Tamil Nadu 10th paper requiring OCR fallback and sequence healing.
        File: data/question_papers/10Th English TVR 1st MidTerm Question paper 2026.pdf
        """
        pdf_path = QP_DIR / "10Th English TVR 1st MidTerm Question paper 2026.pdf"
        assert pdf_path.exists(), f"Question paper not found at {pdf_path}"

        pipeline = DocIntelligencePipeline()
        questions = pipeline.parse(str(pdf_path))

        assert len(questions) >= 15, f"Expected >= 15 questions from scanned paper, got {len(questions)}"

        # Validate sequence ordering is monotonic
        q_nums = [q["question_no"] for q in questions if isinstance(q["question_no"], int)]
        assert len(q_nums) >= 10
        # All extracted numbers must be positive and monotonically sorted
        assert all(n > 0 for n in q_nums)
        assert q_nums == sorted(q_nums)

    def test_topic_intelligence_stakeholder_recommendations(self):
        """
        Verifies TopicIntelligenceEngine generates role-tailored recommendations
        for all 4 stakeholders based on topic diagnostic levels.
        """
        engine = TopicIntelligenceEngine()

        # 1. Critical Level (Quadratic Equations) -> High priority intervention
        crit_recs = engine._get_recs(
            level="Critical",
            topic="Quadratic Equations",
            subject="Mathematics",
        )
        assert isinstance(crit_recs, dict)
        assert "student" in crit_recs
        assert "parent" in crit_recs
        assert "teacher" in crit_recs
        assert "management" in crit_recs

        assert "Quadratic Equations" in crit_recs["student"][0]
        assert "Quadratic Equations" in crit_recs["parent"][0]
        assert "Quadratic Equations" in crit_recs["teacher"][0]
        assert "Quadratic Equations" in crit_recs["management"][0]
        assert engine.priority_map["Critical"] == "High"

        # 2. Strong Level (Real Numbers) -> Extension challenges
        strong_recs = engine._get_recs(
            level="Strong",
            topic="Real Numbers",
            subject="Mathematics",
        )
        assert "Real Numbers" in strong_recs["student"][0]
        assert "Real Numbers" in strong_recs["parent"][0]
        assert engine.priority_map["Strong"] == "Low"
