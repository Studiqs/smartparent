"""
STUDIQS® SmartParent™ (v6.2 Complete) - Multi-Tenant Security & Isolation Service
=============================================================================
Service: isolation_security_service.py (Section 16 - Working Specification v6.0 / v6.1)
Enforces:
1. Family row-level isolation & "Never authorize from child_id alone" rule
2. Expert case-level isolation & case assignment boundary
3. Signed expiring URL generation with boundary pre-checks
4. Cross-role field sanitization (Zero leakage between subscriber & expert)
5. Report & Evaluation document retention lifecycle audits
=============================================================================
"""

import uuid
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import desc

from src.smartparent.db.models.auth import Child, Subscriber
from src.smartparent.db.models.consolidated_report import ConsolidatedReport
from src.smartparent.db.models.marketplace import EvaluationCase, ExpertProfile, Expert
from src.smartparent.engines.section_16_security.document_and_isolation_engine import DocumentAndIsolationEngine
from src.smartparent.schemas.security_isolation import (
    SignedUrlScopeEnum,
    GenerateSignedUrlRequest,
    SignedUrlResponse,
    VerifySignedUrlRequest,
    VerifySignedUrlResponse,
    SanitizedExpertCaseView,
    SanitizedSubscriberExpertProfile,
    ReportRetentionAuditResponse,
    EvaluationRetentionAuditResponse,
)

logger = logging.getLogger("STUDIQS_IsolationSecurityService")


class IsolationSecurityService:
    """
    Section 16 Master Security, Isolation & Document Retention Service.
    """

    def __init__(self, secret_key: Optional[str] = None):
        self.engine = DocumentAndIsolationEngine(secret_key=secret_key)

    # =========================================================================
    # 1. TENANT BOUNDARY CHECKS
    # =========================================================================

    def verify_subscriber_child_boundary(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        child_id: uuid.UUID,
    ) -> Child:
        """
        Enforces non-negotiable B2C subscriber-child boundary check.
        "Never authorize from child_id alone."
        """
        if not subscriber_id or not child_id:
            raise PermissionError("Both subscriber_id and child_id are required for authorization.")

        child = (
            db.query(Child)
            .filter(Child.child_id == child_id, Child.subscriber_id == subscriber_id)
            .first()
        )
        if not child:
            logger.warning(
                f"[IsolationSecurityService] Unauthorized child access attempt: subscriber {subscriber_id} to child {child_id}"
            )
            raise PermissionError("Child profile not found or not authorized for this subscriber.")
        return child

    def verify_expert_evaluation_boundary(
        self,
        db: Session,
        expert_id: uuid.UUID,
        evaluation_id: uuid.UUID,
    ) -> EvaluationCase:
        """
        Enforces expert case-level isolation.
        An expert may access ONLY evaluation rows explicitly assigned to expert_id.
        """
        if not expert_id or not evaluation_id:
            raise PermissionError("Both expert_id and evaluation_id are required for authorization.")

        case = (
            db.query(EvaluationCase)
            .filter(EvaluationCase.case_id == evaluation_id, EvaluationCase.expert_id == expert_id)
            .first()
        )
        if not case:
            logger.warning(
                f"[IsolationSecurityService] Unauthorized expert case access: expert {expert_id} to case {evaluation_id}"
            )
            raise PermissionError("Evaluation case not found or not assigned to this expert.")
        return case

    def verify_subscriber_evaluation_boundary(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        evaluation_id: uuid.UUID,
    ) -> EvaluationCase:
        """
        Enforces subscriber evaluation ownership.
        A subscriber may access ONLY evaluation cases booked for their family.
        """
        if not subscriber_id or not evaluation_id:
            raise PermissionError("Both subscriber_id and evaluation_id are required for authorization.")

        case = (
            db.query(EvaluationCase)
            .filter(EvaluationCase.case_id == evaluation_id, EvaluationCase.subscriber_id == subscriber_id)
            .first()
        )
        if not case:
            logger.warning(
                f"[IsolationSecurityService] Unauthorized subscriber case access: subscriber {subscriber_id} to case {evaluation_id}"
            )
            raise PermissionError("Evaluation case not found or not authorized for this subscriber.")
        return case

    # =========================================================================
    # 2. SIGNED URL DISPATCH
    # =========================================================================

    def generate_signed_document_url(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        request: GenerateSignedUrlRequest,
    ) -> SignedUrlResponse:
        """
        Validates tenant boundaries before generating a cryptographically signed expiring URL.
        """
        # If resource belongs to a child, enforce subscriber-child boundary
        if request.child_id:
            child_uuid = uuid.UUID(request.child_id) if isinstance(request.child_id, str) else request.child_id
            self.verify_subscriber_child_boundary(db, subscriber_id, child_uuid)

        # If resource belongs to an evaluation, enforce subscriber-case boundary
        if request.evaluation_id:
            case_uuid = uuid.UUID(request.evaluation_id) if isinstance(request.evaluation_id, str) else request.evaluation_id
            self.verify_subscriber_evaluation_boundary(db, subscriber_id, case_uuid)

        return self.engine.generate_signed_url(
            resource_path=request.resource_path,
            scope=request.scope,
            expires_in_seconds=request.expires_in_seconds,
        )

    def verify_signed_url_token(self, request: VerifySignedUrlRequest) -> VerifySignedUrlResponse:
        """Verifies HMAC signature and expiration."""
        return self.engine.verify_signed_url(
            resource_path=request.resource_path,
            signature=request.signature,
            expires_at=request.expires_at,
            scope=request.scope,
        )

    # =========================================================================
    # 3. CROSS-BOUNDARY SANITIZED VIEWS
    # =========================================================================

    def get_sanitized_case_for_expert(
        self,
        db: Session,
        expert_id: uuid.UUID,
        evaluation_id: uuid.UUID,
    ) -> SanitizedExpertCaseView:
        """
        Retrieves an evaluation case for an expert, strictly scrubbed of
        parent phone, email, billing, and sibling data.
        """
        case = self.verify_expert_evaluation_boundary(db, expert_id, evaluation_id)
        child = db.query(Child).filter(Child.child_id == case.child_id).first()

        case_data = {
            "evaluation_id": str(case.case_id),
            "student_name": child.student_name if child else "Student",
            "standard_class": child.standard_class if child else "Class 10",
            "board": child.board if child else "CBSE",
            "subject": case.subject,
            "status": getattr(case, "case_status", getattr(case, "status", "ASSIGNED")),
            "assigned_question_set_url": getattr(case, "question_paper_path", getattr(case, "question_set_url", None)),
            "submitted_answer_sheet_url": getattr(case, "answer_sheet_path", getattr(case, "answer_sheet_url", None)),
            "corrected_copy_url": getattr(case, "evaluated_pdf_path", getattr(case, "corrected_copy_url", None)),
            "total_max_marks": float(getattr(case, "total_max_marks", 100.0) or 100.0),
            "turnaround_deadline": case.turnaround_deadline.isoformat() if hasattr(case, "turnaround_deadline") and case.turnaround_deadline else None,
        }
        return self.engine.sanitize_expert_case_view(case_data)

    def get_sanitized_expert_profile_for_subscriber(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        expert_id: uuid.UUID,
    ) -> SanitizedSubscriberExpertProfile:
        """
        Retrieves a public expert profile for a subscriber, strictly scrubbed of
        expert KYC, bank details, payout records, and commission splits.
        """
        expert = db.query(Expert).filter(Expert.expert_id == expert_id).first()
        if not expert:
            raise PermissionError("Expert profile not found or inactive.")

        prof = db.query(ExpertProfile).filter(ExpertProfile.expert_id == expert_id).first()

        expert_data = {
            "expert_id": str(expert.expert_id),
            "display_name": prof.display_alias if prof else expert.full_name,
            "photo_url": getattr(prof, "photo_url", None),
            "subjects": prof.qualified_subjects if prof else [],
            "boards": prof.qualified_boards if prof else [],
            "classes": prof.qualified_classes if prof else [],
            "qualifications": prof.bio if prof else "Certified Board Educator",
            "experience_years": 10,
            "average_rating": float(getattr(prof, "rating_avg", 5.0) or 5.0),
            "total_reviews_count": getattr(prof, "rating_count", 0),
            "turnaround_hours": prof.sla_turnaround_hours if prof else 48,
            "evaluation_fee_inr": float(prof.per_case_fee if prof else 500.0),
        }
        return self.engine.sanitize_subscriber_expert_profile(expert_data)

    # =========================================================================
    # 4. REPORT & EVALUATION RETENTION AUDITS
    # =========================================================================

    def audit_child_report_retention(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        child_id: uuid.UUID,
    ) -> ReportRetentionAuditResponse:
        """
        Audits all consolidated reports for a child against Section 16 retention rules:
        - Current year: all monthly, term, and yearly reports active.
        - Previous years: intermediate monthly/term reports retired, only finalized yearly reports retained.
        """
        child = self.verify_subscriber_child_boundary(db, subscriber_id, child_id)
        current_ay = child.academic_year or "2026-2027"

        reports_records = (
            db.query(ConsolidatedReport)
            .filter(ConsolidatedReport.child_id == child_id)
            .order_by(desc(ConsolidatedReport.period_key))
            .all()
        )

        raw_reports = []
        for r in reports_records:
            raw_reports.append({
                "report_id": str(r.report_id),
                "report_type": r.report_type,
                "academic_year": r.academic_year or current_ay,
                "period_key": r.period_key,
                "pdf_storage_path": r.pdf_storage_path,
            })

        return self.engine.audit_report_retention(
            child_id=str(child_id),
            current_academic_year=current_ay,
            raw_reports=raw_reports,
        )

    def audit_evaluation_retention(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        evaluation_id: uuid.UUID,
    ) -> EvaluationRetentionAuditResponse:
        """
        Audits evaluation retention against 7-year statutory audit policy and 90-day dispute window.
        """
        case = self.verify_subscriber_evaluation_boundary(db, subscriber_id, evaluation_id)
        comp_iso = case.completed_at.isoformat() if case.completed_at else None
        ay = getattr(case, "academic_year", "2026-2027") or "2026-2027"

        return self.engine.audit_evaluation_retention(
            evaluation_id=str(case.case_id),
            academic_year=ay,
            completed_at_iso=comp_iso,
        )
