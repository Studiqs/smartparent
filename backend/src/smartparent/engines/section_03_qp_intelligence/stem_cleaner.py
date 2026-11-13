"""
STUDIQS® SmartParent™ (v6.2 Complete) - Stem Cleaner Module
Modular stem cleaner delegating to the unified NLPPreprocessor.
"""

from src.smartparent.engines.nlp_preprocessor import (
    NLPPreprocessor,
    QUESTION_NUMBER_PREFIX_PATTERN,
    MARKS_NOTATION_PATTERN,
    EXAM_INSTRUCTIONS_PATTERN,
)


class StemCleaner:
    """Provides pure stem extraction stripping question numbering, marks, and boilerplate."""

    def __init__(self):
        self.preprocessor = NLPPreprocessor()

    def clean_stem(self, text: str) -> str:
        """Returns isolated conceptual statement without question numbering or mark brackets."""
        res = self.preprocessor.execute(text)
        return res.cleaned_stem
