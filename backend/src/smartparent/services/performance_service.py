"""
STUDIQS® SmartParent™ (v6.2 Complete) - Performance & Consistency Intelligence Service
=============================================================================
Service: performance_service.py
Governs Section 5:
- Subject Monthly Consistency (e.g. Maths 72 → 78 → 81 | Improving)
- Overall Monthly Movement (+4% vs last comparable result - strict compatibility)
- Term Consistency (Term 1 → Term 2 direction with sufficiency check)
- Topic Movement (Needs Attention → Needs Practice → Mastered)
- Gap Closure Tracking (2 of 3 gaps improved / closed) & Recheck Execution
- Expert Feedback Status & 48h SLA Tracking
=============================================================================
"""

import uuid
import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc

from src.smartparent.db.models.auth import Child, Subscriber
from src.smartparent.db.models.assessment import EvidenceRecord
from src.smartparent.db.models.curriculum import CurriculumNode
from src.smartparent.db.models.diagnostic import TopicGap, TopicScore
from src.smartparent.db.models.marketplace import EvaluationCase, Expert
from src.smartparent.engines.performance_consistency_engine import PerformanceConsistencyEngine
from src.smartparent.engines.gap_recheck_engine import GapRecheckEngine
from src.smartparent.schemas.performance import (
    Section5PerformanceResponse,
    GapRecheckResponseSchema,
    SubjectMonthlyConsistencySchema,
    TermConsistencySchema,
    GapClosureSummarySchema,
)

logger = logging.getLogger("STUDIQS_PerformanceService")


class PerformanceService:
    """
    Section 5 Unified Intelligence Service.
    Enforces strict B2C multi-tenant subscriber-child isolation.
    """

    def __init__(self):
        self.perf_engine = PerformanceConsistencyEngine()
        self.recheck_engine = GapRecheckEngine()

    def get_performance_intelligence(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        child_id: uuid.UUID,
    ) -> Section5PerformanceResponse:
        """
        Retrieves complete Section 5 intelligence for the authorized child.
        """
        # 1. Non-negotiable B2C Boundary Isolation Check
        child = (
            db.query(Child)
            .filter(Child.child_id == child_id, Child.subscriber_id == subscriber_id)
            .first()
        )
        if not child:
            logger.warning(
                f"[PerformanceService] Unauthorized access attempt: subscriber {subscriber_id} tried to access child {child_id}"
            )
            raise PermissionError("Child profile not found or not authorized for this subscriber.")

        student_name = getattr(child, "student_name", getattr(child, "first_name", "Student"))
        academic_year = getattr(child, "academic_year", "2026-2027") or "2026-2027"

        # 2. Extract Confirmed Evidence Records
        records = (
            db.query(EvidenceRecord)
            .filter(EvidenceRecord.child_id == child_id)
            .order_by(asc(EvidenceRecord.test_date), asc(EvidenceRecord.created_at))
            .all()
        )

        assessments_data = [
            {
                "record_id": str(r.record_id),
                "subject": r.subject,
                "test_title": r.test_title,
                "test_date": r.test_date,
                "total_scored_marks": float(r.total_scored_marks),
                "total_max_marks": float(r.total_max_marks),
                "evidence_type": r.evidence_type,
            }
            for r in records
        ]

        # 3. Extract Topic Gaps joined with CurriculumNode
        gaps_query = (
            db.query(TopicGap)
            .join(CurriculumNode, TopicGap.node_id == CurriculumNode.node_id, isouter=True)
            .filter(TopicGap.child_id == child_id)
            .order_by(desc(TopicGap.first_identified_at))
            .all()
        )

        gaps_data = []
        for g in gaps_query:
            c_node = g.curriculum_node
            gaps_data.append({
                "gap_id": str(g.gap_id),
                "node_id": g.node_id,
                "topic_name": c_node.topic_name if c_node else getattr(g, "topic_name", "General Topic"),
                "subject": c_node.subject if c_node else getattr(g, "subject", "General"),
                "gap_status": g.gap_status,
                "first_identified_at": g.first_identified_at.isoformat() if g.first_identified_at else None,
                "resolved_at": g.resolved_at.isoformat() if g.resolved_at else None,
            })

        # 4. Extract Historical Topic Scores for Topic Movement Tracking
        topic_scores = (
            db.query(TopicScore)
            .join(CurriculumNode, TopicScore.node_id == CurriculumNode.node_id, isouter=True)
            .filter(TopicScore.child_id == child_id)
            .order_by(asc(TopicScore.evaluated_at))
            .all()
        )

        # Build chronological history per topic node
        node_scores_map: Dict[str, List[TopicScore]] = {}
        for ts in topic_scores:
            node_scores_map.setdefault(ts.node_id, []).append(ts)

        topic_history_data = []
        for n_id, t_scores in node_scores_map.items():
            latest_score = t_scores[-1]
            c_node = latest_score.curriculum_node
            t_name = c_node.topic_name if c_node else "General Topic"
            subj = c_node.subject if c_node else "General"

            prev_score_val = float(t_scores[-2].percentage) if len(t_scores) > 1 else None

            topic_history_data.append({
                "node_id": n_id,
                "topic_name": t_name,
                "subject": subj,
                "current_score": float(latest_score.percentage),
                "previous_score": prev_score_val,
            })

        # 5. Extract Expert Evaluation Cases joined with Expert Profile
        cases_query = (
            db.query(EvaluationCase)
            .join(Expert, EvaluationCase.expert_id == Expert.expert_id, isouter=True)
            .filter(EvaluationCase.child_id == child_id)
            .order_by(desc(EvaluationCase.created_at))
            .all()
        )

        expert_cases_data = []
        for ec in cases_query:
            expert_name = "Subject Expert"
            if ec.expert:
                expert_name = getattr(ec.expert, "full_name", getattr(ec.expert, "display_alias", "Subject Expert"))

            expert_cases_data.append({
                "case_id": str(ec.case_id),
                "subject": ec.subject,
                "test_title": ec.test_title,
                "expert_name": expert_name,
                "case_status": ec.case_status,
                "submitted_at": ec.submitted_at.isoformat() if ec.submitted_at else None,
                "completed_at": ec.completed_at.isoformat() if ec.completed_at else None,
                "evaluated_pdf_path": ec.evaluated_pdf_path,
                "expert_feedback": None,  # From messages or annotations
            })

        # 6. Execute Engine
        payload = {
            "child_id": str(child.child_id),
            "student_name": student_name,
            "standard_class": child.standard_class,
            "academic_year": academic_year,
            "assessments": assessments_data,
            "gaps": gaps_data,
            "topic_history": topic_history_data,
            "expert_cases": expert_cases_data,
        }

        return self.perf_engine.run(payload)

    def execute_gap_recheck(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        child_id: uuid.UUID,
        gap_id: uuid.UUID,
        scored_marks: float,
        max_marks: float,
        recheck_title: str = "Diagnostic Gap Recheck",
        test_date: Optional[date] = None,
    ) -> GapRecheckResponseSchema:
        """
        Executes a diagnostic gap recheck.
        If score >= 80%: Resolves the gap, records confirmed topic score and evidence record.
        """
        # 1. Non-negotiable B2C Boundary Isolation Check
        child = (
            db.query(Child)
            .filter(Child.child_id == child_id, Child.subscriber_id == subscriber_id)
            .first()
        )
        if not child:
            raise PermissionError("Child profile not found or not authorized for this subscriber.")

        # 2. Locate TopicGap
        gap = (
            db.query(TopicGap)
            .filter(TopicGap.gap_id == gap_id, TopicGap.child_id == child_id)
            .first()
        )
        if not gap:
            raise ValueError(f"Topic gap {gap_id} not found for this child.")

        # Locate Curriculum Node
        c_node = (
            db.query(CurriculumNode)
            .filter(CurriculumNode.node_id == gap.node_id)
            .first()
        )
        topic_name = c_node.topic_name if c_node else "General Topic"
        subject = c_node.subject if c_node else "General"

        # Prior score check
        prior_score_rec = (
            db.query(TopicScore)
            .filter(TopicScore.child_id == child_id, TopicScore.node_id == gap.node_id)
            .order_by(desc(TopicScore.evaluated_at))
            .first()
        )
        prior_pct = float(prior_score_rec.percentage) if prior_score_rec else 35.0

        # 3. Run Gap Recheck Engine
        recheck_payload = {
            "gap_id": str(gap.gap_id),
            "node_id": gap.node_id,
            "topic_name": topic_name,
            "subject": subject,
            "scored_marks": scored_marks,
            "max_marks": max_marks,
            "prior_score_pct": prior_pct,
            "prior_status": gap.gap_status,
        }

        recheck_result = self.recheck_engine.run(recheck_payload)

        # 4. Apply State Changes to Database
        now_dt = datetime.now(timezone.utc)
        if recheck_result.is_gap_closed:
            gap.gap_status = "RESOLVED"
            gap.resolved_at = now_dt
            logger.info(f"[GapRecheck] Gap {gap_id} ({topic_name}) RESOLVED at {recheck_result.recheck_score_pct}%")
        else:
            gap.gap_status = "ACTIVE"
            logger.info(f"[GapRecheck] Gap {gap_id} remains ACTIVE at {recheck_result.recheck_score_pct}%")

        # 5. Persist confirmed TopicScore
        pct = recheck_result.recheck_score_pct
        if pct >= 80.0:
            tier = "STRONG"
        elif pct >= 60.0:
            tier = "AVERAGE"
        elif pct >= 40.0:
            tier = "WEAK"
        else:
            tier = "CRITICAL"

        score_rec = TopicScore(
            score_id=uuid.uuid4(),
            child_id=child_id,
            node_id=gap.node_id,
            scored_marks=scored_marks,
            max_marks=max_marks,
            percentage=pct,
            mastery_tier=tier,
            evaluated_at=now_dt,
        )
        db.add(score_rec)

        # 6. Persist confirmed EvidenceRecord
        t_date = test_date or date.today()
        ev_rec = EvidenceRecord(
            record_id=uuid.uuid4(),
            subscriber_id=subscriber_id,
            child_id=child_id,
            evidence_type="QUICK_MARKS",
            subject=subject,
            test_title=f"{recheck_title} - {topic_name}",
            test_date=t_date,
            total_scored_marks=scored_marks,
            total_max_marks=max_marks,
        )
        db.add(ev_rec)
        db.commit()

        return GapRecheckResponseSchema(
            gap_id=str(gap.gap_id),
            node_id=gap.node_id,
            topic_name=topic_name,
            subject=subject,
            prior_score=prior_pct,
            recheck_score=recheck_result.recheck_score_pct,
            delta=recheck_result.delta_pct,
            prior_status=recheck_result.prior_status,
            new_status=recheck_result.new_status,
            is_gap_closed=recheck_result.is_gap_closed,
            transition_narrative=recheck_result.transition_narrative,
            evaluated_at=recheck_result.evaluated_at,
        )
