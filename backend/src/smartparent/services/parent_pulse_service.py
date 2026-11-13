"""
STUDIQS® SmartParent™ (v6.2 Complete) - Parent Pulse & Learning Cycle Service
=============================================================================
Service: parent_pulse_service.py (Section 6)
Governs the 30-Day Closed-Loop Monthly Learning Cycle:
1. Evidence Intake (Quick Marks, Marks Grid, Question Papers, Expert Evaluations)
2. Automatic Synthesis (updates consistency, mastery levels, active gap watchlist)
3. 3-Card Parent Pulse Generation & Delivery (Green Improvement, Amber Watch, Blue Action)
4. Monthly Action List (Max 3 grounded actions on Home screen)
5. Progress Since Last Update (What changed tracking)

Strict Rule:
"Do not require daily data entry. One meaningful result, paper, diagnostic,
recheck or completed expert evaluation refreshes relevant intelligence.
No new evidence means no fabricated change."
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
from src.smartparent.db.models.marketplace import EvaluationCase
from src.smartparent.db.models.parent_pulse import ParentPulseRecord
from src.smartparent.engines.parent_pulse_engine import ParentPulseEngine
from src.smartparent.schemas.parent_pulse import (
    MonthlyParentPulseResponse,
    PulseCardSchema,
    GroundedActionItemSchema,
    ProgressSinceLastUpdateSchema,
)

logger = logging.getLogger("STUDIQS_ParentPulseService")


class ParentPulseService:
    """
    Section 6 Unified Parent Pulse & Monthly Learning Cycle Service.
    Enforces strict B2C multi-tenant subscriber-child isolation.
    """

    def __init__(self):
        self.pulse_engine = ParentPulseEngine()

    def get_or_synthesize_parent_pulse(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        child_id: uuid.UUID,
        month_key: Optional[str] = None,
        force_refresh: bool = False,
    ) -> MonthlyParentPulseResponse:
        """
        Retrieves or synthesizes the Monthly Parent Pulse for the authorized child.
        Enforces 'No new evidence = no fabricated change'.
        """
        # 1. Non-negotiable B2C Boundary Isolation Check
        child = (
            db.query(Child)
            .filter(Child.child_id == child_id, Child.subscriber_id == subscriber_id)
            .first()
        )
        if not child:
            logger.warning(
                f"[ParentPulse] Unauthorized access attempt: subscriber {subscriber_id} tried to access child {child_id}"
            )
            raise PermissionError("Child profile not found or not authorized for this subscriber.")

        student_name = getattr(child, "student_name", getattr(child, "first_name", "Student"))
        standard_class = child.standard_class

        target_month = month_key or datetime.utcnow().strftime("%Y-%m")
        try:
            pulse_period_label = datetime.strptime(target_month, "%Y-%m").strftime("%B %Y")
        except Exception:
            pulse_period_label = target_month

        # 2. Check for existing pulse record in DB
        existing_record = (
            db.query(ParentPulseRecord)
            .filter(
                ParentPulseRecord.child_id == child_id,
                ParentPulseRecord.month_key == target_month,
            )
            .order_by(desc(ParentPulseRecord.generated_at))
            .first()
        )

        # 3. Check for new evidence since last generation
        records = (
            db.query(EvidenceRecord)
            .filter(EvidenceRecord.child_id == child_id)
            .order_by(asc(EvidenceRecord.test_date), asc(EvidenceRecord.created_at))
            .all()
        )

        new_evidence_count = 0
        if existing_record:
            # Count records created after existing pulse was generated
            for r in records:
                r_created = r.created_at if r.created_at.tzinfo else r.created_at.replace(tzinfo=timezone.utc)
                ex_gen = existing_record.generated_at if existing_record.generated_at.tzinfo else existing_record.generated_at.replace(tzinfo=timezone.utc)
                if r_created > ex_gen:
                    new_evidence_count += 1

            # Strict Rule: "No new evidence means no fabricated change"
            if new_evidence_count == 0 and not force_refresh:
                logger.info(f"[ParentPulse] Returning confirmed pulse for {target_month} without fabricating change.")
                return self._build_response_from_record(
                    record=existing_record,
                    child=child,
                    student_name=student_name,
                    pulse_period=pulse_period_label,
                    has_new_evidence=False,
                )

        # 4. Synthesize New Pulse when new evidence is present or first time
        return self._synthesize_and_persist_pulse(
            db=db,
            child=child,
            subscriber_id=subscriber_id,
            student_name=student_name,
            target_month=target_month,
            pulse_period_label=pulse_period_label,
            records=records,
            existing_record=existing_record,
        )

    def _synthesize_and_persist_pulse(
        self,
        db: Session,
        child: Child,
        subscriber_id: uuid.UUID,
        student_name: str,
        target_month: str,
        pulse_period_label: str,
        records: List[EvidenceRecord],
        existing_record: Optional[ParentPulseRecord],
    ) -> MonthlyParentPulseResponse:
        """Runs the Parent Pulse Engine and commits the verified digest to PostgreSQL."""
        child_id = child.child_id
        standard_class = child.standard_class

        # Group records by month and subject
        subject_scores_synth = []
        prior_month_percentages = []
        cur_month_percentages = []

        by_subject: Dict[str, List[EvidenceRecord]] = {}
        for r in records:
            s_name = r.subject.strip()
            by_subject.setdefault(s_name, []).append(r)

        for s_name, s_records in by_subject.items():
            latest = s_records[-1]
            max_m = float(latest.total_max_marks) or 100.0
            cur_pct = round((float(latest.total_scored_marks) / max_m) * 100.0, 1)
            cur_month_percentages.append(cur_pct)

            prev_pct = cur_pct
            if len(s_records) > 1:
                prev_rec = s_records[-2]
                prev_max = float(prev_rec.total_max_marks) or 100.0
                prev_pct = round((float(prev_rec.total_scored_marks) / prev_max) * 100.0, 1)
                prior_month_percentages.append(prev_pct)

            subject_scores_synth.append({
                "subject": s_name,
                "score": cur_pct,
                "previous": prev_pct,
            })

        # Calculate movement delta
        cur_mean = round(sum(cur_month_percentages) / len(cur_month_percentages), 1) if cur_month_percentages else 0.0
        prior_mean = round(sum(prior_month_percentages) / len(prior_month_percentages), 1) if prior_month_percentages else cur_mean
        delta = round(cur_mean - prior_mean, 1)

        # Extract active topic gaps
        gaps_query = (
            db.query(TopicGap)
            .join(CurriculumNode, TopicGap.node_id == CurriculumNode.node_id, isouter=True)
            .filter(TopicGap.child_id == child_id)
            .all()
        )

        active_gaps = [g for g in gaps_query if g.gap_status in ("ACTIVE", "IN_RECHECK")]
        resolved_gaps = [g for g in gaps_query if g.gap_status == "RESOLVED"]

        # Run ParentPulseEngine
        engine_payload = {
            "child_id": str(child_id),
            "student_name": student_name,
            "pulse_period": pulse_period_label,
            "subject_scores": subject_scores_synth,
            "active_gaps": [
                {
                    "node_id": g.node_id,
                    "topic_name": g.curriculum_node.topic_name if g.curriculum_node else "General Topic",
                    "subject": g.curriculum_node.subject if g.curriculum_node else "General",
                }
                for g in active_gaps
            ],
        }

        pulse_result = self.pulse_engine.run(engine_payload)

        # Synthesize Max 3 Grounded Actions (Section 6 & 7)
        grounded_actions: List[GroundedActionItemSchema] = []

        # Action 1: Targeted practice for critical watch area
        if active_gaps:
            top_gap = active_gaps[0]
            top_topic = top_gap.curriculum_node.topic_name if top_gap.curriculum_node else "Core Concepts"
            top_subj = top_gap.curriculum_node.subject if top_gap.curriculum_node else "General"
            grounded_actions.append(
                GroundedActionItemSchema(
                    action_id=f"act-practice-{str(top_gap.gap_id)[:8]}",
                    action_type="PRACTICE",
                    title=f"Practice 5 Guided Questions in {top_topic}",
                    description=f"Review foundational formulas and attempt targeted practice in {top_subj}.",
                    subject=top_subj,
                    topic_name=top_topic,
                    action_url=f"/practice/{top_gap.node_id}",
                )
            )

            # Action 2: Gap Recheck diagnostic
            grounded_actions.append(
                GroundedActionItemSchema(
                    action_id=f"act-recheck-{str(top_gap.gap_id)[:8]}",
                    action_type="DIAGNOSTIC_RECHECK",
                    title=f"Take 10-Minute Gap Recheck in {top_topic}",
                    description="Verify concept closure after revision. Scoring >= 80% marks the gap resolved.",
                    subject=top_subj,
                    topic_name=top_topic,
                    action_url=f"/recheck/{top_gap.gap_id}",
                )
            )

        # Action 3: Persistent weak subject -> "Ask a Subject Expert" (Section 7 rule)
        weak_subjects = [s["subject"] for s in subject_scores_synth if s["score"] < 50.0]
        if weak_subjects:
            target_weak = weak_subjects[0]
            grounded_actions.append(
                GroundedActionItemSchema(
                    action_id=f"act-expert-{target_weak.lower()[:4]}",
                    action_type="ASK_EXPERT",
                    title=f"Ask a Subject Expert for {target_weak}",
                    description=f"{target_weak} score is below 50%. Submit an answer sheet for certified human expert grading and feedback.",
                    subject=target_weak,
                    action_url=f"/marketplace/experts?subject={target_weak}",
                )
            )
        elif len(grounded_actions) < 3:
            # General revision action
            primary_subj = subject_scores_synth[0]["subject"] if subject_scores_synth else "General"
            grounded_actions.append(
                GroundedActionItemSchema(
                    action_id="act-routine-revision",
                    action_type="REVISION",
                    title=f"Maintain 20-Minute Daily Revision in {primary_subj}",
                    description="Consistent daily review prevents topic erosion and reinforces strong areas.",
                    subject=primary_subj,
                )
            )

        # Cap strictly at 3 actions
        grounded_actions = grounded_actions[:3]

        # Determine Progress Since Last Update
        if delta > 2.0:
            dir_str = "IMPROVING"
            summary_txt = f"+{delta}% upward momentum across confirmed test assessments this month."
        elif delta < -2.0:
            dir_str = "DECLINING"
            summary_txt = f"{delta}% dip observed; remedial practice recommended in watch areas."
        else:
            dir_str = "STABLE"
            summary_txt = "Consistent academic baseline maintained across subjects."

        progress = ProgressSinceLastUpdateSchema(
            prior_period=None,
            current_period=pulse_period_label,
            overall_movement_delta=delta,
            movement_direction=dir_str,
            new_evidence_count=len(records),
            gaps_closed_count=len(resolved_gaps),
            active_gaps_count=len(active_gaps),
            has_meaningful_change=True,
            narrative_summary=summary_txt,
        )

        now_dt = datetime.now(timezone.utc)

        # Persist or update ParentPulseRecord
        if existing_record:
            existing_record.improvement_text = pulse_result.improvement_area.description
            existing_record.watch_area_text = pulse_result.watch_area.description
            existing_record.next_action_text = pulse_result.next_immediate_action.description
            existing_record.grounded_actions = [a.model_dump() for a in grounded_actions]
            existing_record.movement_delta = delta
            existing_record.generated_at = now_dt
            db.commit()
            pulse_id = str(existing_record.pulse_id)
        else:
            new_pulse = ParentPulseRecord(
                pulse_id=uuid.uuid4(),
                subscriber_id=subscriber_id,
                child_id=child_id,
                month_key=target_month,
                improvement_text=pulse_result.improvement_area.description,
                watch_area_text=pulse_result.watch_area.description,
                next_action_text=pulse_result.next_immediate_action.description,
                grounded_actions=[a.model_dump() for a in grounded_actions],
                movement_delta=delta,
                generated_at=now_dt,
            )
            db.add(new_pulse)
            db.commit()
            pulse_id = str(new_pulse.pulse_id)

        # Dispatch Section 15 notification event safely (Avoid spam / zero crash)
        try:
            from src.smartparent.services.notification_service import NotificationService
            from src.smartparent.schemas.notification import NotificationCreateRequest
            from src.smartparent.core.constants import NotificationEventType

            notif_service = NotificationService(db)
            notif_service.dispatch_notification(
                NotificationCreateRequest(
                    subscriber_id=str(subscriber_id),
                    child_id=str(child_id),
                    event_type=NotificationEventType.PARENT_PULSE_READY.value,
                    metadata={
                        "student_name": student_name,
                        "report_month": pulse_period_label,
                    },
                )
            )
        except Exception as notif_err:
            logger.debug(f"[ParentPulseService] Notification dispatch deferred/skipped: {notif_err}")

        return MonthlyParentPulseResponse(
            pulse_id=pulse_id,
            child_id=str(child_id),
            student_name=student_name,
            standard_class=standard_class,
            month_key=target_month,
            pulse_period=pulse_period_label,
            overall_health_indicator=pulse_result.overall_health_indicator,
            improvement_area=PulseCardSchema(
                card_type="IMPROVEMENT",
                title=pulse_result.improvement_area.title,
                headline=pulse_result.improvement_area.headline,
                description=pulse_result.improvement_area.description,
                metric_badge=pulse_result.improvement_area.metric_badge,
                subject=pulse_result.improvement_area.subject,
                priority_level=pulse_result.improvement_area.priority_level,
                color_theme="GREEN",
            ),
            watch_area=PulseCardSchema(
                card_type="WATCH_AREA",
                title=pulse_result.watch_area.title,
                headline=pulse_result.watch_area.headline,
                description=pulse_result.watch_area.description,
                metric_badge=pulse_result.watch_area.metric_badge,
                subject=pulse_result.watch_area.subject,
                priority_level=pulse_result.watch_area.priority_level,
                color_theme="AMBER",
            ),
            next_immediate_action=PulseCardSchema(
                card_type="NEXT_ACTION",
                title=pulse_result.next_immediate_action.title,
                headline=pulse_result.next_immediate_action.headline,
                description=pulse_result.next_immediate_action.description,
                metric_badge=pulse_result.next_immediate_action.metric_badge,
                subject=pulse_result.next_immediate_action.subject,
                priority_level=pulse_result.next_immediate_action.priority_level,
                color_theme="BLUE",
            ),
            grounded_actions=grounded_actions,
            progress_since_last_update=progress,
            is_fabricated=False,
            evidence_status="CONFIRMED_EVIDENCE_PRESENT",
            generated_at=now_dt.isoformat(),
        )

    def _build_response_from_record(
        self,
        record: ParentPulseRecord,
        child: Child,
        student_name: str,
        pulse_period: str,
        has_new_evidence: bool,
    ) -> MonthlyParentPulseResponse:
        """Converts an existing confirmed database record into response."""
        actions = [
            GroundedActionItemSchema(**a) if isinstance(a, dict) else a
            for a in (record.grounded_actions or [])
        ]

        delta = float(record.movement_delta or 0.0)
        dir_str = "IMPROVING" if delta > 2.0 else ("DECLINING" if delta < -2.0 else "STABLE")

        progress = ProgressSinceLastUpdateSchema(
            prior_period=None,
            current_period=pulse_period,
            overall_movement_delta=delta,
            movement_direction=dir_str,
            new_evidence_count=0,
            gaps_closed_count=0,
            active_gaps_count=len(actions),
            has_meaningful_change=False,
            narrative_summary="No new test evidence recorded since last pulse; confirmed baseline preserved.",
        )

        return MonthlyParentPulseResponse(
            pulse_id=str(record.pulse_id),
            child_id=str(child.child_id),
            student_name=student_name,
            standard_class=child.standard_class,
            month_key=record.month_key,
            pulse_period=pulse_period,
            overall_health_indicator="PROGRESSING",
            improvement_area=PulseCardSchema(
                card_type="IMPROVEMENT",
                title="Top Monthly Improvement",
                headline="Demonstrating Upward Momentum",
                description=record.improvement_text,
                color_theme="GREEN",
            ),
            watch_area=PulseCardSchema(
                card_type="WATCH_AREA",
                title="Key Watch Area",
                headline="Pinpointed Concept Attention",
                description=record.watch_area_text,
                color_theme="AMBER",
            ),
            next_immediate_action=PulseCardSchema(
                card_type="NEXT_ACTION",
                title="Immediate Next Action",
                headline="Focused Action Plan",
                description=record.next_action_text,
                color_theme="BLUE",
            ),
            grounded_actions=actions,
            progress_since_last_update=progress,
            is_fabricated=False,
            evidence_status="CONFIRMED_BASELINE_PRESERVED",
            generated_at=record.generated_at.isoformat(),
        )

    def get_grounded_actions(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        child_id: uuid.UUID,
    ) -> List[GroundedActionItemSchema]:
        """Returns the active max 3 grounded actions for the child."""
        pulse = self.get_or_synthesize_parent_pulse(db, subscriber_id, child_id)
        return pulse.grounded_actions

    def get_pulse_history(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        child_id: uuid.UUID,
    ) -> List[MonthlyParentPulseResponse]:
        """Returns all historical parent pulses for the child."""
        child = (
            db.query(Child)
            .filter(Child.child_id == child_id, Child.subscriber_id == subscriber_id)
            .first()
        )
        if not child:
            raise PermissionError("Child profile not found or not authorized.")

        records = (
            db.query(ParentPulseRecord)
            .filter(ParentPulseRecord.child_id == child_id)
            .order_by(desc(ParentPulseRecord.generated_at))
            .all()
        )

        student_name = getattr(child, "student_name", getattr(child, "first_name", "Student"))
        responses = []
        for r in records:
            try:
                p_label = datetime.strptime(r.month_key, "%Y-%m").strftime("%B %Y")
            except Exception:
                p_label = r.month_key

            responses.append(
                self._build_response_from_record(
                    record=r,
                    child=child,
                    student_name=student_name,
                    pulse_period=p_label,
                    has_new_evidence=False,
                )
            )

        return responses
