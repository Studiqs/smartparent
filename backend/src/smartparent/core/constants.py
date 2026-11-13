"""
STUDIQS® SmartParent™ (v6.2 Complete) - Domain Constants & Core Enums
Incorporating 15-Page Core v6.1 Foundation & 3-Page v6.2 Addendum Overrides.

Single source of truth for:
- Pedagogical Mastery Tiers & Thresholds
- Subscription Entitlement Plans
- Tamil Language Exclusion Rule (Section 21)
- 14 Production Engine Operational Codes
- Marketplace Escrow & Commission Rules
- Pro Voice Assistant 6-Pillar Firewall
"""

from enum import StrEnum
from typing import Final, Tuple


# ==============================================================================
# 1. SUBSCRIPTION ENTITLEMENT PLANS
# ==============================================================================
class SubscriptionPlan(StrEnum):
    BASIC = "BASIC"          # ₹200/mo: Topic Intel (Classes 1-12), Marks Grid, 360, Reports
    ADVANCED = "ADVANCED"    # ₹400/mo: Basic + Priority Reports & Deep longitudinal insights
    PRO = "PRO"              # ₹600/mo: Full access including Pro Voice ("Ask Studiqs") Engine


# ==============================================================================
# 2. PEDAGOGICAL TOPIC MASTERY TIERS & THRESHOLDS (Section 18-20)
# ==============================================================================
class MasteryTier(StrEnum):
    STRONG = "STRONG"        # Score >= 80%
    AVERAGE = "AVERAGE"      # 60% <= Score < 80%
    WEAK = "WEAK"            # 40% <= Score < 60%
    CRITICAL = "CRITICAL"    # Score < 40%


# Mathematical Boundary Constants for Scoring Engines
MASTERY_STRONG_THRESHOLD: Final[float] = 80.0
MASTERY_AVERAGE_THRESHOLD: Final[float] = 60.0
MASTERY_WEAK_THRESHOLD: Final[float] = 40.0


def classify_mastery_tier(percentage: float) -> MasteryTier:
    """Deterministic mathematical tier assignment based on percentage marks."""
    if percentage >= MASTERY_STRONG_THRESHOLD:
        return MasteryTier.STRONG
    elif percentage >= MASTERY_AVERAGE_THRESHOLD:
        return MasteryTier.AVERAGE
    elif percentage >= MASTERY_WEAK_THRESHOLD:
        return MasteryTier.WEAK
    else:
        return MasteryTier.CRITICAL


# ==============================================================================
# 3. TOPIC GAP LIFECYCLE & RESOLUTION
# ==============================================================================
class GapStatus(StrEnum):
    ACTIVE = "ACTIVE"              # Persistent weak or critical learning topic
    IN_RECHECK = "IN_RECHECK"      # Diagnostic practice paper attempted, awaiting score
    RESOLVED = "RESOLVED"          # Recheck score >= 80% marks gap as resolved


GAP_RESOLUTION_THRESHOLD: Final[float] = 80.0


# ==============================================================================
# 4. MANDATORY CURRICULUM & SYLLABUS BOUNDARIES (Section 21)
# ==============================================================================
class Board(StrEnum):
    CBSE = "CBSE"
    TN_STATE_BOARD = "TN State Board"


class StreamId(StrEnum):
    BIO_MATHS = "BIO_MATHS"        # Physics, Chemistry, Biology, Mathematics
    CS_MATHS = "CS_MATHS"          # Physics, Chemistry, Mathematics, Computer Science
    COMMERCE = "COMMERCE"          # Accountancy, Business Studies, Economics, Mathematics/CA
    HUMANITIES = "HUMANITIES"      # History, Geography, Political Science, Economics


class SubjectGroup(StrEnum):
    CORE = "CORE"
    CORE_FOUR = "CORE_FOUR"        # Stream-specific 11-12 core subjects
    LANGUAGE = "LANGUAGE"
    EVS = "EVS"


# CRITICAL RULE (Section 21): Tamil language is strictly excluded from Topic Intelligence
EXCLUDED_SUBJECTS: Final[Tuple[str, ...]] = ("TAMIL",)
TAMIL_EXCLUSION_FILTER: Final[str] = "WHERE subject != 'TAMIL'"


# ==============================================================================
# 5. EVIDENCE INTAKE & DOCUMENT AI CODES
# ==============================================================================
class EvidenceType(StrEnum):
    EXCEL_MARKS_GRID = "EXCEL_MARKS_GRID"
    QUICK_MARKS = "QUICK_MARKS"
    UPLOAD_RESULT = "UPLOAD_RESULT"
    QUESTION_PAPER = "QUESTION_PAPER"
    REPEAT_EXAM = "REPEAT_EXAM"



class ScoringSource(StrEnum):
    PARENT_EXCEL_GRID = "PARENT_EXCEL_GRID"
    EXPERT_EVAL = "EXPERT_EVAL"


# ==============================================================================
# 6. LONGITUDINAL CONSISTENCY & TRENDS
# ==============================================================================
class ConsistencyDirection(StrEnum):
    IMPROVING = "IMPROVING"        # Positive trend slope (delta > +5%)
    STABLE = "STABLE"              # Score variance <= 5% across assessments
    DECLINING = "DECLINING"        # Negative trend slope (delta < -5%)
    VOLATILE = "VOLATILE"          # High variance / oscillating performance


# ==============================================================================
# 7. PARENT PULSE DIGEST SYNTHESIS (Section 19)
# ==============================================================================
class ParentPulseCategory(StrEnum):
    IMPROVEMENT = "IMPROVEMENT"    # Green: Exactly 1 top improved subject/topic
    WATCH_AREA = "WATCH_AREA"      # Amber: Exactly 1 primary area needing focus
    NEXT_ACTION = "NEXT_ACTION"    # Blue: Exactly 1 immediate actionable next step


# ==============================================================================
# 8. SUBJECT EXPERT MARKETPLACE & ANTI-CONTACT BOUNDARY (Section 21-22)
# ==============================================================================
class CaseStatus(StrEnum):
    ASSIGNED = "ASSIGNED"                  # Case created & matched with expert
    AWAITING_UPLOAD = "AWAITING_UPLOAD"    # Awaiting answer-sheet PDF upload
    SUBMITTED = "SUBMITTED"                # Uploaded and queued for expert review
    UNDER_REVIEW = "UNDER_REVIEW"          # Expert actively grading in Studio
    COMPLETED = "COMPLETED"                # Evaluation finalized, PDF delivered
    DISPUTED = "DISPUTED"                  # Parent opened review challenge within 48h


class MessageSenderType(StrEnum):
    PARENT = "PARENT"
    EXPERT = "EXPERT"
    SYSTEM = "SYSTEM"


class KycStatus(StrEnum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


class PaymentStatus(StrEnum):
    CREATED = "CREATED"
    PAID = "PAID"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


class PayoutStatus(StrEnum):
    HELD = "HELD"                          # Escrow held during review + 48h dispute window
    APPROVED = "APPROVED"                  # Released post 48h window
    DISBURSED = "DISBURSED"                # Transferred to expert bank account


# Commercial Split Standards
PLATFORM_COMMISSION_PERCENT: Final[float] = 20.0  # 20% Studiqs Platform Commission
EXPERT_NET_PAYOUT_PERCENT: Final[float] = 80.0    # 80% Expert Net Payout
ESCROW_DISPUTE_WINDOW_HOURS: Final[int] = 48      # 48-hour post-completion dispute lock


# ==============================================================================
# 9. PRO VOICE ASSISTANT ("ASK STUDIQS") FIREWALL (Section 22)
# ==============================================================================
class VoicePillar(StrEnum):
    OVERALL_ACADEMIC_STANDING = "OVERALL_ACADEMIC_STANDING"  # 1. Student 360 summary
    SUBJECT_PERFORMANCE = "SUBJECT_PERFORMANCE"              # 2. Latest subject score & delta
    GRANULAR_TOPIC_GAPS = "GRANULAR_TOPIC_GAPS"              # 3. Line-item weak/critical gaps
    MONTH_ON_MONTH_TRENDS = "MONTH_ON_MONTH_TRENDS"          # 4. Trajectory delta
    TERM_CONSISTENCY = "TERM_CONSISTENCY"                    # 5. Stability & performance curve
    NEXT_GAP_RECHECK_ACTION = "NEXT_GAP_RECHECK_ACTION"      # 6. Prioritized recheck paper


VOICE_MAX_TURNAROUND_MS: Final[int] = 350
VOICE_READONLY_ROLE: Final[str] = "studiqs_voice_readonly"
VOICE_MUTATION_BLOCK_MESSAGE: Final[str] = (
    "High-risk account actions cannot be executed via voice. "
    "Please use the dashboard directly."
)


# ==============================================================================
# 10. CONSOLIDATED REPORT LIFECYCLE (Section 4)
# ==============================================================================
class ReportType(StrEnum):
    MONTHLY = "MONTHLY"
    TERM = "TERM"
    YEARLY = "YEARLY"


# ==============================================================================
# 11. SUBSCRIPTION USAGE QUOTAS & LIMITS (Section 10)
# ==============================================================================
PLAN_UPLOAD_LIMITS: Final[dict[str, int]] = {
    "BASIC": 4,
    "ADVANCED": 12,
    "PRO": 30,
}

PLAN_RECHECK_LIMITS: Final[dict[str, int]] = {
    "BASIC": 1,
    "ADVANCED": 3,
    "PRO": 6,
}

PLAN_DIAGNOSTIC_LIMITS: Final[dict[str, int]] = {
    "BASIC": 1,
    "ADVANCED": 3,
    "PRO": 6,
}

PLAN_ACTIVE_EXPERT_CASE_LIMITS: Final[dict[str, int]] = {
    "BASIC": 1,
    "ADVANCED": 3,
    "PRO": 6,
}


# ==============================================================================
# 12. HELP CENTRE & DISPUTE TICKETING (Section 14 - v6.2 Marketplace Disputes)
# ==============================================================================
class TicketType(StrEnum):
    """v6.2 Marketplace-specific ticket types (Section 14). Retained for backward compat."""
    PAYMENT_ISSUE = "PAYMENT_ISSUE"
    EXPERT_DELAY = "EXPERT_DELAY"
    WRONG_FILE = "WRONG_FILE"
    CORRECTION_DISPUTE = "CORRECTION_DISPUTE"
    REFUND_REASSIGNMENT = "REFUND_REASSIGNMENT"
    GENERAL_SUPPORT = "GENERAL_SUPPORT"


class TicketStatus(StrEnum):
    """v6.3 Expanded ticket lifecycle states (Section 27)."""
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    AWAITING_CUSTOMER = "AWAITING_CUSTOMER"  # v6.3: Support requested info from parent
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"
    REOPENED = "REOPENED"                    # v6.3: Parent reports issue persists


# ==============================================================================
# 13. IN-APP EVENT NOTIFICATIONS (Section 15 + v6.3 Extensions)
# ==============================================================================
class NotificationEventType(StrEnum):
    # v6.2 Original Events
    NEW_RESULT_PROCESSED = "NEW_RESULT_PROCESSED"
    REPORT_READY = "REPORT_READY"
    PARENT_PULSE_READY = "PARENT_PULSE_READY"
    TOPIC_RECHECK_DUE = "TOPIC_RECHECK_DUE"
    EXPERT_ASSIGNED = "EXPERT_ASSIGNED"
    ANSWER_SHEET_RECEIVED = "ANSWER_SHEET_RECEIVED"
    EVALUATION_UNDER_REVIEW = "EVALUATION_UNDER_REVIEW"
    EVALUATION_COMPLETED = "EVALUATION_COMPLETED"
    REVISION_REQUESTED = "REVISION_REQUESTED"
    PAYMENT_STATUS_UPDATE = "PAYMENT_STATUS_UPDATE"
    TICKET_STATUS_UPDATE = "TICKET_STATUS_UPDATE"
    # v6.3 Subscription & Billing Events (Section 24)
    SUBSCRIPTION_ACTIVATED = "SUBSCRIPTION_ACTIVATED"
    SUBSCRIPTION_EXPIRING_SOON = "SUBSCRIPTION_EXPIRING_SOON"
    SUBSCRIPTION_EXPIRED = "SUBSCRIPTION_EXPIRED"
    SUBSCRIPTION_RENEWED = "SUBSCRIPTION_RENEWED"
    SUBSCRIPTION_CANCELLED = "SUBSCRIPTION_CANCELLED"
    INVOICE_GENERATED = "INVOICE_GENERATED"
    PAYMENT_RECEIVED = "PAYMENT_RECEIVED"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    REFUND_PROCESSED = "REFUND_PROCESSED"
    # v6.3 Support SLA Events (Section 27)
    SUPPORT_TICKET_CREATED = "SUPPORT_TICKET_CREATED"
    SUPPORT_TICKET_ASSIGNED = "SUPPORT_TICKET_ASSIGNED"
    SUPPORT_TICKET_REPLIED = "SUPPORT_TICKET_REPLIED"
    SUPPORT_SLA_WARNING = "SUPPORT_SLA_WARNING"
    SUPPORT_SLA_BREACHED = "SUPPORT_SLA_BREACHED"


# ==============================================================================
# 14. BOARD & FUTURE READINESS (Section 8)
# ==============================================================================
class ReadinessTier(StrEnum):
    HIGH = "HIGH"
    MODERATE = "MODERATE"
    LOW = "LOW"


# ==============================================================================
# 15. SUBSCRIPTION & BILLING MANAGEMENT (Section 24 - v6.3)
# ==============================================================================
class SubscriptionStatus(StrEnum):
    """Netflix-style subscription lifecycle states."""
    PENDING_PAYMENT = "PENDING_PAYMENT"    # Order created, awaiting Razorpay payment
    ACTIVE = "ACTIVE"                      # Paid and within validity period
    EXPIRING_SOON = "EXPIRING_SOON"        # Within 7 days of expiry
    EXPIRED = "EXPIRED"                    # Past expiry, paid features locked
    CANCELLED = "CANCELLED"                # Voluntary cancellation by parent
    PAST_DUE = "PAST_DUE"                 # Auto-renewal payment failed


class BillingInterval(StrEnum):
    """Subscription duration/billing interval options."""
    MONTHLY = "MONTHLY"            # 1 month
    QUARTERLY = "QUARTERLY"        # 3 months
    HALF_YEARLY = "HALF_YEARLY"    # 6 months
    ANNUAL = "ANNUAL"              # 12 months


BILLING_INTERVAL_MONTHS: Final[dict[str, int]] = {
    "MONTHLY": 1,
    "QUARTERLY": 3,
    "HALF_YEARLY": 6,
    "ANNUAL": 12,
}


class InvoicePaymentStatus(StrEnum):
    """Invoice payment lifecycle states."""
    PENDING = "PENDING"
    PAID = "PAID"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"


# GST Rate Constants (India)
GST_TOTAL_RATE: Final[float] = 18.0      # Total GST rate
GST_CGST_RATE: Final[float] = 9.0        # Central GST (intra-state)
GST_SGST_RATE: Final[float] = 9.0        # State GST (intra-state)
GST_IGST_RATE: Final[float] = 18.0       # Integrated GST (inter-state)


# ==============================================================================
# 16. SUPPORT CENTRE CATEGORIES & SLA (Section 27 - v6.3)
# ==============================================================================
class SupportTicketCategory(StrEnum):
    """v6.3 Support ticket categories (Section 27)."""
    LOGIN_ACCOUNT = "LOGIN_ACCOUNT"
    BILLING_REFUND = "BILLING_REFUND"
    STUDENT_PROFILE = "STUDENT_PROFILE"
    MARKS_ENTRY = "MARKS_ENTRY"
    TOPIC_INTELLIGENCE = "TOPIC_INTELLIGENCE"
    REPORT_PDF = "REPORT_PDF"
    AI_VOICE = "AI_VOICE"
    BUG_REPORT = "BUG_REPORT"
    GUIDANCE = "GUIDANCE"


class SupportTicketPriority(StrEnum):
    """Support ticket priority levels."""
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"


class SupportSenderRole(StrEnum):
    """Message sender role in support thread."""
    PARENT = "PARENT"
    SUPPORT_AGENT = "SUPPORT_AGENT"
    ADMIN = "ADMIN"
    SYSTEM = "SYSTEM"


class SLAEscalationLevel(StrEnum):
    """48-Hour SLA automated escalation milestones."""
    FIRST_RESPONSE_12H = "FIRST_RESPONSE_12H"    # No first response in 12 hours
    REMINDER_24H = "REMINDER_24H"                  # Internal reminder at 24 hours
    LEAD_ALERT_36H = "LEAD_ALERT_36H"              # Support lead alert at 36 hours
    SLA_BREACHED_48H = "SLA_BREACHED_48H"          # SLA Breached — overdue > 48 hours


# SLA Timing Constants (in hours)
SUPPORT_SLA_TOTAL_HOURS: Final[int] = 48
SUPPORT_SLA_FIRST_RESPONSE_HOURS: Final[int] = 12
SUPPORT_SLA_REMINDER_HOURS: Final[int] = 24
SUPPORT_SLA_LEAD_ALERT_HOURS: Final[int] = 36


# ==============================================================================
# 17. RENEWAL REMINDER TYPES (Section 24 - v6.3)
# ==============================================================================
class RenewalReminderType(StrEnum):
    """Automated subscription expiry reminder schedule."""
    REMINDER_7_DAYS = "REMINDER_7_DAYS"
    REMINDER_3_DAYS = "REMINDER_3_DAYS"
    REMINDER_1_DAY = "REMINDER_1_DAY"
    EXPIRED_NOTICE = "EXPIRED_NOTICE"


# ==============================================================================
# 18. TUTORIAL VIDEO CATEGORIES (Section 26 - v6.3)
# ==============================================================================
class TutorialCategory(StrEnum):
    """Tutorial video categorization for UI grouping."""
    ONBOARDING = "ONBOARDING"
    ACADEMIC = "ACADEMIC"
    SUBSCRIPTION = "SUBSCRIPTION"
    SUPPORT = "SUPPORT"
    PRO_FEATURES = "PRO_FEATURES"


# ==============================================================================
# 19. RAZORPAY WEBHOOK EVENT TYPES (Section 24 - v6.3)
# ==============================================================================
class RazorpayEventType(StrEnum):
    """Razorpay webhook event types we process."""
    PAYMENT_CAPTURED = "payment.captured"
    PAYMENT_FAILED = "payment.failed"
    SUBSCRIPTION_CHARGED = "subscription.charged"
    SUBSCRIPTION_CANCELLED = "subscription.cancelled"
    REFUND_PROCESSED = "refund.processed"

