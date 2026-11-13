"""
STUDIQS® SmartParent™ (v6.2 Complete) - Analytics, AI & Topic-Repository Service
=============================================================================
Service: analytics_ai_service.py (Section 17 - Working Specification v6.0 / v6.1)
Enforces:
1. Pure server-side deterministic scoring (zero math hallucination)
2. Grounded AI pedagogical explanations ("No new evidence means no fabricated change")
3. 'Subject Expert Feedback' vs 'AI Feedback' strict visual separation
4. Immutable Source Provenance mapping from Expert Evaluations into Student 360
5. Topic-Repository taxonomy & Gate 2 zero-fake mastery enforcement
=============================================================================
"""

import uuid
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import desc

from src.smartparent.db.models.auth import Child, Subscriber
from src.smartparent.db.models.assessment import EvidenceRecord
from src.smartparent.db.models.curriculum import CurriculumNode
from src.smartparent.db.models.diagnostic import TopicScore, TopicGap
from src.smartparent.db.models.marketplace import EvaluationCase, Expert
from src.smartparent.engines.section_17_analytics_ai.analytics_ai_engine import AnalyticsAiEngine
from src.smartparent.schemas.analytics_ai_rules import (
    FeedbackOriginEnum,
    DeterministicCalculationRequest,
    DeterministicCalculationResponse,
    GroundedAiExplanationRequest,
    GroundedAiExplanationResponse,
    ExpertProvenanceMetadata,
    MapExpertEvaluationToIntelligenceRequest,
    MapExpertEvaluationToIntelligenceResponse,
    TopicNodeValidationRequest,
    TopicNodeValidationResponse,
    Gate2TopicIntelligenceCheckRequest,
    Gate2TopicIntelligenceCheckResponse,
)

logger = logging.getLogger("STUDIQS_AnalyticsAiService")


class AnalyticsAiService:
    """
    Section 17 Master Analytics, AI & Topic-Repository Rules Service.
    """

    def __init__(self):
        self.engine = AnalyticsAiEngine()

    def _verify_tenant_boundary(self, db: Session, subscriber_id: uuid.UUID, child_id: uuid.UUID) -> Child:
        """Enforces non-negotiable B2C subscriber-child boundary check."""
        child = (
            db.query(Child)
            .filter(Child.child_id == child_id, Child.subscriber_id == subscriber_id)
            .first()
        )
        if not child:
            raise PermissionError("Child profile not found or not authorized for this subscriber.")
        return child

    # =========================================================================
    # 1. DETERMINISTIC CALCULATIONS
    # =========================================================================

    def calculate_deterministic_metrics(
        self,
        request: DeterministicCalculationRequest,
    ) -> DeterministicCalculationResponse:
        """Computes server-owned deterministic performance metrics."""
        return self.engine.calculate_deterministic_metrics(
            subject=request.subject,
            scores=request.scores,
        )

    # =========================================================================
    # 2. GROUNDED AI EXPLANATIONS
    # =========================================================================

    def generate_grounded_explanation(
        self,
        request: GroundedAiExplanationRequest,
    ) -> GroundedAiExplanationResponse:
        """Generates grounded pedagogical explanations strictly based on server deltas."""
        return self.engine.generate_grounded_ai_explanation(request)

    # =========================================================================
    # 3. FEEDBACK ORIGIN VISUAL BADGING
    # =========================================================================

    def badge_feedback(
        self,
        text: str,
        origin: FeedbackOriginEnum,
        author_name: Optional[str] = None,
    ) -> Dict[str, str]:
        """Attaches visual and semantic origin labels to feedback."""
        return self.engine.badge_feedback(text=text, origin=origin, author_name=author_name)

    # =========================================================================
    # 4. SOURCE PROVENANCE MAPPING (EXPERT EVALUATION -> STUDENT 360)
    # =========================================================================

    def map_expert_evaluation_to_intelligence(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        request: MapExpertEvaluationToIntelligenceRequest,
    ) -> MapExpertEvaluationToIntelligenceResponse:
        """
        Maps a completed human expert evaluation into Student 360 Topic Intelligence
        with full immutable source provenance:
        (expert_id, evaluation_id, completion_date, evidence_type='EXPERT_EVALUATION').
        """
        child_uuid = uuid.UUID(request.child_id) if isinstance(request.child_id, str) else request.child_id
        child = self._verify_tenant_boundary(db, subscriber_id, child_uuid)

        comp_date = request.completion_date or datetime.now(timezone.utc).isoformat()
        topic_nodes = list(request.topic_ratings.keys())

        # 1. Generate immutable provenance bundle
        provenance = self.engine.generate_expert_provenance(
            expert_id=request.expert_id,
            evaluation_id=request.evaluation_id,
            completion_date=comp_date,
            marks_awarded=request.marks_awarded,
            total_max_marks=request.total_max_marks,
            topic_node_ids=topic_nodes,
        )

        updated_topic_scores = 0
        resolved_gaps = 0

        # 2. Update TopicScore records with full provenance
        for node_id, pct in request.topic_ratings.items():
            clean_pct = round(float(pct), 1)
            tier = "STRONG" if clean_pct >= 80.0 else ("AVERAGE" if clean_pct >= 60.0 else ("WEAK" if clean_pct >= 40.0 else "CRITICAL"))

            # Find or create TopicScore
            ts = (
                db.query(TopicScore)
                .filter(TopicScore.child_id == child_uuid, TopicScore.node_id == node_id)
                .first()
            )
            if ts:
                ts.scored_marks = clean_pct
                ts.max_marks = 100.0
                ts.percentage = clean_pct
                ts.mastery_tier = tier
                ts.evaluated_at = datetime.now(timezone.utc)
            else:
                ts = TopicScore(
                    score_id=uuid.uuid4(),
                    child_id=child_uuid,
                    node_id=node_id,
                    scored_marks=clean_pct,
                    max_marks=100.0,
                    percentage=clean_pct,
                    mastery_tier=tier,
                    evaluated_at=datetime.now(timezone.utc),
                )
                db.add(ts)
            updated_topic_scores += 1

            # Resolve gaps if expert gave >= 80%
            if clean_pct >= 80.0:
                gaps = (
                    db.query(TopicGap)
                    .filter(
                        TopicGap.child_id == child_uuid,
                        TopicGap.node_id == node_id,
                        TopicGap.gap_status.in_(["ACTIVE", "IN_RECHECK"]),
                    )
                    .all()
                )
                for g in gaps:
                    g.gap_status = "RESOLVED"
                    g.resolved_at = datetime.now(timezone.utc)
                    resolved_gaps += 1

        # 3. Create or record an EvidenceRecord for the evaluation
        ev = EvidenceRecord(
            record_id=uuid.uuid4(),
            subscriber_id=subscriber_id,
            child_id=child_uuid,
            evidence_type="EXPERT_EVALUATION",
            subject=request.subject,
            test_title=f"Expert Evaluation ({request.subject})",
            test_date=datetime.now(timezone.utc).date(),
            total_scored_marks=request.marks_awarded,
            total_max_marks=request.total_max_marks,
            storage_file_path=f"provenance://expert/{request.expert_id}/eval/{request.evaluation_id}?hash={provenance.audit_hash}",
        )
        db.add(ev)
        db.commit()

        logger.info(
            f"[AnalyticsAiService] Mapped evaluation {request.evaluation_id} to child {child_uuid} with {updated_topic_scores} topic scores"
        )

        return MapExpertEvaluationToIntelligenceResponse(
            success=True,
            child_id=str(child_uuid),
            subject=request.subject,
            provenance=provenance,
            updated_topic_scores_count=updated_topic_scores,
            resolved_gaps_count=resolved_gaps,
            feedback_origin=FeedbackOriginEnum.HUMAN_EXPERT,
            feedback_badge="Subject Expert Feedback",
            intelligence_status="CONFIRMED_EXPERT_PROVENANCE",
        )

    # =========================================================================
    # 5. TOPIC-REPOSITORY VALIDATION & GATE 2 CHECKS
    # =========================================================================

    def validate_topic_node(
        self,
        request: TopicNodeValidationRequest,
    ) -> TopicNodeValidationResponse:
        """Validates topic node against curriculum taxonomy."""
        return self.engine.validate_topic_repository_node(request)

    def check_gate2_topic_intelligence(
        self,
        request: Gate2TopicIntelligenceCheckRequest,
    ) -> Gate2TopicIntelligenceCheckResponse:
        """Enforces Gate 2 Zero-Fake-Mastery rule."""
        return self.engine.assert_gate2_topic_intelligence_boundary(
            evidence_type=request.evidence_type,
            requested_topic_mastery=request.requested_topic_mastery,
        )

    # =========================================================================
    # 6. RETRIEVAL WITH PROVENANCE
    # =========================================================================

    def get_child_provenance_records(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        child_id: uuid.UUID,
    ) -> List[Dict[str, Any]]:
        """Retrieves all expert evaluation evidence records with full audit trail."""
        child = self._verify_tenant_boundary(db, subscriber_id, child_id)
        records = (
            db.query(EvidenceRecord)
            .filter(
                EvidenceRecord.child_id == child_id,
                EvidenceRecord.evidence_type == "EXPERT_EVALUATION",
            )
            .order_by(desc(EvidenceRecord.created_at))
            .all()
        )
        results = []
        for r in records:
            path = r.storage_file_path or ""
            exp_id = None
            eval_id = None
            audit_hash = None
            if "provenance://expert/" in path:
                try:
                    parts = path.replace("provenance://expert/", "").split("/eval/")
                    if len(parts) == 2:
                        exp_id = parts[0]
                        eval_parts = parts[1].split("?hash=")
                        eval_id = eval_parts[0]
                        if len(eval_parts) == 2:
                            audit_hash = eval_parts[1]
                except Exception:
                    pass

            results.append({
                "record_id": str(r.record_id),
                "subject": r.subject,
                "test_title": r.test_title,
                "test_date": str(r.test_date),
                "scored_marks": float(r.total_scored_marks),
                "max_marks": float(r.total_max_marks),
                "expert_id": exp_id,
                "evaluation_id": eval_id,
                "audit_hash": audit_hash,
                "feedback_origin": FeedbackOriginEnum.HUMAN_EXPERT.value,
                "feedback_badge": "Subject Expert Feedback",
            })
        return results
