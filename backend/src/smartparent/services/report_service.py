"""
STUDIQS® SmartParent™ (v6.2 Complete) - Report Centre & Lifecycle Service
=============================================================================
Section 4: Student 360 and Consolidated Report Lifecycle.
Handles:
1. Dynamic generation of Monthly, Term-wise, and Yearly Consolidated Reports.
2. Vector PDF compilation via ReportLab 2-Pass NumberedCanvas.
3. Current-year active report retrieval (Monthly, Term, Yearly).
4. Academic-Year Rollover:
   - Finalizes and archives the Yearly Consolidated Report.
   - Retires redundant previous-year monthly/term reports.
   - Preserves historical yearly reports for export & print.
=============================================================================
"""

import os
import uuid
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

from src.smartparent.db.models.auth import Child
from src.smartparent.db.models.consolidated_report import ConsolidatedReport
from src.smartparent.engines.report_generator import (
    ReportGenerator,
    StudentProfileSchema,
    ReportGenerationResult,
)
from src.smartparent.services.student_360_service import Student360Service

logger = logging.getLogger("STUDIQS_ReportService")


class ReportService:
    """
    Enterprise Report Lifecycle Service implementing Section 4 specifications.
    """

    STORAGE_BASE_DIR = Path("storage") / "reports"

    def __init__(self):
        self.student_360_service = Student360Service()
        self.pdf_engine = ReportGenerator()
        self.STORAGE_BASE_DIR.mkdir(parents=True, exist_ok=True)

    def _verify_child_ownership(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        child_id: uuid.UUID,
    ) -> Child:
        """Enforces Section 1 & 16 non-negotiable subscriber boundary."""
        child = (
            db.query(Child)
            .filter(Child.child_id == child_id, Child.subscriber_id == subscriber_id)
            .first()
        )
        if not child:
            logger.warning(
                f"[ReportService] Security boundary breach: subscriber {subscriber_id} tried to operate on child {child_id}"
            )
            raise PermissionError("Child profile not found or unauthorized for this subscriber.")
        return child

    def generate_consolidated_report(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        child_id: uuid.UUID,
        report_type: str,
        academic_year: str,
        period_key: str,
        report_title: Optional[str] = None,
        include_pdf: bool = True,
    ) -> ConsolidatedReport:
        """
        Generates and saves a formal Monthly, Term-wise, or Yearly Consolidated Report.
        """
        child = self._verify_child_ownership(db, subscriber_id, child_id)

        clean_type = report_type.upper().strip()
        if clean_type not in ("MONTHLY", "TERM", "YEARLY"):
            raise ValueError(f"Invalid report_type: {report_type}. Must be 'MONTHLY', 'TERM', or 'YEARLY'.")

        # 1. Fetch live Student 360 intelligence
        s360 = self.student_360_service.get_student_360(db, subscriber_id, child_id)

        # 2. Formulate Default Title if not provided
        if not report_title:
            if clean_type == "MONTHLY":
                report_title = f"Monthly Consolidated Report - {period_key}"
            elif clean_type == "TERM":
                report_title = f"{period_key} Consolidated Report - {academic_year}"
            else:
                report_title = f"Academic Year {academic_year} Consolidated Report"

        # 3. Generate Vector PDF if requested
        pdf_path_str: Optional[str] = None
        if include_pdf:
            try:
                child_storage = self.STORAGE_BASE_DIR / str(child_id)
                child_storage.mkdir(parents=True, exist_ok=True)
                target_pdf = child_storage / f"{clean_type}_{period_key}.pdf"

                prof_data = StudentProfileSchema(
                    student_name=getattr(child, "student_name", getattr(child, "first_name", "Student")),
                    student_id=str(child.child_id)[:8],
                    standard_class=child.standard_class,
                    board=child.board,
                    school_name=getattr(child, "school_name", "Studiqs Academy") or "Studiqs Academy",
                    academic_year=academic_year,
                )

                scorecards = [
                    {
                        "subject": s["subject_name"],
                        "marks": float(s["current_marks"]),
                        "current_score": float(s["current_marks"]),
                        "previous_score": float(s["previous_marks"]) if s["previous_marks"] is not None else float(s["current_marks"]),
                        "delta": s["delta"] or 0.0,
                        "trend": s["consistency_tier"],
                    }
                    for s in s360.get("subject_performance", [])
                ]

                gaps = [
                    {
                        "subject": g["subject"],
                        "topic_name": g["topic_name"],
                        "severity": g["severity"],
                        "status": g["status"],
                    }
                    for g in s360.get("top_unresolved_gaps", [])
                ]

                pulse_cards = s360.get("parent_pulse_cards", [])

                gen_input = {
                    "report_type": clean_type,
                    "student_profile": prof_data.model_dump(),
                    "subject_movement": scorecards,
                    "active_gaps": gaps,
                    "pulse_digest": {"cards": pulse_cards},
                    "pdf_output_path": str(target_pdf),
                }

                pdf_result = self.pdf_engine.run(gen_input)
                if isinstance(pdf_result, ReportGenerationResult):
                    pdf_path_str = pdf_result.pdf_path
                elif isinstance(pdf_result, dict):
                    pdf_path_str = pdf_result.get("pdf_path")
            except Exception as e:
                logger.error(f"[ReportService] PDF compilation failed: {e}")
                pdf_path_str = None


        # 4. Check for existing record in current period
        existing_report = (
            db.query(ConsolidatedReport)
            .filter(
                ConsolidatedReport.child_id == child_id,
                ConsolidatedReport.report_type == clean_type,
                ConsolidatedReport.period_key == period_key,
                ConsolidatedReport.academic_year == academic_year,
            )
            .first()
        )

        if existing_report:
            existing_report.report_title = report_title
            existing_report.report_data = s360
            existing_report.pdf_storage_path = pdf_path_str
            existing_report.generated_at = datetime.utcnow()
            db.commit()
            db.refresh(existing_report)
            return existing_report

        # 5. Insert new report record
        new_report = ConsolidatedReport(
            subscriber_id=subscriber_id,
            child_id=child_id,
            report_type=clean_type,
            academic_year=academic_year,
            period_key=period_key,
            report_title=report_title,
            report_data=s360,
            pdf_storage_path=pdf_path_str,
            is_finalized=(clean_type == "YEARLY"),
            is_archived_yearly=False,
        )
        db.add(new_report)
        db.commit()
        db.refresh(new_report)

        return new_report

    def get_current_year_reports(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        child_id: uuid.UUID,
        academic_year: str,
    ) -> List[ConsolidatedReport]:
        """
        Returns active reports (Monthly, Term, Yearly) for present academic year.
        Section 4: Every completed/current month and term in present academic year.
        """
        self._verify_child_ownership(db, subscriber_id, child_id)

        reports = (
            db.query(ConsolidatedReport)
            .filter(
                ConsolidatedReport.child_id == child_id,
                ConsolidatedReport.academic_year == academic_year,
                ConsolidatedReport.is_archived_yearly == False,
            )
            .order_by(desc(ConsolidatedReport.generated_at))
            .all()
        )
        return reports

    def get_report_history(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        child_id: uuid.UUID,
    ) -> List[ConsolidatedReport]:
        """
        Returns archived finalized Yearly reports from previous academic years.
        Section 4: Archive only finalized Yearly Consolidated Reports as report history.
        """
        self._verify_child_ownership(db, subscriber_id, child_id)

        historical = (
            db.query(ConsolidatedReport)
            .filter(
                ConsolidatedReport.child_id == child_id,
                ConsolidatedReport.report_type == "YEARLY",
                ConsolidatedReport.is_archived_yearly == True,
            )
            .order_by(desc(ConsolidatedReport.academic_year))
            .all()
        )
        return historical

    def execute_academic_year_rollover(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        child_id: uuid.UUID,
        previous_academic_year: str,
        new_academic_year: str,
        new_standard_class: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes Section 4 Academic-Year Rollover:
        1. Ensures Yearly Consolidated Report for previous year exists and is finalized.
        2. Sets is_archived_yearly = True on the finalized Yearly Report.
        3. Retires previous-year monthly/term report records.
        4. Updates child profile to new academic year (and promotes class if specified).
        """
        child = self._verify_child_ownership(db, subscriber_id, child_id)

        # 1. Find or generate previous year's Yearly report
        yearly_report = (
            db.query(ConsolidatedReport)
            .filter(
                ConsolidatedReport.child_id == child_id,
                ConsolidatedReport.report_type == "YEARLY",
                ConsolidatedReport.academic_year == previous_academic_year,
            )
            .first()
        )

        if not yearly_report:
            logger.info(f"[Rollover] Auto-generating finalized yearly report for {previous_academic_year}")
            yearly_report = self.generate_consolidated_report(
                db=db,
                subscriber_id=subscriber_id,
                child_id=child_id,
                report_type="YEARLY",
                academic_year=previous_academic_year,
                period_key=f"YEAR_{previous_academic_year.replace('-', '_')}",
                report_title=f"Academic Year {previous_academic_year} Finalized Consolidated Report",
                include_pdf=True,
            )

        # 2. Archive the Yearly Report
        yearly_report.is_finalized = True
        yearly_report.is_archived_yearly = True

        # 3. Retire previous-year Monthly and Term reports (Section 4 mandate)
        retired_reports = (
            db.query(ConsolidatedReport)
            .filter(
                ConsolidatedReport.child_id == child_id,
                ConsolidatedReport.academic_year == previous_academic_year,
                ConsolidatedReport.report_type.in_(["MONTHLY", "TERM"]),
            )
            .all()
        )
        retired_count = len(retired_reports)
        for r in retired_reports:
            db.delete(r)

        # 4. Update Child's current academic year and grade
        if hasattr(child, "academic_year"):
            child.academic_year = new_academic_year
        if new_standard_class:
            child.standard_class = new_standard_class

        db.commit()
        db.refresh(yearly_report)

        logger.info(
            f"[Rollover] Successfully rolled over child {child_id}: "
            f"Archived {previous_academic_year} Yearly Report ({yearly_report.report_id}), "
            f"Retired {retired_count} prior monthly/term reports."
        )

        return {
            "child_id": str(child_id),
            "previous_academic_year": previous_academic_year,
            "new_academic_year": new_academic_year,
            "archived_yearly_report_id": str(yearly_report.report_id),
            "retired_reports_count": retired_count,
            "status": "COMPLETED",
            "message": (
                f"Academic year rollover completed. {previous_academic_year} Yearly Report archived; "
                f"{retired_count} monthly/term items retired."
            ),
        }
