"""
STUDIQS® SmartParent™ (v6.2 Complete) - Subject Expert Marketplace Service
=============================================================================
Service: marketplace_service.py (Section 11 & 12 - Working Specification v6.0 / v6.1)
Governs the complete deterministic 9-step Subject Expert Marketplace lifecycle:
1. Need Detected: Subject weakness triggers expert recommendation / catalog filter
2. Choose Expert: Safe public alias profile browsing (no private contact info)
3. Evaluation Created: Payment order + 20/80 escrow commission split + Plan quota check
4. Paper Assigned: Verified diagnostic question set assigned by expert
5. Student Writes & Uploads: Answer script scan uploaded, starting 48h SLA clock
6. Expert Corrects: Split-screen grading with Section 21 anti-contact moderation
7. Expert Returns: Evaluated PDF + line-item question marks + structured feedback
8. Intelligence Updated: Automatic sync into Student 360, TopicScore & Gap resolution
9. Rate Expert: 1–5 star controlled review recalculating rolling rating average
=============================================================================
"""

import uuid
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple, Union
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc, func

from src.smartparent.db.models.auth import Child, Subscriber
from src.smartparent.db.models.assessment import EvidenceRecord, Question, QuestionPaper, StudentQuestionMark
from src.smartparent.db.models.curriculum import CurriculumNode
from src.smartparent.db.models.diagnostic import TopicGap, TopicScore
from src.smartparent.db.models.marketplace import (
    Expert,
    ExpertProfile,
    EvaluationCase,
    PaymentOrder,
    CommissionLedger,
    ExpertReview,
    CaseMessage,
)
from src.smartparent.db.models.usage_quota import SubscriberUsageQuota
from src.smartparent.core.constants import (
    CaseStatus,
    PaymentStatus,
    PayoutStatus,
    MessageSenderType,
    PLATFORM_COMMISSION_PERCENT,
    EXPERT_NET_PAYOUT_PERCENT,
    ESCROW_DISPUTE_WINDOW_HOURS,
    classify_mastery_tier,
)
from src.smartparent.engines.case_workflow import (
    CaseWorkflowEngine,
    CaseTransitionPayloadSchema,
    QuestionScoreItemSchema,
)
from src.smartparent.engines.controlled_comm import ControlledCommEngine, MessagePayloadSchema
from src.smartparent.schemas.marketplace import (
    ExpertPublicCard,
    ExpertCatalogResponse,
    CreateEvaluationCaseRequest,
    PaymentOrderInitiateResponse,
    ConfirmPaymentRequest,
    UploadAnswerSheetRequest,
    QuestionScoreItem,
    CompleteEvaluationSubmissionRequest,
    IntelligenceSyncResultResponse,
    CreateExpertReviewRequest,
    ExpertReviewResponse,
    RaiseDisputeRequest,
    SendCaseMessageRequest,
    CaseMessageResponse,
    EvaluationCaseDetailResponse,
)

logger = logging.getLogger("STUDIQS_MarketplaceService")

# Plan active evaluation quotas per child per month from PDF Section 10
ACTIVE_EVALUATION_QUOTAS: Dict[str, int] = {
    "BASIC": 1,
    "ADVANCED": 3,
    "PRO": 6,
}


class MarketplaceService:
    """
    Section 11 Subject Expert Marketplace Service.
    Enforces strict B2C multi-tenant boundaries, case-scoped expert isolation,
    48h SLA tracking, 20/80 escrow financial ledger, and Student 360 auto-sync.
    """

    def __init__(self):
        self.workflow_engine = CaseWorkflowEngine()
        self.controlled_comm_engine = ControlledCommEngine()

    # =========================================================================
    # TENANT & AUTHORIZATION SECURITY BOUNDARIES
    # =========================================================================

    def _verify_tenant_boundary(self, db: Session, subscriber_id: uuid.UUID, child_id: uuid.UUID) -> Child:
        """Enforces non-negotiable B2C subscriber-child boundary check."""
        child = (
            db.query(Child)
            .filter(Child.child_id == child_id, Child.subscriber_id == subscriber_id)
            .first()
        )
        if not child:
            logger.warning(
                f"[MarketplaceService] Unauthorized access attempt: subscriber {subscriber_id} to child {child_id}"
            )
            raise PermissionError("Child profile not found or not authorized for this subscriber.")
        return child

    def _verify_case_parent_boundary(
        self, db: Session, subscriber_id: uuid.UUID, case_id: uuid.UUID
    ) -> EvaluationCase:
        """Verifies that an evaluation case belongs to the calling parent/subscriber."""
        case = (
            db.query(EvaluationCase)
            .filter(EvaluationCase.case_id == case_id, EvaluationCase.subscriber_id == subscriber_id)
            .first()
        )
        if not case:
            raise PermissionError("Evaluation case not found or not authorized for this subscriber.")
        return case

    def _verify_expert_boundary(
        self, db: Session, expert_id: uuid.UUID, case_id: uuid.UUID
    ) -> EvaluationCase:
        """
        Enforces case-scoped expert isolation rule:
        The expert is NOT a family user. Expert authorization is strictly case-scoped.
        May access only the specific evaluation_id assigned to them.
        """
        case = (
            db.query(EvaluationCase)
            .filter(EvaluationCase.case_id == case_id, EvaluationCase.expert_id == expert_id)
            .first()
        )
        if not case:
            logger.warning(
                f"[MarketplaceService] Case isolation violation: expert {expert_id} attempted access to case {case_id}"
            )
            raise PermissionError("Case not found or unauthorized for this expert.")
        return case

    # =========================================================================
    # STEP 1 & 2: NEED DETECTED & CHOOSE EXPERT (CATALOG DISCOVERY)
    # =========================================================================

    def get_expert_catalog(
        self,
        db: Session,
        board: Optional[str] = None,
        standard_class: Optional[str] = None,
        subject: Optional[str] = None,
        min_rating: Optional[float] = None,
        max_fee: Optional[float] = None,
    ) -> ExpertCatalogResponse:
        """
        Step 1 & 2: Discover and filter approved human experts.
        Masks all private contact information (phone, email) exposing only public aliases.
        """
        query = (
            db.query(Expert, ExpertProfile)
            .join(ExpertProfile, Expert.expert_id == ExpertProfile.expert_id)
            .filter(Expert.is_active.is_(True), Expert.kyc_status == "VERIFIED")
        )

        rows = query.all()
        matched: List[ExpertPublicCard] = []

        for expert, profile in rows:
            # Board filter
            if board:
                b_match = any(board.lower() in str(b).lower() for b in profile.qualified_boards)
                if not b_match:
                    continue

            # Class filter
            if standard_class:
                c_match = any(standard_class.lower() in str(c).lower() for c in profile.qualified_classes)
                if not c_match:
                    continue

            # Subject filter
            if subject:
                s_match = any(subject.lower() in str(s).lower() for s in profile.qualified_subjects)
                if not s_match:
                    continue

            # Rating filter
            if min_rating is not None and float(profile.rating_avg) < min_rating:
                continue

            # Fee filter
            if max_fee is not None and float(profile.per_case_fee) > max_fee:
                continue

            matched.append(
                ExpertPublicCard(
                    expert_id=str(expert.expert_id),
                    display_alias=profile.display_alias,
                    bio=profile.bio,
                    qualified_boards=profile.qualified_boards or [],
                    qualified_classes=profile.qualified_classes or [],
                    qualified_subjects=profile.qualified_subjects or [],
                    sla_turnaround_hours=profile.sla_turnaround_hours or 48,
                    per_case_fee=float(profile.per_case_fee),
                    rating_avg=float(profile.rating_avg),
                    total_reviews=profile.total_reviews or 0,
                )
            )

        # Sort by rating desc, then reviews count desc
        matched.sort(key=lambda x: (x.rating_avg, x.total_reviews), reverse=True)

        return ExpertCatalogResponse(
            total_count=len(matched),
            matched_subject=subject,
            matched_class=standard_class,
            matched_board=board,
            experts=matched,
        )

    def get_expert_public_profile(self, db: Session, expert_id: uuid.UUID) -> ExpertPublicCard:
        """Retrieves a single verified expert's public card."""
        row = (
            db.query(Expert, ExpertProfile)
            .join(ExpertProfile, Expert.expert_id == ExpertProfile.expert_id)
            .filter(Expert.expert_id == expert_id, Expert.is_active.is_(True))
            .first()
        )
        if not row:
            raise ValueError("Verified expert profile not found.")

        expert, profile = row
        return ExpertPublicCard(
            expert_id=str(expert.expert_id),
            display_alias=profile.display_alias,
            bio=profile.bio,
            qualified_boards=profile.qualified_boards or [],
            qualified_classes=profile.qualified_classes or [],
            qualified_subjects=profile.qualified_subjects or [],
            sla_turnaround_hours=profile.sla_turnaround_hours or 48,
            per_case_fee=float(profile.per_case_fee),
            rating_avg=float(profile.rating_avg),
            total_reviews=profile.total_reviews or 0,
        )

    # =========================================================================
    # STEP 3: EVALUATION BOOKED (COMMERCIAL SPLIT & QUOTA CHECK)
    # =========================================================================

    def create_evaluation_case(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        payload: CreateEvaluationCaseRequest,
    ) -> Tuple[EvaluationCase, PaymentOrder]:
        """
        Step 3: Book an expert evaluation case.
        - Enforces Plan quota (Basic: 1 active/mo, Advanced: 3/mo, Pro: 6/mo).
        - Creates EvaluationCase (ASSIGNED).
        - Creates PaymentOrder (Razorpay intent).
        - Computes 20% Studiqs commission / 80% Expert net payout in Escrow HELD.
        """
        child_id = uuid.UUID(payload.child_id)
        expert_id = uuid.UUID(payload.expert_id)

        child = self._verify_tenant_boundary(db, subscriber_id, child_id)
        subscriber = db.query(Subscriber).filter(Subscriber.subscriber_id == subscriber_id).first()
        plan_tier = getattr(subscriber, "subscription_plan", None) or getattr(subscriber, "plan_tier", "BASIC") or "BASIC"
        max_active = ACTIVE_EVALUATION_QUOTAS.get(str(plan_tier).upper(), 1)

        # Count active cases for this child
        active_statuses = [
            CaseStatus.ASSIGNED.value,
            CaseStatus.AWAITING_UPLOAD.value,
            CaseStatus.SUBMITTED.value,
            CaseStatus.UNDER_REVIEW.value,
        ]
        active_count = (
            db.query(EvaluationCase)
            .filter(
                EvaluationCase.child_id == child_id,
                EvaluationCase.case_status.in_(active_statuses),
            )
            .count()
        )

        if active_count >= max_active:
            raise ValueError(
                f"Active expert evaluation limit ({max_active}) reached for your {plan_tier} plan. "
                f"Please complete or resolve existing active cases before booking a new evaluation."
            )

        # Verify expert exists and get fee
        profile = db.query(ExpertProfile).filter(ExpertProfile.expert_id == expert_id).first()
        if not profile:
            raise ValueError("Selected expert profile does not exist.")

        fee = float(profile.per_case_fee)
        case_id = uuid.uuid4()

        # Create EvaluationCase
        case = EvaluationCase(
            case_id=case_id,
            subscriber_id=subscriber_id,
            child_id=child_id,
            expert_id=expert_id,
            subject=payload.subject,
            test_title=payload.test_title,
            case_status=CaseStatus.ASSIGNED.value,
            gross_fee=fee,
            question_paper_path=payload.question_paper_path,
        )

        # Create PaymentOrder
        gateway_order_id = f"order_{uuid.uuid4().hex[:14]}"
        payment_order = PaymentOrder(
            order_id=uuid.uuid4(),
            case_id=case_id,
            subscriber_id=subscriber_id,
            gateway_order_id=gateway_order_id,
            amount=fee,
            payment_status=PaymentStatus.CREATED.value,
        )

        # Create 20/80 Commission Escrow Ledger
        commission_amt = round(fee * (PLATFORM_COMMISSION_PERCENT / 100.0), 2)
        net_payout = round(fee * (EXPERT_NET_PAYOUT_PERCENT / 100.0), 2)
        ledger = CommissionLedger(
            ledger_id=uuid.uuid4(),
            case_id=case_id,
            expert_id=expert_id,
            gross_amount=fee,
            platform_commission=commission_amt,
            expert_net_payout=net_payout,
            payout_status=PayoutStatus.HELD.value,
        )

        # Update subscriber monthly quota record
        month_key = datetime.now(timezone.utc).strftime("%Y-%m")
        quota = (
            db.query(SubscriberUsageQuota)
            .filter(
                SubscriberUsageQuota.subscriber_id == subscriber_id,
                SubscriberUsageQuota.month_key == month_key,
            )
            .first()
        )
        if quota:
            quota.active_expert_cases += 1
        else:
            quota = SubscriberUsageQuota(
                quota_id=uuid.uuid4(),
                subscriber_id=subscriber_id,
                month_key=month_key,
                active_expert_cases=1,
            )
            db.add(quota)

        db.add_all([case, payment_order, ledger])
        db.commit()
        db.refresh(case)
        db.refresh(payment_order)

        logger.info(f"[MarketplaceService] Case {case_id} booked for child {child_id} with expert {expert_id}")
        return case, payment_order

    def confirm_payment(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        case_id: uuid.UUID,
        gateway_payment_id: str,
    ) -> EvaluationCase:
        """
        Step 3 Confirmation: Captures payment gateway success.
        Moves case from ASSIGNED -> AWAITING_UPLOAD.
        """
        case = self._verify_case_parent_boundary(db, subscriber_id, case_id)
        payment_order = (
            db.query(PaymentOrder).filter(PaymentOrder.case_id == case_id).first()
        )
        if not payment_order:
            raise ValueError("Payment order not found for this case.")

        payment_order.payment_status = PaymentStatus.PAID.value
        payment_order.gateway_payment_id = gateway_payment_id

        # Transition case to AWAITING_UPLOAD
        if case.case_status == CaseStatus.ASSIGNED.value:
            case.case_status = CaseStatus.AWAITING_UPLOAD.value

        db.commit()
        db.refresh(case)
        return case

    # =========================================================================
    # STEP 4: PAPER ASSIGNED
    # =========================================================================

    def assign_question_paper(
        self,
        db: Session,
        expert_id: uuid.UUID,
        case_id: uuid.UUID,
        question_paper_path: str,
    ) -> EvaluationCase:
        """
        Step 4: Assigned expert attaches official practice/diagnostic question paper.
        Expert content is accessible only for that paid/assigned case.
        """
        case = self._verify_expert_boundary(db, expert_id, case_id)
        case.question_paper_path = question_paper_path
        db.commit()
        db.refresh(case)
        return case

    # =========================================================================
    # STEP 5: STUDENT WRITES & UPLOADS
    # =========================================================================

    def upload_answer_sheet(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        child_id: uuid.UUID,
        case_id: uuid.UUID,
        answer_sheet_path: str,
    ) -> EvaluationCase:
        """
        Step 5: Parent uploads child's offline written answer sheet scan.
        Transitions case status: AWAITING_UPLOAD -> SUBMITTED.
        Stops wait time and starts 48-Hour SLA clock for expert review.
        """
        self._verify_tenant_boundary(db, subscriber_id, child_id)
        case = self._verify_case_parent_boundary(db, subscriber_id, case_id)

        # Validate state transition via workflow engine
        transition_payload = CaseTransitionPayloadSchema(
            case_id=str(case.case_id),
            current_status=CaseStatus(case.case_status),
            target_status=CaseStatus.SUBMITTED,
            actor_type="PARENT",
            answer_sheet_path=answer_sheet_path,
        )
        self.workflow_engine.execute(transition_payload)

        case.answer_sheet_path = answer_sheet_path
        case.case_status = CaseStatus.SUBMITTED.value
        case.submitted_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(case)
        logger.info(f"[MarketplaceService] Case {case_id} submitted by parent; 48h SLA clock started.")
        return case

    # =========================================================================
    # STEP 6: EXPERT CLAIMS CASE (SPLIT-SCREEN STUDIO)
    # =========================================================================

    def expert_claim_case(
        self,
        db: Session,
        expert_id: uuid.UUID,
        case_id: uuid.UUID,
    ) -> EvaluationCase:
        """
        Step 6: Expert opens case in Split-Screen Evaluation Studio.
        Transitions status: SUBMITTED -> UNDER_REVIEW.
        """
        case = self._verify_expert_boundary(db, expert_id, case_id)

        transition_payload = CaseTransitionPayloadSchema(
            case_id=str(case.case_id),
            current_status=CaseStatus(case.case_status),
            target_status=CaseStatus.UNDER_REVIEW,
            actor_type="EXPERT",
            actor_id=str(expert_id),
        )
        self.workflow_engine.execute(transition_payload)

        case.case_status = CaseStatus.UNDER_REVIEW.value
        db.commit()
        db.refresh(case)
        return case

    # =========================================================================
    # STEP 7 & 8: EXPERT RETURNS EVALUATION & INTELLIGENCE SYNC
    # =========================================================================

    def expert_submit_evaluation(
        self,
        db: Session,
        expert_id: uuid.UUID,
        case_id: uuid.UUID,
        payload: CompleteEvaluationSubmissionRequest,
    ) -> Tuple[EvaluationCase, IntelligenceSyncResultResponse]:
        """
        Step 7: Expert submits vector-annotated PDF, line-item marks and structured feedback.
        Step 8: Scored question marks automatically flow into child's Student 360 profile,
                updating EvidenceRecord, TopicScores, and resolving TopicGaps >= 80%.
        SLA clock stops. 48-Hour Escrow dispute window begins.
        """
        case = self._verify_expert_boundary(db, expert_id, case_id)

        # Convert evaluations to schema for engine validation
        engine_evals = [
            QuestionScoreItemSchema(
                question_no=e.question_no,
                topic=e.topic_name,
                marks_scored=e.marks_scored,
                max_marks=e.max_marks,
                remarks=e.remarks,
            )
            for e in payload.evaluations
        ]

        # State transition validation (UNDER_REVIEW -> COMPLETED)
        transition_payload = CaseTransitionPayloadSchema(
            case_id=str(case.case_id),
            current_status=CaseStatus(case.case_status),
            target_status=CaseStatus.COMPLETED,
            actor_type="EXPERT",
            actor_id=str(expert_id),
            evaluated_pdf_path=payload.evaluated_pdf_path,
            evaluations=engine_evals,
            submitted_at=case.submitted_at,
            expert_feedback=payload.overall_feedback,
        )
        engine_res = self.workflow_engine.execute(transition_payload)

        now = datetime.now(timezone.utc)
        case.case_status = CaseStatus.COMPLETED.value
        case.evaluated_pdf_path = payload.evaluated_pdf_path
        case.completed_at = now

        # Compute totals
        total_scored = sum(e.marks_scored for e in payload.evaluations)
        total_max = sum(e.max_marks for e in payload.evaluations)
        pct = round((total_scored / (total_max or 100.0)) * 100.0, 2)

        # ---------------------------------------------------------------------
        # STEP 8: AUTOMATED INTELLIGENCE SYNC INTO STUDENT 360
        # ---------------------------------------------------------------------
        evidence_rec = EvidenceRecord(
            record_id=uuid.uuid4(),
            subscriber_id=case.subscriber_id,
            child_id=case.child_id,
            evidence_type="QUESTION_PAPER",
            subject=case.subject,
            test_title=f"Expert Eval: {case.test_title}",
            test_date=date.today(),
            total_scored_marks=total_scored,
            total_max_marks=total_max,
            storage_file_path=payload.evaluated_pdf_path,
        )
        db.add(evidence_rec)
        db.flush()

        qp_rec = QuestionPaper(
            qp_id=uuid.uuid4(),
            record_id=evidence_rec.record_id,
            file_name=case.question_paper_path or f"expert_eval_{case.case_id}.pdf",
            total_questions=len(payload.evaluations),
            parsed_json={"total_questions": len(payload.evaluations)},
        )
        db.add(qp_rec)
        db.flush()

        topics_updated: List[str] = []
        gaps_resolved: List[str] = []
        gaps_flagged: List[str] = []

        # Group evaluations by topic
        topic_groups: Dict[str, List[QuestionScoreItem]] = {}
        for ev in payload.evaluations:
            t = ev.topic_name.strip()
            topic_groups.setdefault(t, []).append(ev)

        child = db.query(Child).filter(Child.child_id == case.child_id).first()
        board_val = getattr(child, "board", "CBSE")
        class_val = getattr(child, "standard_class", "Class 10")

        for topic_name, ev_items in topic_groups.items():
            t_scored = sum(item.marks_scored for item in ev_items)
            t_max = sum(item.max_marks for item in ev_items)
            t_pct = round((t_scored / (t_max or 1.0)) * 100.0, 2)
            tier = classify_mastery_tier(t_pct).value

            # Lookup or create CurriculumNode
            cnode = (
                db.query(CurriculumNode)
                .filter(
                    CurriculumNode.topic_name == topic_name,
                    CurriculumNode.subject == case.subject,
                )
                .first()
            )
            if not cnode:
                cnode = CurriculumNode(
                    node_id=f"cnode_{case.subject[:3].lower()}_{uuid.uuid4().hex[:8]}",
                    board=board_val,
                    standard_class=class_val,
                    subject=case.subject,
                    chapter_name="General Chapter",
                    topic_name=topic_name,
                    semantic_keywords=[],
                )
                db.add(cnode)
                db.flush()

            # Record line-item Question and StudentQuestionMark
            for item in ev_items:
                q_rec = Question(
                    question_id=uuid.uuid4(),
                    qp_id=qp_rec.qp_id,
                    question_number=str(item.question_no),
                    question_stem=f"Expert Question {item.question_no}: {topic_name}",
                    max_marks=item.max_marks,
                    mapped_node_id=cnode.node_id,
                    mapping_confidence=1.0,
                )
                db.add(q_rec)
                db.flush()

                mark_rec = StudentQuestionMark(
                    mark_id=uuid.uuid4(),
                    question_id=q_rec.question_id,
                    child_id=case.child_id,
                    scored_marks=item.marks_scored,
                    scoring_source="EXPERT_EVAL",
                )
                db.add(mark_rec)

            # Update or create TopicScore
            tscore = (
                db.query(TopicScore)
                .filter(TopicScore.child_id == case.child_id, TopicScore.node_id == cnode.node_id)
                .first()
            )
            if tscore:
                tscore.scored_marks = t_scored
                tscore.max_marks = t_max
                tscore.percentage = t_pct
                tscore.mastery_tier = tier
                tscore.evaluated_at = now
            else:
                tscore = TopicScore(
                    score_id=uuid.uuid4(),
                    child_id=case.child_id,
                    node_id=cnode.node_id,
                    scored_marks=t_scored,
                    max_marks=t_max,
                    percentage=t_pct,
                    mastery_tier=tier,
                    evaluated_at=now,
                )
                db.add(tscore)

            topics_updated.append(topic_name)

            # Check gap resolution threshold (>= 80% marks gap as resolved)
            active_gap = (
                db.query(TopicGap)
                .filter(
                    TopicGap.child_id == case.child_id,
                    TopicGap.node_id == cnode.node_id,
                    TopicGap.gap_status.in_(["ACTIVE", "IN_RECHECK"]),
                )
                .first()
            )

            if t_pct >= 80.0:
                if active_gap:
                    active_gap.gap_status = "RESOLVED"
                    active_gap.resolved_at = now
                    gaps_resolved.append(topic_name)
            elif t_pct < 60.0:
                if not active_gap:
                    new_gap = TopicGap(
                        gap_id=uuid.uuid4(),
                        child_id=case.child_id,
                        node_id=cnode.node_id,
                        gap_status="ACTIVE",
                    )
                    db.add(new_gap)
                    gaps_flagged.append(topic_name)

        # Release active count in SubscriberUsageQuota
        month_key = now.strftime("%Y-%m")
        quota = (
            db.query(SubscriberUsageQuota)
            .filter(
                SubscriberUsageQuota.subscriber_id == case.subscriber_id,
                SubscriberUsageQuota.month_key == month_key,
            )
            .first()
        )
        if quota and quota.active_expert_cases > 0:
            quota.active_expert_cases -= 1

        db.commit()
        db.refresh(case)

        sync_result = IntelligenceSyncResultResponse(
            evidence_id=str(evidence_rec.record_id),
            scored_marks=total_scored,
            total_max_marks=total_max,
            percentage=pct,
            topics_updated=topics_updated,
            gaps_resolved=gaps_resolved,
            gaps_flagged=gaps_flagged,
        )

        logger.info(
            f"[MarketplaceService] Case {case_id} completed. Intelligence synced: {len(topics_updated)} topics, "
            f"{len(gaps_resolved)} gaps resolved."
        )
        return case, sync_result

    # =========================================================================
    # STEP 9: RATE EXPERT (1–5 REVIEW & ROLLING RATING)
    # =========================================================================

    def rate_expert(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        child_id: uuid.UUID,
        case_id: uuid.UUID,
        payload: CreateExpertReviewRequest,
    ) -> ExpertReviewResponse:
        """
        Step 9: Parent submits a 1–5 star rating and controlled review.
        Allowed only after a completed paid evaluation case.
        Recalculates rolling rating average on ExpertProfile.
        """
        self._verify_tenant_boundary(db, subscriber_id, child_id)
        case = self._verify_case_parent_boundary(db, subscriber_id, case_id)

        if case.case_status not in [CaseStatus.COMPLETED.value, CaseStatus.DISPUTED.value]:
            raise ValueError(
                f"Rating is only permitted after evaluation case is completed. Current status: {case.case_status}"
            )

        # Check for duplicate review
        existing = db.query(ExpertReview).filter(ExpertReview.case_id == case_id).first()
        if existing:
            raise ValueError("A review has already been submitted for this evaluation case.")

        review = ExpertReview(
            review_id=uuid.uuid4(),
            case_id=case.case_id,
            child_id=child_id,
            expert_id=case.expert_id,
            rating=payload.rating,
            feedback_text=payload.feedback_text,
        )
        db.add(review)
        db.flush()

        # Recalculate rolling average
        profile = db.query(ExpertProfile).filter(ExpertProfile.expert_id == case.expert_id).first()
        if profile:
            all_reviews = db.query(ExpertReview).filter(ExpertReview.expert_id == case.expert_id).all()
            if all_reviews:
                avg = sum(r.rating for r in all_reviews) / len(all_reviews)
                profile.rating_avg = round(avg, 2)
                profile.total_reviews = len(all_reviews)

        db.commit()
        db.refresh(review)

        return ExpertReviewResponse(
            review_id=str(review.review_id),
            case_id=str(review.case_id),
            child_id=str(review.child_id),
            expert_id=str(review.expert_id),
            rating=review.rating,
            feedback_text=review.feedback_text,
            created_at=review.created_at.isoformat() if review.created_at else datetime.now(timezone.utc).isoformat(),
        )

    # =========================================================================
    # ESCROW & DISPUTE WORKFLOW (SECTION 12 & 14)
    # =========================================================================

    def raise_dispute(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        child_id: uuid.UUID,
        case_id: uuid.UUID,
        payload: RaiseDisputeRequest,
    ) -> EvaluationCase:
        """
        Challenges an evaluation within the mandatory 48-hour post-completion window.
        Transitions case status: COMPLETED -> DISPUTED.
        Freezes payout escrow in HELD status pending administrative review.
        """
        self._verify_tenant_boundary(db, subscriber_id, child_id)
        case = self._verify_case_parent_boundary(db, subscriber_id, case_id)

        if case.case_status != CaseStatus.COMPLETED.value:
            raise ValueError(f"Only completed cases can be challenged. Current status: {case.case_status}")

        now = datetime.now(timezone.utc)
        completed_at = case.completed_at
        if completed_at:
            if completed_at.tzinfo is None:
                completed_at = completed_at.replace(tzinfo=timezone.utc)
            elapsed_hours = (now - completed_at).total_seconds() / 3600.0
            if elapsed_hours > ESCROW_DISPUTE_WINDOW_HOURS:
                raise ValueError(
                    f"48-hour dispute window has expired ({elapsed_hours:.1f}h elapsed). "
                    f"Payout escrow has been approved."
                )

        case.case_status = CaseStatus.DISPUTED.value

        # Freeze CommissionLedger
        ledger = db.query(CommissionLedger).filter(CommissionLedger.case_id == case_id).first()
        if ledger:
            ledger.payout_status = PayoutStatus.HELD.value

        # Insert system dispute message into thread
        sys_msg = CaseMessage(
            message_id=uuid.uuid4(),
            case_id=case_id,
            sender_type="SYSTEM",
            sender_id=subscriber_id,
            message_text=f"DISPUTE FILED by Parent: {payload.dispute_reason}. Escrow payout frozen.",
        )
        db.add(sys_msg)

        db.commit()
        db.refresh(case)
        logger.warning(f"[MarketplaceService] Case {case_id} marked DISPUTED. Reason: {payload.dispute_reason}")
        return case

    # =========================================================================
    # IN-PLATFORM CONTROLLED MESSAGING (SECTION 21/22 ANTI-CONTACT BOUNDARY)
    # =========================================================================

    def send_case_message(
        self,
        db: Session,
        case_id: uuid.UUID,
        sender_type: str,
        sender_id: uuid.UUID,
        message_text: str,
    ) -> CaseMessageResponse:
        """
        Sends an in-platform case communication message.
        Scans message with ControlledCommEngine (Engine 11) for phone numbers, emails,
        UPI handles, URLs, and off-platform solicitation keywords.
        Blocks or redacts violating messages while preserving academic context.
        """
        case = db.query(EvaluationCase).filter(EvaluationCase.case_id == case_id).first()
        if not case:
            raise ValueError("Case not found.")

        # Run through anti-contact boundary moderation engine
        mod_payload = MessagePayloadSchema(
            case_id=str(case_id),
            sender_type=MessageSenderType(sender_type.upper()),
            sender_id=str(sender_id),
            message_text=message_text,
            policy_action="BLOCK",
        )
        mod_res = self.controlled_comm_engine.execute(mod_payload)

        msg_rec = CaseMessage(
            message_id=uuid.uuid4(),
            case_id=case_id,
            sender_type=sender_type.upper(),
            sender_id=sender_id,
            message_text=mod_res.sanitized_text,
            is_blocked=mod_res.is_blocked,
            block_reason=mod_res.block_reason if mod_res.is_blocked else None,
        )
        db.add(msg_rec)
        db.commit()
        db.refresh(msg_rec)

        return CaseMessageResponse(
            message_id=str(msg_rec.message_id),
            case_id=str(msg_rec.case_id),
            sender_type=msg_rec.sender_type,
            sender_id=str(msg_rec.sender_id),
            message_text=msg_rec.message_text,
            is_blocked=msg_rec.is_blocked,
            block_reason=msg_rec.block_reason,
            sent_at=msg_rec.sent_at.isoformat() if msg_rec.sent_at else datetime.now(timezone.utc).isoformat(),
        )

    def get_case_messages(
        self,
        db: Session,
        case_id: uuid.UUID,
        user_type: str,
        user_id: uuid.UUID,
    ) -> List[CaseMessageResponse]:
        """Retrieves in-platform case messaging thread."""
        case = db.query(EvaluationCase).filter(EvaluationCase.case_id == case_id).first()
        if not case:
            raise ValueError("Case not found.")

        # Verify access authorization
        if user_type.upper() == "PARENT":
            if case.subscriber_id != user_id:
                raise PermissionError("Unauthorized to view messages for this case.")
        elif user_type.upper() == "EXPERT":
            if case.expert_id != user_id:
                raise PermissionError("Unauthorized to view messages for this case.")

        messages = (
            db.query(CaseMessage)
            .filter(CaseMessage.case_id == case_id)
            .order_by(asc(CaseMessage.sent_at))
            .all()
        )

        return [
            CaseMessageResponse(
                message_id=str(m.message_id),
                case_id=str(m.case_id),
                sender_type=m.sender_type,
                sender_id=str(m.sender_id),
                message_text=m.message_text,
                is_blocked=m.is_blocked,
                block_reason=m.block_reason,
                sent_at=m.sent_at.isoformat() if m.sent_at else datetime.now(timezone.utc).isoformat(),
            )
            for m in messages
        ]

    # =========================================================================
    # CASE DETAIL & LIST QUERIES
    # =========================================================================

    def get_case_detail(
        self,
        db: Session,
        case_id: uuid.UUID,
        subscriber_id: Optional[uuid.UUID] = None,
        expert_id: Optional[uuid.UUID] = None,
    ) -> EvaluationCaseDetailResponse:
        """
        Retrieves full 360-degree case status and metadata.
        Respects case-scoped isolation rules for parents and experts.
        """
        case = db.query(EvaluationCase).filter(EvaluationCase.case_id == case_id).first()
        if not case:
            raise ValueError("Evaluation case not found.")

        # Boundary checks
        if subscriber_id and case.subscriber_id != subscriber_id:
            raise PermissionError("Access unauthorized for this subscriber.")
        if expert_id and case.expert_id != expert_id:
            raise PermissionError("Access unauthorized for this expert.")

        child = db.query(Child).filter(Child.child_id == case.child_id).first()
        profile = (
            db.query(ExpertProfile).filter(ExpertProfile.expert_id == case.expert_id).first()
            if case.expert_id
            else None
        )
        ledger = db.query(CommissionLedger).filter(CommissionLedger.case_id == case_id).first()
        review = db.query(ExpertReview).filter(ExpertReview.case_id == case_id).first()

        # Calculate SLA turnaround metrics
        sla_hours = profile.sla_turnaround_hours if profile else 48
        sla_breached = False
        if case.submitted_at and not case.completed_at:
            sub_at = case.submitted_at
            if sub_at.tzinfo is None:
                sub_at = sub_at.replace(tzinfo=timezone.utc)
            elapsed = (datetime.now(timezone.utc) - sub_at).total_seconds() / 3600.0
            sla_breached = elapsed > sla_hours
        elif case.submitted_at and case.completed_at:
            sub_at = case.submitted_at
            comp_at = case.completed_at
            if sub_at.tzinfo is None:
                sub_at = sub_at.replace(tzinfo=timezone.utc)
            if comp_at.tzinfo is None:
                comp_at = comp_at.replace(tzinfo=timezone.utc)
            elapsed = (comp_at - sub_at).total_seconds() / 3600.0
            sla_breached = elapsed > sla_hours

        # Dispute eligibility
        can_dispute = False
        if case.case_status == CaseStatus.COMPLETED.value and case.completed_at:
            comp_at = case.completed_at
            if comp_at.tzinfo is None:
                comp_at = comp_at.replace(tzinfo=timezone.utc)
            can_dispute = (datetime.now(timezone.utc) - comp_at).total_seconds() / 3600.0 <= ESCROW_DISPUTE_WINDOW_HOURS

        review_resp = None
        if review:
            review_resp = ExpertReviewResponse(
                review_id=str(review.review_id),
                case_id=str(review.case_id),
                child_id=str(review.child_id),
                expert_id=str(review.expert_id),
                rating=review.rating,
                feedback_text=review.feedback_text,
                created_at=review.created_at.isoformat() if review.created_at else datetime.now(timezone.utc).isoformat(),
            )

        return EvaluationCaseDetailResponse(
            case_id=str(case.case_id),
            subscriber_id=str(case.subscriber_id),
            child_id=str(case.child_id),
            child_alias=child.student_name if child else "Student",
            standard_class=child.standard_class if child else "Class 10",
            board=child.board if child else "CBSE",
            expert_id=str(case.expert_id) if case.expert_id else None,
            expert_alias=profile.display_alias if profile else "Verified Expert",
            subject=case.subject,
            test_title=case.test_title,
            case_status=case.case_status,
            question_paper_path=case.question_paper_path,
            answer_sheet_path=case.answer_sheet_path,
            evaluated_pdf_path=case.evaluated_pdf_path,
            gross_fee=float(case.gross_fee),
            platform_commission=float(ledger.platform_commission) if ledger else round(float(case.gross_fee) * 0.20, 2),
            expert_net_payout=float(ledger.expert_net_payout) if ledger else round(float(case.gross_fee) * 0.80, 2),
            payout_status=ledger.payout_status if ledger else "HELD",
            submitted_at=case.submitted_at.isoformat() if case.submitted_at else None,
            completed_at=case.completed_at.isoformat() if case.completed_at else None,
            created_at=case.created_at.isoformat() if hasattr(case, "created_at") and case.created_at else datetime.now(timezone.utc).isoformat(),
            sla_turnaround_hours=sla_hours,
            sla_breached=sla_breached,
            can_dispute=can_dispute,
            review=review_resp,
        )

    def get_child_cases(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        child_id: uuid.UUID,
    ) -> List[EvaluationCaseDetailResponse]:
        """Lists all evaluation cases belonging to a child."""
        self._verify_tenant_boundary(db, subscriber_id, child_id)
        cases = (
            db.query(EvaluationCase)
            .filter(EvaluationCase.child_id == child_id)
            .order_by(desc(EvaluationCase.created_at))
            .all()
        )
        return [self.get_case_detail(db, c.case_id, subscriber_id=subscriber_id) for c in cases]
