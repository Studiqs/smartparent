"""
STUDIQS® SmartParent™ (v6.2 Complete) - Academic Concept Bridge Module
Modular concept bridge delegating to the unified NLPPreprocessor.
"""

from typing import Dict, Optional
from src.smartparent.engines.nlp_preprocessor import CONCEPT_BRIDGES


class AcademicConceptBridge:
    """Harmonizes non-canonical or cross-board concept terms into canonical curriculum entities."""

    def __init__(self):
        self.bridges: Dict[str, str] = CONCEPT_BRIDGES

    def harmonize_concept(self, text: str) -> str:
        """Returns canonical curriculum concept if alias detected."""
        lowered = text.lower()
        for alias, canonical in self.bridges.items():
            if alias.lower() in lowered:
                return canonical
        return text
