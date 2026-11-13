"""
Unit tests for STUDIQS SmartParent Result Card Parser Engine (Hybrid Document AI)
"""

import sys
from pathlib import Path
backend_dir = Path(__file__).resolve().parents[2]
src_dir = backend_dir / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import pytest
try:
    from smartparent.engines.result_parser import (
        ResultParserEngine,
        CanonicalSubjectResolver,
        SpatialLayoutParser,
        DeterministicReportCardParser,
        ExtractedSubjectMark,
        ResultParserOutput
    )
except ImportError:
    from src.smartparent.engines.result_parser import (
        ResultParserEngine,
        CanonicalSubjectResolver,
        SpatialLayoutParser,
        DeterministicReportCardParser,
        ExtractedSubjectMark,
        ResultParserOutput
    )


class TestCanonicalSubjectResolver:
    """Test subject normalization and typo resilience."""

    def setup_method(self):
        self.resolver = CanonicalSubjectResolver()

    def test_exact_matches(self):
        subj, conf = self.resolver.resolve("Mathematics")
        assert subj == "Mathematics"
        assert conf == 1.0

        subj, conf = self.resolver.resolve("Science")
        assert subj == "Science"
        assert conf == 1.0

    def test_alias_matches(self):
        subj, conf = self.resolver.resolve("Maths")
        assert subj == "Mathematics"
        assert conf == 1.0

        subj, conf = self.resolver.resolve("Mat")
        assert subj == "Mathematics"
        assert conf == 1.0

        subj, conf = self.resolver.resolve("SST")
        assert subj == "Social Science"
        assert conf == 1.0

        subj, conf = self.resolver.resolve("Sci & Tech")
        assert subj == "Science"
        assert conf == 1.0

    def test_fuzzy_typo_tolerance(self):
        # Typo: "Mathematecs" -> "Mathematics"
        subj, conf = self.resolver.resolve("Mathematecs")
        assert subj == "Mathematics"
        assert conf >= 0.80

        # Typo: "Phyzics" -> "Physics"
        subj, conf = self.resolver.resolve("Phyzics")
        assert subj == "Physics"
        assert conf >= 0.80


class TestDeterministicParsers:
    """Test Strategy A, B, C extraction heuristics."""

    def setup_method(self):
        self.resolver = CanonicalSubjectResolver()
        self.parser = DeterministicReportCardParser(self.resolver)

    def test_strategy_a_ratio(self):
        # Standard fraction
        res = self.parser.parse_line_ratio("Mathematics : 45/50")
        assert res is not None
        subj, raw_subj, obt, max_m, conf = res
        assert subj == "Mathematics"
        assert obt == 45.0
        assert max_m == 50.0

        # "out of" variation
        res = self.parser.parse_line_ratio("Science 85 out of 100")
        assert res is not None
        subj, raw_subj, obt, max_m, conf = res
        assert subj == "Science"
        assert obt == 85.0
        assert max_m == 100.0

    def test_strategy_b_columnar(self):
        # Columnar: [Subject, Internal, External, Total, Max]
        res = self.parser.parse_line_columnar("Tamil 18 72 90 100")
        assert res is not None
        subj, raw_subj, obt, max_m, conf = res
        assert subj == "Tamil"
        assert obt == 90.0
        assert max_m == 100.0

        # Columnar two numbers: [Subject, Scored, Max]
        res = self.parser.parse_line_columnar("Social Science 42 50")
        assert res is not None
        subj, raw_subj, obt, max_m, conf = res
        assert subj == "Social Science"
        assert obt == 42.0
        assert max_m == 50.0

    def test_strategy_c_keyval(self):
        res = self.parser.parse_line_keyval("English Core : 78", default_max=100.0)
        assert res is not None
        subj, raw_subj, obt, max_m, conf = res
        assert subj == "English"
        assert obt == 78.0
        assert max_m == 100.0


class TestSpatialLayoutParser:
    """Test 2D bounding box line clustering."""

    def test_line_clustering(self):
        spatial = SpatialLayoutParser(y_threshold=10.0)
        # 2 words on line 1 (y around 100), 2 words on line 2 (y around 150)
        words = [
            (10.0, 98.0, 50.0, 108.0, "Mathematics"),
            (100.0, 101.0, 140.0, 111.0, "95/100"),
            (10.0, 148.0, 50.0, 158.0, "Science"),
            (100.0, 152.0, 140.0, 162.0, "88/100"),
        ]
        lines = spatial.cluster_words_into_lines(words)
        assert len(lines) == 2
        assert "Mathematics 95/100" in lines[0]["text"]
        assert "Science 88/100" in lines[1]["text"]


class TestResultParserEngineMaster:
    """Test the complete hybrid end-to-end parser engine."""

    def setup_method(self):
        # Test without needing disk OCR
        self.engine = ResultParserEngine(use_ocr_fallback=False)

    def test_multi_subject_report_card(self):
        raw_marksheet = """
        DELHI PUBLIC SCHOOL - TERMINAL REPORT CARD
        Student: Rahul Sharma | Class: 10-A | Term: Mid-Term 2026
        ----------------------------------------------------------
        Mathematics : 46 / 50
        General Science : 42 / 50
        English Core : 38 / 50
        Social Studies 40 50
        Tamil Language : 48 / 50
        ----------------------------------------------------------
        Total Marks: 214 / 250
        """

        output = self.engine.parse(
            input_source=raw_marksheet,
            student_id="STU-1019",
            student_name="Rahul Sharma",
            exam_name="Mid-Term Assessment 2026"
        )

        assert isinstance(output, ResultParserOutput)
        assert output.student_id == "STU-1019"
        assert len(output.subjects) == 5

        # Check Gate 2 Rule: Zero fake topic mastery
        assert output.is_topic_intelligence_eligible is False
        assert output.needs_human_confirmation is True

        # Check total metrics
        subjects_dict = {s.subject: s for s in output.subjects}
        assert "Mathematics" in subjects_dict
        assert subjects_dict["Mathematics"].marks_obtained == 46.0
        assert subjects_dict["Mathematics"].max_marks == 50.0
        assert subjects_dict["Mathematics"].score_percent == 92.0
        assert subjects_dict["Mathematics"].score_band == "Band 1: Strong"
        assert subjects_dict["Mathematics"].band_code == 1

        assert "Science" in subjects_dict
        assert subjects_dict["Science"].marks_obtained == 42.0

        assert "English" in subjects_dict
        assert subjects_dict["English"].marks_obtained == 38.0

        assert "Social Science" in subjects_dict
        assert subjects_dict["Social Science"].marks_obtained == 40.0

        assert "Tamil" in subjects_dict
        assert subjects_dict["Tamil"].marks_obtained == 48.0

        # Total marks: 46+42+38+40+48 = 214 / 250 = 85.6% -> Band 1 Strong
        assert output.total_marks_obtained == 214.0
        assert output.total_max_marks == 250.0
        assert output.overall_percentage == 85.6
        assert output.overall_score_band == "Band 1: Strong"
        assert output.overall_band_code == 1

    def test_pydantic_validation_error_on_invalid_marks(self):
        with pytest.raises(ValueError):
            ExtractedSubjectMark(
                subject="Mathematics",
                raw_subject_text="Maths",
                marks_obtained=105.0,  # Invalid: > max_marks
                max_marks=100.0,
                score_percent=105.0,
                score_band="Band 1: Strong",
                band_code=1,
                confidence=1.0,
                extraction_tier="REGEX_RATIO"
            )

    def test_tesseract_image_ocr_end_to_end(self, tmp_path):
        """Generates a test marksheet image and verifies Tesseract OCR extraction."""
        from PIL import Image, ImageDraw
        tesseract_engine = ResultParserEngine(use_ocr_fallback=True)

        if not tesseract_engine._init_tesseract():
            pytest.skip("Tesseract executable not available on host system.")

        # Create clean synthetic marksheet image
        img = Image.new("RGB", (600, 200), color="white")
        draw = ImageDraw.Draw(img)
        draw.text((20, 30), "Mathematics : 92 / 100", fill="black")
        draw.text((20, 80), "Science : 85 / 100", fill="black")
        draw.text((20, 130), "English : 78 / 100", fill="black")

        test_img_path = tmp_path / "test_report_card.png"
        img.save(str(test_img_path))

        result = tesseract_engine.parse(str(test_img_path))
        assert isinstance(result, ResultParserOutput)
        assert result.extraction_method in ["TESSERACT_OCR_SPATIAL", "DETERMINISTIC_HEURISTIC"]
        assert len(result.subjects) >= 2

        subjects_found = [s.subject for s in result.subjects]
        assert "Mathematics" in subjects_found
        assert "Science" in subjects_found

    def test_sample_fixtures_e2e(self):
        """Verifies all 3 sample fixtures (PDF, clean PNG, skewed shadow PNG) extract 5/5 subjects."""
        from pathlib import Path
        fixtures_dir = Path(__file__).resolve().parent.parent / "fixtures" / "samples"
        engine = ResultParserEngine()

        for filename in ["sample_cbse_report_card.pdf", "sample_report_card_clean.png", "sample_report_card_skewed_shadow.png"]:
            file_path = fixtures_dir / filename
            if not file_path.exists():
                continue
            res = engine.parse(str(file_path))
            assert len(res.subjects) == 5, f"Failed on {filename}: only {len(res.subjects)} subjects"
            assert res.total_marks_obtained == 432.0
            assert res.total_max_marks == 500.0
            assert res.overall_percentage == 86.4
            assert res.is_topic_intelligence_eligible is False


