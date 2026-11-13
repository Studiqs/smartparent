"""
STUDIQS® SmartParent™ (v6.3 Complete) - Diagnostic Intelligence Service
=============================================================================
Module: src.smartparent.services.diagnostic_service

Provides Student 360 diagnostic aggregation, Topic Mastery breakdown,
and Learning Gap Watchlist lifecycle management with multi-tenant firewall.
=============================================================================
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, desc

from src.smartparent.db.models.auth import Child
from src.smartparent.db.models.curriculum import CurriculumNode
from src.smartparent.db.models.diagnostic import TopicScore, TopicGap
from src.smartparent.schemas.diagnostic import (
    TopicScoreItemSchema,
    TopicGapItemSchema,
    StudentDiagnosticSummaryResponse,
    ResolveGapRequest,
    ResolveGapResponse,
)

logger = logging.getLogger("STUDIQS_DiagnosticService")


class DiagnosticService:
    """
    Diagnostic & Student 360 Service.
    Enforces strict subscriber authorization before querying child telemetry.
    """

    def _verify_child_ownership(self, db: Session, subscriber_id: uuid.UUID, child_id: uuid.UUID) -> Child:
        """Ensures child exists and belongs exclusively to the requesting subscriber."""
        stmt = select(Child).where(
            and_(
                Child.child_id == child_id,
                Child.subscriber_id == subscriber_id,
            )
        )
        child = db.execute(stmt).scalar_one_or_none()
        if not child:
            raise PermissionError(
                f"Access Denied: Child {child_id} does not belong to subscriber {subscriber_id}."
            )
        return child

    def get_child_diagnostic_summary(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        child_id: uuid.UUID,
    ) -> StudentDiagnosticSummaryResponse:
        """
        Calculates holistic Student 360 diagnostic telemetry:
        Aggregates mastery tiers, overall percentage, and active gaps.
        """
        child = self._verify_child_ownership(db, subscriber_id, child_id)

        # Query all topic scores for child
        scores_stmt = (
            select(TopicScore, CurriculumNode)
            .join(CurriculumNode, TopicScore.node_id == CurriculumNode.node_id)
            .where(TopicScore.child_id == child_id)
            .order_by(desc(TopicScore.evaluated_at))
        )
        scores_res = db.execute(scores_stmt).all()

        strong_count = 0
        avg_count = 0
        weak_count = 0
        crit_count = 0
        total_scored = 0.0
        total_max = 0.0

        score_items: List[TopicScoreItemSchema] = []
        for ts, node in scores_res:
            pct = float(ts.percentage)
            total_scored += float(ts.scored_marks)
            total_max += float(ts.max_marks)

            if ts.mastery_tier == "STRONG":
                strong_count += 1
            elif ts.mastery_tier == "AVERAGE":
                avg_count += 1
            elif ts.mastery_tier == "WEAK":
                weak_count += 1
            else:
                crit_count += 1

            if len(score_items) < 15:  # Recent 15 items
                score_items.append(
                    TopicScoreItemSchema(
                        score_id=ts.score_id,
                        node_id=ts.node_id,
                        topic_name=node.topic_name,
                        chapter_name=node.chapter_name,
                        subject=node.subject,
                        scored_marks=float(ts.scored_marks),
                        max_marks=float(ts.max_marks),
                        percentage=pct,
                        mastery_tier=ts.mastery_tier,
                        evaluated_at=ts.evaluated_at,
                    )
                )

        overall_pct = round((total_scored / total_max * 100.0), 2) if total_max > 0 else 0.0

        # Query active gaps
        gaps_stmt = (
            select(TopicGap, CurriculumNode)
            .join(CurriculumNode, TopicGap.node_id == CurriculumNode.node_id)
            .where(
                and_(
                    TopicGap.child_id == child_id,
                    TopicGap.gap_status == "ACTIVE",
                )
            )
            .order_by(desc(TopicGap.first_identified_at))
        )
        gaps_res = db.execute(gaps_stmt).all()

        gap_items: List[TopicGapItemSchema] = []
        for tg, node in gaps_res:
            gap_items.append(
                TopicGapItemSchema(
                    gap_id=tg.gap_id,
                    node_id=tg.node_id,
                    topic_name=node.topic_name,
                    chapter_name=node.chapter_name,
                    subject=node.subject,
                    gap_status=tg.gap_status,
                    first_identified_at=tg.first_identified_at,
                    resolved_at=tg.resolved_at,
                )
            )

        return StudentDiagnosticSummaryResponse(
            child_id=child.child_id,
            student_name=child.student_name,
            standard_class=child.standard_class,
            board=child.board,
            academic_year=child.academic_year or "2025-2026",
            overall_mastery_percentage=overall_pct,
            total_evaluated_topics=len(scores_res),
            strong_topics_count=strong_count,
            average_topics_count=avg_count,
            weak_topics_count=weak_count,
            critical_topics_count=crit_count,
            active_gaps_count=len(gap_items),
            recent_scores=score_items,
            critical_gaps=gap_items[:10],
        )

    def resolve_gap(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        gap_id: uuid.UUID,
        payload: ResolveGapRequest,
    ) -> ResolveGapResponse:
        """Updates or marks a learning gap as resolved."""
        stmt = select(TopicGap).where(TopicGap.gap_id == gap_id)
        gap = db.execute(stmt).scalar_one_or_none()
        if not gap:
            raise KeyError(f"Learning gap {gap_id} not found.")

        # Multi-tenant check
        self._verify_child_ownership(db, subscriber_id, gap.child_id)

        gap.gap_status = payload.gap_status
        if payload.gap_status == "RESOLVED":
            gap.resolved_at = datetime.now(timezone.utc)
        db.commit()

        return ResolveGapResponse(
            gap_id=gap.gap_id,
            child_id=gap.child_id,
            node_id=gap.node_id,
            new_status=gap.gap_status,
            resolved_at=gap.resolved_at,
            message=f"Gap status successfully updated to {gap.gap_status}.",
        )


diagnostic_service = DiagnosticService()

