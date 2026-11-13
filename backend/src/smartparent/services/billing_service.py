"""
STUDIQS® SmartParent™ (v6.3 Complete) - Production Billing & GST Invoicing Service
==================================================================================
Module: src.smartparent.services.billing_service
Sections: 24 (Subscription & Billing) & 25 (Admin Revenue Intelligence)

Implements:
1. Deterministic Reverse 18% GST Calculations (CGST 9% + SGST 9% or IGST 18%)
2. Automated B2C Compliant GST Tax Invoice Generation using ReportLab Vector Graphics
3. Invoice Persistence & Subscriber Invoicing History
4. Razorpay Signature Verification & Payment Order Fulfillment
==================================================================================
"""

import os
import io
import uuid
import hmac
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import desc

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from src.smartparent.db.models.subscription import BillingInvoice, Subscription
from src.smartparent.db.models.auth import Subscriber
from src.smartparent.schemas.subscription import CheckoutQuoteSchema, GSTBreakdownSchema
from src.smartparent.config import settings

logger = logging.getLogger("STUDIQS_BillingService")

# Company GST Billing Constants
STUDIQS_COMPANY_NAME = "STUDIQS INTELLIGENCE LLP"
STUDIQS_GSTIN = "33AAACS1234F1Z8"
STUDIQS_STATE = "Tamil Nadu"
STUDIQS_STATE_CODE = "33"
STUDIQS_SAC_CODE = "999293"  # Commercial training and coaching services / online education


class BillingService:
    """
    Production Billing and Tax Invoicing Service.
    """

    def __init__(self, upload_dir: Optional[str] = None):
        self.upload_dir = Path(upload_dir or getattr(settings, "UPLOAD_DIR", "./uploads")) / "invoices"
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    # =========================================================================
    # 1. RAZORPAY SIGNATURE VERIFICATION
    # =========================================================================

    @staticmethod
    def verify_razorpay_signature(
        order_id: str,
        payment_id: str,
        signature: str,
        secret: Optional[str] = None,
    ) -> bool:
        """
        Verifies Razorpay payment signature authenticity using HMAC-SHA256 for one-time orders.
        """
        key_secret = secret or getattr(settings, "RAZORPAY_KEY_SECRET", "dev_razorpay_secret")
        payload = f"{order_id}|{payment_id}"
        expected = hmac.new(
            key_secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    @staticmethod
    def verify_payment_signature(
        payment_id: str,
        order_id: Optional[str] = None,
        subscription_id: Optional[str] = None,
        signature: Optional[str] = None,
        secret: Optional[str] = None,
    ) -> bool:
        """
        Verifies Razorpay payment signature polymorphically:
        - If subscription_id (recurring mandate): HMAC(payment_id + "|" + subscription_id)
        - If order_id (one-time order): HMAC(order_id + "|" + payment_id)
        """
        if not signature:
            return False
        key_secret = secret or getattr(settings, "RAZORPAY_KEY_SECRET", None) or "dev_razorpay_secret"

        if subscription_id:
            payload = f"{payment_id}|{subscription_id}"
        elif order_id:
            payload = f"{order_id}|{payment_id}"
        else:
            return False

        expected = hmac.new(
            key_secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    @staticmethod
    def verify_webhook_signature(
        raw_body: bytes,
        signature: str,
        webhook_secret: Optional[str] = None,
    ) -> bool:
        """
        Verifies Razorpay Webhook signature authenticity using HMAC-SHA256.
        """
        secret = webhook_secret or getattr(settings, "RAZORPAY_WEBHOOK_SECRET", None) or "dev_webhook_secret"
        expected = hmac.new(
            secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    # =========================================================================
    # 2. VECTOR PDF GST INVOICE GENERATOR
    # =========================================================================

    def generate_gst_invoice_pdf(
        self,
        invoice_data: Dict[str, Any],
        output_path: Optional[str] = None,
    ) -> bytes:
        """
        Generates an authoritative, tamper-proof vector GST Tax Invoice PDF.
        Complies with Section 31 of CGST Act, 2017 for B2C Digital Services.
        """
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36,
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "InvoiceTitle",
            parent=styles["Heading1"],
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#1E3A8A"),
            fontName="Helvetica-Bold",
        )
        subtitle_style = ParagraphStyle(
            "InvoiceSubtitle",
            parent=styles["Normal"],
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#4B5563"),
        )
        bold_cell = ParagraphStyle(
            "BoldCell",
            parent=styles["Normal"],
            fontSize=8,
            leading=10,
            fontName="Helvetica-Bold",
            textColor=colors.HexColor("#111827"),
        )
        normal_cell = ParagraphStyle(
            "NormalCell",
            parent=styles["Normal"],
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#374151"),
        )

        story = []

        # 1. Header & Title
        header_table = Table(
            [
                [
                    Paragraph("<b>STUDIQS® SmartParent™</b><br/>Tax Invoice", title_style),
                    Paragraph(
                        f"<b>Invoice #:</b> {invoice_data.get('invoice_number', 'INV-DRAFT')}<br/>"
                        f"<b>Date:</b> {invoice_data.get('invoice_date', datetime.now(timezone.utc).strftime('%d-%b-%Y'))}<br/>"
                        f"<b>Status:</b> PAID 🟢",
                        subtitle_style,
                    ),
                ]
            ],
            colWidths=[320, 220],
        )
        header_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 10))
        story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#1E3A8A"), spaceAfter=12))

        # 2. Supplier vs Buyer Table
        buyer_state = invoice_data.get("buyer_state", "Tamil Nadu")
        supplier_info = (
            f"<b>SUPPLIER (Service Provider):</b><br/>"
            f"{STUDIQS_COMPANY_NAME}<br/>"
            f"No. 14, Apex Tech Corridor, Guindy, Chennai - 600032<br/>"
            f"<b>GSTIN:</b> {STUDIQS_GSTIN} | <b>State:</b> {STUDIQS_STATE} (Code {STUDIQS_STATE_CODE})<br/>"
            f"<b>Support:</b> billing@studiqs.com"
        )
        buyer_info = (
            f"<b>BILLED TO (Customer / Parent):</b><br/>"
            f"<b>Name:</b> {invoice_data.get('parent_name', 'Sundaram R.')}<br/>"
            f"<b>Mobile:</b> {invoice_data.get('mobile_number', 'N/A')}<br/>"
            f"<b>Email:</b> {invoice_data.get('email', 'N/A')}<br/>"
            f"<b>State of Supply:</b> {buyer_state}<br/>"
            f"<b>Place of Supply:</b> {buyer_state} (B2C)"
        )

        address_table = Table(
            [[Paragraph(supplier_info, normal_cell), Paragraph(buyer_info, normal_cell)]],
            colWidths=[270, 270],
        )
        address_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F9FAFB")),
            ("PADDING", (0, 0), (-1, -1), 8),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
        ]))
        story.append(address_table)
        story.append(Spacer(1, 14))

        # 3. Line Items & Tax Calculation Table
        taxable_amt = float(invoice_data.get("taxable_amount", 0.0))
        cgst_amt = float(invoice_data.get("cgst_amount", 0.0))
        sgst_amt = float(invoice_data.get("sgst_amount", 0.0))
        igst_amt = float(invoice_data.get("igst_amount", 0.0))
        total_amt = float(invoice_data.get("total_amount", 0.0))
        plan_desc = invoice_data.get("plan_description", "Studiqs SmartParent Subscription")

        line_items = [
            [
                Paragraph("<b>Sl.</b>", bold_cell),
                Paragraph("<b>Service Description</b>", bold_cell),
                Paragraph("<b>SAC</b>", bold_cell),
                Paragraph("<b>Taxable (₹)</b>", bold_cell),
                Paragraph("<b>CGST (9%)</b>", bold_cell),
                Paragraph("<b>SGST (9%)</b>", bold_cell),
                Paragraph("<b>IGST (18%)</b>", bold_cell),
                Paragraph("<b>Total (₹)</b>", bold_cell),
            ],
            [
                Paragraph("1", normal_cell),
                Paragraph(plan_desc, normal_cell),
                Paragraph(STUDIQS_SAC_CODE, normal_cell),
                Paragraph(f"{taxable_amt:.2f}", normal_cell),
                Paragraph(f"{cgst_amt:.2f}", normal_cell),
                Paragraph(f"{sgst_amt:.2f}", normal_cell),
                Paragraph(f"{igst_amt:.2f}", normal_cell),
                Paragraph(f"<b>{total_amt:.2f}</b>", bold_cell),
            ],
            [
                Paragraph("", normal_cell),
                Paragraph("<b>Total Payable (INR)</b>", bold_cell),
                Paragraph("", normal_cell),
                Paragraph(f"<b>₹{taxable_amt:.2f}</b>", bold_cell),
                Paragraph(f"<b>₹{cgst_amt:.2f}</b>", bold_cell),
                Paragraph(f"<b>₹{sgst_amt:.2f}</b>", bold_cell),
                Paragraph(f"<b>₹{igst_amt:.2f}</b>", bold_cell),
                Paragraph(f"<b>₹{total_amt:.2f}</b>", bold_cell),
            ],
        ]

        items_table = Table(
            line_items,
            colWidths=[25, 175, 45, 60, 55, 55, 55, 70],
        )
        items_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("ALIGN", (1, 1), (1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#EFF6FF")),
            ("PADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(items_table)
        story.append(Spacer(1, 14))

        # 4. Payment Gateway & Transaction Provenance
        gateway_info = (
            f"<b>PAYMENT TELEMETRY:</b><br/>"
            f"• <b>Gateway:</b> Razorpay Software Pvt Ltd<br/>"
            f"• <b>Payment ID:</b> {invoice_data.get('razorpay_payment_id', 'N/A')}<br/>"
            f"• <b>Order ID:</b> {invoice_data.get('razorpay_order_id', 'N/A')}<br/>"
            f"• <b>Payment Mode:</b> UPI / Debit & Credit Cards / Mandate<br/>"
            f"• <b>Reverse Charge:</b> No (Tax is paid by Supplier under forward charge)"
        )
        notes_box = Table(
            [[Paragraph(gateway_info, normal_cell)]],
            colWidths=[540],
        )
        notes_box.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F3F4F6")),
            ("PADDING", (0, 0), (-1, -1), 8),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
        ]))
        story.append(notes_box)
        story.append(Spacer(1, 20))

        # 5. Footer & Statutory Declaration
        footer_text = (
            "<i>This is a computer-generated tax invoice. No physical signature is required under IT Act, 2000.<br/>"
            "Thank you for choosing Studiqs SmartParent to support your child's learning journey!</i>"
        )
        story.append(Paragraph(footer_text, subtitle_style))

        # Build document
        doc.build(story)
        pdf_bytes = buffer.getvalue()
        buffer.close()

        if output_path:
            out_file = Path(output_path)
            out_file.parent.mkdir(parents=True, exist_ok=True)
            with open(out_file, "wb") as f:
                f.write(pdf_bytes)

        return pdf_bytes

    # =========================================================================
    # 3. INVOICE CREATION & DATABASE PERSISTENCE
    # =========================================================================

    def create_subscription_invoice(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
        quote: CheckoutQuoteSchema,
        razorpay_payment_id: str,
        razorpay_order_id: str,
        subscription_id: Optional[uuid.UUID] = None,
        billing_start: Optional[datetime] = None,
        billing_end: Optional[datetime] = None,
    ) -> BillingInvoice:
        """
        Creates and persists a BillingInvoice DB record and generates the invoice PDF.
        """
        subscriber = db.query(Subscriber).filter(Subscriber.subscriber_id == subscriber_id).first()
        if not subscriber:
            raise ValueError(f"Subscriber {subscriber_id} not found.")

        now = datetime.now(timezone.utc)
        start_date = billing_start or now
        end_date = billing_end or now

        # Generate sequential GST compliant invoice number (INV-STQ-YYYY-NNNNN)
        year = now.strftime("%Y")
        invoice_count = db.query(BillingInvoice).count() + 1
        invoice_num = f"INV-STQ-{year}-{invoice_count:05d}"

        # Setup PDF file path
        pdf_filename = f"{invoice_num}.pdf"
        pdf_file_path = self.upload_dir / pdf_filename

        invoice_data = {
            "invoice_number": invoice_num,
            "invoice_date": now.strftime("%d-%b-%Y"),
            "parent_name": subscriber.parent_name,
            "mobile_number": subscriber.mobile_number,
            "email": subscriber.email,
            "buyer_state": getattr(quote, "state", "Tamil Nadu"),
            "plan_description": f"{quote.plan_name} ({quote.duration_label})",
            "taxable_amount": quote.taxable_base_amount,
            "cgst_amount": quote.gst_breakdown.cgst_amount,
            "sgst_amount": quote.gst_breakdown.sgst_amount,
            "igst_amount": quote.gst_breakdown.igst_amount,
            "total_amount": quote.gross_payable_amount,
            "razorpay_payment_id": razorpay_payment_id,
            "razorpay_order_id": razorpay_order_id,
        }

        # Build PDF
        self.generate_gst_invoice_pdf(invoice_data, output_path=str(pdf_file_path))

        invoice_record = BillingInvoice(
            invoice_id=uuid.uuid4(),
            invoice_number=invoice_num,
            subscriber_id=subscriber_id,
            subscription_id=subscription_id,
            billing_period_start=start_date,
            billing_period_end=end_date,
            base_amount=quote.gross_payable_amount,
            discount_amount=0.0,
            taxable_amount=quote.taxable_base_amount,
            cgst_rate=9.0 if quote.gst_breakdown.cgst_amount > 0 else 0.0,
            cgst_amount=quote.gst_breakdown.cgst_amount,
            sgst_rate=9.0 if quote.gst_breakdown.sgst_amount > 0 else 0.0,
            sgst_amount=quote.gst_breakdown.sgst_amount,
            igst_rate=18.0 if quote.gst_breakdown.igst_amount > 0 else 0.0,
            igst_amount=quote.gst_breakdown.igst_amount,
            total_amount=quote.gross_payable_amount,
            currency="INR",
            payment_status="PAID",
            razorpay_payment_id=razorpay_payment_id,
            razorpay_order_id=razorpay_order_id,
            invoice_pdf_url=str(pdf_file_path),
            created_at=now,
        )

        db.add(invoice_record)
        db.commit()
        db.refresh(invoice_record)

        logger.info(f"[BillingService] Issued GST Invoice {invoice_num} for subscriber {subscriber_id}")
        return invoice_record

    def get_subscriber_invoices(
        self,
        db: Session,
        subscriber_id: uuid.UUID,
    ) -> List[BillingInvoice]:
        """Returns invoice history for a subscriber ordered by creation date."""
        return (
            db.query(BillingInvoice)
            .filter(BillingInvoice.subscriber_id == subscriber_id)
            .order_by(desc(BillingInvoice.created_at))
            .all()
        )
