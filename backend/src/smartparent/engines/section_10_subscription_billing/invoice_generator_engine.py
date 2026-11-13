"""
STUDIQS® SmartParent™ - Section 24: GST Invoice & Receipt Generation Engine
=============================================================================
Module: src.smartparent.engines.section_10_subscription_billing.invoice_generator_engine

Generates standardized GST Tax Invoices for Indian consumer compliance:
  - Sequential invoice numbers: INV-STQ-YYYY-NNNNN (e.g. INV-STQ-2026-00142).
  - Indian SAC Code 998431 (Online Educational Services).
  - CGST 9% + SGST 9% (Intra-state) or IGST 18% (Inter-state).
  - Itemized receipt structure ready for PDF compilation or client receipt UI.
=============================================================================
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict
from src.smartparent.engines.section_00_core.base_engine import BaseEngine
from src.smartparent.engines.section_10_subscription_billing.subscription_pricing_engine import CheckoutQuoteSchema


# =============================================================================
# 1. Company Information & Schemas
# =============================================================================

STUDIQS_COMPANY_INFO: Dict[str, str] = {
    "legal_name": "Studiqs Intelligence LLP",
    "trade_name": "Studiqs SmartParent™",
    "gstin": "33AAQFS1234F1Z8",  # Tamil Nadu state code 33
    "pan": "AAQFS1234F",
    "sac_code": "998431",  # Online education & academic analytics
    "sac_description": "Online Portal & Academic Analytics Services",
    "address_line1": "No. 42, Innovation Campus, OMR",
    "city": "Chennai",
    "state": "Tamil Nadu",
    "pincode": "600096",
    "support_email": "billing@studiqs.com",
}


class InvoiceItemSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")
    item_no: int = 1
    description: str
    sac_code: str = "998431"
    duration_label: str
    taxable_amount: float
    gst_rate_pct: float = 18.0
    gst_amount: float
    total_amount: float


class TaxInvoiceSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")
    invoice_number: str
    invoice_id: str
    subscriber_id: str
    subscription_id: Optional[str] = None
    invoice_date: datetime
    billing_period_start: datetime
    billing_period_end: datetime
    # Parties
    company_details: Dict[str, str]
    customer_name: str
    customer_phone: str
    customer_state: str
    place_of_supply: str
    # Line Items & Money
    items: List[InvoiceItemSchema]
    taxable_base_amount: float
    is_interstate: bool
    cgst_rate: float
    cgst_amount: float
    sgst_rate: float
    sgst_amount: float
    igst_rate: float
    igst_amount: float
    total_tax_amount: float
    gross_total_amount: float
    currency: str = "INR"
    # Payment info
    payment_status: str = "PAID"
    payment_reference_id: Optional[str] = None
    gateway_order_id: Optional[str] = None


# =============================================================================
# 2. Production Invoice Generator Engine
# =============================================================================

class InvoiceGeneratorEngine(BaseEngine):
    """
    Section 24 GST Tax Invoice & Receipt Engine.
    Emits deterministic, audited tax invoice records formatted to Indian GST rules.
    """

    def __init__(self, failure_threshold: int = 5):
        super().__init__(name="InvoiceGeneratorEngine", failure_threshold=failure_threshold)

    # -------------------------------------------------------------------------
    # BaseEngine Lifecycle Hooks
    # -------------------------------------------------------------------------

    def validate_input(self, input_data: Any) -> Dict[str, Any]:
        """Validates quote and customer info for invoice creation."""
        if not isinstance(input_data, dict):
            raise ValueError("Input must be a dictionary")
        if "quote" not in input_data:
            raise ValueError("Missing 'quote' in invoice generator input")
        return input_data

    def execute_core(self, validated_data: Dict[str, Any]) -> TaxInvoiceSchema:
        """Generates the tax invoice schema."""
        return self.create_invoice(
            sequence_number=int(validated_data.get("sequence_number", 1)),
            subscriber_id=str(validated_data.get("subscriber_id", "")),
            subscription_id=validated_data.get("subscription_id"),
            customer_name=str(validated_data.get("customer_name", "Parent")),
            customer_phone=str(validated_data.get("customer_phone", "")),
            customer_state=str(validated_data.get("customer_state", "Tamil Nadu")),
            quote=validated_data["quote"],
            billing_start=validated_data["billing_start"],
            billing_end=validated_data["billing_end"],
            payment_ref=validated_data.get("payment_ref"),
            gateway_order_id=validated_data.get("gateway_order_id"),
        )

    def fallback(self, error: Exception, input_data: Any) -> TaxInvoiceSchema:
        """Safe fallback placeholder invoice."""
        self.logger.warning("InvoiceGeneratorEngine fallback invoked: %s", error)
        now = datetime.now(timezone.utc)
        return TaxInvoiceSchema(
            invoice_number=f"INV-STQ-{now.year}-00000",
            invoice_id=str(uuid.uuid4()),
            subscriber_id="UNKNOWN",
            invoice_date=now,
            billing_period_start=now,
            billing_period_end=now,
            company_details=STUDIQS_COMPANY_INFO,
            customer_name="Parent",
            customer_phone="",
            customer_state="Tamil Nadu",
            place_of_supply="Tamil Nadu",
            items=[],
            taxable_base_amount=0.0,
            is_interstate=False,
            cgst_rate=9.0,
            cgst_amount=0.0,
            sgst_rate=9.0,
            sgst_amount=0.0,
            igst_rate=0.0,
            igst_amount=0.0,
            total_tax_amount=0.0,
            gross_total_amount=0.0,
        )

    # -------------------------------------------------------------------------
    # Core Domain Logic
    # -------------------------------------------------------------------------

    @staticmethod
    def format_invoice_number(sequence_number: int, invoice_date: Optional[datetime] = None) -> str:
        """
        Formats sequential invoice number: INV-STQ-YYYY-NNNNN
        """
        dt = invoice_date or datetime.now(timezone.utc)
        year = dt.year
        return f"INV-STQ-{year}-{sequence_number:05d}"

    def create_invoice(
        self,
        sequence_number: int,
        subscriber_id: str,
        customer_name: str,
        customer_phone: str,
        customer_state: str,
        quote: Any,  # CheckoutQuoteSchema or dict
        billing_start: datetime,
        billing_end: datetime,
        subscription_id: Optional[str] = None,
        payment_ref: Optional[str] = None,
        gateway_order_id: Optional[str] = None,
        invoice_date: Optional[datetime] = None,
    ) -> TaxInvoiceSchema:
        """
        Builds complete TaxInvoiceSchema compliant with GST rules.
        """
        now = invoice_date or datetime.now(timezone.utc)
        inv_number = self.format_invoice_number(sequence_number, invoice_date=now)

        # Extract quote fields
        if hasattr(quote, "plan_name"):
            plan_name = quote.plan_name
            dur_label = quote.duration_label
            taxable_base = quote.taxable_base_amount
            gross = quote.gross_payable_amount
            gst = quote.gst_breakdown
            is_interstate = gst.is_interstate
            cgst_rate = gst.cgst_rate
            cgst_amt = gst.cgst_amount
            sgst_rate = gst.sgst_rate
            sgst_amt = gst.sgst_amount
            igst_rate = gst.igst_rate
            igst_amt = gst.igst_amount
            total_tax = gst.total_tax_amount
        else:
            plan_name = quote.get("plan_name", "Studiqs Subscription")
            dur_label = quote.get("duration_label", "MONTHLY")
            taxable_base = float(quote.get("taxable_base_amount", 0.0))
            gross = float(quote.get("gross_payable_amount", 0.0))
            gst_d = quote.get("gst_breakdown", {})
            is_interstate = bool(gst_d.get("is_interstate", False))
            cgst_rate = float(gst_d.get("cgst_rate", 9.0))
            cgst_amt = float(gst_d.get("cgst_amount", 0.0))
            sgst_rate = float(gst_d.get("sgst_rate", 9.0))
            sgst_amt = float(gst_d.get("sgst_amount", 0.0))
            igst_rate = float(gst_d.get("igst_rate", 0.0))
            igst_amt = float(gst_d.get("igst_amount", 0.0))
            total_tax = float(gst_d.get("total_tax_amount", 0.0))

        item_desc = f"{plan_name} - {dur_label} Subscription"
        line_item = InvoiceItemSchema(
            item_no=1,
            description=item_desc,
            sac_code=STUDIQS_COMPANY_INFO["sac_code"],
            duration_label=dur_label,
            taxable_amount=taxable_base,
            gst_rate_pct=18.0,
            gst_amount=total_tax,
            total_amount=gross,
        )

        return TaxInvoiceSchema(
            invoice_number=inv_number,
            invoice_id=str(uuid.uuid4()),
            subscriber_id=str(subscriber_id),
            subscription_id=str(subscription_id) if subscription_id else None,
            invoice_date=now,
            billing_period_start=billing_start,
            billing_period_end=billing_end,
            company_details=STUDIQS_COMPANY_INFO,
            customer_name=customer_name,
            customer_phone=customer_phone,
            customer_state=customer_state,
            place_of_supply=customer_state,
            items=[line_item],
            taxable_base_amount=taxable_base,
            is_interstate=is_interstate,
            cgst_rate=cgst_rate,
            cgst_amount=cgst_amt,
            sgst_rate=sgst_rate,
            sgst_amount=sgst_amt,
            igst_rate=igst_rate,
            igst_amount=igst_amt,
            total_tax_amount=total_tax,
            gross_total_amount=gross,
            currency="INR",
            payment_status="PAID",
            payment_reference_id=payment_ref,
            gateway_order_id=gateway_order_id,
        )
