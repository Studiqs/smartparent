"""Unit tests for qp_parser.py hardcoding removal refactoring.

Tests verify that:
1. The generic OCR sequence healer (_ocr_heal_question_number) correctly
   handles ALL the old hardcoded cases AND new unseen OCR errors.
2. _get_default_marks_for_section() uses ONLY document-extracted evidence
   (prescan_marks, section_marks, instruction_ranges) — no static board maps.
3. _finalize_current_question() no longer applies hardcoded keyword overrides
   (passage=4, CBSE Section A=1, ruler/compass=5).
"""

import sys
import os
import re
import pytest

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.smartparent.engines.qp_parser import QuestionExtractor


# ============================================================
# 1. OCR Sequence Healer Tests
# ============================================================

class TestOCRSequenceHealer:
    """Tests for _ocr_heal_question_number() — the generic OCR digit healer."""

    def _make_extractor(self, last_q: int) -> QuestionExtractor:
        ext = QuestionExtractor(board="Generic", ocr_lang="eng")
        ext.last_question_no = last_q
        return ext

    # ── Previously hardcoded cases (regression tests) ────────────

    def test_39_healed_to_3_when_last_is_2(self):
        """Old hardcode: '39 What is...' → '3) What is...' when last_q=2."""
        ext = self._make_extractor(2)
        result = ext._ocr_heal_question_number("39 What is the formula?")
        assert "3)" in result or result.startswith("3")
        assert "What is the formula" in result

    def test_i1_healed_to_11_when_last_is_10(self):
        """Old hardcode: 'i1) Find...' → '11) Find...' when last_q=10."""
        ext = self._make_extractor(10)
        result = ext._ocr_heal_question_number("i1) Find the value")
        assert result.strip().startswith("11")

    def test_I1_healed_to_11_when_last_is_10(self):
        """Same as above but with uppercase I."""
        ext = self._make_extractor(10)
        result = ext._ocr_heal_question_number("I1) Find the value")
        assert result.strip().startswith("11")

    def test_3A_healed_to_34_when_last_is_33(self):
        """Old hardcode: '3A) Prove...' → '34) Prove...' when last_q=33."""
        ext = self._make_extractor(33)
        result = ext._ocr_heal_question_number("3A) Prove that the angle")
        assert result.strip().startswith("34")

    # ── New generic cases (proves generality) ────────────────────

    def test_l2_healed_to_12_when_last_is_11(self):
        """OCR reads 'l' as '1': 'l2. Calculate...' → '12. Calculate...'."""
        ext = self._make_extractor(11)
        result = ext._ocr_heal_question_number("l2. Calculate the area")
        assert result.strip().startswith("12")

    def test_Z3_healed_to_23_when_last_is_22(self):
        """OCR reads 'Z' as '2': 'Z3) Explain...' → '23) Explain...'."""
        ext = self._make_extractor(22)
        result = ext._ocr_heal_question_number("Z3) Explain the process")
        assert result.strip().startswith("23")

    def test_S_healed_to_5_when_last_is_4(self):
        """OCR reads 'S' as '5': 'S. State the law' → '5. State the law'."""
        ext = self._make_extractor(4)
        result = ext._ocr_heal_question_number("S. State the law of")
        assert result.strip().startswith("5")

    def test_B_healed_to_8_when_last_is_7(self):
        """OCR reads 'B' as '8': 'B) Define the term' → '8) Define the term'."""
        ext = self._make_extractor(7)
        result = ext._ocr_heal_question_number("B) Define the term")
        assert result.strip().startswith("8")

    def test_no_heal_when_already_correct(self):
        """Should not modify a line that already has the correct question number."""
        ext = self._make_extractor(4)
        line = "5. What is photosynthesis?"
        result = ext._ocr_heal_question_number(line)
        assert result == line

    def test_no_heal_when_no_alphabetic_content(self):
        """Should NOT heal a line that has no alphabetic content (page number, formula)."""
        ext = self._make_extractor(5)
        line = "6 36"
        result = ext._ocr_heal_question_number(line)
        assert result == line  # No alphabetic chars after number → no heal

    def test_no_heal_when_last_q_is_zero(self):
        """No healing when no questions have been seen yet."""
        ext = self._make_extractor(0)
        line = "B) Define the term osmosis"
        result = ext._ocr_heal_question_number(line)
        assert result == line

    def test_no_heal_for_long_token(self):
        """Tokens longer than 5 chars should not be healed (not question numbers)."""
        ext = self._make_extractor(5)
        line = "ABCDEF. Some question text"
        result = ext._ocr_heal_question_number(line)
        assert result == line

    def test_gap_tolerance_heal_q_plus_2(self):
        """Should heal when the token matches expected_q+2 (gap tolerance)."""
        ext = self._make_extractor(8)
        # Token 'lO' (l=1, O=0) → expected 10 (last=8, so expected+2=10)
        result = ext._ocr_heal_question_number("lO. Determine the velocity")
        assert result.strip().startswith("10")

    def test_heal_with_tamil_content(self):
        """Should heal when rest of line contains Tamil alphabetic content."""
        ext = self._make_extractor(4)
        result = ext._ocr_heal_question_number("S. விளக்கம் தருக")
        assert result.strip().startswith("5")

    def test_heal_with_hindi_content(self):
        """Should heal when rest of line contains Hindi alphabetic content."""
        ext = self._make_extractor(4)
        result = ext._ocr_heal_question_number("S. निम्नलिखित का वर्णन")
        assert result.strip().startswith("5")


# ============================================================
# 2. Dynamic Marks Resolution Tests
# ============================================================

class TestDynamicMarksResolution:
    """Tests for _get_default_marks_for_section() — document-only evidence."""

    def _make_extractor(self, **kwargs) -> QuestionExtractor:
        ext = QuestionExtractor(board=kwargs.get("board", "Generic"), ocr_lang="eng")
        ext.prescan_marks = kwargs.get("prescan_marks", {})
        ext.section_marks = kwargs.get("section_marks", {})
        ext.instruction_ranges = kwargs.get("instruction_ranges", [])
        ext.global_counter = kwargs.get("global_counter", 1)
        return ext

    def test_returns_none_with_no_evidence(self):
        """With no document evidence, should return None."""
        ext = self._make_extractor()
        assert ext._get_default_marks_for_section("A") is None
        assert ext._get_default_marks_for_section("I") is None
        assert ext._get_default_marks_for_section("IV") is None

    def test_no_cbse_hardcoded_map(self):
        """Even with board='CBSE', should NOT return hardcoded marks without evidence."""
        ext = self._make_extractor(board="CBSE")
        # Without any document-extracted data, these should all be None
        assert ext._get_default_marks_for_section("A") is None
        assert ext._get_default_marks_for_section("B") is None
        assert ext._get_default_marks_for_section("D") is None

    def test_no_state_board_hardcoded_map(self):
        """Even with board containing 'higher'/'11th', should NOT return hardcoded marks."""
        ext = self._make_extractor(board="Tamil Nadu Higher Secondary 12th")
        assert ext._get_default_marks_for_section("I") is None
        assert ext._get_default_marks_for_section("III") is None
        assert ext._get_default_marks_for_section("IV") is None

    def test_prescan_marks_priority(self):
        """prescan_marks should be the highest priority source."""
        ext = self._make_extractor(
            prescan_marks={"A": 2, "B": 3},
            section_marks={"A": 1, "B": 5}  # lower priority
        )
        assert ext._get_default_marks_for_section("A") == 2
        assert ext._get_default_marks_for_section("B") == 3

    def test_section_marks_fallback(self):
        """section_marks used when prescan_marks don't have the section."""
        ext = self._make_extractor(
            prescan_marks={"A": 1},
            section_marks={"B": 3, "C": 5}
        )
        assert ext._get_default_marks_for_section("B") == 3
        assert ext._get_default_marks_for_section("C") == 5

    def test_instruction_ranges_by_global_counter(self):
        """instruction_ranges matched by current global_counter position."""
        ext = self._make_extractor(
            instruction_ranges=[
                {"start": 1, "end": 16, "marks": 1, "section": "A"},
                {"start": 17, "end": 21, "marks": 2, "section": "B"},
                {"start": 22, "end": 28, "marks": 3, "section": "C"},
            ],
            global_counter=18
        )
        assert ext._get_default_marks_for_section("UNKNOWN") == 2

    def test_instruction_ranges_by_section_name(self):
        """instruction_ranges matched by section name when global_counter doesn't match."""
        ext = self._make_extractor(
            instruction_ranges=[
                {"start": 1, "end": 16, "marks": 1, "section": "A"},
                {"start": 17, "end": 21, "marks": 2, "section": "B"},
            ],
            global_counter=99  # out of range
        )
        assert ext._get_default_marks_for_section("B") == 2

    def test_section_prefix_stripping(self):
        """Should handle 'SECTION_A' by stripping prefix to 'A'."""
        ext = self._make_extractor(section_marks={"A": 3})
        assert ext._get_default_marks_for_section("SECTION_A") == 3

    def test_part_used_as_fallback(self):
        """Part parameter should be checked if sec doesn't match."""
        ext = self._make_extractor(prescan_marks={"III": 5})
        assert ext._get_default_marks_for_section("UNKNOWN", part="III") == 5


# ============================================================
# 3. No Keyword Mark Override Tests
# ============================================================

class TestNoKeywordMarkOverrides:
    """Tests verifying that hardcoded keyword overrides have been removed."""

    def test_no_passage_equals_4_override(self):
        """The source code should not contain 'passage' → 4 marks override."""
        import inspect
        source = inspect.getsource(QuestionExtractor._finalize_current_question)
        # Check that the old pattern doesn't exist
        assert "final_marks = 4" not in source or "passage" not in source

    def test_no_cbse_section_a_equals_1_override(self):
        """The source code should not contain CBSE Section A → 1 mark override."""
        import inspect
        source = inspect.getsource(QuestionExtractor._finalize_current_question)
        assert "CBSE" not in source or "SECTION_A" not in source

    def test_no_ruler_compass_override(self):
        """The source code should not contain ruler/compass → 5 marks override."""
        import inspect
        source = inspect.getsource(QuestionExtractor._finalize_current_question)
        assert "ruler" not in source.lower()
        assert "compass" not in source.lower()


# ============================================================
# 4. OCR Shape Map Tests
# ============================================================

class TestOCRShapeMap:
    """Tests for the _ocr_chars_match helper and shape map integrity."""

    def _make_extractor(self) -> QuestionExtractor:
        return QuestionExtractor(board="Generic", ocr_lang="eng")

    def test_exact_match(self):
        ext = self._make_extractor()
        assert ext._ocr_chars_match("12", "12") is True

    def test_I_matches_1(self):
        ext = self._make_extractor()
        assert ext._ocr_chars_match("I", "1") is True

    def test_l_matches_1(self):
        ext = self._make_extractor()
        assert ext._ocr_chars_match("l", "1") is True

    def test_S_matches_5(self):
        ext = self._make_extractor()
        assert ext._ocr_chars_match("S", "5") is True

    def test_B_matches_8(self):
        ext = self._make_extractor()
        assert ext._ocr_chars_match("B", "8") is True

    def test_Z_matches_2(self):
        ext = self._make_extractor()
        assert ext._ocr_chars_match("Z", "2") is True

    def test_A_matches_4(self):
        ext = self._make_extractor()
        assert ext._ocr_chars_match("A", "4") is True

    def test_3B_matches_38(self):
        ext = self._make_extractor()
        assert ext._ocr_chars_match("3B", "38") is True

    def test_length_mismatch_returns_false(self):
        ext = self._make_extractor()
        assert ext._ocr_chars_match("123", "12") is False

    def test_no_confusion_returns_false(self):
        ext = self._make_extractor()
        assert ext._ocr_chars_match("X", "5") is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
