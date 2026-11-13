"""
STUDIQS® SmartParent™ (v6.2 Complete) - Student 360 Intelligence Service
=============================================================================
Section 4: Mandatory Core USP.
Compiles a grounded, multi-dimensional academic intelligence picture for any
child across subjects, consistency trends, topic gaps, parent pulse cards,
board readiness, and completed expert evaluations.
=============================================================================
"""

import uuid
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import desc

from src.smartparent.db.models.auth import Child
from src.smartparent.db.models.assessment import EvidenceRecord
from src.smartparent.db.models.curriculum import CurriculumNode
from src.smartparent.db.models.diagnostic import TopicGap
from src.smartparent.db.models.parent_pulse import ParentPulseRecord
from src.smartparent.db.models.readiness import BoardReadinessRecord
from src.smartparent.db.models.marketplace import EvaluationCase
from src.smartparent.engines.parent_pulse_engine import ParentPulseEngine



logger = logging.getLogger("STUDIQS_Student360")


class Student360Service:
    """
    Unified intelligence aggregator compiling Student 360 views with zero cross-tenant leakage.
    """

    def __init__(self):
        self.pulse_engine = ParentPulseEngine()

    def get_student_360(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        child_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """
        Retrieves the complete Student 360 intelligence view.
        Enforces strict subscriber-child ownership verification.
        """
        # 1. Non-negotiable B2C Boundary Ownership Check
        child = (
            db.query(Child)
            .filter(Child.child_id == child_id, Child.subscriber_id == subscriber_id)
            .first()
        )
        if not child:
            logger.warning(
                f"[Student360] Unauthorized access attempt: subscriber {subscriber_id} tried to access child {child_id}"
            )
            raise PermissionError("Child profile not found or not authorized for this subscriber.")

        # 2. Extract Profile
        profile_data = {
            "child_id": str(child.child_id),
            "student_name": getattr(child, "student_name", getattr(child, "first_name", "Student")),
            "standard_class": child.standard_class,
            "board": child.board,
            "academic_year": getattr(child, "academic_year", "2026-2027") or "2026-2027",
            "school_name": getattr(child, "school_name", None),
        }

        # 3. Extract Subject Marks & Performance Trends via EvidenceRecord
        records = (
            db.query(EvidenceRecord)
            .filter(EvidenceRecord.child_id == child_id)
            .order_by(desc(EvidenceRecord.test_date), desc(EvidenceRecord.created_at))
            .all()
        )

        subject_performance: List[Dict[str, Any]] = []
        overall_average = 0.0
        monthly_movement = 0.0

        if records:
            # Group records by subject chronologically
            subject_groups: Dict[str, List[EvidenceRecord]] = {}
            for r in records:
                s_name = r.subject.strip()
                subject_groups.setdefault(s_name, []).append(r)

            latest_percentages = []
            prior_percentages = []

            for s_name, s_records in subject_groups.items():
                latest_rec = s_records[0]
                max_m = float(latest_rec.total_max_marks) or 100.0
                scored_m = float(latest_rec.total_scored_marks)
                cur_pct = round((scored_m / max_m) * 100.0, 1)
                latest_percentages.append(cur_pct)

                prev_pct: Optional[float] = None
                delta: Optional[float] = None
                if len(s_records) > 1:
                    prev_rec = s_records[1]
                    prev_max = float(prev_rec.total_max_marks) or 100.0
                    prev_pct = round((float(prev_rec.total_scored_marks) / prev_max) * 100.0, 1)
                    prior_percentages.append(prev_pct)
                    delta = round(cur_pct - prev_pct, 1)

                if delta is not None:
                    if delta > 3.0:
                        tier = "Improving"
                        symbol = "↗"
                    elif delta < -3.0:
                        tier = "Declining"
                        symbol = "↘"
                    else:
                        tier = "Stable"
                        symbol = "→"
                else:
                    tier = "Stable"
                    symbol = "→"

                subject_performance.append({
                    "subject_name": s_name,
                    "current_marks": cur_pct,
                    "previous_marks": prev_pct,
                    "delta": delta,
                    "consistency_tier": tier,
                    "direction_symbol": symbol,
                })

            if latest_percentages:
                overall_average = round(sum(latest_percentages) / len(latest_percentages), 1)

            if prior_percentages:
                prior_avg = sum(prior_percentages) / len(prior_percentages)
                monthly_movement = round(overall_average - prior_avg, 1)


        # 4. Extract Top Unresolved Topic Gaps
        topic_gaps = (
            db.query(TopicGap)
            .join(CurriculumNode, TopicGap.node_id == CurriculumNode.node_id, isouter=True)
            .filter(TopicGap.child_id == child_id, TopicGap.gap_status.in_(["ACTIVE", "IN_RECHECK"]))
            .order_by(desc(TopicGap.first_identified_at))
            .limit(5)
            .all()
        )
        gaps_list = []
        for g in topic_gaps:
            c_node = getattr(g, "curriculum_node", None)
            subject = getattr(c_node, "subject", None) if c_node else getattr(g, "subject", "General")
            topic_name = getattr(c_node, "topic_name", None) if c_node else getattr(g, "topic_name", "General Topic")
            status = getattr(g, "gap_status", getattr(g, "status", "ACTIVE"))
            severity = getattr(g, "severity", "Critical") or "Critical"
            gaps_list.append({
                "gap_id": str(g.gap_id),
                "subject": subject or "General",
                "topic_name": topic_name or "General Topic",
                "status": status,
                "severity": severity,
            })

        # 5. Extract Parent Pulse Cards
        pulse_rec = (
            db.query(ParentPulseRecord)
            .filter(ParentPulseRecord.child_id == child_id)
            .order_by(desc(ParentPulseRecord.generated_at))
            .first()
        )

        pulse_cards = []
        if pulse_rec:
            pulse_cards = [
                {
                    "card_type": "Improvement",
                    "headline": "Top Improvement",
                    "narrative": pulse_rec.improvement_text,
                    "action_text": "Keep momentum",
                    "color_theme": "GREEN",
                },
                {
                    "card_type": "Watch Area",
                    "headline": "Critical Focus",
                    "narrative": pulse_rec.watch_area_text,
                    "action_text": "Practice recommended",
                    "color_theme": "AMBER",
                },
                {
                    "card_type": "Next Action",
                    "headline": "Action Item",
                    "narrative": pulse_rec.next_action_text,
                    "action_text": "View guidance",
                    "color_theme": "BLUE",
                },
            ]
        elif subject_performance:

            # Dynamically synthesize pulse cards if assessments exist but digest wasn't persisted
            synth_scores = [
                {"subject": s["subject_name"], "score": s["current_marks"], "previous": s["previous_marks"] or s["current_marks"]}
                for s in subject_performance
            ]
            pulse_payload = {
                "student_id": str(child_id),
                "student_name": getattr(child, "student_name", getattr(child, "first_name", "Student")),
                "subject_scores": synth_scores,
            }
            pulse_result = self.pulse_engine.run(pulse_payload)
            if hasattr(pulse_result, "improvement_area"):
                for card_obj in [pulse_result.improvement_area, pulse_result.watch_area, pulse_result.next_immediate_action]:
                    if card_obj:
                        pulse_cards.append({
                            "card_type": getattr(card_obj, "card_type", "CARD"),
                            "title": getattr(card_obj, "title", ""),
                            "description": getattr(card_obj, "description", getattr(card_obj, "headline", "")),
                            "actionable_insight": getattr(card_obj, "headline", getattr(card_obj, "description", "")),
                            "metric_badge": getattr(card_obj, "metric_badge", None),
                            "color_theme": "GREEN" if getattr(card_obj, "card_type", "") == "IMPROVEMENT" else ("AMBER" if getattr(card_obj, "card_type", "") == "WATCH_AREA" else "BLUE"),
                        })
            elif isinstance(pulse_result, dict):
                pulse_cards = pulse_result.get("cards", [])

        # 6. Extract Board Readiness (Classes 10 & 12)
        readiness_data = None
        if child.standard_class in ("Class 10", "Class 12", "10", "12"):
            readiness_rec = (
                db.query(BoardReadinessRecord)
                .filter(BoardReadinessRecord.child_id == child_id)
                .order_by(desc(BoardReadinessRecord.evaluated_at))
                .first()
            )
            if readiness_rec:
                readiness_data = {
                    "projected_board_score": float(readiness_rec.projected_board_score),
                    "projected_cutoff": float(readiness_rec.projected_cutoff) if readiness_rec.projected_cutoff else None,
                    "stream_readiness_data": readiness_rec.stream_readiness_data,
                    "career_readiness_summary": readiness_rec.career_readiness_summary,
                    "evaluated_at": readiness_rec.evaluated_at.isoformat() if readiness_rec.evaluated_at else None,
                }

        # 7. Extract Expert Evaluations
        evaluations = (
            db.query(EvaluationCase)
            .filter(EvaluationCase.child_id == child_id)
            .order_by(desc(EvaluationCase.created_at))
            .limit(5)
            .all()
        )
        eval_list = []
        for ev in evaluations:
            eval_list.append({
                "case_id": str(ev.case_id),
                "status": ev.status,
                "subject": ev.subject,
                "expert_id": str(ev.expert_id) if ev.expert_id else None,
                "created_at": ev.created_at.isoformat() if ev.created_at else None,
            })


        return {
            "profile": profile_data,
            "overall_average": overall_average,
            "monthly_movement": monthly_movement,
            "subject_performance": subject_performance,
            "top_unresolved_gaps": gaps_list,
            "parent_pulse_cards": pulse_cards,
            "board_readiness": readiness_data,
            "expert_evaluations": eval_list,
            "evidence_count": len(records),
            "last_updated": datetime.utcnow().isoformat(),
        }

