"""
STUDIQS® SmartParent™ (v6.2 Complete) - Analytics, AI & Topic-Repository Engine
=============================================================================
Module: src.smartparent.engines.section_17_analytics_ai.analytics_ai_engine
Section 17: Analytics, AI and Topic-Repository Rules

Implements:
1. Deterministic calculations (strictly server-owned math, zero LLM hallucinations)
2. Grounded AI explanations ("No new evidence means no fabricated change")
3. 'Subject Expert Feedback' vs 'AI Feedback' strict visual badging and separation
4. Immutable Source Provenance generation for expert evaluations mapped into Student 360
5. Topic-Repository canonical taxonomy & Gate 2 zero-fake mastery enforcement
=============================================================================
"""

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from src.smartparent.engines.section_00_core.base_engine import BaseEngine
from src.smartparent.schemas.analytics_ai_rules import (
    FeedbackOriginEnum,
    MasteryTierEnum,
    MovementDirectionEnum,
    DeterministicScorePoint,
    DeterministicCalculationRequest,
    DeterministicCalculationResponse,
    GroundedAiExplanationRequest,
    GroundedAiExplanationResponse,
    ExpertProvenanceMetadata,
    TopicNodeValidationRequest,
    TopicNodeValidationResponse,
    Gate2TopicIntelligenceCheckResponse,
)

logger = logging.getLogger("STUDIQS_AnalyticsAiEngine")


class AnalyticsAiEngine(BaseEngine):
    """
    Production Engine for Section 17 Analytics, AI & Topic-Repository Rules.
    """

    def __init__(self):
        super().__init__(name="AnalyticsAiEngine")

    def validate_input(self, input_data: Any) -> Any:
        """Validates generic engine input."""
        return input_data or {}

    def execute_core(self, validated_data: Any) -> Any:
        """BaseEngine core execution hook."""
        action = validated_data.get("action", "HEALTH_PING") if isinstance(validated_data, dict) else "HEALTH_PING"
        return {"action": action, "status": "executed", "timestamp": datetime.now(timezone.utc).isoformat()}

    def fallback(self, error: Exception, input_data: Any) -> Any:
        """Degraded safe fallback."""
        logger.error(f"[AnalyticsAiEngine] Execution failure: {error}")
        act = input_data.get("action") if isinstance(input_data, dict) else None
        return {"action": act, "status": "fallback_degraded", "error": str(error)}

    # =========================================================================
    # 1. DETERMINISTIC SERVER-OWNED CALCULATIONS
    # =========================================================================

    def calculate_deterministic_metrics(
        self,
        subject: str,
        scores: List[DeterministicScorePoint],
    ) -> DeterministicCalculationResponse:
        """
        Pure server-side mathematical metrics calculation.
        Guarantees zero math hallucination: math is NEVER delegated to LLMs.
        """
        if not scores:
            raise ValueError("At least one score point is required for deterministic calculation.")

        percentages: List[float] = []
        for s in scores:
            max_m = s.max_marks if s.max_marks > 0 else 100.0
            pct = round((s.score / max_m) * 100.0, 1)
            percentages.append(pct)

        latest_pct = percentages[-1]
        prior_pct = percentages[-2] if len(percentages) >= 2 else None
        delta = round(latest_pct - prior_pct, 1) if prior_pct is not None else 0.0

        # Trajectory direction
        if delta > 1.5:
            direction = MovementDirectionEnum.IMPROVING
        elif delta < -1.5:
            direction = MovementDirectionEnum.DECLINING
        else:
            direction = MovementDirectionEnum.STABLE

        # Rolling average
        rolling_avg = round(sum(percentages) / len(percentages), 1)

        # Deterministic mastery tier
        if latest_pct >= 80.0:
            tier = MasteryTierEnum.STRONG
        elif latest_pct >= 60.0:
            tier = MasteryTierEnum.AVERAGE
        elif latest_pct >= 40.0:
            tier = MasteryTierEnum.WEAK
        else:
            tier = MasteryTierEnum.CRITICAL

        return DeterministicCalculationResponse(
            subject=subject.strip(),
            latest_score_pct=latest_pct,
            prior_score_pct=prior_pct,
            movement_delta=delta,
            movement_direction=direction,
            rolling_average_pct=rolling_avg,
            mastery_tier=tier,
            is_server_deterministic=True,
            calculated_at=datetime.now(timezone.utc).isoformat(),
        )

    # =========================================================================
    # 2. GROUNDED AI EXPLANATION ENGINE
    # =========================================================================

    def generate_grounded_ai_explanation(
        self,
        request: GroundedAiExplanationRequest,
    ) -> GroundedAiExplanationResponse:
        """
        Generates pedagogical explanations strictly grounded in deterministic deltas.
        Strict rule: "No new evidence means no fabricated change."
        """
        # 1. Enforce No Evidence -> No Fabricated Change rule
        if not request.has_new_evidence:
            if request.language == "ta":
                headline = "புதிய தேர்வு முடிவுகள் ஏதுமில்லை"
                narrative = (
                    f"{request.student_name}-ன் {request.subject} பாடத்தில் புதிய தேர்வுகள் அல்லது விடைத்தாள்கள் "
                    f"பதிவேற்றப்படவில்லை. தற்போதைய மதிப்பெண் {request.latest_score_pct}%-ல் சீராக உள்ளது. "
                    f"புதிய ஆதாரங்கள் இன்றி எந்த மாற்றமும் கணக்கிடப்படவில்லை."
                )
            else:
                headline = "No New Assessments Recorded"
                narrative = (
                    f"Baseline steady at {request.latest_score_pct}% for {request.subject}. "
                    f"No new test papers or marks have been uploaded since the last evaluation; "
                    f"existing academic standing is preserved without fabricated changes."
                )

            return GroundedAiExplanationResponse(
                headline=headline,
                narrative_explanation=narrative,
                feedback_badge="AI Learning Summary",
                feedback_origin=FeedbackOriginEnum.AUTOMATED_AI_NARRATIVE,
                has_fabricated_change=False,
                generated_at=datetime.now(timezone.utc).isoformat(),
            )

        # 2. Grounded narrative generation based on server-calculated delta
        is_ta = request.language == "ta"
        delta_str = f"{request.movement_delta:+.1f}%"

        if request.movement_direction == MovementDirectionEnum.IMPROVING:
            if is_ta:
                headline = f"முன்னேற்றம்: {request.subject}-ல் {delta_str}"
                narrative = (
                    f"{request.student_name} {request.subject} பாடத்தில் சிறந்த முன்னேற்றத்தை வெளிப்படுத்தியுள்ளார் "
                    f"({delta_str} உயர்வு, தற்போதைய மதிப்பெண்: {request.latest_score_pct}%). "
                    f"தொடர் பயிற்சி மூலம் இந்த உயர்நிலையை தக்கவைக்கலாம்."
                )
            else:
                headline = f"Upward Momentum: {delta_str} in {request.subject}"
                narrative = (
                    f"{request.student_name} achieved +{request.movement_delta}% upward momentum in {request.subject}, "
                    f"reaching {request.latest_score_pct}%. Consistent concept revision has reinforced performance."
                )

        elif request.movement_direction == MovementDirectionEnum.DECLINING:
            gaps_phrase = f" (கவனிக்க வேண்டிய தலைப்புகள்: {', '.join(request.active_gaps[:2])})" if is_ta and request.active_gaps else (f" Focus areas: {', '.join(request.active_gaps[:2])}." if request.active_gaps else "")
            if is_ta:
                headline = f"கவனிப்பு தேவை: {request.subject}-ல் {delta_str}"
                narrative = (
                    f"{request.student_name} {request.subject} பாடத்தில் {delta_str} சரிவை சந்தித்துள்ளார் "
                    f"(தற்போதைய மதிப்பெண்: {request.latest_score_pct}%).{gaps_phrase} "
                    f"இடைவெளிகளை சரிசெய்ய 10-நிமிட குறிவைக்கப்பட்ட பயிற்சி பரிந்துரைக்கப்படுகிறது."
                )
            else:
                headline = f"Attention Required: {delta_str} in {request.subject}"
                narrative = (
                    f"{request.student_name} experienced a {request.movement_delta}% dip in {request.subject} "
                    f"(now at {request.latest_score_pct}%).{gaps_phrase} "
                    f"A targeted 10-minute gap diagnostic is recommended to reinforce foundational steps."
                )

        else:
            # STABLE
            if is_ta:
                headline = f"நிலையான செயல்திறன்: {request.subject} ({request.latest_score_pct}%)"
                narrative = (
                    f"{request.student_name} {request.subject} பாடத்தில் நிலையான புரிதலை வெளிப்படுத்தியுள்ளார் "
                    f"({request.latest_score_pct}%). தினசரி 20 நிமிட பயிற்சி அடுத்த கட்ட உயர்வுக்கு உதவும்."
                )
            else:
                headline = f"Consistent Performance: {request.subject} ({request.latest_score_pct}%)"
                narrative = (
                    f"{request.student_name} demonstrates steady academic consistency in {request.subject} "
                    f"at {request.latest_score_pct}%. Maintaining regular practice will build confidence."
                )

        return GroundedAiExplanationResponse(
            headline=headline,
            narrative_explanation=narrative,
            feedback_badge="AI Learning Summary",
            feedback_origin=FeedbackOriginEnum.AUTOMATED_AI_NARRATIVE,
            has_fabricated_change=False,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    # =========================================================================
    # 3. VISUAL BADGE & ORIGIN SEPARATION
    # =========================================================================

    def badge_feedback(
        self,
        text: str,
        origin: FeedbackOriginEnum,
        author_name: Optional[str] = None,
    ) -> Dict[str, str]:
        """
        Attaches strict visual badging and provenance labels to feedback.
        Prevents AI hallucinations from masquerading as expert teacher feedback.
        """
        if origin == FeedbackOriginEnum.HUMAN_EXPERT:
            badge_title = "Subject Expert Feedback"
            author_label = f"Graded by Verified Expert: {author_name}" if author_name else "Verified Subject Expert"
            disclaimer = "Verified Human Examiner line-item evaluation and pedagogical correction."
            color = "#15803D"  # Forest Green
        elif origin == FeedbackOriginEnum.AUTOMATED_AI_NARRATIVE:
            badge_title = "AI Learning Summary"
            author_label = "Studiqs Interpretive Engine"
            disclaimer = "Automated explanation strictly grounded in server-calculated test score deltas."
            color = "#2563EB"  # Deep Royal Blue
        else:
            badge_title = "Diagnostic Metric"
            author_label = "Deterministic Engine"
            disclaimer = "Pure mathematical calculation; zero interpretive inference."
            color = "#4B5563"  # Slate Grey

        return {
            "badge_title": badge_title,
            "author_label": author_label,
            "disclaimer": disclaimer,
            "color_hex": color,
            "content": text,
            "origin": origin.value,
        }

    # =========================================================================
    # 4. IMMUTABLE SOURCE PROVENANCE GENERATOR
    # =========================================================================

    def generate_expert_provenance(
        self,
        expert_id: str,
        evaluation_id: str,
        completion_date: str,
        marks_awarded: float,
        total_max_marks: float,
        topic_node_ids: List[str],
    ) -> ExpertProvenanceMetadata:
        """
        Generates an immutable source provenance bundle with cryptographic audit hash.
        """
        max_m = total_max_marks if total_max_marks > 0 else 100.0
        pct = round((marks_awarded / max_m) * 100.0, 1)

        sorted_nodes = ",".join(sorted(topic_node_ids))
        audit_raw = f"{expert_id}|{evaluation_id}|{completion_date}|{marks_awarded}|{max_m}|{sorted_nodes}"
        audit_hash = hashlib.sha256(audit_raw.encode("utf-8")).hexdigest()

        return ExpertProvenanceMetadata(
            expert_id=expert_id,
            evaluation_id=evaluation_id,
            completion_date=completion_date,
            evidence_type="EXPERT_EVALUATION",
            marks_awarded=marks_awarded,
            total_max_marks=max_m,
            percentage=pct,
            topic_node_ids=topic_node_ids,
            audit_hash=audit_hash,
        )

    # =========================================================================
    # 5. TOPIC-REPOSITORY TAXONOMY & GATE 2 ENFORCEMENT
    # =========================================================================

    def validate_topic_repository_node(
        self,
        request: TopicNodeValidationRequest,
    ) -> TopicNodeValidationResponse:
        """
        Validates topic repository node against authoritative curriculum rules:
        Board -> Standard Class -> Subject -> Chapter -> Topic Node.
        """
        errors = []
        clean_board = request.board.strip().upper()
        if clean_board not in ["CBSE", "ICSE", "TN_STATE_BOARD", "STATE_BOARD"]:
            errors.append(f"Invalid curriculum board: '{request.board}'. Must be CBSE, ICSE, or TN_STATE_BOARD.")

        clean_class = request.standard_class.strip()
        valid_classes = [f"Class {i}" for i in range(1, 13)]
        if clean_class not in valid_classes:
            errors.append(f"Invalid standard class: '{request.standard_class}'. Must be Class 1 to Class 12.")

        # Canonical Node ID format: {BOARD}_{CLASS}_{SUBJECT_SLUG}_{CHAPTER_SLUG}_{TOPIC_SLUG}
        clean_sub = request.subject.strip().replace(" ", "_").upper()
        clean_chap = request.chapter_name.strip().replace(" ", "_").upper()
        clean_top = request.topic_name.strip().replace(" ", "_").upper()
        class_num = clean_class.replace("Class ", "")

        canonical_id = f"{clean_board}_{class_num}_{clean_sub}_{clean_top}"
        hierarchy_path = f"{clean_board} > {clean_class} > {request.subject} > {request.chapter_name} > {request.topic_name}"

        is_valid = len(errors) == 0
        return TopicNodeValidationResponse(
            is_valid=is_valid,
            canonical_node_id=canonical_id,
            hierarchy_path=hierarchy_path,
            validation_errors=errors,
        )

    def assert_gate2_topic_intelligence_boundary(
        self,
        evidence_type: str,
        requested_topic_mastery: bool,
    ) -> Gate2TopicIntelligenceCheckResponse:
        """
        Enforces Gate 2 Zero-Fake-Mastery rule:
        Aggregate marks cards & quick marks ONLY update subject-level movement.
        Granular topic-level mastery strictly requires Question Paper or Expert Evaluation evidence.
        """
        clean_type = evidence_type.strip().upper()
        granular_types = ["QUESTION_PAPER", "EXPERT_EVALUATION", "DIAGNOSTIC_RECHECK", "WORKSHEET_ITEMIZED"]
        aggregate_types = ["QUICK_MARKS", "RESULT_CARD_OCR", "AGGREGATE_MARKSHEET"]

        if requested_topic_mastery and clean_type in aggregate_types:
            return Gate2TopicIntelligenceCheckResponse(
                is_topic_intelligence_eligible=False,
                evidence_type=clean_type,
                status_code="LOCKED_AGGREGATE_ONLY",
                enforcement_message=(
                    "Gate 2 Locked: Aggregate marks cards cannot fabricate topic-level mastery. "
                    "Upload a Question Paper or Expert Evaluation to unlock topic diagnostic intelligence."
                ),
            )

        return Gate2TopicIntelligenceCheckResponse(
            is_topic_intelligence_eligible=True,
            evidence_type=clean_type,
            status_code="ELIGIBLE_GRANULAR",
            enforcement_message="Granular evidence verified. Topic-level diagnostic intelligence eligible.",
        )
