"""
STUDIQS® SmartParent™ (v6.2 Complete) - Section 7 Parent Actions, Gap Recheck & Handoff Service
=============================================================================
Service: parent_actions_service.py (Section 7 & Section 9)
Governs:
1. Home Screen Action List (Strictly Max 3 Grounded Actions)
2. Targeted Diagnostic Gap Recheck Quiz Generator & Resolver
3. Academic Handoff Brief Engine for PTM / School Teachers / Home Tutors
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
from src.smartparent.engines.gap_recheck_engine import GapRecheckEngine
from src.smartparent.engines.academic_handoff_engine import AcademicHandoffEngine
from src.smartparent.schemas.actions import (
    ParentActionsListResponse,
    ActionCardSchema,
    RecheckQuizGenerateResponse,
    RecheckQuizQuestionSchema,
    RecheckQuizSubmitResponse,
    AcademicHandoffBriefResponse,
)

logger = logging.getLogger("STUDIQS_ParentActionsService")


class ParentActionsService:
    """
    Section 7 Unified Parent Actions, Gap Recheck & Academic Handoff Service.
    Enforces strict B2C multi-tenant subscriber-child isolation.
    """

    def __init__(self):
        self.recheck_engine = GapRecheckEngine()
        self.handoff_engine = AcademicHandoffEngine()

    def get_home_actions(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        child_id: uuid.UUID,
    ) -> ParentActionsListResponse:
        """
        Synthesizes the Home screen action cockpit.
        Enforces the non-negotiable Section 7 rule: strictly <= 3 actions!
        """
        # 1. Non-negotiable B2C Boundary Isolation Check
        child = (
            db.query(Child)
            .filter(Child.child_id == child_id, Child.subscriber_id == subscriber_id)
            .first()
        )
        if not child:
            logger.warning(
                f"[ParentActions] Unauthorized access attempt: subscriber {subscriber_id} tried to access child {child_id}"
            )
            raise PermissionError("Child profile not found or not authorized for this subscriber.")

        student_name = getattr(child, "student_name", getattr(child, "first_name", "Student"))

        # 2. Extract Active Topic Gaps joined with CurriculumNode
        active_gaps = (
            db.query(TopicGap)
            .join(CurriculumNode, TopicGap.node_id == CurriculumNode.node_id, isouter=True)
            .filter(TopicGap.child_id == child_id, TopicGap.gap_status.in_(["ACTIVE", "IN_RECHECK"]))
            .order_by(desc(TopicGap.first_identified_at))
            .all()
        )

        # 3. Check for Persistent Weak Subjects (< 50%) across confirmed evidence
        recent_evidence = (
            db.query(EvidenceRecord)
            .filter(EvidenceRecord.child_id == child_id)
            .order_by(desc(EvidenceRecord.test_date), desc(EvidenceRecord.created_at))
            .limit(10)
            .all()
        )

        subject_averages: Dict[str, List[float]] = {}
        for r in recent_evidence:
            max_m = float(r.total_max_marks) or 100.0
            pct = (float(r.total_scored_marks) / max_m) * 100.0
            subject_averages.setdefault(r.subject.strip(), []).append(pct)

        persistent_weak_subjects = [
            subj for subj, scores in subject_averages.items()
            if (sum(scores) / len(scores)) < 50.0
        ]

        # 4. Synthesize Prioritized Actions (Max 3)
        actions: List[ActionCardSchema] = []

        # Priority 1: Persistent weak subject -> "Ask a Subject Expert" (Section 7 Mandate)
        if persistent_weak_subjects:
            weak_subj = persistent_weak_subjects[0]
            actions.append(
                ActionCardSchema(
                    action_id=f"act-expert-{weak_subj.lower()[:4]}",
                    action_type="ASK_EXPERT",
                    priority="HIGH",
                    title=f"Ask a Subject Expert for {weak_subj}",
                    description=f"Performance in {weak_subj} is persistently below 50%. Connect with a verified subject expert for structured answer-sheet evaluation.",
                    subject=weak_subj,
                    action_url=f"/marketplace/experts?subject={weak_subj}",
                )
            )

        # Priority 2: Critical gap -> "Take 10-Minute Gap Recheck"
        if active_gaps:
            top_gap = active_gaps[0]
            top_topic = top_gap.curriculum_node.topic_name if top_gap.curriculum_node else "Core Concepts"
            top_subj = top_gap.curriculum_node.subject if top_gap.curriculum_node else "General"

            actions.append(
                ActionCardSchema(
                    action_id=f"act-recheck-{str(top_gap.gap_id)[:8]}",
                    action_type="DIAGNOSTIC_RECHECK",
                    priority="HIGH",
                    title=f"Take 10-Min Diagnostic Recheck in {top_topic}",
                    description=f"Verify whether recent practice closed the learning gap in {top_topic}. Scoring >= 80% marks it RESOLVED.",
                    subject=top_subj,
                    topic_name=top_topic,
                    node_id=top_gap.node_id,
                    gap_id=str(top_gap.gap_id),
                    action_url=f"/student/recheck/{top_gap.gap_id}",
                )
            )

            # Priority 3: Guided Practice for second gap if exists, else targeted drills
            if len(active_gaps) > 1 and len(actions) < 3:
                second_gap = active_gaps[1]
                s_topic = second_gap.curriculum_node.topic_name if second_gap.curriculum_node else "Foundations"
                s_subj = second_gap.curriculum_node.subject if second_gap.curriculum_node else "General"
                actions.append(
                    ActionCardSchema(
                        action_id=f"act-practice-{str(second_gap.gap_id)[:8]}",
                        action_type="PRACTICE",
                        priority="MEDIUM",
                        title=f"Practice 5 Targeted Problems in {s_topic}",
                        description=f"Work through curated practice questions to reinforce step-by-step problem solving in {s_subj}.",
                        subject=s_subj,
                        topic_name=s_topic,
                        node_id=second_gap.node_id,
                        gap_id=str(second_gap.gap_id),
                        action_url=f"/student/practice/{second_gap.node_id}",
                    )
                )

        # Fallback routine revision if fewer than 3 actions
        if len(actions) < 3:
            primary_subj = list(subject_averages.keys())[0] if subject_averages else "Mathematics"
            actions.append(
                ActionCardSchema(
                    action_id="act-daily-routine",
                    action_type="REVISION",
                    priority="ROUTINE",
                    title=f"Maintain 20-Min Daily Revision in {primary_subj}",
                    description="Consistent daily review prevents knowledge decay and maintains upward momentum.",
                    subject=primary_subj,
                )
            )

        # Enforce non-negotiable Section 7 rule: strictly <= 3 actions
        actions = actions[:3]

        return ParentActionsListResponse(
            child_id=str(child_id),
            student_name=student_name,
            actions=actions,
            total_actions_available=len(actions),
            active_gaps_count=len(active_gaps),
            generated_at=datetime.utcnow().isoformat(),
        )

    def generate_recheck_quiz(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        child_id: uuid.UUID,
        gap_id: uuid.UUID,
    ) -> RecheckQuizGenerateResponse:
        """
        Generates a 5-question targeted diagnostic recheck quiz for the specific topic gap.
        """
        # 1. Non-negotiable B2C Boundary Isolation Check
        child = (
            db.query(Child)
            .filter(Child.child_id == child_id, Child.subscriber_id == subscriber_id)
            .first()
        )
        if not child:
            raise PermissionError("Child profile not found or not authorized for this subscriber.")

        gap = (
            db.query(TopicGap)
            .filter(TopicGap.gap_id == gap_id, TopicGap.child_id == child_id)
            .first()
        )
        if not gap:
            raise ValueError(f"Topic gap {gap_id} not found for this child.")

        c_node = (
            db.query(CurriculumNode)
            .filter(CurriculumNode.node_id == gap.node_id)
            .first()
        )
        topic_name = c_node.topic_name if c_node else "Core Concepts"
        subject = c_node.subject if c_node else "General"
        standard_class = child.standard_class

        # Synthesize 5 targeted questions across Bloom levels
        questions = [
            RecheckQuizQuestionSchema(
                question_id=f"q1_{gap.node_id}",
                question_no=1,
                question_text=f"Define the fundamental concept and state the primary formula associated with {topic_name}.",
                marks=2.0,
                options=[f"Standard formula for {topic_name}", "Inverted formula", "Alternative formulation", "None of the above"],
                correct_answer=f"Standard formula for {topic_name}",
                explanation=f"Foundational definition for {topic_name}.",
                bloom_level="Remember",
            ),
            RecheckQuizQuestionSchema(
                question_id=f"q2_{gap.node_id}",
                question_no=2,
                question_text=f"Which of the following conditions must be satisfied when solving a direct problem in {topic_name}?",
                marks=2.0,
                options=["Discriminant >= 0", "Denominator equals zero", "Complex roots only", "Constant term is zero"],
                correct_answer="Discriminant >= 0",
                explanation="Basic constraint for real mathematical solutions.",
                bloom_level="Understand",
            ),
            RecheckQuizQuestionSchema(
                question_id=f"q3_{gap.node_id}",
                question_no=3,
                question_text=f"Calculate the unknown variable given standard parameters in {topic_name} and simplify the result.",
                marks=2.0,
                bloom_level="Apply",
            ),
            RecheckQuizQuestionSchema(
                question_id=f"q4_{gap.node_id}",
                question_no=4,
                question_text=f"A real-world practical scenario models an application of {topic_name}. Solve for the optimal solution.",
                marks=2.0,
                bloom_level="Analyze",
            ),
            RecheckQuizQuestionSchema(
                question_id=f"q5_{gap.node_id}",
                question_no=5,
                question_text=f"Identify the common conceptual error in an erroneous student working of {topic_name} and write the correct step.",
                marks=2.0,
                bloom_level="Evaluate",
            ),
        ]

        return RecheckQuizGenerateResponse(
            quiz_id=f"QUIZ_{datetime.utcnow().strftime('%Y%m%d%H%M')}_{str(gap_id)[:8]}",
            gap_id=str(gap.gap_id),
            node_id=gap.node_id,
            topic_name=topic_name,
            subject=subject,
            standard_class=standard_class,
            total_questions=5,
            total_max_marks=10.0,
            questions=questions,
            passing_threshold_pct=80.0,
            instructions="Answer all 5 questions. Score >= 80% (8/10 marks) to verify concept mastery and resolve this gap.",
        )

    def submit_recheck_quiz(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        child_id: uuid.UUID,
        gap_id: uuid.UUID,
        scored_marks: float,
        max_marks: float,
        recheck_title: str = "Diagnostic Gap Recheck Quiz",
    ) -> RecheckQuizSubmitResponse:
        """
        Evaluates diagnostic recheck submission:
        - If score >= 80%: Resolves gap, records confirmed TopicScore and EvidenceRecord.
        - If score < 80%: Retains ACTIVE status with delta tracking.
        """
        # 1. Non-negotiable B2C Boundary Isolation Check
        child = (
            db.query(Child)
            .filter(Child.child_id == child_id, Child.subscriber_id == subscriber_id)
            .first()
        )
        if not child:
            raise PermissionError("Child profile not found or not authorized for this subscriber.")

        gap = (
            db.query(TopicGap)
            .filter(TopicGap.gap_id == gap_id, TopicGap.child_id == child_id)
            .first()
        )
        if not gap:
            raise ValueError(f"Topic gap {gap_id} not found for this child.")

        c_node = (
            db.query(CurriculumNode)
            .filter(CurriculumNode.node_id == gap.node_id)
            .first()
        )
        topic_name = c_node.topic_name if c_node else "Core Topic"
        subject = c_node.subject if c_node else "General"

        # Prior score check
        prior_score_rec = (
            db.query(TopicScore)
            .filter(TopicScore.child_id == child_id, TopicScore.node_id == gap.node_id)
            .order_by(desc(TopicScore.evaluated_at))
            .first()
        )
        prior_pct = float(prior_score_rec.percentage) if prior_score_rec else 35.0

        # 2. Run GapRecheckEngine
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
        res = self.recheck_engine.run(recheck_payload)

        # 3. Apply state changes to PostgreSQL
        now_dt = datetime.now(timezone.utc)
        if res.is_gap_closed:
            gap.gap_status = "RESOLVED"
            gap.resolved_at = now_dt
            logger.info(f"[ParentActions] Gap {gap_id} ({topic_name}) RESOLVED at {res.recheck_score_pct}%")
        else:
            gap.gap_status = "ACTIVE"
            logger.info(f"[ParentActions] Gap {gap_id} remains ACTIVE at {res.recheck_score_pct}%")

        # 4. Persist confirmed TopicScore
        pct = res.recheck_score_pct
        tier = "STRONG" if pct >= 80.0 else ("AVERAGE" if pct >= 60.0 else ("WEAK" if pct >= 40.0 else "CRITICAL"))
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

        # 5. Persist confirmed EvidenceRecord
        ev_rec = EvidenceRecord(
            record_id=uuid.uuid4(),
            subscriber_id=subscriber_id,
            child_id=child_id,
            evidence_type="QUICK_MARKS",
            subject=subject,
            test_title=f"{recheck_title} - {topic_name}",
            test_date=date.today(),
            total_scored_marks=scored_marks,
            total_max_marks=max_marks,
        )
        db.add(ev_rec)
        db.commit()

        return RecheckQuizSubmitResponse(
            gap_id=str(gap.gap_id),
            node_id=gap.node_id,
            topic_name=topic_name,
            subject=subject,
            scored_marks=scored_marks,
            max_marks=max_marks,
            score_percentage=pct,
            prior_score=prior_pct,
            delta_percentage=res.delta_pct,
            prior_status=res.prior_status,
            new_status=res.new_status,
            is_gap_closed=res.is_gap_closed,
            transition_narrative=res.transition_narrative,
            pedagogical_badge=res.pedagogical_badge,
            evaluated_at=res.evaluated_at,
        )

    def generate_academic_handoff_brief(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        child_id: uuid.UUID,
    ) -> AcademicHandoffBriefResponse:
        """
        Synthesizes high-impact diagnostic Academic Handoff Brief for PTM / Tutors.
        """
        # 1. Non-negotiable B2C Boundary Isolation Check
        child = (
            db.query(Child)
            .filter(Child.child_id == child_id, Child.subscriber_id == subscriber_id)
            .first()
        )
        if not child:
            raise PermissionError("Child profile not found or not authorized for this subscriber.")

        student_name = getattr(child, "student_name", getattr(child, "first_name", "Student"))
        standard_class = child.standard_class
        board = child.board
        academic_year = getattr(child, "academic_year", "2026-2027") or "2026-2027"

        # 2. Extract Strengths (TopicScores >= 70%)
        strengths_query = (
            db.query(TopicScore)
            .join(CurriculumNode, TopicScore.node_id == CurriculumNode.node_id, isouter=True)
            .filter(TopicScore.child_id == child_id, TopicScore.percentage >= 70.0)
            .order_by(desc(TopicScore.percentage))
            .limit(5)
            .all()
        )

        strengths_data = [
            {
                "subject": ts.curriculum_node.subject if ts.curriculum_node else "General",
                "topic_name": ts.curriculum_node.topic_name if ts.curriculum_node else "Mastered Topic",
                "mastery_percentage": float(ts.percentage),
            }
            for ts in strengths_query
        ]

        # 3. Extract Active Gaps
        gaps_query = (
            db.query(TopicGap)
            .join(CurriculumNode, TopicGap.node_id == CurriculumNode.node_id, isouter=True)
            .filter(TopicGap.child_id == child_id, TopicGap.gap_status.in_(["ACTIVE", "IN_RECHECK"]))
            .order_by(desc(TopicGap.first_identified_at))
            .limit(5)
            .all()
        )

        gaps_data = []
        for g in gaps_query:
            c_node = g.curriculum_node
            # Check latest score if available
            ts = (
                db.query(TopicScore)
                .filter(TopicScore.child_id == child_id, TopicScore.node_id == g.node_id)
                .order_by(desc(TopicScore.evaluated_at))
                .first()
            )
            pct = float(ts.percentage) if ts else 35.0

            gaps_data.append({
                "subject": c_node.subject if c_node else "General",
                "chapter_name": c_node.chapter_name if c_node else (c_node.topic_name if c_node else "Core Topic"),
                "topic_name": c_node.topic_name if c_node else "Core Topic",
                "node_id": g.node_id,
                "current_percentage": pct,
            })

        # 4. Run AcademicHandoffEngine
        payload = {
            "child_id": str(child_id),
            "student_name": student_name,
            "standard_class": standard_class,
            "board": board,
            "academic_year": academic_year,
            "strengths": strengths_data,
            "gaps": gaps_data,
        }

        return self.handoff_engine.run(payload)
