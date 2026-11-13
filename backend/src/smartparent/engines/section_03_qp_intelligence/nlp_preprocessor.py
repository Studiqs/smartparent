"""
STUDIQS® SmartParent™ (v6.2 Complete) - NLP Preprocessor Engine
Engine 3: nlp_preprocessor.py

Consolidates Stem Cleaning, Domain Routing, and Academic Concept Harmonization
into a high-performance preprocessing layer for Question Paper Intelligence.

Pillars:
  1. Stem Cleaner: Strips question numbers, Roman sub-numerals, mark brackets,
     exam instructions, and LaTeX noise to isolate the pure conceptual statement.
  2. Domain Router: Multi-lexicon academic router categorizing questions into
     Mathematics, Physics, Chemistry, Biology, or Social Science sub-domains.
  3. Academic Concept Bridge: Harmonizes cross-board curriculum terminology
     (e.g., GCD <-> HCF, Ray Optics <-> Reflection and Refraction).
  4. Scenario Detector: Detects story/case-study context questions.
"""

import re
import logging
from typing import Any, Dict, List, Optional, Tuple, Union
from pydantic import BaseModel, Field, ConfigDict

from src.smartparent.engines.base_engine import BaseEngine, EngineHealthStatus

logger = logging.getLogger("STUDIQS_NLPPreprocessor")


# =============================================================================
# 1. Pydantic v2 Type-Safe Schemas
# =============================================================================

class NLPPreprocessInputSchema(BaseModel):
    """Input payload for text preprocessing."""
    model_config = ConfigDict(extra="ignore")

    raw_text: str = Field(..., min_length=1)
    question_no: Optional[Union[int, str]] = None
    subject: Optional[str] = None
    board: Optional[str] = "CBSE"
    standard_class: Optional[str] = "Class 10"


class CleanedQuestionResultSchema(BaseModel):
    """Output payload representing cleaned concept core and domain metadata."""
    model_config = ConfigDict(extra="ignore")

    question_no: Optional[Union[int, str]] = None
    original_text: str
    cleaned_stem: str
    concept_query: str
    detected_domain: str
    domain_confidence: float
    is_scenario_question: bool
    applied_bridges: List[str] = Field(default_factory=list)
    stripped_tokens: List[str] = Field(default_factory=list)


# =============================================================================
# 2. Regex Patterns for Exam Noise & Instructions
# =============================================================================

# Question number prefixes (e.g. "Q.1", "Q 14:", "12.", "(iv)", "(a)", "Section A:")
QUESTION_NUMBER_PREFIX_PATTERN = re.compile(
    r"^(?:(?:Q(?:uestion)?\.?\s*\d+[\.\:\)\-]?)|(?:\d+[\.\:\)\-])|(?:\([ivxlcdm]+\))|(?:\([a-z]\))|"
    r"(?:Section\s*[\-\–]?\s*[A-E][\:\.\-]?)|(?:Part\s*[\-\–]?\s*[I|V|X]+[\:\.\-]?))\s*",
    re.IGNORECASE
)

# Marks notations: [5 Marks], (3M), [1 x 4 = 4], [2 marks]
MARKS_NOTATION_PATTERN = re.compile(
    r"(?:\[|\()(?:(?:\d+\s*(?:x|\*)\s*\d+\s*=\s*\d+)|(?:\d+(?:\.\d+)?\s*(?:marks?|mark|m|pts?)))(?:\]|\))",
    re.IGNORECASE
)

# Exam instructional leading clauses
EXAM_INSTRUCTIONS_PATTERN = re.compile(
    r"^(?:(?:state\s+whether\s+(?:true\s+or\s+false|the\s+statement\s+is\s+true\s+or\s+false))|"
    r"(?:fill\s+in\s+the\s+blanks?)|"
    r"(?:choose\s+the\s+correct\s+(?:option|answer)(?:\s+from\s+the\s+following)?)|"
    r"(?:answer\s+(?:any\s+\d+|the\s+following)(?:\s+questions?)?)|"
    r"(?:with\s+the\s+help\s+of\s+a\s+(?:neat\s+)?labeled\s+diagram\,?\s*(?:explain|draw|describe)?)|"
    r"(?:read\s+the\s+(?:passage|case\s+study|extract)\s+given\s+below\s+and\s+answer(?:\s+the\s+following)?)|"
    r"(?:differentiate\s+between\s+(?:the\s+following)?)|"
    r"(?:give\s+(?:scientific\s+)?reasons?\s+for\s+the\s+following)|"
    r"(?:match\s+the\s+following(?:\s+columns?)?))\s*[\:\.\,\-]?\s*",
    re.IGNORECASE
)

# LaTeX command cleanup: \frac{a}{b} -> a/b, \sqrt{x} -> sqrt(x)
LATEX_FRAC_PATTERN = re.compile(r"\\frac\{([^\}]+)\}\{([^\}]+)\}")
LATEX_SQRT_PATTERN = re.compile(r"\\sqrt\{([^\}]+)\}")
LATEX_COMMANDS_PATTERN = re.compile(r"\\[a-zA-Z]+\b")


# =============================================================================
# 3. Domain Lexicons & Cross-Board Concept Bridges
# =============================================================================

DOMAIN_LEXICONS: Dict[str, List[str]] = {
    "Mathematics": [
        "algebra", "quadratic", "polynomial", "linear equation", "arithmetic progression",
        "trigonometry", "sin", "cos", "tan", "hypotenuse", "coordinate geometry",
        "triangle", "circle", "tangent", "surface area", "volume", "mensuration",
        "statistics", "mean", "median", "mode", "probability", "pythagoras",
        "matrix", "determinant", "calculus", "derivative", "integral", "vector"
    ],
    "Physics": [
        "reflection", "refraction", "mirror", "lens", "focal length", "magnification",
        "prism", "dispersion", "spectrum", "electricity", "current", "voltage", "resistance",
        "ohm's law", "circuit", "resistor", "magnetic", "magnetic field", "solenoid",
        "electromagnetic", "motor", "generator", "force", "velocity", "acceleration",
        "gravitation", "work", "power", "energy", "motion", "thermodynamics"
    ],
    "Chemistry": [
        "chemical reaction", "equation", "oxidation", "reduction", "redox", "acid", "base",
        "salt", "ph", "litmus", "neutralization", "metal", "non-metal", "corrosion",
        "carbon", "covalent", "ionic", "hydrocarbon", "alkane", "alkene", "alkyne",
        "periodic table", "atomic number", "valency", "mole", "catalyst", "exothermic",
        "endothermic", "electrolyte", "combustion", "isomerism"
    ],
    "Biology": [
        "photosynthesis", "chlorophyll", "respiration", "aerobic", "anaerobic",
        "digestive", "enzyme", "circulatory", "heart", "artery", "vein", "xylem",
        "phloem", "excretion", "kidney", "nephron", "nervous system", "neuron",
        "brain", "hormone", "reproduction", "fertilization", "dna", "heredity",
        "evolution", "mendel", "chromosome", "ecosystem", "food chain", "biodiversity"
    ],
    "Social Science": [
        "nationalism", "freedom struggle", "gandhi", "satyagraha", "revolt", "french revolution",
        "democracy", "constitution", "parliament", "federalism", "election", "judiciary",
        "resources", "agriculture", "minerals", "manufacturing", "climate", "soil",
        "monsoon", "development", "gdp", "money", "banking", "globalization", "consumer rights"
    ]
}

# Cross-Board Concept Bridges (Standardizing terminology to canonical representations)
CONCEPT_BRIDGES: Dict[str, str] = {
    "gcd": "HCF and LCM",
    "greatest common divisor": "HCF and LCM",
    "highest common factor": "HCF and LCM",
    "ray optics": "Light Reflection and Refraction",
    "optics": "Light Reflection and Refraction",
    "current electricity": "Electricity and Circuits",
    "organic chemistry": "Carbon and Its Compounds",
    "genetics": "Heredity and Evolution",
    "laws of motion": "Force and Laws of Motion",
    "mensuration": "Surface Areas and Volumes",
    "solid figures": "Surface Areas and Volumes",
    "chemical changes": "Chemical Reactions and Equations",
    "life processes": "Life Processes and Nutrition",
    "magnetic effect": "Magnetic Effects of Electric Current"
}

# Scenario context indicators
SCENARIO_INDICATORS = [
    "ramesh", "suresh", "anita", "priya", "student observed", "in an experiment",
    "a teacher showed", "in a village", "a farmer", "a factory", "during a laboratory activity"
]


# =============================================================================
# 4. Production NLP Preprocessor Engine Implementation
# =============================================================================

class NLPPreprocessor(BaseEngine):
    """
    Engine 3: NLP Preprocessor & Concept Normalization Engine.
    
    Transforms noisy question paper text into clean, domain-tagged concept queries
    optimized for semantic vector similarity mapping.
    """

    def __init__(self, failure_threshold: int = 5):
        super().__init__(name="NLPPreprocessor", failure_threshold=failure_threshold)

    # -------------------------------------------------------------------------
    # BaseEngine Template Method Lifecycle Hooks
    # -------------------------------------------------------------------------

    def validate_input(self, input_data: Any) -> NLPPreprocessInputSchema:
        """Validates raw question payload."""
        if not input_data:
            raise ValueError("Input text payload cannot be empty.")

        if isinstance(input_data, str):
            return NLPPreprocessInputSchema(raw_text=input_data.strip())

        if isinstance(input_data, NLPPreprocessInputSchema):
            return input_data

        if hasattr(input_data, "model_dump"):
            data = input_data.model_dump()
        elif hasattr(input_data, "dict"):
            data = input_data.dict()
        elif isinstance(input_data, dict):
            data = dict(input_data)
            if "raw_text" not in data and "question_text" in data:
                data["raw_text"] = data["question_text"]
            elif "raw_text" not in data and "text" in data:
                data["raw_text"] = data["text"]
        else:
            raise ValueError(f"Unsupported input type for NLPPreprocessor: {type(input_data)}")

        return NLPPreprocessInputSchema(**data)

    def execute_core(self, payload: NLPPreprocessInputSchema) -> CleanedQuestionResultSchema:
        """Executes full cleaning, instruction stripping, domain classification, and bridge harmonization."""
        raw = payload.raw_text.strip()
        stripped_tokens: List[str] = []

        # 1. Strip Question Number Prefixes
        cleaned, prefix_match = self._strip_question_prefix(raw)
        if prefix_match:
            stripped_tokens.append(f"PREFIX: {prefix_match}")

        # 2. Strip Marks Notations
        cleaned, marks_match = self._strip_marks_notations(cleaned)
        if marks_match:
            stripped_tokens.extend([f"MARK: {m}" for m in marks_match])

        # 3. Strip Exam Instructional Clauses
        cleaned, instr_match = self._strip_instructions(cleaned)
        if instr_match:
            stripped_tokens.append(f"INSTRUCTION: {instr_match}")

        # 4. Normalize LaTeX and Whitespace
        cleaned = self._clean_latex_and_symbols(cleaned)

        # 5. Detect Scenario / Story Context
        is_scenario = any(ind in cleaned.lower() for ind in SCENARIO_INDICATORS)

        # 6. Domain Routing
        domain, conf = self._classify_domain(cleaned, payload.subject)

        # 7. Apply Concept Bridges
        concept_query, applied_bridges = self._apply_concept_bridges(cleaned)

        return CleanedQuestionResultSchema(
            question_no=payload.question_no,
            original_text=raw,
            cleaned_stem=cleaned,
            concept_query=concept_query,
            detected_domain=domain,
            domain_confidence=conf,
            is_scenario_question=is_scenario,
            applied_bridges=applied_bridges,
            stripped_tokens=stripped_tokens
        )

    def fallback(self, error: Exception, input_data: Any) -> CleanedQuestionResultSchema:
        """Safe degraded fallback returning sanitized plain text without crashing."""
        logger.warning(f"[NLPPreprocessor] Fallback invoked due to error: {error}")
        text = ""
        q_no = None

        if isinstance(input_data, str):
            text = input_data
        elif isinstance(input_data, dict):
            text = str(input_data.get("raw_text") or input_data.get("question_text") or "")
            q_no = input_data.get("question_no")

        cleaned = re.sub(r"\s+", " ", text).strip()
        return CleanedQuestionResultSchema(
            question_no=q_no,
            original_text=text,
            cleaned_stem=cleaned,
            concept_query=cleaned,
            detected_domain="General",
            domain_confidence=0.0,
            is_scenario_question=False,
            applied_bridges=[],
            stripped_tokens=["FALLBACK_INVOKED"]
        )

    # -------------------------------------------------------------------------
    # Core Cleaning & Parsing Algorithms
    # -------------------------------------------------------------------------

    def _strip_question_prefix(self, text: str) -> Tuple[str, Optional[str]]:
        """Strips leading question numbers like 'Q.14 (a):'."""
        match = QUESTION_NUMBER_PREFIX_PATTERN.match(text)
        if match:
            prefix = match.group(0).strip()
            return text[match.end():].strip(), prefix
        return text, None

    def _strip_marks_notations(self, text: str) -> Tuple[str, List[str]]:
        """Strips marks tags like '[3 Marks]' or '(5M)'."""
        matches = MARKS_NOTATION_PATTERN.findall(text)
        cleaned = MARKS_NOTATION_PATTERN.sub("", text)
        return re.sub(r"\s+", " ", cleaned).strip(), matches

    def _strip_instructions(self, text: str) -> Tuple[str, Optional[str]]:
        """Strips generic clauses like 'State whether true or false:'."""
        match = EXAM_INSTRUCTIONS_PATTERN.match(text)
        if match:
            instr = match.group(0).strip()
            return text[match.end():].strip(), instr
        return text, None

    def _clean_latex_and_symbols(self, text: str) -> str:
        """Cleans LaTeX fractions, square roots, and formatting symbols."""
        # \frac{a}{b} -> a/b
        res = LATEX_FRAC_PATTERN.sub(r"\1/\2", text)
        # \sqrt{x} -> sqrt(x)
        res = LATEX_SQRT_PATTERN.sub(r"sqrt(\1)", res)
        # \times -> *
        res = res.replace(r"\times", "*").replace(r"\pm", "±")
        # remove leftover commands like \degree
        res = LATEX_COMMANDS_PATTERN.sub("", res)
        # Normalize multiple spaces
        return re.sub(r"\s+", " ", res).strip()

    def _classify_domain(self, text: str, subject_hint: Optional[str] = None) -> Tuple[str, float]:
        """Classifies text into primary academic domain based on lexicon hits."""
        lowered = text.lower()
        domain_scores: Dict[str, int] = {}

        for domain, keywords in DOMAIN_LEXICONS.items():
            score = sum(1 for kw in keywords if re.search(r"\b" + re.escape(kw) + r"\b", lowered))
            domain_scores[domain] = score

        best_domain = max(domain_scores, key=domain_scores.get)
        max_score = domain_scores[best_domain]

        if max_score == 0:
            if subject_hint and subject_hint.title() in DOMAIN_LEXICONS:
                return subject_hint.title(), 0.5
            return "General", 0.0

        confidence = min(1.0, 0.4 + (max_score * 0.15))
        return best_domain, round(confidence, 2)

    def _apply_concept_bridges(self, text: str) -> Tuple[str, List[str]]:
        """Harmonizes non-canonical terms into standard cross-curriculum concepts."""
        lowered = text.lower()
        applied: List[str] = []
        enriched_query = text

        for alias, canonical in CONCEPT_BRIDGES.items():
            if re.search(r"\b" + re.escape(alias) + r"\b", lowered):
                applied.append(f"{alias} -> {canonical}")
                if canonical.lower() not in lowered:
                    enriched_query = f"{enriched_query} ({canonical})"

        return enriched_query, applied


# Alias for backward compatibility
NLPPreprocessorEngine = NLPPreprocessor
