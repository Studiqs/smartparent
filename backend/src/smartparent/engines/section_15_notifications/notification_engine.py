"""
STUDIQS® SmartParent™ (v6.2 & v6.3 Extension) - Notification & Engagement Engine
=============================================================================
Module: src.smartparent.engines.section_15_notifications.notification_engine
Section 15: Notifications, Monthly Parent Pulse and Engagement

Governs:
  1. Event Template Resolution: Maps all 20+ NotificationEventType constants to
     personalized, non-alarmist titles, messages, and actionable deep-links.
  2. Multi-Lingual Support: Generates bilingual templates (English & Tamil).
  3. Intelligent Priority & Urgency Scoring:
     - URGENT: Payment failure, Hard SLA breach, Subscription expiration lockout.
     - HIGH: Report compilation complete, Evaluation annotations ready, Topic recheck due.
     - NORMAL: Expert assigned, Under review, Ticket response received, Payment confirmed.
     - LOW: Background status pings & minor milestones.
  4. Anti-Spam Frequency Throttling:
     - Protects parents from notification fatigue with configurable cooldown deduplication.
  5. Multi-Channel Dispatch Preparation (In-App, Push/FCM, WhatsApp/SMS payloads).
=============================================================================
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union
from pydantic import BaseModel, Field, ConfigDict

from src.smartparent.engines.section_00_core.base_engine import BaseEngine
from src.smartparent.core.constants import NotificationEventType

logger = logging.getLogger("STUDIQS_NotificationEngine")


# =============================================================================
# 1. Pydantic v2 Type-Safe Schemas for Notification Engine
# =============================================================================

class NotificationPayloadInput(BaseModel):
    """Input payload for generating an in-app or push notification."""
    model_config = ConfigDict(extra="ignore")

    subscriber_id: str
    event_type: str
    child_id: Optional[str] = None
    title: Optional[str] = None
    message: Optional[str] = None
    action_url: Optional[str] = None
    action_label: Optional[str] = None
    priority: Optional[str] = None
    language: str = "en"  # "en" or "ta"
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None


class EnrichedNotificationResult(BaseModel):
    """Normalized, enriched notification ready for persistence and dispatch."""
    model_config = ConfigDict(extra="ignore")

    subscriber_id: str
    child_id: Optional[str] = None
    event_type: str
    title: str
    message: str
    action_url: Optional[str] = None
    action_label: Optional[str] = None
    priority: str = "NORMAL"  # 'LOW', 'NORMAL', 'HIGH', 'URGENT'
    icon_type: str = "SYSTEM" # 'REPORT', 'EXPERT', 'PAYMENT', 'SUPPORT', 'TOPIC', 'SYSTEM'
    payload_json: Dict[str, Any] = Field(default_factory=dict)
    is_throttled: bool = False
    throttle_reason: Optional[str] = None


# =============================================================================
# 2. Canonical Event Templates (English & Tamil)
# =============================================================================

EVENT_TEMPLATES: Dict[str, Dict[str, Dict[str, str]]] = {
    NotificationEventType.NEW_RESULT_PROCESSED.value: {
        "en": {
            "title": "New Assessment Processed for {student_name}",
            "message": "{subject} test marks and topic diagnostic have been calculated.",
            "action_label": "View Diagnostics",
            "action_url": "/diagnostic/{child_id}",
            "icon": "TOPIC",
            "priority": "NORMAL",
        },
        "ta": {
            "title": "{student_name}-ன் புதிய தேர்வு மதிப்பீடு தயாராக உள்ளது",
            "message": "{subject} பாடத்திற்கான மதிப்பெண்கள் மற்றும் தலைப்பு பகுப்பாய்வு கணக்கிடப்பட்டுள்ளது.",
            "action_label": "விவரங்களை பார்க்க",
            "action_url": "/diagnostic/{child_id}",
            "icon": "TOPIC",
            "priority": "NORMAL",
        },
    },
    NotificationEventType.REPORT_READY.value: {
        "en": {
            "title": "Monthly Parent Pulse Report Ready",
            "message": "{student_name}'s {report_month} learning cycle report is now available.",
            "action_label": "View Report",
            "action_url": "/reports/{child_id}/monthly",
            "icon": "REPORT",
            "priority": "HIGH",
        },
        "ta": {
            "title": "மாதாந்திர கற்றல் அறிக்கை தயாராக உள்ளது",
            "message": "{student_name}-ன் {report_month} மாதாந்திர அறிக்கை இப்போது பார்வைக்கு உள்ளது.",
            "action_label": "அறிக்கையை பார்க்க",
            "action_url": "/reports/{child_id}/monthly",
            "icon": "REPORT",
            "priority": "HIGH",
        },
    },
    NotificationEventType.PARENT_PULSE_READY.value: {
        "en": {
            "title": "Monthly Parent Pulse Ready",
            "message": "1 Improvement + 1 Watch Area + 1 Next Action synthesized for {student_name}.",
            "action_label": "View Parent Pulse",
            "action_url": "/pulse/{child_id}",
            "icon": "PULSE",
            "priority": "HIGH",
        },
        "ta": {
            "title": "மாதாந்திர பெற்றோர் துடிப்பு தயாராக உள்ளது",
            "message": "{student_name}-ன் 1 முன்னேற்றம் + 1 கவனிப்பு பகுதி + 1 அடுத்த செயல்முறை தயாராக உள்ளன.",
            "action_label": "துடிப்பை பார்க்க",
            "action_url": "/pulse/{child_id}",
            "icon": "PULSE",
            "priority": "HIGH",
        },
    },
    NotificationEventType.TOPIC_RECHECK_DUE.value: {
        "en": {
            "title": "Topic Recheck Due: {topic_name}",
            "message": "It has been 14 days since {student_name} diagnosed a gap in {subject}. Time for a quick 5-question check!",
            "action_label": "Start Recheck",
            "action_url": "/practice/{child_id}?topic={topic_id}",
            "icon": "TOPIC",
            "priority": "HIGH",
        },
        "ta": {
            "title": "மறு ஆய்வு தேவை: {topic_name}",
            "message": "{student_name} {subject} பாடத்தில் கற்றல் இடைவெளி கண்டறிந்து 14 நாட்கள் ஆயின. 5-வினா பயிற்சி செய்யவும்!",
            "action_label": "பயிற்சி செய்ய",
            "action_url": "/practice/{child_id}?topic={topic_id}",
            "icon": "TOPIC",
            "priority": "HIGH",
        },
    },
    NotificationEventType.EXPERT_ASSIGNED.value: {
        "en": {
            "title": "Subject Expert Assigned",
            "message": "{expert_name} has accepted {student_name}'s {subject} answer sheet for evaluation.",
            "action_label": "Track Case",
            "action_url": "/evaluations/{case_id}",
            "icon": "EXPERT",
            "priority": "NORMAL",
        },
        "ta": {
            "title": "பாட நிபுணர் நியமிக்கப்பட்டுள்ளார்",
            "message": "{expert_name} {student_name}-ன் {subject} விடைத்தாளை மதிப்பீடு செய்ய ஏற்றுக்கொண்டுள்ளார்.",
            "action_label": "நிலையை பார்க்க",
            "action_url": "/evaluations/{case_id}",
            "icon": "EXPERT",
            "priority": "NORMAL",
        },
    },
    NotificationEventType.EVALUATION_UNDER_REVIEW.value: {
        "en": {
            "title": "Paper Evaluation Under Review",
            "message": "Expert evaluation is underway. Step-by-step digital annotation is in progress.",
            "action_label": "View Progress",
            "action_url": "/evaluations/{case_id}",
            "icon": "EXPERT",
            "priority": "NORMAL",
        },
        "ta": {
            "title": "விடைத்தாள் மதிப்பீடு செய்யப்படுகிறது",
            "message": "படி வாரியாக விரிவான டிஜிட்டல் மதிப்பீடு நடைபெற்று வருகிறது.",
            "action_label": "நிலையை பார்க்க",
            "action_url": "/evaluations/{case_id}",
            "icon": "EXPERT",
            "priority": "NORMAL",
        },
    },
    NotificationEventType.EVALUATION_COMPLETED.value: {
        "en": {
            "title": "Evaluated Answer Sheet Ready!",
            "message": "Expert {expert_name} has finalized digital marking for {student_name}'s {subject} test.",
            "action_label": "View Annotations",
            "action_url": "/evaluations/{case_id}/pdf",
            "icon": "EXPERT",
            "priority": "HIGH",
        },
        "ta": {
            "title": "மதிப்பீடு செய்யப்பட்ட விடைத்தாள் தயார்!",
            "message": "நிபுணர் {expert_name} {student_name}-ன் {subject} விடைத்தாளை முழுமையாக மதிப்பீடு செய்துள்ளார்.",
            "action_label": "விடைத்தாளை பார்க்க",
            "action_url": "/evaluations/{case_id}/pdf",
            "icon": "EXPERT",
            "priority": "HIGH",
        },
    },
    NotificationEventType.ANSWER_SHEET_RECEIVED.value: {
        "en": {
            "title": "Answer Sheet Received",
            "message": "{student_name}'s handwritten answer sheet for {subject} has been received and queued for evaluation.",
            "action_label": "Track Status",
            "action_url": "/evaluations/{case_id}",
            "icon": "EXPERT",
            "priority": "NORMAL",
        },
        "ta": {
            "title": "விடைத்தாள் பெறப்பட்டது",
            "message": "{student_name}-ன் {subject} விடைத்தாள் பெறப்பட்டு மதிப்பீட்டு வரிசையில் சேர்க்கப்பட்டுள்ளது.",
            "action_label": "நிலையை பார்க்க",
            "action_url": "/evaluations/{case_id}",
            "icon": "EXPERT",
            "priority": "NORMAL",
        },
    },
    NotificationEventType.REVISION_REQUESTED.value: {
        "en": {
            "title": "Evaluation Revision Requested",
            "message": "A revision or clarification request has been submitted for {student_name}'s {subject} evaluation.",
            "action_label": "View Details",
            "action_url": "/evaluations/{case_id}",
            "icon": "EXPERT",
            "priority": "HIGH",
        },
        "ta": {
            "title": "மதிப்பீட்டு மறுஆய்வு கோரப்பட்டுள்ளது",
            "message": "{student_name}-ன் {subject} மதிப்பீட்டிற்கு மறுஆய்வு கோரிக்கை சமர்ப்பிக்கப்பட்டுள்ளது.",
            "action_label": "விவரங்களை பார்க்க",
            "action_url": "/evaluations/{case_id}",
            "icon": "EXPERT",
            "priority": "HIGH",
        },
    },
    NotificationEventType.PAYMENT_STATUS_UPDATE.value: {
        "en": {
            "title": "Payment Status: {status}",
            "message": "Your transaction for Rs. {amount} has been updated ({status}).",
            "action_label": "View Invoices",
            "action_url": "/subscription/invoices",
            "icon": "PAYMENT",
            "priority": "NORMAL",
        },
        "ta": {
            "title": "பரிவர்த்தனை நிலை: {status}",
            "message": "ரூ. {amount} பரிவர்த்தனை நிலை புதுப்பிக்கப்பட்டுள்ளது ({status}).",
            "action_label": "பரிவர்த்தனைகளை பார்க்க",
            "action_url": "/subscription/invoices",
            "icon": "PAYMENT",
            "priority": "NORMAL",
        },
    },
    NotificationEventType.TICKET_STATUS_UPDATE.value: {
        "en": {
            "title": "Support Ticket Status Updated",
            "message": "Your support ticket #{ticket_number} regarding {subject} status is now {status}.",
            "action_label": "View Ticket",
            "action_url": "/support/tickets/{ticket_id}",
            "icon": "SUPPORT",
            "priority": "NORMAL",
        },
        "ta": {
            "title": "உதவி கோரிக்கை நிலை புதுப்பிக்கப்பட்டது",
            "message": "உங்கள் உதவி கோரிக்கை #{ticket_number} நிலை இப்போது {status}.",
            "action_label": "கோரிக்கையை பார்க்க",
            "action_url": "/support/tickets/{ticket_id}",
            "icon": "SUPPORT",
            "priority": "NORMAL",
        },
    },
    NotificationEventType.SUBSCRIPTION_ACTIVATED.value: {
        "en": {
            "title": "Subscription Activated Successfully",
            "message": "Welcome to Studiqs SmartParent {plan_name} plan. All features are now unlocked.",
            "action_label": "Go to Dashboard",
            "action_url": "/dashboard",
            "icon": "PAYMENT",
            "priority": "NORMAL",
        },
        "ta": {
            "title": "சந்தா வெற்றிகரமாக செயல்படுத்தப்பட்டது",
            "message": "Studiqs SmartParent {plan_name} திட்டத்திற்கு நல்வரவு. அனைத்து வசதிகளும் திறக்கப்பட்டுள்ளன.",
            "action_label": "முகப்புக்கு செல்ல",
            "action_url": "/dashboard",
            "icon": "PAYMENT",
            "priority": "NORMAL",
        },
    },
    NotificationEventType.SUBSCRIPTION_EXPIRING_SOON.value: {
        "en": {
            "title": "Subscription Expiring in {days_left} Days",
            "message": "Your {plan_name} plan expires on {expiry_date}. Renew today to preserve student learning streaks.",
            "action_label": "Renew Plan",
            "action_url": "/subscription/renew",
            "icon": "PAYMENT",
            "priority": "HIGH",
        },
        "ta": {
            "title": "சந்தா இன்னும் {days_left} நாட்களில் முடிவடைகிறது",
            "message": "உங்கள் {plan_name} திட்டம் {expiry_date} அன்று முடிவடைகிறது. தொடர் பயன்பாட்டிற்கு புதுப்பிக்கவும்.",
            "action_label": "புதுப்பிக்க",
            "action_url": "/subscription/renew",
            "icon": "PAYMENT",
            "priority": "HIGH",
        },
    },
    NotificationEventType.SUBSCRIPTION_EXPIRED.value: {
        "en": {
            "title": "Subscription Expired",
            "message": "Your SmartParent subscription has ended. Student diagnostic history is safely preserved.",
            "action_label": "Reactivate Now",
            "action_url": "/subscription/catalog",
            "icon": "PAYMENT",
            "priority": "URGENT",
        },
        "ta": {
            "title": "சந்தா முடிவடைந்தது",
            "message": "உங்கள் SmartParent சந்தா காலம் முடிந்தது. மாணவர் தரவுகள் பாதுகாப்பாக சேமிக்கப்பட்டுள்ளன.",
            "action_label": "மீண்டும் செயல்படுத்த",
            "action_url": "/subscription/catalog",
            "icon": "PAYMENT",
            "priority": "URGENT",
        },
    },
    NotificationEventType.INVOICE_GENERATED.value: {
        "en": {
            "title": "Official GST Tax Invoice Generated",
            "message": "Tax Invoice {invoice_number} for Rs. {amount} is ready for download.",
            "action_label": "Download Invoice",
            "action_url": "/subscription/invoices",
            "icon": "PAYMENT",
            "priority": "NORMAL",
        },
        "ta": {
            "title": "GST வரி விலைப்பட்டியல் தயாராக உள்ளது",
            "message": "விலைப்பட்டியல் {invoice_number} (ரூ. {amount}) பதிவிறக்கத்திற்கு தயாராக உள்ளது.",
            "action_label": "பதிவிறக்க",
            "action_url": "/subscription/invoices",
            "icon": "PAYMENT",
            "priority": "NORMAL",
        },
    },
    NotificationEventType.PAYMENT_FAILED.value: {
        "en": {
            "title": "Payment Authorization Failed",
            "message": "Your transaction for Rs. {amount} was declined by the bank gateway. No amount was deducted.",
            "action_label": "Retry Payment",
            "action_url": "/subscription/checkout",
            "icon": "PAYMENT",
            "priority": "URGENT",
        },
        "ta": {
            "title": "பணம் செலுத்துதல் தோல்வியடைந்தது",
            "message": "ரூ. {amount} செலுத்தப்பட்ட பரிவர்த்தனை வங்கியால் நிராகரிக்கப்பட்டது.",
            "action_label": "மீண்டும் செலுத்த",
            "action_url": "/subscription/checkout",
            "icon": "PAYMENT",
            "priority": "URGENT",
        },
    },
    NotificationEventType.SUPPORT_TICKET_CREATED.value: {
        "en": {
            "title": "Support Ticket Received ({ticket_number})",
            "message": "Your inquiry regarding {subject} has been queued with 48-Hour Hard SLA guarantee.",
            "action_label": "View Ticket",
            "action_url": "/support/tickets/{ticket_id}",
            "icon": "SUPPORT",
            "priority": "NORMAL",
        },
        "ta": {
            "title": "உதவி கோரிக்கை பெறப்பட்டது ({ticket_number})",
            "message": "உங்கள் உதவி கோரிக்கை 48 மணிநேர உத்தரவாதத்துடன் பதிவு செய்யப்பட்டுள்ளது.",
            "action_label": "கோரிக்கையை பார்க்க",
            "action_url": "/support/tickets/{ticket_id}",
            "icon": "SUPPORT",
            "priority": "NORMAL",
        },
    },
    NotificationEventType.SUPPORT_TICKET_REPLIED.value: {
        "en": {
            "title": "Reply on Ticket {ticket_number}",
            "message": "Support Agent replied: \"{snippet}\"",
            "action_label": "Read Reply",
            "action_url": "/support/tickets/{ticket_id}",
            "icon": "SUPPORT",
            "priority": "NORMAL",
        },
        "ta": {
            "title": "உதவி கோரிக்கைக்கு பதில் வந்துள்ளது ({ticket_number})",
            "message": "உதவி அதிகாரி பதில் அளித்துள்ளார்: \"{snippet}\"",
            "action_label": "பதிலை படிக்க",
            "action_url": "/support/tickets/{ticket_id}",
            "icon": "SUPPORT",
            "priority": "NORMAL",
        },
    },
    NotificationEventType.SUPPORT_SLA_BREACHED.value: {
        "en": {
            "title": "Support Ticket Escalated to Senior Leadership",
            "message": "Ticket {ticket_number} exceeded 48-hour SLA deadline. Priority elevated to Highest Executive Queue.",
            "action_label": "View Status",
            "action_url": "/support/tickets/{ticket_id}",
            "icon": "SUPPORT",
            "priority": "URGENT",
        },
        "ta": {
            "title": "உதவி கோரிக்கை உயர் அதிகாரிகளுக்கு அனுப்பப்பட்டுள்ளது",
            "message": "கோரிக்கை {ticket_number} 48 மணிநேரத்திற்குள் தீர்க்கப்படாததால் உயர் நிலைக்கு உயர்த்தப்பட்டுள்ளது.",
            "action_label": "நிலையை பார்க்க",
            "action_url": "/support/tickets/{ticket_id}",
            "icon": "SUPPORT",
            "priority": "URGENT",
        },
    },
}


# =============================================================================
# 3. Notification & Engagement Engine Implementation
# =============================================================================

class NotificationEngine(BaseEngine):
    """
    Section 15 In-App Event Notifications & Engagement Engine.
    Enforces respectful frequency, deep-link resolution, multi-lingual templates,
    and priority categorization.
    """

    # Cooldown window in seconds for deduplicating identical event notifications
    DEFAULT_COOLDOWN_SECONDS: int = 1800  # 30 Minutes

    def __init__(self, failure_threshold: int = 5):
        super().__init__(name="NotificationEngine", failure_threshold=failure_threshold)
        self.logger = logger

    # -------------------------------------------------------------------------
    # BaseEngine Lifecycle Hooks
    # -------------------------------------------------------------------------

    def validate_input(self, input_data: Any) -> Dict[str, Any]:
        """Validates incoming notification creation payload."""
        if not isinstance(input_data, dict):
            raise ValueError("Input to NotificationEngine must be a dictionary")

        if not input_data.get("subscriber_id"):
            raise ValueError("subscriber_id is required for NotificationEngine")

        if not input_data.get("event_type"):
            raise ValueError("event_type is required for NotificationEngine")

        return input_data

    def execute_core(self, validated_data: Dict[str, Any]) -> EnrichedNotificationResult:
        """Enriches raw event parameters into production-grade notification."""
        payload = NotificationPayloadInput(**validated_data)
        return self.enrich_notification(payload)

    def fallback(self, error: Exception, input_data: Any) -> EnrichedNotificationResult:
        """Safe degraded fallback preventing service crash."""
        self.logger.warning("NotificationEngine fallback invoked: %s", error)
        sub_id = str(input_data.get("subscriber_id", "UNKNOWN")) if isinstance(input_data, dict) else "UNKNOWN"
        ev_type = str(input_data.get("event_type", "SYSTEM_ALERT")) if isinstance(input_data, dict) else "SYSTEM_ALERT"

        return EnrichedNotificationResult(
            subscriber_id=sub_id,
            child_id=input_data.get("child_id") if isinstance(input_data, dict) else None,
            event_type=ev_type,
            title="Notification Alert",
            message="A system update is available for your Studiqs SmartParent account.",
            action_url="/dashboard",
            action_label="Go to Dashboard",
            priority="NORMAL",
            icon_type="SYSTEM",
            payload_json=input_data if isinstance(input_data, dict) else {},
            is_throttled=False
        )

    # -------------------------------------------------------------------------
    # Core Domain Logic
    # -------------------------------------------------------------------------

    def enrich_notification(
        self,
        payload: NotificationPayloadInput
    ) -> EnrichedNotificationResult:
        """
        Enriches an event into an actionable, localized, deep-linked notification.
        """
        event_type = payload.event_type.upper()
        lang = payload.language.lower() if payload.language in ["en", "ta"] else "en"
        meta = payload.metadata or {}

        # Default fallbacks
        student_name = meta.get("student_name", "Student")
        subject = meta.get("subject", "Academic")
        report_month = meta.get("report_month", datetime.now(timezone.utc).strftime("%B %Y"))
        topic_name = meta.get("topic_name", "Curriculum Topic")
        topic_id = meta.get("topic_id", "")
        expert_name = meta.get("expert_name", "Subject Expert")
        case_id = meta.get("case_id", "")
        plan_name = meta.get("plan_name", "SmartParent")
        days_left = str(meta.get("days_left", "3"))
        expiry_date = meta.get("expiry_date", "soon")
        invoice_number = meta.get("invoice_number", "INV-STQ-001")
        amount = str(meta.get("amount", "0"))
        ticket_number = meta.get("ticket_number", "TKT-001")
        ticket_id = meta.get("ticket_id", "")
        snippet = str(meta.get("snippet", "Update on your inquiry"))[:60]

        # 1. Lookup Canonical Template
        template_entry = EVENT_TEMPLATES.get(event_type, {}).get(lang)
        if not template_entry:
            # Fallback to English template if Tamil is missing
            template_entry = EVENT_TEMPLATES.get(event_type, {}).get("en")

        if template_entry:
            # Format title & message with interpolations
            fmt_dict = {
                "student_name": student_name,
                "subject": subject,
                "report_month": report_month,
                "topic_name": topic_name,
                "topic_id": topic_id,
                "expert_name": expert_name,
                "case_id": case_id,
                "child_id": payload.child_id or "",
                "plan_name": plan_name,
                "days_left": days_left,
                "expiry_date": expiry_date,
                "invoice_number": invoice_number,
                "amount": amount,
                "ticket_number": ticket_number,
                "ticket_id": ticket_id,
                "snippet": snippet,
            }

            try:
                computed_title = template_entry["title"].format(**fmt_dict)
                computed_message = template_entry["message"].format(**fmt_dict)
                computed_action_label = template_entry.get("action_label")
                computed_action_url = template_entry.get("action_url", "").format(**fmt_dict)
            except Exception:
                computed_title = template_entry["title"]
                computed_message = template_entry["message"]
                computed_action_label = template_entry.get("action_label")
                computed_action_url = template_entry.get("action_url", "")

            computed_priority = template_entry.get("priority", "NORMAL")
            computed_icon = template_entry.get("icon", "SYSTEM")
        else:
            # Generic fallback
            computed_title = payload.title or f"Notification: {event_type.replace('_', ' ').title()}"
            computed_message = payload.message or "A new update is available in your Studiqs SmartParent portal."
            computed_action_label = payload.action_label or "View Details"
            computed_action_url = payload.action_url or "/dashboard"
            computed_priority = "NORMAL"
            computed_icon = "SYSTEM"

        # Explicit overrides from payload have top precedence
        final_title = payload.title or computed_title
        final_message = payload.message or computed_message
        final_action_url = payload.action_url or computed_action_url
        final_action_label = payload.action_label or computed_action_label
        final_priority = payload.priority or computed_priority

        # Enriched payload_json for front-end rendering
        enriched_payload = {
            **meta,
            "action_url": final_action_url,
            "action_label": final_action_label,
            "priority": final_priority,
            "icon_type": computed_icon,
            "language": lang,
        }

        return EnrichedNotificationResult(
            subscriber_id=payload.subscriber_id,
            child_id=payload.child_id,
            event_type=event_type,
            title=final_title,
            message=final_message,
            action_url=final_action_url,
            action_label=final_action_label,
            priority=final_priority,
            icon_type=computed_icon,
            payload_json=enriched_payload,
            is_throttled=False
        )

    @classmethod
    def evaluate_throttling(
        cls,
        event_type: str,
        last_sent_at: Optional[datetime],
        current_time: Optional[datetime] = None,
        custom_cooldown_seconds: Optional[int] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Anti-Spam Frequency Throttling Check:
        Returns: (is_throttled, reason)
        """
        if not last_sent_at:
            return False, None

        now = current_time or datetime.now(timezone.utc)
        if last_sent_at.tzinfo is None:
            last_sent_at = last_sent_at.replace(tzinfo=timezone.utc)

        cooldown = custom_cooldown_seconds or cls.DEFAULT_COOLDOWN_SECONDS
        elapsed = (now - last_sent_at).total_seconds()

        if elapsed < cooldown:
            remaining = int(cooldown - elapsed)
            return True, f"Throttled: identical event sent {int(elapsed)}s ago. Cooldown active for {remaining}s."

        return False, None
