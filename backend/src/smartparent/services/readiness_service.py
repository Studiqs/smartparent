"""
STUDIQS® SmartParent™ (v6.2 Complete) - Section 8 Board Readiness & Share Mode Service
=============================================================================
Service: readiness_service.py (Section 8)
Governs:
1. Board Exam Readiness Index & High-Weightage Risk Radar (Classes 10 & 12)
2. Student Academic Milestones & Achievement Badges Engine
3. Parent-Authorized 72-Hour Time-Limited Share Link Generation
4. Public Sanitized Diagnostic Report Viewer (Zero Privacy Leakage for Tutors)
5. Parent-Controlled Instant Link Revocation
=============================================================================
"""

import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

from src.smartparent.db.models.auth import Child, Subscriber
from src.smartparent.db.models.assessment import EvidenceRecord
from src.smartparent.db.models.curriculum import CurriculumNode
from src.smartparent.db.models.diagnostic import TopicGap, TopicScore
from src.smartparent.db.models.readiness import BoardReadinessRecord, SharedReportToken
from src.smartparent.engines.board_readiness_engine import BoardReadinessEngine
from src.smartparent.engines.achievement_engine import AchievementEngine
from src.smartparent.schemas.readiness import (
    BoardReadinessResponse,
    ScoreCorridorSchema,
    SyllabusCoverageSchema,
    HighWeightageRiskTopicSchema,
    RiskRadarSchema,
    SubjectReadinessDetailSchema,
    StreamAlignmentSchema,
    PriorityActionItemSchema,
    StudentAchievementsResponse,
    AchievementBadgeSchema,
    ShareLinkResponse,
    ActiveShareTokenSchema,
    ActiveShareTokensListResponse,
    RevokeShareLinkResponse,
    PublicSharedReportResponse,
)

logger = logging.getLogger("STUDIQS_ReadinessService")


class ReadinessService:
    """
    Section 8 Unified Board Readiness, Achievements & Secure Share Mode Service.
    Enforces strict B2C multi-tenant subscriber-child isolation and zero-privacy leakage.
    """

    def __init__(self):
        self.board_engine = BoardReadinessEngine()
        self.achievement_engine = AchievementEngine()

    def get_board_readiness(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        child_id: uuid.UUID,
    ) -> BoardReadinessResponse:
        """
        Calculates and returns complete Board Exam Readiness Index.
        Persists snapshot in `board_readiness_records`.
        """
        # 1. Non-negotiable B2C Boundary Isolation Check
        child = (
            db.query(Child)
            .filter(Child.child_id == child_id, Child.subscriber_id == subscriber_id)
            .first()
        )
        if not child:
            raise PermissionError("Unauthorized: Student record does not belong to subscriber.")

        # 2. Gather verified test evidence
        evidence_records_raw = (
            db.query(EvidenceRecord)
            .filter(EvidenceRecord.child_id == child_id)
            .order_by(desc(EvidenceRecord.created_at))
            .limit(25)
            .all()
        )
        evidence_dicts = []
        for rec in evidence_records_raw:
            scored = float(getattr(rec, "total_scored_marks", getattr(rec, "scored_marks", 0.0)))
            max_m = float(getattr(rec, "total_max_marks", getattr(rec, "max_marks", 100.0)))
            if max_m > 0:
                evidence_dicts.append({
                    "subject": rec.subject,
                    "scored_marks": scored,
                    "max_marks": max_m,
                    "exam_type": getattr(rec, "evidence_type", getattr(rec, "exam_type", "OTHER")),
                    "test_title": rec.test_title or "School Test",
                })

        # 3. Gather topic scores
        topic_scores_raw = (
            db.query(TopicScore)
            .filter(TopicScore.child_id == child_id)
            .all()
        )
        topic_score_dicts = [
            {
                "topic_id": str(ts.node_id),
                "topic_name": ts.curriculum_node.topic_name if ts.curriculum_node else getattr(ts, "topic_name", "General Topic"),
                "subject": ts.curriculum_node.subject if ts.curriculum_node else getattr(ts, "subject", "GENERAL"),
                "score_percentage": float(ts.percentage) if hasattr(ts, "percentage") else float(getattr(ts, "score_percentage", 0.0)),
                "mastery_tier": ts.mastery_tier,
            }
            for ts in topic_scores_raw
        ]

        # 4. Gather topic gaps
        topic_gaps_raw = (
            db.query(TopicGap)
            .filter(TopicGap.child_id == child_id)
            .all()
        )
        topic_gap_dicts = [
            {
                "gap_id": str(g.gap_id),
                "topic_name": g.curriculum_node.topic_name if g.curriculum_node else getattr(g, "topic_name", "General Topic"),
                "subject": g.curriculum_node.subject if g.curriculum_node else getattr(g, "subject", "GENERAL"),
                "gap_status": g.gap_status,
                "is_critical": getattr(g, "is_critical", g.gap_status == "ACTIVE"),
                "severity": getattr(g, "severity", "CRITICAL" if g.gap_status == "ACTIVE" else "MODERATE"),
            }
            for g in topic_gaps_raw
        ]

        # 5. Gather curriculum taxonomy for child's class and board
        curriculum_query = db.query(CurriculumNode).filter(
            CurriculumNode.standard_class == child.standard_class,
            CurriculumNode.board == child.board,
        )
        # Section 5 non-negotiable rule: Tamil language exclusion
        curriculum_query = curriculum_query.filter(CurriculumNode.subject != "TAMIL")
        curriculum_nodes = curriculum_query.all()

        curriculum_dicts = [
            {
                "node_id": str(node.node_id),
                "topic_name": node.topic_name,
                "subject": node.subject,
                "chapter_name": node.chapter_name or "Core Chapter",
                "weightage_marks": float(node.weightage_marks) if hasattr(node, "weightage_marks") and node.weightage_marks else 10.0,
            }
            for node in curriculum_nodes
        ]

        # 6. Execute Board Readiness Engine
        eval_result = self.board_engine.evaluate_board_readiness(
            standard_class=child.standard_class,
            board=child.board,
            evidence_records=evidence_dicts,
            topic_scores=topic_score_dicts,
            topic_gaps=topic_gap_dicts,
            curriculum_topics=curriculum_dicts,
            consistency_slope=0.08,  # Default steady positive slope
            stability_index=0.82,
        )

        now_utc = datetime.now(timezone.utc)

        # 7. Persist or Update BoardReadinessRecord
        existing_record = (
            db.query(BoardReadinessRecord)
            .filter(
                BoardReadinessRecord.child_id == child_id,
                BoardReadinessRecord.standard_class == child.standard_class,
            )
            .first()
        )

        stream_data = eval_result["stream_alignment"]
        score_corridor = eval_result["score_corridor"]

        if existing_record:
            existing_record.projected_board_score = score_corridor["most_likely_pct"]
            existing_record.stream_readiness_data = stream_data
            existing_record.career_readiness_summary = eval_result["status_rationale"]
            existing_record.evaluated_at = now_utc
        else:
            new_record = BoardReadinessRecord(
                child_id=child_id,
                standard_class=child.standard_class,
                stream_id=stream_data.get("recommended_stream"),
                projected_board_score=score_corridor["most_likely_pct"],
                stream_readiness_data=stream_data,
                career_readiness_summary=eval_result["status_rationale"],
                evaluated_at=now_utc,
            )
            db.add(new_record)

        try:
            db.commit()
        except Exception as e:
            logger.warning(f"Could not persist BoardReadinessRecord snapshot: {e}")
            db.rollback()

        # 8. Assemble Pydantic v2 response
        corridor_schema = ScoreCorridorSchema(**score_corridor)
        coverage_schema = SyllabusCoverageSchema(**eval_result["syllabus_coverage"])

        risk_topics_schemas = [
            HighWeightageRiskTopicSchema(**rt)
            for rt in eval_result["risk_radar"]["risk_topics"]
        ]
        risk_radar_schema = RiskRadarSchema(
            high_weightage_risk_count=eval_result["risk_radar"]["high_weightage_risk_count"],
            critical_risk_count=eval_result["risk_radar"]["critical_risk_count"],
            risk_index=eval_result["risk_radar"]["risk_index"],
            risk_level=eval_result["risk_radar"]["risk_level"],
            risk_topics=risk_topics_schemas,
        )

        subject_breakdown_schemas = {
            subj: SubjectReadinessDetailSchema(**data)
            for subj, data in eval_result["subject_breakdown"].items()
        }

        stream_schema = StreamAlignmentSchema(**stream_data)

        priority_actions = [
            PriorityActionItemSchema(**act)
            for act in eval_result["priority_action_checklist"]
        ]

        return BoardReadinessResponse(
            child_id=child_id,
            student_name=child.student_name,
            standard_class=child.standard_class,
            board=child.board,
            readiness_status=eval_result["readiness_status"],
            status_rationale=eval_result["status_rationale"],
            is_board_appearing_grade=eval_result["is_board_appearing_grade"],
            score_corridor=corridor_schema,
            syllabus_coverage=coverage_schema,
            risk_radar=risk_radar_schema,
            subject_breakdown=subject_breakdown_schemas,
            stream_alignment=stream_schema,
            priority_action_checklist=priority_actions,
            evaluated_at=now_utc,
        )

    def get_student_achievements(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        child_id: uuid.UUID,
    ) -> StudentAchievementsResponse:
        """
        Evaluates dynamic student achievements and milestones.
        """
        child = (
            db.query(Child)
            .filter(Child.child_id == child_id, Child.subscriber_id == subscriber_id)
            .first()
        )
        if not child:
            raise PermissionError("Unauthorized: Student record does not belong to subscriber.")

        # Gather evidence & gaps
        evidence_records_raw = (
            db.query(EvidenceRecord)
            .filter(EvidenceRecord.child_id == child_id)
            .all()
        )
        evidence_dicts = []
        for rec in evidence_records_raw:
            scored = float(getattr(rec, "total_scored_marks", getattr(rec, "scored_marks", 0.0)))
            max_m = float(getattr(rec, "total_max_marks", getattr(rec, "max_marks", 100.0)))
            if max_m > 0:
                evidence_dicts.append({
                    "subject": rec.subject,
                    "scored_marks": scored,
                    "max_marks": max_m,
                    "test_title": rec.test_title or "School Assessment",
                })

        topic_gaps_raw = (
            db.query(TopicGap)
            .filter(TopicGap.child_id == child_id)
            .all()
        )
        topic_gap_dicts = [
            {
                "topic_name": g.curriculum_node.topic_name if g.curriculum_node else "Topic",
                "gap_status": g.gap_status,
            }
            for g in topic_gaps_raw
        ]

        # Calculate coverage ratio
        curriculum_count = (
            db.query(CurriculumNode)
            .filter(
                CurriculumNode.standard_class == child.standard_class,
                CurriculumNode.board == child.board,
                CurriculumNode.subject != "TAMIL",
            )
            .count()
        )
        tested_count = (
            db.query(TopicScore)
            .filter(TopicScore.child_id == child_id)
            .count()
        )
        total_curr = max(curriculum_count, 50)
        cov_pct = round((tested_count / total_curr) * 100.0, 1)

        # Evaluate achievement badges
        achieve_result = self.achievement_engine.evaluate_achievements(
            evidence_records=evidence_dicts,
            topic_gaps=topic_gap_dicts,
            coverage_metrics={"coverage_percentage": cov_pct},
            board_readiness_status="ON_TRACK" if len(evidence_dicts) >= 3 else "NEEDS_ATTENTION",
            consistency_slope=0.08,
        )

        unlocked_schemas = [
            AchievementBadgeSchema(**b) for b in achieve_result["unlocked_badges"]
        ]
        in_progress_schemas = [
            AchievementBadgeSchema(**b) for b in achieve_result["in_progress_badges"]
        ]

        return StudentAchievementsResponse(
            child_id=child_id,
            student_name=child.student_name,
            total_badges_count=achieve_result["total_badges_count"],
            unlocked_count=achieve_result["unlocked_count"],
            in_progress_count=achieve_result["in_progress_count"],
            completion_percentage=achieve_result["completion_percentage"],
            unlocked_badges=unlocked_schemas,
            in_progress_badges=in_progress_schemas,
        )

    def generate_share_token(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        child_id: uuid.UUID,
        duration_hours: int = 72,
        base_url: str = "https://app.studiqs.com",
    ) -> ShareLinkResponse:
        """
        Generates parent-authorized 72-hour time-limited cryptographic share link.
        """
        child = (
            db.query(Child)
            .filter(Child.child_id == child_id, Child.subscriber_id == subscriber_id)
            .first()
        )
        if not child:
            raise PermissionError("Unauthorized: Student record does not belong to subscriber.")

        duration_hours = max(1, min(168, duration_hours))
        raw_token = secrets.token_urlsafe(32)
        now_utc = datetime.now(timezone.utc)
        expires_at = now_utc + timedelta(hours=duration_hours)

        shared_token_record = SharedReportToken(
            subscriber_id=subscriber_id,
            child_id=child_id,
            share_token=raw_token,
            expires_at=expires_at,
            is_revoked=False,
            created_at=now_utc,
        )
        db.add(shared_token_record)
        db.commit()
        db.refresh(shared_token_record)

        seconds_remaining = int((expires_at - now_utc).total_seconds())
        time_display = self._format_countdown(seconds_remaining)
        share_url = f"{base_url}/share/{raw_token}"

        return ShareLinkResponse(
            token_id=shared_token_record.token_id,
            child_id=child_id,
            share_token=raw_token,
            share_url=share_url,
            expires_at=expires_at,
            hours_valid=duration_hours,
            seconds_remaining=seconds_remaining,
            time_remaining_display=time_display,
            is_revoked=False,
            created_at=now_utc,
        )

    def get_public_shared_report(
        self,
        db: Session,
        share_token: str,
    ) -> PublicSharedReportResponse:
        """
        Zero-Leakage Public Diagnostic View for verified tutors and school teachers.
        Completely strips subscriber identity, phone, email, billing, and sibling data.
        """
        token_record = (
            db.query(SharedReportToken)
            .filter(SharedReportToken.share_token == share_token)
            .first()
        )
        if not token_record:
            raise ValueError("Invalid or unknown share link.")

        now_utc = datetime.now(timezone.utc)
        expires_at_utc = self._ensure_utc(token_record.expires_at)

        # Check Revocation
        if token_record.is_revoked:
            return PublicSharedReportResponse(
                is_valid=False,
                token_status="REVOKED",
                expires_at=expires_at_utc,
                seconds_remaining=0,
                time_remaining_display="Revoked by Parent",
                student_alias="Student",
                standard_class="",
                board="",
                readiness_status="LINK_REVOKED",
                status_rationale="This diagnostic share link was revoked by the student's parent.",
                score_corridor=ScoreCorridorSchema(
                    lower_bound_pct=0.0, most_likely_pct=0.0, upper_bound_pct=0.0,
                    corridor_spread_pct=0.0, projection_confidence="REVOKED", confidence_score=0.0
                ),
                subject_breakdown={},
                top_strengths=[],
                priority_remedial_gaps=[],
            )

        # Check Expiration
        if now_utc > expires_at_utc:
            return PublicSharedReportResponse(
                is_valid=False,
                token_status="EXPIRED",
                expires_at=expires_at_utc,
                seconds_remaining=0,
                time_remaining_display="Expired (72h Exceeded)",
                student_alias="Student",
                standard_class="",
                board="",
                readiness_status="LINK_EXPIRED",
                status_rationale="This 72-hour temporary diagnostic share link has expired.",
                score_corridor=ScoreCorridorSchema(
                    lower_bound_pct=0.0, most_likely_pct=0.0, upper_bound_pct=0.0,
                    corridor_spread_pct=0.0, projection_confidence="EXPIRED", confidence_score=0.0
                ),
                subject_breakdown={},
                top_strengths=[],
                priority_remedial_gaps=[],
            )

        # Fetch child record
        child = db.query(Child).filter(Child.child_id == token_record.child_id).first()
        if not child:
            raise ValueError("Student record not found.")

        # Sanitized Student Alias: First Name + Initial (e.g. 'Arun S.' or 'Student')
        parts = child.student_name.strip().split()
        if len(parts) >= 2:
            student_alias = f"{parts[0]} {parts[-1][0]}."
        elif parts:
            student_alias = parts[0]
        else:
            student_alias = "Student"

        # Fetch internal board readiness
        readiness_resp = self.get_board_readiness(
            db=db,
            subscriber_id=token_record.subscriber_id,
            child_id=token_record.child_id,
        )

        seconds_left = max(0, int((expires_at_utc - now_utc).total_seconds()))
        time_display = self._format_countdown(seconds_left)

        # Extract top strengths and remedial areas
        strengths = [
            f"{s.subject} ({s.average_percentage}% Mastery)"
            for s in readiness_resp.subject_breakdown.values()
            if s.health_tier in ["STRONG", "AVERAGE"]
        ][:3]
        if not strengths:
            strengths = ["Active learning consistency across assessments"]

        remedial_gaps = [
            f"{r.topic_name} ({r.subject} - {r.remediation_action})"
            for r in readiness_resp.risk_radar.risk_topics[:3]
        ]
        if not remedial_gaps:
            remedial_gaps = ["No critical high-weightage topic gaps currently detected"]

        return PublicSharedReportResponse(
            is_valid=True,
            token_status="ACTIVE",
            expires_at=token_record.expires_at,
            seconds_remaining=seconds_left,
            time_remaining_display=time_display,
            student_alias=student_alias,
            standard_class=child.standard_class,
            board=child.board,
            readiness_status=readiness_resp.readiness_status,
            status_rationale=readiness_resp.status_rationale,
            score_corridor=readiness_resp.score_corridor,
            subject_breakdown=readiness_resp.subject_breakdown,
            top_strengths=strengths,
            priority_remedial_gaps=remedial_gaps,
        )

    def revoke_share_token(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        token_id: uuid.UUID,
    ) -> RevokeShareLinkResponse:
        """
        Parent-controlled instantaneous link revocation.
        """
        token_record = (
            db.query(SharedReportToken)
            .filter(
                SharedReportToken.token_id == token_id,
                SharedReportToken.subscriber_id == subscriber_id,
            )
            .first()
        )
        if not token_record:
            raise PermissionError("Unauthorized: Token not found or not owned by subscriber.")

        token_record.is_revoked = True
        db.commit()

        return RevokeShareLinkResponse(
            token_id=token_id,
            is_revoked=True,
            revoked_at=datetime.now(timezone.utc),
            message="Share link successfully revoked. Access has been immediately terminated.",
        )

    def list_active_share_tokens(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        child_id: uuid.UUID,
        base_url: str = "https://app.studiqs.com",
    ) -> ActiveShareTokensListResponse:
        """
        Lists all generated share links for student profile management.
        """
        child = (
            db.query(Child)
            .filter(Child.child_id == child_id, Child.subscriber_id == subscriber_id)
            .first()
        )
        if not child:
            raise PermissionError("Unauthorized: Student record does not belong to subscriber.")

        tokens_raw = (
            db.query(SharedReportToken)
            .filter(
                SharedReportToken.child_id == child_id,
                SharedReportToken.subscriber_id == subscriber_id,
            )
            .order_by(desc(SharedReportToken.created_at))
            .all()
        )

        now_utc = datetime.now(timezone.utc)
        token_schemas = []
        for t in tokens_raw:
            exp_utc = self._ensure_utc(t.expires_at)
            created_utc = self._ensure_utc(t.created_at)
            is_expired = now_utc > exp_utc
            sec_rem = max(0, int((exp_utc - now_utc).total_seconds())) if not is_expired else 0
            if t.is_revoked:
                disp = "Revoked"
            elif is_expired:
                disp = "Expired"
            else:
                disp = self._format_countdown(sec_rem)

            token_schemas.append(ActiveShareTokenSchema(
                token_id=t.token_id,
                share_token=t.share_token,
                share_url=f"{base_url}/share/{t.share_token}",
                expires_at=exp_utc,
                is_revoked=t.is_revoked,
                is_expired=is_expired,
                seconds_remaining=sec_rem,
                time_remaining_display=disp,
                created_at=created_utc,
            ))

        active_count = sum(1 for ts in token_schemas if not ts.is_revoked and not ts.is_expired)

        return ActiveShareTokensListResponse(
            child_id=child_id,
            active_tokens_count=active_count,
            tokens=token_schemas,
        )

    def _ensure_utc(self, dt: Optional[datetime]) -> datetime:
        """Ensures a datetime object is timezone-aware in UTC."""
        if dt is None:
            return datetime.now(timezone.utc)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    def _format_countdown(self, seconds: int) -> str:
        """Formats remaining seconds into clean human-readable countdown e.g. '71h 58m'."""
        if seconds <= 0:
            return "0m"
        hours = seconds // 3600
        mins = (seconds % 3600) // 60
        if hours > 0:
            return f"{hours}h {mins}m remaining"
        return f"{mins}m remaining"
