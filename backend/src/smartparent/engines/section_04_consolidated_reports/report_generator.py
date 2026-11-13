"""
STUDIQS® SmartParent™ (v6.2 Complete) - Report Generation Engine
Engine 14: report_generator.py

Builds pixel-perfect vector PDF documents using ReportLab 2-Pass NumberedCanvas,
and returns rich structured JSON payloads for Mobile/Web Diagnostic Report Cards.
Supports Monthly Consolidated, Term-wise, and Academic Diagnostic reports.
"""

import os
import io
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from pydantic import BaseModel, Field, ConfigDict

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch, mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
    HRFlowable
)
from reportlab.pdfgen import canvas

from src.smartparent.engines.base_engine import BaseEngine, EngineHealthStatus

logger = logging.getLogger("STUDIQS_ReportGenerator")


# =============================================================================
# 1. ReportLab 2-Pass Dynamic Numbered Canvas
# =============================================================================

class NumberedCanvas(canvas.Canvas):
    """
    Two-pass dynamic canvas that accurately renders 'Page X of Y',
    brand footers, and confidentiality notices on all pages.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_elements(num_pages)
            super().showPage()
        super().save()

    def draw_page_elements(self, page_count: int):
        self.saveState()
        self.setFont("Helvetica", 8.5)
        self.setFillColor(colors.HexColor("#64748B"))  # Slate gray

        # Running Footer
        footer_text = f"STUDIQS® SmartParent™ Diagnostic Intelligence  |  Confidential Student Report"
        self.drawString(45, 30, footer_text)

        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(A4[0] - 45, 30, page_str)

        # Thin footer rule
        self.setStrokeColor(colors.HexColor("#E2E8F0"))
        self.setLineWidth(0.75)
        self.line(45, 42, A4[0] - 45, 42)

        self.restoreState()


# =============================================================================
# 2. Pydantic v2 Type-Safe Schemas
# =============================================================================

class StudentProfileSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")

    student_name: str = "Aarav Sharma"
    student_id: Optional[str] = None
    standard_class: str = "Class 10"
    board: str = "CBSE"
    school_name: Optional[str] = "Studiqs Academy"
    academic_year: str = "2025-2026"


class ReportGenerationResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    report_id: str
    report_type: str
    student_name: str
    pdf_path: Optional[str] = None
    pdf_bytes_size: int = 0
    total_pages: int = 0
    generation_status: str  # 'SUCCESS', 'DEGRADED', 'FAILED'
    executive_summary: Dict[str, Any] = Field(default_factory=dict)
    subject_scorecard: List[Dict[str, Any]] = Field(default_factory=list)
    parent_pulse_digest: Dict[str, Any] = Field(default_factory=dict)
    generated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


# =============================================================================
# 3. Production Report Generation Engine Implementation
# =============================================================================

class ReportGenerator(BaseEngine):
    """
    Engine 14: Report Generation Engine (report_generator.py)
    
    Generates publication-quality, pixel-perfect PDF diagnostic reports and
    structured interactive dashboard telemetry for students, parents, and schools.
    """

    def __init__(self, output_dir: Optional[Union[str, Path]] = None, failure_threshold: int = 5):
        super().__init__(name="ReportGenerator", failure_threshold=failure_threshold)
        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            self.output_dir = Path("outputs/reports")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------------------
    # BaseEngine Template Method Lifecycle Hooks
    # -------------------------------------------------------------------------

    def validate_input(self, input_data: Any) -> Dict[str, Any]:
        """Validates report request payload."""
        if not input_data:
            raise ValueError("Report input payload cannot be empty.")

        if hasattr(input_data, "model_dump"):
            data = input_data.model_dump()
        elif hasattr(input_data, "dict"):
            data = input_data.dict()
        elif isinstance(input_data, dict):
            data = dict(input_data)
        else:
            raise ValueError(f"Unsupported report payload type: {type(input_data)}")

        return data

    def execute_core(self, validated_data: Dict[str, Any]) -> ReportGenerationResult:
        """Executes full diagnostic report compilation and vector PDF rendering."""
        report_type = validated_data.get("report_type", "MONTHLY_CONSOLIDATED")
        profile_raw = validated_data.get("child_profile") or validated_data.get("student_profile") or {}
        if isinstance(profile_raw, StudentProfileSchema):
            profile = profile_raw
        elif hasattr(profile_raw, "model_dump"):
            profile = StudentProfileSchema(**profile_raw.model_dump())
        elif hasattr(profile_raw, "dict"):
            profile = StudentProfileSchema(**profile_raw.dict())
        else:
            profile = StudentProfileSchema(**profile_raw)
        report_id = f"RPT_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{profile.student_name.replace(' ', '_')[:10]}"

        # Parse Data Blocks
        pulse_digest_raw = validated_data.get("parent_pulse_digest") or validated_data.get("pulse_digest")
        if hasattr(pulse_digest_raw, "model_dump"):
            pulse_digest = pulse_digest_raw.model_dump()
        elif hasattr(pulse_digest_raw, "dict"):
            pulse_digest = pulse_digest_raw.dict()
        elif isinstance(pulse_digest_raw, dict):
            pulse_digest = dict(pulse_digest_raw)
        else:
            pulse_digest = {}

        subject_movement = validated_data.get("subject_movement") or validated_data.get("subject_trajectories") or {}
        active_gaps = validated_data.get("active_gaps") or validated_data.get("critical_topics") or []
        overall_stats = validated_data.get("overall_stats") or {}

        # Auto-synthesize Parent Pulse if not explicitly provided
        if not pulse_digest and (subject_movement or active_gaps):
            try:
                from src.smartparent.engines.parent_pulse_engine import ParentPulseEngine
                pulse_engine = ParentPulseEngine()
                pulse_result = pulse_engine.execute({
                    "student_name": profile.student_name,
                    "subject_trajectories": subject_movement,
                    "active_gaps": active_gaps,
                    "weak_topics": validated_data.get("weak_topics") or [],
                    "strong_topics": validated_data.get("strong_topics") or []
                })
                pulse_digest = pulse_result.model_dump()
            except Exception as e:
                logger.warning(f"Could not auto-synthesize pulse digest in report generator: {e}")
                pulse_digest = {}

        # 1. Build Structured Subject Scorecard Table Data
        scorecard = self._build_scorecard(subject_movement)

        # 2. Build Executive Summary
        exec_summary = {
            "overall_average": overall_stats.get("overall_mean_percentage") or self._calc_average(scorecard),
            "trajectory_indicator": overall_stats.get("asymmetry_summary") or "Steady progress across core subjects",
            "critical_gaps_count": len(active_gaps),
            "report_month": datetime.utcnow().strftime("%B %Y")
        }

        # 3. Render Pixel-Perfect Vector PDF via ReportLab
        pdf_path_override = validated_data.get("pdf_output_path")
        if pdf_path_override:
            target_pdf_path = Path(pdf_path_override)
            target_pdf_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            pdf_filename = f"{report_id}.pdf"
            target_pdf_path = self.output_dir / pdf_filename

        pdf_bytes, page_count = self._render_pdf(
            target_path=target_pdf_path,
            report_id=report_id,
            report_type=report_type,
            profile=profile,
            exec_summary=exec_summary,
            pulse_digest=pulse_digest,
            scorecard=scorecard,
            active_gaps=active_gaps
        )

        return ReportGenerationResult(
            report_id=report_id,
            report_type=report_type,
            student_name=profile.student_name,
            pdf_path=str(target_pdf_path),
            pdf_bytes_size=len(pdf_bytes),
            total_pages=page_count,
            generation_status="SUCCESS",
            executive_summary=exec_summary,
            subject_scorecard=scorecard,
            parent_pulse_digest=pulse_digest
        )

    def fallback(self, error: Exception, input_data: Any) -> ReportGenerationResult:
        """Safe degraded fallback returning valid structured report data without crash."""
        logger.warning(f"[ReportGenerator] Invoking fallback due to error: {error}")
        report_id = f"RPT_FALLBACK_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        return ReportGenerationResult(
            report_id=report_id,
            report_type="MONTHLY_CONSOLIDATED",
            student_name="Student",
            pdf_path=None,
            pdf_bytes_size=0,
            total_pages=0,
            generation_status="DEGRADED",
            executive_summary={"note": "Degraded report generation", "error": str(error)[:100]},
            subject_scorecard=[],
            parent_pulse_digest={}
        )

    # -------------------------------------------------------------------------
    # Report Data Builders
    # -------------------------------------------------------------------------

    def _build_scorecard(self, subject_movement: Union[Dict, List]) -> List[Dict[str, Any]]:
        """Normalizes subject trajectories into clean tabular scorecard rows."""
        rows = []
        if isinstance(subject_movement, dict):
            for subj, data in subject_movement.items():
                if isinstance(data, dict):
                    rows.append({
                        "subject": subj,
                        "latest_percentage": float(data.get("latest_percentage", 0.0)),
                        "movement": str(data.get("movement_indicator", "→ 0.0%")),
                        "status": str(data.get("trajectory_status", "STABLE")),
                        "consistency_index": float(data.get("consistency_index", 100.0)),
                        "assessments_count": int(data.get("total_tests", 1))
                    })
                else:
                    rows.append({
                        "subject": subj,
                        "latest_percentage": float(getattr(data, "latest_percentage", 0.0)),
                        "movement": str(getattr(data, "movement_indicator", "→ 0.0%")),
                        "status": str(getattr(data, "trajectory_status", "STABLE")),
                        "consistency_index": float(getattr(data, "consistency_index", 100.0)),
                        "assessments_count": int(getattr(data, "total_tests", 1))
                    })
        elif isinstance(subject_movement, list):
            for item in subject_movement:
                if isinstance(item, dict):
                    rows.append({
                        "subject": item.get("subject", "General"),
                        "latest_percentage": float(item.get("latest_percentage", item.get("percentage", 0.0))),
                        "movement": str(item.get("movement", item.get("movement_indicator", "→ 0.0%"))),
                        "status": str(item.get("status", item.get("trajectory_status", "STABLE"))),
                        "consistency_index": float(item.get("consistency_index", 100.0)),
                        "assessments_count": int(item.get("assessments_count", 1))
                    })
        return rows

    def _calc_average(self, scorecard: List[Dict[str, Any]]) -> float:
        if not scorecard:
            return 0.0
        return round(sum(r["latest_percentage"] for r in scorecard) / len(scorecard), 1)

    # -------------------------------------------------------------------------
    # PDF Visual Design & Flowable Construction
    # -------------------------------------------------------------------------

    def _render_pdf(
        self,
        target_path: Path,
        report_id: str,
        report_type: str,
        profile: StudentProfileSchema,
        exec_summary: Dict[str, Any],
        pulse_digest: Dict[str, Any],
        scorecard: List[Dict[str, Any]],
        active_gaps: List[Any]
    ) -> Tuple[bytes, int]:
        """Assembles Flowable story and compiles vector PDF using NumberedCanvas."""
        doc = SimpleDocTemplate(
            str(target_path),
            pagesize=A4,
            leftMargin=45,
            rightMargin=45,
            topMargin=45,
            bottomMargin=55
        )

        styles = getSampleStyleSheet()
        
        # Custom Brand Typographic Styles
        title_style = ParagraphStyle(
            "ReportTitle",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#0F766E")  # Deep Teal
        )
        subtitle_style = ParagraphStyle(
            "ReportSubtitle",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=10,
            leading=13,
            textColor=colors.HexColor("#64748B")
        )
        section_h1 = ParagraphStyle(
            "SectionH1",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=16,
            textColor=colors.HexColor("#1E293B"),
            spaceBefore=10,
            spaceAfter=6
        )
        body_text = ParagraphStyle(
            "BodyDark",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13.5,
            textColor=colors.HexColor("#334155")
        )
        card_title_green = ParagraphStyle(
            "CardTitleGreen",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10.5,
            leading=13,
            textColor=colors.HexColor("#065F46")  # Emerald
        )
        card_title_amber = ParagraphStyle(
            "CardTitleAmber",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10.5,
            leading=13,
            textColor=colors.HexColor("#92400E")  # Amber
        )
        card_title_blue = ParagraphStyle(
            "CardTitleBlue",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10.5,
            leading=13,
            textColor=colors.HexColor("#1E40AF")  # Blue
        )

        story = []

        # ── 1. Document Brand Header ───────────────────────────────────────────
        header_table_data = [
            [
                Paragraph("<b>STUDIQS® SmartParent™</b>", title_style),
                Paragraph(f"<b>REPORT ID:</b> {report_id}<br/><b>DATE:</b> {datetime.utcnow().strftime('%d %B %Y')}", subtitle_style)
            ],
            [
                Paragraph(f"Comprehensive Longitudinal Diagnostic Report  |  {exec_summary.get('report_month')}", subtitle_style),
                ""
            ]
        ]
        t_header = Table(header_table_data, colWidths=[330, 180])
        t_header.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
        ]))
        story.append(t_header)
        story.append(Spacer(1, 8))
        story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#0F766E"), spaceBefore=2, spaceAfter=10))

        # ── 2. Student Profile & Executive Scorecard ───────────────────────────
        profile_data = [
            [
                Paragraph(f"<b>Student:</b> {profile.student_name}", body_text),
                Paragraph(f"<b>Class / Board:</b> {profile.standard_class} ({profile.board})", body_text),
                Paragraph(f"<b>School:</b> {profile.school_name}", body_text),
                Paragraph(f"<b>Overall Score:</b> <b>{exec_summary.get('overall_average')}%</b>", body_text)
            ]
        ]
        t_prof = Table(profile_data, colWidths=[140, 130, 140, 100])
        t_prof.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#E2E8F0")),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        story.append(t_prof)
        story.append(Spacer(1, 12))

        # ── 3. Parent Pulse 3-Card Digest (Mandatory Core Feature) ──────────────
        story.append(Paragraph("Monthly Parent Pulse Digest", section_h1))
        
        def _to_dict(obj: Any) -> Dict[str, Any]:
            if not obj:
                return {}
            if hasattr(obj, "model_dump"):
                return obj.model_dump()
            if hasattr(obj, "dict"):
                return obj.dict()
            if isinstance(obj, dict):
                return dict(obj)
            return {}

        imp_data = _to_dict(pulse_digest.get("improvement_area"))
        watch_data = _to_dict(pulse_digest.get("watch_area"))
        action_data = _to_dict(pulse_digest.get("next_immediate_action"))

        # Fallback values if empty
        imp_headline = imp_data.get("headline", "Solid Progress across Assessed Chapters")
        imp_desc = imp_data.get("description", f"{profile.student_name} demonstrates steady academic discipline and growing retention.")
        
        watch_headline = watch_data.get("headline", "Targeted Concept Review Recommended")
        watch_desc = watch_data.get("description", "A few topics will benefit from dedicated practice before upcoming term assessments.")
        
        act_headline = action_data.get("headline", "15-Minute Home Reinforcement Plan")
        act_desc = action_data.get("description", "Review highlighted challenge topics for 15 minutes this weekend with practice problems.")

        pulse_boxes = [
            [
                Paragraph(f"<b>KEY STRENGTH:</b> {imp_headline}", card_title_green),
                Paragraph(f"<b>WATCH AREA:</b> {watch_headline}", card_title_amber),
                Paragraph(f"<b>NEXT 2-WEEK ACTION:</b> {act_headline}", card_title_blue),
            ],
            [
                Paragraph(imp_desc, body_text),
                Paragraph(watch_desc, body_text),
                Paragraph(act_desc, body_text),
            ]
        ]
        t_pulse = Table(pulse_boxes, colWidths=[168, 168, 169])
        t_pulse.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, 1), colors.HexColor("#ECFDF5")),  # Soft Green
            ('BACKGROUND', (1, 0), (1, 1), colors.HexColor("#FFFBEB")),  # Soft Amber
            ('BACKGROUND', (2, 0), (2, 1), colors.HexColor("#EFF6FF")),  # Soft Blue
            ('BOX', (0, 0), (0, 1), 1, colors.HexColor("#A7F3D0")),
            ('BOX', (1, 0), (1, 1), 1, colors.HexColor("#FDE68A")),
            ('BOX', (2, 0), (2, 1), 1, colors.HexColor("#BFDBFE")),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        story.append(t_pulse)
        story.append(Spacer(1, 14))

        # ── 4. Subject-Wise Performance & Longitudinal Scorecard ────────────────
        story.append(Paragraph("Subject-Wise Longitudinal Scorecard", section_h1))
        
        scorecard_rows = [
            [
                Paragraph("<b>Subject</b>", body_text),
                Paragraph("<b>Latest Score</b>", body_text),
                Paragraph("<b>60-Day Delta</b>", body_text),
                Paragraph("<b>Trajectory Status</b>", body_text),
                Paragraph("<b>Consistency Index</b>", body_text),
            ]
        ]
        
        if scorecard:
            for s in scorecard:
                scorecard_rows.append([
                    Paragraph(f"<b>{s.get('subject')}</b>", body_text),
                    Paragraph(f"{s.get('latest_percentage'):.1f}%", body_text),
                    Paragraph(f"{s.get('movement')}", body_text),
                    Paragraph(f"{s.get('status')}", body_text),
                    Paragraph(f"{s.get('consistency_index'):.1f} / 100", body_text),
                ])
        else:
            scorecard_rows.append([
                Paragraph("General Performance", body_text),
                Paragraph(f"{exec_summary.get('overall_average')}%", body_text),
                Paragraph("→ 0.0%", body_text),
                Paragraph("STABLE", body_text),
                Paragraph("100.0 / 100", body_text),
            ])

        t_scorecard = Table(scorecard_rows, colWidths=[135, 90, 95, 105, 80])
        t_scorecard.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#CBD5E1")),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ]))
        story.append(t_scorecard)
        story.append(Spacer(1, 14))

        # ── 5. Actionable Topic Gap Watchlist ───────────────────────────────────
        if active_gaps:
            story.append(Paragraph("Actionable Topic Gap Watchlist", section_h1))
            gap_rows = [
                [
                    Paragraph("<b>#</b>", body_text),
                    Paragraph("<b>Topic Name</b>", body_text),
                    Paragraph("<b>Priority Level</b>", body_text),
                    Paragraph("<b>Recommended Action</b>", body_text)
                ]
            ]
            for idx, g in enumerate(active_gaps[:6], 1):
                topic_title = g if isinstance(g, str) else g.get("topic", "Topic Gap")
                gap_rows.append([
                    Paragraph(str(idx), body_text),
                    Paragraph(f"<b>{topic_title}</b>", body_text),
                    Paragraph("<font color='#DC2626'><b>CRITICAL</b></font>", body_text),
                    Paragraph("15-minute concept review + 3 ladder practice problems", body_text)
                ])

            t_gaps = Table(gap_rows, colWidths=[25, 175, 95, 210])
            t_gaps.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
                ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#CBD5E1")),
                ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            story.append(t_gaps)

        # Build Document
        doc.build(story, canvasmaker=NumberedCanvas)
        
        # Read back bytes
        with open(target_path, "rb") as f:
            pdf_bytes = f.read()

        # Exact page count recorded by SimpleDocTemplate
        page_count = max(1, getattr(doc, "page", 1))
        return pdf_bytes, page_count
