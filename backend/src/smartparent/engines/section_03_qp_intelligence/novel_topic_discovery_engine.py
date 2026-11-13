"""
STUDIQS® SmartParent™ (v6.2 Complete) - Novel Topic Discovery Engine
Engine: novel_topic_discovery_engine.py

Discovers out-of-syllabus, newly updated, and novel curriculum concepts
from unmapped or low-confidence questions without force-mapping to wrong existing nodes.

Key Features:
  1. General Scenario Filter: Screens out story-based / generic scenario questions
     to prevent curriculum ontology pollution.
  2. Nearest Chapter Matching: Matches unmapped stems to candidate parent chapters
     using domain lexicons and keyword clustering.
  3. Salient Concept Extraction: Extracts concise candidate topic titles using
     academic compound noun extraction.
  4. Canonical Topic ID Minting: Formats candidate IDs following [Subject][Class][Chapter][Seq].
  5. Admin Review Queue: Enqueues candidate topics with confidence calibration
     (High >= 0.60, Medium 0.40 - 0.59, Low < 0.40) for human approval.
"""

import re
import logging
from typing import Any, Dict, List, Optional, Tuple, Union
from pydantic import BaseModel, Field, ConfigDict

from src.smartparent.engines.base_engine import BaseEngine, EngineHealthStatus

logger = logging.getLogger("STUDIQS_NovelTopicDiscoveryEngine")


# =============================================================================
# 1. Pydantic v2 Type-Safe Schemas
# =============================================================================

class UnmappedQuestionSchema(BaseModel):
    """Input representation of an unmapped or low-confidence question."""
    model_config = ConfigDict(extra="ignore")

    question_no: Optional[Union[int, str]] = None
    question_text: str = Field(..., min_length=3)
    subject: str = "General"
    grade: str = "Class 10"
    board: str = "CBSE"
    current_confidence: float = 0.0


class NovelTopicCandidateSchema(BaseModel):
    """Candidate topic discovered from unmapped question text."""
    model_config = ConfigDict(extra="ignore")

    candidate_topic_id: str
    candidate_topic_name: str
    suggested_chapter: str
    subject: str
    grade: str
    confidence_level: str  # 'HIGH', 'MEDIUM', 'LOW'
    similarity_score: float
    sample_question_no: Optional[Union[int, str]] = None
    sample_question_stem: str
    review_status: str = "PENDING_ADMIN_REVIEW"
    recommendation: str


class DiscoveryResultSchema(BaseModel):
    """Aggregated output from novel topic discovery process."""
    model_config = ConfigDict(extra="ignore")

    total_unmapped_analyzed: int
    novel_topics_discovered: List[NovelTopicCandidateSchema] = Field(default_factory=list)
    general_scenarios_filtered: List[Dict[str, Any]] = Field(default_factory=list)
    summary: Dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# 2. Standard Curriculum Chapter Lexicons
# =============================================================================

CHAPTER_LEXICONS: Dict[str, Dict[str, List[str]]] = {
    "Science": {
        "Chemical Reactions and Equations": ["chemical reaction", "balanced equation", "combination", "decomposition", "displacement", "redox", "corrosion", "rancidity"],
        "Acids Bases and Salts": ["acid", "base", "salt", "ph", "indicator", "litmus", "neutralization", "chlor-alkali", "bleaching powder", "baking soda", "plaster of paris"],
        "Metals and Non-Metals": ["metal", "non-metal", "malleability", "ductility", "reactivity series", "ionic bond", "metallurgy", "roasting", "calcination", "alloy"],
        "Carbon and its Compounds": ["carbon", "covalent bond", "tetravalency", "catenation", "allotrope", "hydrocarbon", "alkane", "alkene", "alkyne", "functional group", "esterification", "saponification"],
        "Life Processes": ["photosynthesis", "nutrition", "autotrophic", "heterotrophic", "respiration", "aerobic", "anaerobic", "xylem", "phloem", "dialysis", "excretion", "nephron"],
        "Control and Coordination": ["nervous system", "neuron", "synapse", "reflex arc", "brain", "hormone", "endocrine", "auxin", "gibberellin", "cytokinin"],
        "How do Organisms Reproduce": ["reproduction", "asexual", "binary fission", "budding", "vegetative propagation", "pollination", "fertilization", "contraception"],
        "Heredity": ["heredity", "variation", "mendel", "monohybrid", "dihybrid", "dominant", "recessive", "sex determination", "chromosome"],
        "Light Reflection and Refraction": ["reflection", "refraction", "concave", "convex", "mirror", "lens", "focal length", "magnification", "snell's law", "refractive index", "power of lens"],
        "The Human Eye and Colourful World": ["human eye", "myopia", "hypermetropia", "presbyopia", "prism", "dispersion", "spectrum", "atmospheric refraction", "scattering of light", "tyndall effect"],
        "Electricity": ["electric current", "potential difference", "voltage", "ohm's law", "resistance", "resistivity", "series", "parallel", "joule's heating", "electric power"],
        "Magnetic Effects of Electric Current": ["magnetic field", "field lines", "right hand thumb rule", "solenoid", "fleming's left hand rule", "electric motor", "electromagnetic induction", "generator"],
        "Our Environment": ["ecosystem", "food chain", "food web", "trophic level", "ozone layer", "biological magnification", "waste management"]
    },
    "Mathematics": {
        "Real Numbers": ["fundamental theorem of arithmetic", "prime factorization", "irrational number", "hcf", "lcm"],
        "Polynomials": ["zeros of polynomial", "quadratic polynomial", "cubic polynomial", "coefficients", "parabola"],
        "Pair of Linear Equations in Two Variables": ["linear equations", "substitution method", "elimination method", "graphical method", "consistency"],
        "Quadratic Equations": ["quadratic equation", "factorization", "quadratic formula", "discriminant", "nature of roots"],
        "Arithmetic Progressions": ["arithmetic progression", "common difference", "nth term", "sum of n terms"],
        "Triangles": ["similarity of triangles", "basic proportionality theorem", "thales theorem", "aaa similarity", "sas similarity"],
        "Coordinate Geometry": ["distance formula", "section formula", "midpoint formula", "collinear points"],
        "Introduction to Trigonometry": ["trigonometric ratios", "sin", "cos", "tan", "trigonometric identities", "specific angles"],
        "Some Applications of Trigonometry": ["angle of elevation", "angle of depression", "heights and distances", "line of sight"],
        "Circles": ["tangent to circle", "point of contact", "radius and tangent", "lengths of tangents"],
        "Areas Related to Circles": ["sector of circle", "segment of circle", "area of sector", "arc length"],
        "Surface Areas and Volumes": ["surface area", "volume", "cylinder", "cone", "sphere", "hemisphere", "combination of solids"],
        "Statistics": ["mean", "median", "mode", "grouped data", "assumed mean method", "step deviation"],
        "Probability": ["probability", "elementary event", "complementary event", "cards", "dice", "coins"]
    }
}

# Stopwords to clean from extracted noun chunks
EXTRACT_STOPWORDS = {
    "a", "an", "the", "what", "is", "explain", "describe", "define", "why", "how",
    "calculate", "find", "determine", "state", "show", "give", "write", "which",
    "whose", "where", "diagram", "figure", "question", "following", "between",
    "difference", "briefly", "neat", "labeled", "given", "below", "with", "from"
}


# =============================================================================
# 3. Production Novel Topic Discovery Engine Implementation
# =============================================================================

class NovelTopicDiscoveryEngine(BaseEngine):
    """
    Engine: Novel Topic Discovery Engine (novel_topic_discovery_engine.py)
    
    Identifies out-of-syllabus questions and proposes candidate new curriculum topics
    for human review, preserving knowledge graph integrity.
    """

    def __init__(self, failure_threshold: int = 5):
        super().__init__(name="NovelTopicDiscoveryEngine", failure_threshold=failure_threshold)

    # -------------------------------------------------------------------------
    # BaseEngine Template Method Lifecycle Hooks
    # -------------------------------------------------------------------------

    def validate_input(self, input_data: Any) -> List[UnmappedQuestionSchema]:
        """Validates list of unmapped question payloads."""
        if not input_data:
            raise ValueError("Input questions list cannot be empty.")

        questions: List[UnmappedQuestionSchema] = []

        if isinstance(input_data, dict):
            raw_list = input_data.get("unmapped_questions") or input_data.get("questions") or [input_data]
        elif isinstance(input_data, list):
            raw_list = input_data
        else:
            raise ValueError(f"Unsupported input type for NovelTopicDiscoveryEngine: {type(input_data)}")

        for item in raw_list:
            if isinstance(item, UnmappedQuestionSchema):
                questions.append(item)
            elif isinstance(item, dict):
                q_text = item.get("question_text") or item.get("raw_text") or item.get("text") or ""
                if len(q_text.strip()) >= 3:
                    questions.append(UnmappedQuestionSchema(
                        question_no=item.get("question_no"),
                        question_text=q_text.strip(),
                        subject=item.get("subject", "General"),
                        grade=item.get("grade", item.get("standard_class", "Class 10")),
                        board=item.get("board", "CBSE"),
                        current_confidence=float(item.get("current_confidence", item.get("confidence", 0.0)))
                    ))

        if not questions:
            raise ValueError("No valid unmapped questions with question_text found in input.")

        return questions

    def execute_core(self, questions: List[UnmappedQuestionSchema]) -> DiscoveryResultSchema:
        """Executes novel topic discovery, scenario filtering, and candidate proposal."""
        novel_discoveries: List[NovelTopicCandidateSchema] = []
        general_scenarios: List[Dict[str, Any]] = []
        topic_seq_counter = 101

        for q in questions:
            text = q.question_text

            # 1. Screen for General / Story Scenarios
            if self._is_general_scenario(text):
                general_scenarios.append({
                    "question_no": q.question_no,
                    "question_text": text,
                    "reason": "General scenario / context without isolated curriculum entity"
                })
                continue

            # 2. Nearest Chapter Matching
            matched_chapter, chapter_score = self._match_nearest_chapter(text, q.subject)

            # 3. Salient Topic Name Extraction
            candidate_topic_name = self._extract_salient_topic_name(text)

            # 4. Mint Candidate Topic ID
            candidate_id = self._mint_candidate_topic_id(
                subject=q.subject,
                grade=q.grade,
                chapter=matched_chapter,
                seq=topic_seq_counter
            )
            topic_seq_counter += 1

            # 5. Calibrate Confidence
            if chapter_score >= 0.60:
                conf_level = "HIGH"
                rec = "Candidate syllabus expansion: High relevance to parent chapter. Recommend approval."
            elif chapter_score >= 0.35:
                conf_level = "MEDIUM"
                rec = "Potential niche or updated topic. Recommend subject teacher review."
            else:
                conf_level = "LOW"
                rec = "Interdisciplinary or non-standard formulation. Check if question is valid."

            novel_discoveries.append(NovelTopicCandidateSchema(
                candidate_topic_id=candidate_id,
                candidate_topic_name=candidate_topic_name,
                suggested_chapter=matched_chapter,
                subject=q.subject,
                grade=q.grade,
                confidence_level=conf_level,
                similarity_score=round(chapter_score, 2),
                sample_question_no=q.question_no,
                sample_question_stem=text,
                review_status="PENDING_ADMIN_REVIEW",
                recommendation=rec
            ))

        summary = {
            "total_questions_processed": len(questions),
            "novel_topics_proposed": len(novel_discoveries),
            "general_scenarios_filtered": len(general_scenarios),
            "high_confidence_candidates": sum(1 for d in novel_discoveries if d.confidence_level == "HIGH"),
            "unique_chapters_impacted": list(set(d.suggested_chapter for d in novel_discoveries))
        }

        return DiscoveryResultSchema(
            total_unmapped_analyzed=len(questions),
            novel_topics_discovered=novel_discoveries,
            general_scenarios_filtered=general_scenarios,
            summary=summary
        )

    def fallback(self, error: Exception, input_data: Any) -> DiscoveryResultSchema:
        """Safe degraded fallback preventing discovery crashes."""
        logger.warning(f"[NovelTopicDiscoveryEngine] Fallback triggered due to error: {error}")
        return DiscoveryResultSchema(
            total_unmapped_analyzed=0,
            novel_topics_discovered=[],
            general_scenarios_filtered=[],
            summary={"status": "DEGRADED", "error": str(error)[:100]}
        )

    # -------------------------------------------------------------------------
    # Discovery Algorithms
    # -------------------------------------------------------------------------

    def _is_general_scenario(self, text: str) -> bool:
        """Determines if question is a pure situational word-problem devoid of domain keywords."""
        lowered = text.lower()
        scenario_markers = ["suppose a student", "in a school sports day", "ramesh bought", "in a village"]
        has_marker = any(m in lowered for m in scenario_markers)
        
        # Check if text contains almost zero academic terms
        total_domain_hits = 0
        for subj_chapters in CHAPTER_LEXICONS.values():
            for words in subj_chapters.values():
                total_domain_hits += sum(1 for w in words if w in lowered)
                if total_domain_hits >= 2:
                    return False

        return has_marker and total_domain_hits <= 1

    def _match_nearest_chapter(self, text: str, subject: str) -> Tuple[str, float]:
        """Matches unmapped text against chapter taxonomy lexicons."""
        lowered = text.lower()
        subj_key = "Science" if "sci" in subject.lower() or "phys" in subject.lower() or "chem" in subject.lower() or "bio" in subject.lower() else "Mathematics"
        taxonomy = CHAPTER_LEXICONS.get(subj_key, CHAPTER_LEXICONS["Science"])

        best_chapter = "General Curriculum"
        best_score = 0.0

        for chapter, keywords in taxonomy.items():
            matches = sum(1 for kw in keywords if re.search(r"\b" + re.escape(kw) + r"\b", lowered))
            if matches > 0:
                score = min(0.95, 0.35 + (matches * 0.20))
                if score > best_score:
                    best_score = score
                    best_chapter = chapter

        if best_score == 0.0:
            best_chapter = list(taxonomy.keys())[0] if taxonomy else "General Concepts"
            best_score = 0.25

        return best_chapter, best_score

    def _extract_salient_topic_name(self, text: str) -> str:
        """Extracts candidate title from key noun phrases and academic terminology."""
        clean = re.sub(r"[^\w\s\-\/]", " ", text)
        tokens = [w for w in clean.split() if w.lower() not in EXTRACT_STOPWORDS and len(w) > 2]

        if not tokens:
            return "Novel Conceptual Application"

        # Form a 2 to 4 word candidate topic name
        candidate_tokens = tokens[:4]
        title = " ".join(candidate_tokens).title()
        return title

    def _mint_candidate_topic_id(self, subject: str, grade: str, chapter: str, seq: int) -> str:
        """Mints standardized candidate topic identifier."""
        sub_code = "MTH" if "math" in subject.lower() else "SCI"
        grade_num = re.findall(r"\d+", grade)
        grade_code = grade_num[0] if grade_num else "10"
        
        # 2-letter chapter abbreviation
        ch_words = re.findall(r"\b[A-Za-z]", chapter)
        ch_code = "".join(ch_words[:2]).upper() if len(ch_words) >= 2 else "GN"

        return f"CBSE{grade_code}{sub_code}-{ch_code}{seq}"
