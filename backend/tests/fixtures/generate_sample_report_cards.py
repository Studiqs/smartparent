"""
STUDIQS® SmartParent™ - Synthetic Report Card Generator
=============================================================================
Generates authentic test fixtures for ResultParserEngine:
1. sample_cbse_report_card.pdf (Digital Vector PDF with tables)
2. sample_report_card_clean.png (High-resolution clean 300 DPI render)
3. sample_report_card_skewed_shadow.png (Realistic smartphone photo with +4.5° tilt & shadows)
=============================================================================
"""

import os
from pathlib import Path
import cv2
import numpy as np
import fitz
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch


def generate_test_fixtures(output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = output_dir / "sample_cbse_report_card.pdf"
    clean_png_path = output_dir / "sample_report_card_clean.png"
    skewed_png_path = output_dir / "sample_report_card_skewed_shadow.png"

    # =========================================================================
    # 1. Generate Clean Digital PDF via ReportLab
    # =========================================================================
    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'SchoolTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        alignment=1,
        textColor=colors.HexColor('#0F172A')
    )
    sub_style = ParagraphStyle(
        'SchoolSub',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=11,
        leading=14,
        alignment=1,
        textColor=colors.HexColor('#475569')
    )
    meta_style = ParagraphStyle(
        'MetaText',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=13,
        textColor=colors.HexColor('#1E293B')
    )
    cell_style = ParagraphStyle(
        'CellText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=12,
        textColor=colors.HexColor('#0F172A')
    )
    cell_bold = ParagraphStyle(
        'CellBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=12,
        textColor=colors.HexColor('#0F172A')
    )

    elements = []
    elements.append(Paragraph("DELHI PUBLIC SCHOOL - CHENNAI", title_style))
    elements.append(Paragraph("Affiliated to CBSE, New Delhi | Affiliation No: 1930245", sub_style))
    elements.append(Paragraph("ANNUAL PROGRESS REPORT CARD — CLASS X (2025-2026)", sub_style))
    elements.append(Spacer(1, 0.2 * inch))

    # Student metadata table
    meta_table_data = [
        [Paragraph("Student Name: <b>Rahul Sharma</b>", meta_style), Paragraph("Admission No: <b>DPS-2021-102</b>", meta_style)],
        [Paragraph("Class & Section: <b>Class 10 - A</b>", meta_style), Paragraph("Roll Number: <b>10A24</b>", meta_style)],
        [Paragraph("Date of Birth: <b>12-May-2010</b>", meta_style), Paragraph("Term: <b>Terminal Assessment 2026</b>", meta_style)]
    ]
    meta_table = Table(meta_table_data, colWidths=[3.5 * inch, 3.5 * inch])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#CBD5E1')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 0.25 * inch))

    # Academic Marks Table
    marks_data = [
        [Paragraph("<b>Subject Code & Name</b>", cell_bold), Paragraph("<b>Max Marks</b>", cell_bold), Paragraph("<b>Marks Obtained</b>", cell_bold), Paragraph("<b>Grade</b>", cell_bold), Paragraph("<b>Performance</b>", cell_bold)],
        [Paragraph("Tamil Language", cell_style), Paragraph("100", cell_style), Paragraph("92", cell_bold), Paragraph("A1", cell_style), Paragraph("Strong", cell_style)],
        [Paragraph("English Core", cell_style), Paragraph("100", cell_style), Paragraph("84", cell_bold), Paragraph("A2", cell_style), Paragraph("Strong", cell_style)],
        [Paragraph("Mathematics", cell_style), Paragraph("100", cell_style), Paragraph("78", cell_bold), Paragraph("B1", cell_style), Paragraph("Average", cell_style)],
        [Paragraph("General Science", cell_style), Paragraph("100", cell_style), Paragraph("88", cell_bold), Paragraph("A2", cell_style), Paragraph("Strong", cell_style)],
        [Paragraph("Social Science", cell_style), Paragraph("100", cell_style), Paragraph("90", cell_bold), Paragraph("A1", cell_style), Paragraph("Strong", cell_style)],
        [Paragraph("<b>Grand Total</b>", cell_bold), Paragraph("<b>500</b>", cell_bold), Paragraph("<b>432</b>", cell_bold), Paragraph("<b>A2</b>", cell_bold), Paragraph("<b>86.4% (Pass)</b>", cell_bold)]
    ]

    marks_table = Table(marks_data, colWidths=[2.6 * inch, 1.1 * inch, 1.2 * inch, 0.9 * inch, 1.2 * inch])
    marks_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E293B')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#94A3B8')),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#F1F5F9')),
    ]))

    elements.append(marks_table)
    elements.append(Spacer(1, 0.4 * inch))

    # Signatures
    sig_data = [
        [Paragraph("Class Teacher: <i>S. Revathi</i>", meta_style), Paragraph("Principal: <i>Dr. K. Ramanathan</i>", meta_style), Paragraph("School Seal: <b>[OFFICIALLY VERIFIED]</b>", meta_style)]
    ]
    sig_table = Table(sig_data, colWidths=[2.5 * inch, 2.5 * inch, 2.0 * inch])
    elements.append(sig_table)

    doc.build(elements)
    print(f"[Generated] Digital Report Card PDF: {pdf_path}")

    # =========================================================================
    # 2. Render High-Resolution Clean PNG (300 DPI)
    # =========================================================================
    fitz_doc = fitz.open(str(pdf_path))
    page = fitz_doc[0]
    pix = page.get_pixmap(dpi=300)
    pix.save(str(clean_png_path))
    fitz_doc.close()
    print(f"[Generated] Clean 300 DPI Marksheet Image: {clean_png_path}")

    # =========================================================================
    # 3. Generate Realistic Distorted Mobile Photo (Skew + Shadow + Noise)
    # =========================================================================
    clean_cv = cv2.imread(str(clean_png_path))
    h, w = clean_cv.shape[:2]

    # A. Add Tilt / Skew (+4.5 degrees)
    angle = 4.5
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 0.96)
    skewed = cv2.warpAffine(clean_cv, M, (w, h), borderMode=cv2.BORDER_CONSTANT, borderValue=(235, 230, 225))

    # B. Add Realistic Smartphone Radial Shadow (Darker at bottom-right)
    Y, X = np.ogrid[:h, :w]
    # Center of shadow near bottom-right
    dist_from_light = np.sqrt(((X - w * 0.8) / w) ** 2 + ((Y - h * 0.8) / h) ** 2)
    shadow_mask = np.clip(1.0 - 0.45 * dist_from_light, 0.55, 1.0)
    shadowed = (skewed.astype(np.float32) * shadow_mask[:, :, np.newaxis]).astype(np.uint8)

    # C. Add Subtle Sensor Grain Noise
    noise = np.random.normal(0, 3, shadowed.shape).astype(np.int16)
    noisy = np.clip(shadowed.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    cv2.imwrite(str(skewed_png_path), noisy)
    print(f"[Generated] Realistic Skewed & Shadowed Mobile Photo: {skewed_png_path}")

    return {
        "pdf": pdf_path,
        "clean_png": clean_png_path,
        "skewed_png": skewed_png_path
    }


if __name__ == "__main__":
    fixtures_dir = Path(__file__).resolve().parent / "samples"
    generate_test_fixtures(fixtures_dir)
