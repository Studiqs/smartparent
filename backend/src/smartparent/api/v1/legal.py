"""
STUDIQS® SmartParent™ (v6.3 Complete) - Razorpay & Statutory Legal Compliance API
=================================================================================
Module: src.smartparent.api.v1.legal
Statutory Requirements for Razorpay Live Merchant Activation & DPDP Act 2023:
  1. Terms & Conditions (ToS)
  2. Privacy Policy (DPDP Act 2023 Student Data Protection)
  3. Cancellation and Refund Policy (Section 24.7 compliance)
  4. Shipping & Delivery Policy (Instant Digital Academic Telemetry)
  5. Grievance Redressal & Contact Us (Statutory Grievance Officer Details)
=================================================================================
"""

from fastapi import APIRouter, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/legal", tags=["Razorpay & Regulatory Legal Compliance"])


class LegalPolicyResponse(BaseModel):
    policy_name: str
    last_updated: str = "2026-11-09"
    version: str = "6.3.0"
    content_markdown: str
    contact_email: str = "grievance@studiqs.com"


TERMS_CONTENT = """# Terms and Conditions
**Last Updated:** November 9, 2026 | **Version:** 6.3.0

Welcome to **STUDIQS® SmartParent™** ("Platform"), owned and operated by Studiqs AI Technologies Private Limited ("Company", "we", "us", or "our").

### 1. Acceptance of Terms
By accessing or using the STUDIQS® SmartParent™ platform (via Web, Progressive Web App, or Mobile), you ("Parent", "Subscriber", or "User") agree to be bound by these Terms and Conditions and our Privacy Policy.

### 2. Nature of Services
STUDIQS® SmartParent™ provides high-concurrency academic diagnostic telemetry, student performance tracking, curriculum gap intelligence, consolidated reports, and a verified subject-matter expert evaluation marketplace for Classes 1 to 12 across CBSE, ICSE, and State Boards.

### 3. User Account and Security
- Parents must register using a valid 10-digit Indian mobile number authenticated via Time-based One-Time Password (TOTP/OTP).
- You are responsible for safeguarding your session tokens and credentials. Any unauthorized access must be reported immediately.

### 4. Subscription & Billing
- Subscriptions are billed upfront in Indian Rupees (INR) inclusive of 18% GST (SAC Code 998439).
- Available billing cycles: 1 Month, 3 Months, 6 Months, and 12 Months.
- Feature gating and quota entitlements are enforced according to your active tier (Basic, Advanced, or Pro).

### 5. Intellectual Property
All algorithms, question-paper parsers, diagnostic engines, report layouts, and Voice AI models are proprietary intellectual property of Studiqs AI Technologies Pvt Ltd.
"""

PRIVACY_CONTENT = """# Privacy Policy
**Last Updated:** November 9, 2026 | **Version:** 6.3.0  
**Regulatory Compliance:** Digital Personal Data Protection Act (DPDP Act 2023), India

### 1. Our Commitment to Student Data Privacy
At STUDIQS®, student privacy is sacrosanct. We treat academic marks, handwritten answer sheets, and student diagnostic data as confidential personal telemetry.

### 2. Data We Collect
- **Parent Profile:** Full Name, 10-digit Mobile Number, Email Address.
- **Child Academic Profile:** Student Alias/First Name, Standard/Grade (Classes 1-12), Board of Education (CBSE, ICSE, State Boards).
- **Academic Telemetry:** Scored marks, question-level marks, answer sheet uploads, and learning gap indicators.

### 3. Purpose of Processing
Telemetry is processed strictly to:
- Generate 1-page printable diagnostic reports and parent summaries.
- Pinpoint specific foundational gaps and recommend remedial practice.
- Facilitate blind, controlled evaluations via verified educators without disclosing parent contact details.

### 4. Zero Data Selling & Third-Party Non-Disclosure
We NEVER sell, rent, monetize, or share student data with advertisers, third-party data brokers, or unverified entities.

### 5. Storage & Row-Level Security
All data is stored in ISO 27001 / SOC-2 compliant data centers in India. Multi-tenant database access is guarded by strict PostgreSQL Row-Level Security (RLS) policies.
"""

REFUND_CONTENT = """# Cancellation and Refund Policy
**Last Updated:** November 9, 2026 | **Version:** 6.3.0  
**Compliance:** Consumer Protection (E-Commerce) Rules, 2020 & Razorpay Merchant Guidelines

### 1. 7-Day Money-Back Guarantee
If you are dissatisfied with your STUDIQS® SmartParent™ subscription within the first 7 calendar days of your initial purchase, you are entitled to a 100% full refund, no questions asked.

### 2. Cancellation of Active Subscriptions
- You may cancel your subscription at any time via the Parent Settings or Support Helpdesk.
- Upon cancellation, your paid entitlements remain active until the end of the current billing cycle. No further recurring charges will be incurred.

### 3. Marketplace Evaluation Cases
- If an expert fails to complete an assigned answer sheet evaluation within the committed 48-Hour SLA, the case escrow is automatically refunded 100% back to your original payment method.
- Parents may raise a dispute within 48 hours of evaluation delivery. While disputed, expert escrow payout is frozen until our academic audit team reviews the submission.

### 4. Refund Processing SLA
Approved refunds are processed via our payment gateway (Razorpay) within 24 hours and typically reflect in your bank account or UPI source within 5 to 7 business days.
"""

SHIPPING_CONTENT = """# Shipping and Delivery Policy
**Last Updated:** November 9, 2026 | **Version:** 6.3.0

### 1. Digital Services Delivery
STUDIQS® SmartParent™ provides purely digital software-as-a-service (SaaS) and academic telemetry products. No physical shipment is required or dispatched.

### 2. Instant Delivery Timeline
- **Subscription Activation:** Immediate upon successful Razorpay payment callback (< 3 seconds).
- **Academic Reports & Telemetry:** Instant on-demand generation and downloadable PDF.
- **Expert Evaluations:** Completed and delivered digitally within 48 hours of paper submission.
- **Invoices:** Formal GST Tax Invoices are instantly delivered via email and downloadable within the Parent Dashboard.
"""

CONTACT_CONTENT = """# Contact Us & Grievance Redressal
**Last Updated:** November 9, 2026 | **Compliance:** Information Technology Act, 2000 & IT Rules, 2021

### Corporate Office
**Studiqs AI Technologies Private Limited**  
CIN: U72900TN2026PTC123456  
Tamil Nadu, India.  
Website: https://studiqs.com  
Support Email: support@studiqs.com  
Toll-Free Support Line: +91 1800-STUDIQS (+91 1800-788-3477) (Mon-Sat, 9:00 AM - 8:00 PM IST)

### Statutory Grievance Redressal Officer
In accordance with the Information Technology Act 2000 and the DPDP Act 2023, the details of the Grievance Redressal Officer are as follows:

- **Name:** Mr. S. Vigneshwaran
- **Designation:** Head of Legal & Student Data Governance
- **Email:** grievance@studiqs.com
- **Direct Phone:** +91 94440-12345
- **Response SLA:** Acknowledgment within 24 hours; resolution within 15 working days.
"""


@router.get("/terms", response_model=LegalPolicyResponse, summary="Terms and Conditions")
def get_terms():
    return LegalPolicyResponse(policy_name="Terms and Conditions", content_markdown=TERMS_CONTENT)


@router.get("/privacy", response_model=LegalPolicyResponse, summary="Privacy Policy (DPDP Act 2023)")
def get_privacy():
    return LegalPolicyResponse(policy_name="Privacy Policy", content_markdown=PRIVACY_CONTENT)


@router.get("/refunds", response_model=LegalPolicyResponse, summary="Cancellation and Refund Policy")
def get_refunds():
    return LegalPolicyResponse(policy_name="Cancellation and Refund Policy", content_markdown=REFUND_CONTENT)


@router.get("/shipping", response_model=LegalPolicyResponse, summary="Shipping and Delivery Policy")
def get_shipping():
    return LegalPolicyResponse(policy_name="Shipping and Delivery Policy", content_markdown=SHIPPING_CONTENT)


@router.get("/contact", response_model=LegalPolicyResponse, summary="Contact Us & Grievance Officer")
def get_contact():
    return LegalPolicyResponse(policy_name="Contact Us & Grievance Redressal", content_markdown=CONTACT_CONTENT)


@router.get("/view/{policy_type}", response_class=HTMLResponse, summary="Render Public Policy as HTML")
def view_policy_html(policy_type: str):
    """Renders a clean, mobile-responsive HTML view for Razorpay verification and parent review."""
    mapping = {
        "terms": ("Terms and Conditions", TERMS_CONTENT),
        "privacy": ("Privacy Policy", PRIVACY_CONTENT),
        "refunds": ("Cancellation & Refund Policy", REFUND_CONTENT),
        "shipping": ("Shipping & Delivery Policy", SHIPPING_CONTENT),
        "contact": ("Contact Us & Grievance Redressal", CONTACT_CONTENT),
    }
    title, md = mapping.get(policy_type.lower(), ("Terms and Conditions", TERMS_CONTENT))
    html_body = md.replace("\n", "<br>").replace("### ", "<h3>").replace("## ", "<h2>").replace("# ", "<h1>")
    
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} — STUDIQS® SmartParent™</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #1e293b; max-width: 800px; margin: 0 auto; padding: 24px; }}
        h1 {{ color: #0f172a; border-bottom: 2px solid #e2e8f0; padding-bottom: 8px; }}
        h2, h3 {{ color: #1e293b; margin-top: 24px; }}
        .header {{ text-align: center; margin-bottom: 32px; padding: 16px; background: #f8fafc; border-radius: 8px; }}
        .footer {{ margin-top: 48px; padding-top: 16px; border-top: 1px solid #e2e8f0; font-size: 0.9em; color: #64748b; text-align: center; }}
    </style>
</head>
<body>
    <div class="header">
        <strong>STUDIQS® SmartParent™ Legal & Regulatory Portal</strong>
    </div>
    <div>{html_body}</div>
    <div class="footer">
        © 2026 Studiqs AI Technologies Pvt Ltd. All rights reserved. Registered under Indian Companies Act.
    </div>
</body>
</html>"""

