"""
STUDIQS® SmartParent™ (v6.2 Complete) - Parent Pulse Engine
Engine 10: parent_pulse_engine.py

Synthesizes complex longitudinal and topic diagnostic telemetry into the mandatory
3-Card Parent Pulse Digest:
  1. One Improvement Area (Green Card) - Praise & upward momentum
  2. One Watch Area (Amber Card) - Non-alarmist, pinpointed conceptual gap
  3. One Next Immediate Action (Blue Card) - Practical, high-ROI 2-week home guidance
"""

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, ConfigDict

from src.smartparent.engines.base_engine import BaseEngine, EngineHealthStatus

logger = logging.getLogger("STUDIQS_ParentPulseEngine")


# =============================================================================
# 1. Pydantic v2 Type-Safe Schemas
# =============================================================================

class ParentPulseCardSchema(BaseModel):
    """Schema for an individual pulse card (Improvement, Watch, or Action)."""
    model_config = ConfigDict(extra="ignore")

    card_type: str  # 'IMPROVEMENT', 'WATCH_AREA', 'NEXT_ACTION'
    title: str
    headline: str
    description: str
    metric_badge: Optional[str] = None
    subject: Optional[str] = None
    priority_level: str = "NORMAL"  # 'NORMAL', 'HIGH', 'URGENT'


class ParentPulseDigestResult(BaseModel):
    """Complete 3-card Parent Pulse Digest output for Mobile Dashboard and Monthly Report."""
    model_config = ConfigDict(extra="ignore")

    child_id: Optional[str] = None
    student_name: str = "Student"
    pulse_period: str = Field(default_factory=lambda: datetime.utcnow().strftime("%B %Y"))
    overall_health_indicator: str  # 'EXCELLENT', 'PROGRESSING', 'ATTENTION_NEEDED'
    improvement_area: ParentPulseCardSchema
    watch_area: ParentPulseCardSchema
    next_immediate_action: ParentPulseCardSchema
    supporting_metrics: Dict[str, Any] = Field(default_factory=dict)
    generated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


# =============================================================================
# 2. Production Parent Pulse Engine Implementation
# =============================================================================

class ParentPulseEngine(BaseEngine):
    """
    Engine 10: Parent Pulse Engine
    
    Transforms student assessment telemetry into empathetic, non-stressful,
    high-clarity parent insights. Applies a 'Praise First, Nudge Second'
    pedagogical psychology standard.
    """

    def __init__(self, failure_threshold: int = 5):
        super().__init__(name="ParentPulseEngine", failure_threshold=failure_threshold)

    # -------------------------------------------------------------------------
    # BaseEngine Template Method Lifecycle Hooks
    # -------------------------------------------------------------------------

    def validate_input(self, input_data: Any) -> Dict[str, Any]:
        """
        Validates input telemetry. Accepts:
          - Dict containing consistency results, topic gaps, and student metadata
          - MultiSubjectConsistencyResult instance or dict
        """
        if not input_data:
            raise ValueError("Input data cannot be empty.")

        if hasattr(input_data, "model_dump"):
            data = input_data.model_dump()
        elif hasattr(input_data, "dict"):
            data = input_data.dict()
        elif isinstance(input_data, dict):
            data = dict(input_data)
        else:
            raise ValueError(f"Unsupported input type for ParentPulseEngine: {type(input_data)}")

        return data

    def execute_core(self, validated_data: Dict[str, Any]) -> ParentPulseDigestResult:
        """Executes core synthesis of the 3-Card Parent Pulse Digest."""
        student_name = str(validated_data.get("student_name") or validated_data.get("child_name") or "Your child").strip()
        child_id = str(validated_data.get("child_id") or "")
        period = validated_data.get("pulse_period") or validated_data.get("period") or datetime.utcnow().strftime("%B %Y")

        # 1. Parse Consistency / Trajectory Data
        trajectories = validated_data.get("subject_trajectories")
        c_res = validated_data.get("consistency_result") or validated_data.get("multi_subject_consistency")
        if not trajectories and c_res:
            if hasattr(c_res, "subject_trajectories"):
                trajectories = c_res.subject_trajectories
            elif isinstance(c_res, dict):
                trajectories = c_res.get("subject_trajectories", {})
        if not trajectories and "evaluated_subjects" in validated_data:
            trajectories = validated_data.get("subject_trajectories", {})
        if not trajectories:
            trajectories = {}

        # 2. Parse Topic Gaps Data
        active_gaps = validated_data.get("active_gaps") or validated_data.get("critical_topics") or []
        weak_topics = validated_data.get("weak_topics") or []
        strong_topics = validated_data.get("strong_topics") or []

        # 3. Synthesize Card 1: Improvement Area (Green)
        improvement_card = self._synthesize_improvement_card(trajectories, strong_topics, student_name)

        # 4. Synthesize Card 2: Watch Area (Amber)
        watch_card = self._synthesize_watch_card(trajectories, active_gaps, weak_topics, student_name)

        # 5. Synthesize Card 3: Next Immediate Action (Blue)
        action_card = self._synthesize_action_card(watch_card, student_name)

        # 6. Overall Health Determination
        health_status = self._determine_overall_health(improvement_card, watch_card, trajectories)

        # Supporting Metrics Resolution
        pillar_subjects = validated_data.get("pillar_subjects")
        risk_subjects = validated_data.get("risk_subjects")
        overall_mean = validated_data.get("overall_mean_percentage")
        if c_res:
            if pillar_subjects is None:
                pillar_subjects = getattr(c_res, "pillar_subjects", c_res.get("pillar_subjects", [])) if isinstance(c_res, dict) else getattr(c_res, "pillar_subjects", [])
            if risk_subjects is None:
                risk_subjects = getattr(c_res, "risk_subjects", c_res.get("risk_subjects", [])) if isinstance(c_res, dict) else getattr(c_res, "risk_subjects", [])
            if overall_mean is None:
                overall_mean = getattr(c_res, "overall_mean_percentage", c_res.get("overall_mean_percentage", 0.0)) if isinstance(c_res, dict) else getattr(c_res, "overall_mean_percentage", 0.0)

        supporting_metrics = {
            "total_subjects_evaluated": len(trajectories),
            "pillar_subjects": pillar_subjects or [],
            "risk_subjects": risk_subjects or [],
            "overall_mean_percentage": float(overall_mean or 0.0),
            "unresolved_critical_gaps_count": len(active_gaps)
        }

        return ParentPulseDigestResult(
            child_id=child_id if child_id else None,
            student_name=student_name,
            pulse_period=period,
            overall_health_indicator=health_status,
            improvement_area=improvement_card,
            watch_area=watch_card,
            next_immediate_action=action_card,
            supporting_metrics=supporting_metrics
        )

    def fallback(self, error: Exception, input_data: Any) -> ParentPulseDigestResult:
        """Safe degraded fallback response ensuring parent mobile screens never crash."""
        logger.warning(f"[ParentPulseEngine] Executing fallback due to error: {error}")
        curr_period = datetime.utcnow().strftime("%B %Y")
        return ParentPulseDigestResult(
            student_name="Student",
            pulse_period=curr_period,
            overall_health_indicator="PROGRESSING",
            improvement_area=ParentPulseCardSchema(
                card_type="IMPROVEMENT",
                title="Academic Consistency",
                headline="Active Learning in Progress",
                description="Your child is participating in ongoing academic assessments.",
                metric_badge="Steady Effort"
            ),
            watch_area=ParentPulseCardSchema(
                card_type="WATCH_AREA",
                title="Core Concept Retention",
                headline="Regular Practice Suggested",
                description="Continue supporting routine homework review and periodic chapter practice.",
                metric_badge="Monitor"
            ),
            next_immediate_action=ParentPulseCardSchema(
                card_type="NEXT_ACTION",
                title="Weekly Review Routine",
                headline="Dedicate 20 Minutes to Concept Discussions",
                description="Spend 20 minutes this weekend asking your child to explain their favorite chapter topic to you.",
                priority_level="NORMAL"
            ),
            supporting_metrics={"error": str(error)[:100], "degraded": True}
        )

    # -------------------------------------------------------------------------
    # Card Synthesis Algorithms
    # -------------------------------------------------------------------------

    def _synthesize_improvement_card(
        self,
        trajectories: Dict[str, Any],
        strong_topics: List[Any],
        student_name: str
    ) -> ParentPulseCardSchema:
        """Synthesizes the Green Improvement Card (Praise First standard)."""
        best_subj = None
        best_delta = -999.0
        best_actual_delta = 0.0
        best_latest_pct = 0.0

        for subj, traj in trajectories.items():
            if isinstance(traj, dict):
                delta = float(traj.get("direction_delta_60d", traj.get("recent_delta", 0.0)))
                latest_pct = float(traj.get("latest_percentage", 0.0))
                status = str(traj.get("trajectory_status", ""))
            else:
                delta = getattr(traj, "direction_delta_60d", getattr(traj, "recent_delta", 0.0))
                latest_pct = getattr(traj, "latest_percentage", 0.0)
                status = getattr(traj, "trajectory_status", "")

            # Prioritize improving trajectories with highest positive delta, or strong mastery
            score_weight = delta * 1.5 + (latest_pct * 0.5)
            if score_weight > best_delta:
                best_delta = score_weight
                best_actual_delta = delta
                best_subj = subj
                best_latest_pct = latest_pct

        strong_topic_name = self._extract_topic_name(strong_topics[0]) if strong_topics else ""

        if best_subj and (best_delta > 0 or best_latest_pct >= 60.0):
            if best_actual_delta > 0:
                headline = f"Strong Progress in {best_subj}"
                badge = f"+{best_actual_delta:.1f}% Growth"
            else:
                headline = f"Consistent Mastery in {best_subj}"
                badge = f"{best_latest_pct:.1f}% Score"

            if strong_topic_name:
                desc = (
                    f"{student_name} has shown notable strength in {best_subj} (currently at {best_latest_pct:.1f}%), "
                    f"demonstrating solid mastery in topics like {strong_topic_name}."
                )
            else:
                desc = (
                    f"{student_name} demonstrates steady academic discipline in {best_subj}, "
                    f"reaching {best_latest_pct:.1f}% on recent assessments."
                )
        elif strong_topic_name:
            headline = f"Mastery in {strong_topic_name}"
            desc = f"{student_name} demonstrates excellent conceptual clarity and high retention in {strong_topic_name}."
            badge = "Mastered"
            best_subj = "General"
        else:
            headline = "Consistent Academic Engagement"
            desc = f"{student_name} maintains steady diligence across core academic subjects. Acknowledge their effort to keep motivation high."
            badge = "Steady"
            best_subj = "General"

        return ParentPulseCardSchema(
            card_type="IMPROVEMENT",
            title="Key Academic Strength",
            headline=headline,
            description=desc,
            metric_badge=badge,
            subject=best_subj
        )

    def _synthesize_watch_card(
        self,
        trajectories: Dict[str, Any],
        critical_gaps: List[Any],
        weak_topics: List[Any],
        student_name: str
    ) -> ParentPulseCardSchema:
        """Synthesizes the Amber Watch Area Card (Pinpointed, non-alarmist)."""
        worst_subj = None
        worst_delta = 999.0
        worst_latest_pct = 100.0

        for subj, traj in trajectories.items():
            if isinstance(traj, dict):
                delta = float(traj.get("direction_delta_60d", traj.get("recent_delta", 0.0)))
                latest_pct = float(traj.get("latest_percentage", 100.0))
            else:
                delta = getattr(traj, "direction_delta_60d", getattr(traj, "recent_delta", 0.0))
                latest_pct = getattr(traj, "latest_percentage", 100.0)

            if delta < worst_delta:
                worst_delta = delta
                worst_subj = subj
                worst_latest_pct = latest_pct

        gap_topic_name = ""
        if critical_gaps:
            gap_topic_name = self._extract_topic_name(critical_gaps[0])
        elif weak_topics:
            gap_topic_name = self._extract_topic_name(weak_topics[0])

        if gap_topic_name and worst_subj and (worst_delta < -3.0 or worst_latest_pct < 60.0):
            headline = f"{worst_subj}: Needs Focus in {gap_topic_name}"
            if worst_delta < -3.0:
                desc = (
                    f"Recent scores in {worst_subj} experienced a slight dip ({worst_delta:.1f}%), "
                    f"primarily related to conceptual difficulty in {gap_topic_name}. Targeted review will quickly bridge this."
                )
                badge = f"Drop: {worst_delta:.1f}%"
            else:
                desc = (
                    f"Current scores in {worst_subj} are at {worst_latest_pct:.1f}%, "
                    f"with specific challenges observed in {gap_topic_name}. Targeted review will quickly bridge this."
                )
                badge = f"Current: {worst_latest_pct:.1f}%"
            priority = "HIGH"
        elif gap_topic_name:
            headline = f"Conceptual Gap in {gap_topic_name}"
            desc = (
                f"{student_name} is finding {gap_topic_name} somewhat challenging. "
                f"Reinforcing the underlying basics over the next two weeks will restore confidence."
            )
            badge = "Review Needed"
            priority = "HIGH"
        elif worst_subj and (worst_delta < -3.0 or worst_latest_pct < 60.0):
            if worst_delta < -3.0:
                headline = f"Attention Needed in {worst_subj}"
                desc = (
                    f"{worst_subj} has shown a temporary downward trend ({worst_delta:.1f}%, currently {worst_latest_pct:.1f}%). "
                    f"Scheduling light daily practice will help reverse this movement."
                )
                badge = f"{worst_delta:.1f}%"
            else:
                headline = f"Foundational Support Needed in {worst_subj}"
                desc = (
                    f"{worst_subj} scores are currently at {worst_latest_pct:.1f}%. "
                    f"Scheduling light daily practice will help build mastery and exam readiness."
                )
                badge = f"Current: {worst_latest_pct:.1f}%"
            priority = "HIGH" if worst_latest_pct < 50.0 else "NORMAL"
        else:
            headline = "Maintaining Foundation Consistency"
            desc = f"No critical conceptual gaps detected. Focus on routine revision to prevent end-of-term exam rush."
            badge = "On Track"
            priority = "NORMAL"
            worst_subj = "General"

        return ParentPulseCardSchema(
            card_type="WATCH_AREA",
            title="Key Area for Home Support",
            headline=headline,
            description=desc,
            metric_badge=badge,
            subject=worst_subj,
            priority_level=priority
        )

    def _synthesize_action_card(
        self,
        watch_card: ParentPulseCardSchema,
        student_name: str
    ) -> ParentPulseCardSchema:
        """Synthesizes the Blue Next Immediate Action Card (Actionable, High-ROI)."""
        topic = watch_card.headline.split(":")[-1].replace("Needs Focus in", "").replace("Conceptual Gap in", "").strip()
        if not topic or topic.lower() in ("maintaining foundation consistency", "general"):
            headline = "Celebrate Wins and Set Weekend Goals"
            desc = (
                f"Praise {student_name}'s steady effort. Spend 15 minutes this weekend reviewing "
                f"upcoming test schedules together to maintain momentum."
            )
            priority = "NORMAL"
        else:
            headline = f"15-Minute Daily Guided Drill on {topic}"
            desc = (
                f"Have {student_name} solve 3 foundational problems on {topic} over the next 4 days. "
                f"Estimated outcome: +5 to +8 marks recovery on the next classroom assessment."
            )
            priority = "HIGH"

        return ParentPulseCardSchema(
            card_type="NEXT_ACTION",
            title="Next 2-Week Action Plan",
            headline=headline,
            description=desc,
            metric_badge="High Payoff",
            subject=watch_card.subject,
            priority_level=priority
        )

    def _determine_overall_health(
        self,
        imp: ParentPulseCardSchema,
        watch: ParentPulseCardSchema,
        trajectories: Dict[str, Any]
    ) -> str:
        """Determines holistic progress badge."""
        if watch.priority_level == "HIGH":
            return "ATTENTION_NEEDED"
        elif any(
            (getattr(t, "trajectory_status", "") == "IMPROVING" or (isinstance(t, dict) and t.get("trajectory_status") == "IMPROVING"))
            for t in trajectories.values()
        ):
            return "EXCELLENT"
        return "PROGRESSING"

    def _extract_topic_name(self, topic_item: Any) -> str:
        """Extracts plain topic string from string, dictionary, or object representation."""
        if not topic_item:
            return ""
        if isinstance(topic_item, str):
            return topic_item.strip()
        if hasattr(topic_item, "topic_name"):
            return str(topic_item.topic_name).strip()
        if hasattr(topic_item, "topic"):
            return str(topic_item.topic).strip()
        if hasattr(topic_item, "name"):
            return str(topic_item.name).strip()
        if isinstance(topic_item, dict):
            return str(topic_item.get("topic_name") or topic_item.get("topic") or topic_item.get("name") or "Concept").strip()
        return str(topic_item).strip()
