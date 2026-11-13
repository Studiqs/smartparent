"""
STUDIQS® SmartParent™ (v6.2 & v6.3 Extension) - Evidence Intake & QP Service
=============================================================================
Module: src.smartparent.services.intake_service

Provides production service orchestration for Section 3:
  1. Multi-Tenant Evidence Intake: Uploads question papers (PDF/Image) with
     strict subscriber isolation.
  2. Document AI Processing: Triggers asynchronous Celery parsing with
     graceful synchronous in-process fallback.
  3. Quick Marks Fast Feed: Immediate test marks recording and mastery updates.
  4. Line-Item Marks Confirmation: Commits confirmed question marks into
     `StudentQuestionMark`, updates `EvidenceRecord` totals, and synchronizes
     `TopicScore` and `TopicGap` diagnostic records.
  5. Upload History & Status Tracking: Real-time processing telemetry.
=============================================================================
"""

import os
import uuid
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, desc

from src.smartparent.db.models.auth import Child, Subscriber
from src.smartparent.db.models.assessment import (
    EvidenceRecord,
    QuestionPaper,
    Question,
    StudentQuestionMark,
)
from src.smartparent.db.models.diagnostic import TopicScore, TopicGap
from src.smartparent.db.models.curriculum import CurriculumNode
from src.smartparent.schemas.intake import (
    EvidenceTypeEnum,
    EvidenceStatusEnum,
    EvidenceUploadResponse,
    EvidenceStatusResponse,
    EvidenceListItemSchema,
    ParsedPaperDetailResponse,
    ParsedQuestionItemSchema,
    QuickMarksFeedRequest,
    QuickMarksFeedResponse,
    ConfirmQuestionMarksRequest,
    ConfirmQuestionMarksResponse,
)

logger = logging.getLogger("STUDIQS_IntakeService")


class IntakeService:
    """
    Enterprise Evidence Intake & Question Paper Management Service.
    """

    def __init__(self, storage_root: Optional[str] = None):
        if not storage_root:
            backend_root = Path(__file__).resolve().parent.parent.parent.parent
            storage_root = str(backend_root / "storage" / "evidence")
        self.storage_root = Path(storage_root)
        self.storage_root.mkdir(parents=True, exist_ok=True)

    def _verify_child_ownership(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        child_id: uuid.UUID,
    ) -> Child:
        """
        Enforces non-negotiable multi-tenant boundary:
        Verifies child belongs to authenticated subscriber.
        """
        stmt = select(Child).where(
            and_(
                Child.child_id == child_id,
                Child.subscriber_id == subscriber_id,
                Child.is_active == True,
            )
        )
        child = db.execute(stmt).scalar_one_or_none()
        if not child:
            raise PermissionError(
                f"Access Denied: Child profile {child_id} does not belong to subscriber {subscriber_id}."
            )
        return child

    def upload_question_paper(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        child_id: uuid.UUID,
        subject: str,
        test_title: str,
        test_date: date,
        file_bytes: bytes,
        file_name: str,
    ) -> EvidenceUploadResponse:
        """
        Stores uploaded PDF/image exam paper and initializes async processing.
        """
        child = self._verify_child_ownership(db, subscriber_id, child_id)

        # 1. Save file to isolated subscriber storage
        child_dir = self.storage_root / str(subscriber_id) / str(child_id)
        child_dir.mkdir(parents=True, exist_ok=True)
        unique_file_name = f"{uuid.uuid4().hex[:8]}_{file_name}"
        saved_file_path = child_dir / unique_file_name

        with open(saved_file_path, "wb") as f:
            f.write(file_bytes)

        # 2. Create initial EvidenceRecord in database
        evidence_id = uuid.uuid4()
        evidence = EvidenceRecord(
            record_id=evidence_id,
            subscriber_id=subscriber_id,
            child_id=child_id,
            evidence_type=EvidenceTypeEnum.QUESTION_PAPER.value,
            subject=subject,
            test_title=test_title,
            test_date=test_date,
            total_scored_marks=0.0,
            total_max_marks=0.0,
            storage_file_path=str(saved_file_path),
        )
        db.add(evidence)

        # 3. Create initial QuestionPaper tracker
        qp = QuestionPaper(
            qp_id=uuid.uuid4(),
            record_id=evidence_id,
            file_name=file_name,
            total_questions=0,
            parsed_json={"status": "PROCESSING", "file_path": str(saved_file_path)},
        )
        db.add(qp)
        db.commit()
        db.refresh(evidence)

        # 4. Trigger Celery async parsing task with synchronous fallback
        dispatched_async = False
        try:
            from src.smartparent.tasks.evidence_tasks import parse_question_paper_async_task
            parse_question_paper_async_task.delay(
                child_id=str(child_id),
                qp_file_path=str(saved_file_path),
                subject=subject,
            )
            dispatched_async = True
            logger.info(f"[IntakeService] Enqueued Celery task for evidence: {evidence_id}")
        except Exception as e:
            logger.warning(f"[IntakeService] Celery worker unavailable ({e}). Running synchronous fallback...")
            self._process_paper_synchronous(db, evidence, qp, str(saved_file_path), child)

        return EvidenceUploadResponse(
            evidence_id=evidence.record_id,
            subscriber_id=evidence.subscriber_id,
            child_id=evidence.child_id,
            subject=evidence.subject,
            test_title=evidence.test_title,
            evidence_type=EvidenceTypeEnum.QUESTION_PAPER,
            status=EvidenceStatusEnum.PROCESSING if dispatched_async else EvidenceStatusEnum.COMPLETED,
            file_name=file_name,
            message="Question paper uploaded successfully. Analysis in progress.",
            created_at=evidence.created_at,
        )

    def _process_paper_synchronous(
        self,
        db: Session,
        evidence: EvidenceRecord,
        qp: QuestionPaper,
        file_path: str,
        child: Child,
    ) -> None:
        """
        Synchronous fallback execution for OCR, layout parsing, and topic mapping.
        Guarantees zero-crash execution even without external Redis/Celery queue.
        """
        try:
            from src.smartparent.engines.section_03_qp_intelligence.ocr_service import ocr_service
            from src.smartparent.engines.section_03_qp_intelligence.topic_mapper import QPTopicMapperV3

            full_text, pages, meta = ocr_service.extract_text_from_pdf(file_path)
            
            # Simple spatial question splitter heuristic for questions (Q1, 1., etc.)
            import re
            pattern = re.compile(
                r"(?:^|[\r\n]+|(?<=\s)Question\s+)\s*(?:Question\s+|Q\s*|Q\.)?(\d{1,2})[\.\)]\s*(.*?)(?=(?:[\r\n]+\s*(?:Question\s+|Q\s*|Q\.)?\d{1,2}[\.\)]|\Z))",
                re.DOTALL | re.IGNORECASE,
            )
            matches = pattern.findall(full_text)

            questions_data = []
            if matches:
                for q_num, q_stem in matches[:25]:  # Process up to 25 extracted items
                    clean_stem = q_stem.strip()
                    if len(clean_stem) >= 10:
                        questions_data.append({
                            "question_number": f"Q{q_num}",
                            "question_stem": clean_stem[:300],
                            "max_marks": 2.0,  # Default standard mark
                        })
            else:
                # Fallback: single synthetic diagnostic unit if unparsed
                questions_data.append({
                    "question_number": "Q1",
                    "question_stem": f"Core diagnostic assessment for {evidence.subject}",
                    "max_marks": 50.0,
                })

            total_max = sum(q["max_marks"] for q in questions_data)
            evidence.total_max_marks = total_max
            qp.total_questions = len(questions_data)

            # Map topics
            mapper = QPTopicMapperV3()
            for q_dict in questions_data:
                mapped = mapper.map_question(
                    raw_question_text=q_dict["question_stem"],
                    subject=evidence.subject or "Mathematics",
                    target_grade=child.standard_class or "Class 10",
                    board=child.board or "CBSE",
                )
                topic_id = mapped.get("topic_id") if isinstance(mapped, dict) else None
                conf = float(mapped.get("confidence_score", 0.75)) if isinstance(mapped, dict) else 0.75

                q_entity = Question(
                    question_id=uuid.uuid4(),
                    qp_id=qp.qp_id,
                    question_number=q_dict["question_number"],
                    question_stem=q_dict["question_stem"],
                    max_marks=q_dict["max_marks"],
                    mapped_node_id=topic_id if topic_id != "UNKNOWN" else None,
                    mapping_confidence=conf,
                )
                db.add(q_entity)

            qp.parsed_json = {
                "status": "COMPLETED",
                "extracted_questions_count": len(questions_data),
                "total_max_marks": total_max,
            }
            db.commit()
            logger.info(f"[IntakeService] Synchronous paper parsing completed: {len(questions_data)} questions.")
        except Exception as e:
            logger.error(f"[IntakeService] Synchronous processing error: {e}")
            qp.parsed_json = {"status": "FAILED", "error": str(e)}
            db.commit()

    def submit_quick_marks(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        request: QuickMarksFeedRequest,
    ) -> QuickMarksFeedResponse:
        """
        Fast Route: Records exam marks in seconds and immediately updates telemetry.
        """
        child = self._verify_child_ownership(db, subscriber_id, request.child_id)

        pct = round((request.total_scored_marks / request.total_max_marks) * 100.0, 2)
        evidence_id = uuid.uuid4()

        evidence = EvidenceRecord(
            record_id=evidence_id,
            subscriber_id=subscriber_id,
            child_id=request.child_id,
            evidence_type=EvidenceTypeEnum.QUICK_MARKS.value,
            subject=request.subject,
            test_title=request.test_title,
            test_date=request.test_date,
            total_scored_marks=request.total_scored_marks,
            total_max_marks=request.total_max_marks,
        )
        db.add(evidence)

        # Check / update TopicScore baseline for this subject
        tier = (
            "STRONG" if pct >= 75.0 else ("AVERAGE" if pct >= 60.0 else ("WEAK" if pct >= 40.0 else "CRITICAL"))
        )

        # Find or create a curriculum node for this subject
        node_stmt = select(CurriculumNode).where(
            and_(
                CurriculumNode.subject == request.subject,
                CurriculumNode.standard_class == child.standard_class,
            )
        ).limit(1)
        node = db.execute(node_stmt).scalar_one_or_none()
        
        if node:
            score_stmt = select(TopicScore).where(
                and_(
                    TopicScore.child_id == request.child_id,
                    TopicScore.node_id == node.node_id,
                )
            )
            existing_score = db.execute(score_stmt).scalar_one_or_none()
            if existing_score:
                existing_score.scored_marks = request.total_scored_marks
                existing_score.max_marks = request.total_max_marks
                existing_score.percentage = pct
                existing_score.mastery_tier = tier
                existing_score.evaluated_at = datetime.now(timezone.utc)
            else:
                new_score = TopicScore(
                    score_id=uuid.uuid4(),
                    child_id=request.child_id,
                    node_id=node.node_id,
                    scored_marks=request.total_scored_marks,
                    max_marks=request.total_max_marks,
                    percentage=pct,
                    mastery_tier=tier,
                )
                db.add(new_score)

        db.commit()

        return QuickMarksFeedResponse(
            evidence_id=evidence_id,
            child_id=request.child_id,
            subject=request.subject,
            test_title=request.test_title,
            total_scored_marks=request.total_scored_marks,
            total_max_marks=request.total_max_marks,
            percentage=pct,
            mastery_delta_estimate=round(pct - 70.0, 1),
            status=EvidenceStatusEnum.CONFIRMED,
            message="Quick marks recorded and telemetry updated successfully.",
            created_at=datetime.now(timezone.utc),
        )

    def get_evidence_status(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        evidence_id: uuid.UUID,
    ) -> EvidenceStatusResponse:
        """
        Retrieves real-time processing status of an uploaded evidence record.
        """
        stmt = select(EvidenceRecord).where(
            and_(
                EvidenceRecord.record_id == evidence_id,
                EvidenceRecord.subscriber_id == subscriber_id,
            )
        )
        evidence = db.execute(stmt).scalar_one_or_none()
        if not evidence:
            raise KeyError(f"Evidence record {evidence_id} not found.")

        # Check QP details
        qp_stmt = select(QuestionPaper).where(QuestionPaper.record_id == evidence_id)
        qp = db.execute(qp_stmt).scalar_one_or_none()

        status = EvidenceStatusEnum.PROCESSING
        total_questions = 0
        error_msg = None

        if qp:
            total_questions = qp.total_questions
            p_status = qp.parsed_json.get("status", "PROCESSING")
            if p_status == "COMPLETED":
                status = EvidenceStatusEnum.COMPLETED
            elif p_status == "FAILED":
                status = EvidenceStatusEnum.FAILED
                error_msg = qp.parsed_json.get("error", "Document parsing error.")
        elif evidence.evidence_type == EvidenceTypeEnum.QUICK_MARKS.value:
            status = EvidenceStatusEnum.CONFIRMED

        return EvidenceStatusResponse(
            evidence_id=evidence.record_id,
            child_id=evidence.child_id,
            status=status,
            evidence_type=EvidenceTypeEnum(evidence.evidence_type),
            subject=evidence.subject,
            test_title=evidence.test_title,
            total_questions=total_questions,
            total_max_marks=float(evidence.total_max_marks or 0.0),
            total_scored_marks=float(evidence.total_scored_marks or 0.0),
            is_ready_for_review=(status == EvidenceStatusEnum.COMPLETED),
            error_message=error_msg,
            created_at=evidence.created_at,
            updated_at=evidence.updated_at,
        )

    def get_parsed_paper(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        evidence_id: uuid.UUID,
    ) -> ParsedPaperDetailResponse:
        """
        Fetches parsed question paper and line-item questions for review.
        """
        stmt = select(EvidenceRecord).where(
            and_(
                EvidenceRecord.record_id == evidence_id,
                EvidenceRecord.subscriber_id == subscriber_id,
            )
        )
        evidence = db.execute(stmt).scalar_one_or_none()
        if not evidence:
            raise KeyError(f"Evidence record {evidence_id} not found.")

        child = db.execute(select(Child).where(Child.child_id == evidence.child_id)).scalar_one()

        qp_stmt = select(QuestionPaper).where(QuestionPaper.record_id == evidence_id)
        qp = db.execute(qp_stmt).scalar_one_or_none()

        questions_list: List[ParsedQuestionItemSchema] = []
        if qp:
            q_stmt = select(Question).where(Question.qp_id == qp.qp_id)
            db_questions = db.execute(q_stmt).scalars().all()
            import re
            db_questions = sorted(db_questions, key=lambda q: int(re.sub(r"\D", "", q.question_number) or 0))

            for q in db_questions:
                topic_name = None
                chapter_name = None
                if q.mapped_node_id:
                    node = db.execute(select(CurriculumNode).where(CurriculumNode.node_id == q.mapped_node_id)).scalar_one_or_none()
                    if node:
                        topic_name = node.topic_name
                        chapter_name = node.chapter_name

                questions_list.append(
                    ParsedQuestionItemSchema(
                        question_id=q.question_id,
                        question_number=q.question_number,
                        question_stem=q.question_stem,
                        max_marks=float(q.max_marks),
                        mapped_topic_id=q.mapped_node_id,
                        mapped_topic_name=topic_name or "General Topic",
                        chapter_name=chapter_name or "General Chapter",
                        mapping_confidence=float(q.mapping_confidence or 0.0),
                        manual_review_flag=(float(q.mapping_confidence or 0.0) < 0.50),
                    )
                )

        return ParsedPaperDetailResponse(
            evidence_id=evidence.record_id,
            qp_id=qp.qp_id if qp else None,
            child_id=evidence.child_id,
            child_name=child.student_name,
            subject=evidence.subject,
            test_title=evidence.test_title,
            test_date=evidence.test_date,
            total_questions=len(questions_list),
            total_max_marks=float(evidence.total_max_marks or 0.0),
            total_scored_marks=float(evidence.total_scored_marks or 0.0),
            status=EvidenceStatusEnum.COMPLETED if qp else EvidenceStatusEnum.PROCESSING,
            questions=questions_list,
        )

    def confirm_question_marks(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        evidence_id: uuid.UUID,
        payload: ConfirmQuestionMarksRequest,
    ) -> ConfirmQuestionMarksResponse:
        """
        Confirms line-item marks per question and synchronizes TopicScores.
        """
        stmt = select(EvidenceRecord).where(
            and_(
                EvidenceRecord.record_id == evidence_id,
                EvidenceRecord.subscriber_id == subscriber_id,
            )
        )
        evidence = db.execute(stmt).scalar_one_or_none()
        if not evidence:
            raise KeyError(f"Evidence record {evidence_id} not found.")

        child = db.execute(select(Child).where(Child.child_id == evidence.child_id)).scalar_one()

        total_scored = 0.0
        topic_scores_count = 0

        # Save student question marks
        for item in payload.marks:
            q_stmt = select(Question).where(Question.question_id == item.question_id)
            question = db.execute(q_stmt).scalar_one_or_none()
            if not question:
                continue

            scored = min(float(item.scored_marks), float(question.max_marks))
            total_scored += scored

            # Insert/Update StudentQuestionMark
            mark_entry = StudentQuestionMark(
                mark_id=uuid.uuid4(),
                question_id=question.question_id,
                child_id=child.child_id,
                scored_marks=scored,
                scoring_source="PARENT_EXCEL_GRID",
            )
            db.add(mark_entry)

            # Update TopicScore if question has mapped curriculum node
            if question.mapped_node_id:
                pct = round((scored / float(question.max_marks)) * 100.0, 2)
                tier = (
                    "STRONG" if pct >= 75.0 else ("AVERAGE" if pct >= 60.0 else ("WEAK" if pct >= 40.0 else "CRITICAL"))
                )

                score_stmt = select(TopicScore).where(
                    and_(
                        TopicScore.child_id == child.child_id,
                        TopicScore.node_id == question.mapped_node_id,
                    )
                )
                topic_score = db.execute(score_stmt).scalar_one_or_none()
                if topic_score:
                    # Rolling average
                    topic_score.scored_marks = float(topic_score.scored_marks) + scored
                    topic_score.max_marks = float(topic_score.max_marks) + float(question.max_marks)
                    topic_score.percentage = round(
                        (float(topic_score.scored_marks) / float(topic_score.max_marks)) * 100.0, 2
                    )
                    topic_score.mastery_tier = (
                        "STRONG" if topic_score.percentage >= 75.0
                        else ("AVERAGE" if topic_score.percentage >= 60.0 else ("WEAK" if topic_score.percentage >= 40.0 else "CRITICAL"))
                    )
                    topic_score.evaluated_at = datetime.now(timezone.utc)
                else:
                    new_ts = TopicScore(
                        score_id=uuid.uuid4(),
                        child_id=child.child_id,
                        node_id=question.mapped_node_id,
                        scored_marks=scored,
                        max_marks=float(question.max_marks),
                        percentage=pct,
                        mastery_tier=tier,
                    )
                    db.add(new_ts)

                # Add to TopicGap if weak or critical
                if tier in ("WEAK", "CRITICAL"):
                    gap_stmt = select(TopicGap).where(
                        and_(
                            TopicGap.child_id == child.child_id,
                            TopicGap.node_id == question.mapped_node_id,
                            TopicGap.gap_status == "ACTIVE",
                        )
                    )
                    gap = db.execute(gap_stmt).scalar_one_or_none()
                    if not gap:
                        new_gap = TopicGap(
                            gap_id=uuid.uuid4(),
                            child_id=child.child_id,
                            node_id=question.mapped_node_id,
                            gap_status="ACTIVE",
                        )
                        db.add(new_gap)

                topic_scores_count += 1

        # Finalize EvidenceRecord
        evidence.total_scored_marks = total_scored
        db.commit()

        overall_pct = (
            round((total_scored / float(evidence.total_max_marks)) * 100.0, 2)
            if float(evidence.total_max_marks or 0.0) > 0 else 0.0
        )

        return ConfirmQuestionMarksResponse(
            evidence_id=evidence.record_id,
            child_id=child.child_id,
            subject=evidence.subject,
            status=EvidenceStatusEnum.CONFIRMED,
            total_scored_marks=total_scored,
            total_max_marks=float(evidence.total_max_marks or 0.0),
            percentage=overall_pct,
            topic_scores_updated=topic_scores_count,
            message=f"Confirmed marks for {len(payload.marks)} questions. Topic Intelligence synchronized.",
        )

    def list_child_evidence(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        child_id: uuid.UUID,
        limit: int = 20,
    ) -> List[EvidenceListItemSchema]:
        """
        Returns chronological upload history for a specific child.
        """
        self._verify_child_ownership(db, subscriber_id, child_id)

        stmt = (
            select(EvidenceRecord)
            .where(
                and_(
                    EvidenceRecord.child_id == child_id,
                    EvidenceRecord.subscriber_id == subscriber_id,
                )
            )
            .order_by(desc(EvidenceRecord.test_date), desc(EvidenceRecord.created_at))
            .limit(limit)
        )
        records = db.execute(stmt).scalars().all()

        results = []
        for r in records:
            scored = float(r.total_scored_marks or 0.0)
            max_m = float(r.total_max_marks or 0.0)
            pct = round((scored / max_m) * 100.0, 2) if max_m > 0 else 0.0
            
            # Check question count if QP
            q_count = 0
            if r.question_paper:
                q_count = r.question_paper.total_questions

            results.append(
                EvidenceListItemSchema(
                    evidence_id=r.record_id,
                    child_id=r.child_id,
                    evidence_type=EvidenceTypeEnum(r.evidence_type),
                    subject=r.subject,
                    test_title=r.test_title,
                    test_date=r.test_date,
                    total_scored_marks=scored,
                    total_max_marks=max_m,
                    percentage=pct,
                    status=EvidenceStatusEnum.CONFIRMED if scored > 0 else EvidenceStatusEnum.COMPLETED,
                    total_questions=q_count,
                    created_at=r.created_at,
                )
            )

        return results
