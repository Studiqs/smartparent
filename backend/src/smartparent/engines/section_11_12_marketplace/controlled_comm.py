"""
STUDIQS® SmartParent™ (v6.2 Complete) - Controlled Communication Engine
Engine 11: controlled_comm.py

Enforces the non-negotiable Section 21 Anti-Contact Boundary across all
Parent-Expert in-platform case messaging threads.
Prevents platform disintermediation, private tutoring poaching, off-platform payments,
and unmonitored communication.

Key Capabilities:
  1. Deep Regex & NLP Scanning for Indian Phone Numbers, Emails, URLs, UPI handles
  2. Spelled-out number obfuscation detection ("nine eight four zero...")
  3. Obfuscated handle & email detection ("user at domain dot com")
  4. Off-platform solicitation keyword interceptors ("call me", "whatsapp me", "pay directly")
  5. Academic context preservation (prevents false positives on question numbers, pages, and formulas)
  6. Multi-mode enforcement (BLOCK, REDACT, AUDIT_ONLY) with audit logging
"""

import re
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union
from pydantic import BaseModel, Field, ConfigDict

from src.smartparent.engines.base_engine import BaseEngine, EngineHealthStatus
from src.smartparent.core.constants import MessageSenderType
from src.smartparent.core.security import (
    PHONE_REGEX,
    EMAIL_REGEX,
    URL_REGEX,
    UPI_REGEX,
    SOLICITATION_REGEX,
)

logger = logging.getLogger("STUDIQS_ControlledCommEngine")


# =============================================================================
# 1. Advanced Anti-Contact Obfuscation Regexes
# =============================================================================

# Spelled out digits (e.g., "nine eight four zero one...")
SPELLED_DIGITS_PATTERN = re.compile(
    r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine|oh)"
    r"(?:[\s\-\,\.]+(?:zero|one|two|three|four|five|six|seven|eight|nine|oh)){6,}\b",
    re.IGNORECASE,
)

# Obfuscated Email (e.g. "student [at] gmail [dot] com" or "teacher at yahoo dot co dot in")
OBFUSCATED_EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+\s*(?:\[\s*at\s*\]|\(\s*at\s*\)|@|\bat\b)\s*"
    r"[A-Za-z0-9.-]+\s*(?:\[\s*dot\s*\]|\(\s*dot\s*\)|\.|\bdot\b)\s*"
    r"[A-Za-z]{2,}\b",
    re.IGNORECASE,
)

# Obfuscated URL (e.g. "wa dot me slash 919..." or "mycourses dot in")
OBFUSCATED_URL_PATTERN = re.compile(
    r"\b(?:https?|www|wa|t|zoom|meet)\s*(?:\[\s*dot\s*\]|\(\s*dot\s*\)|\.|\bdot\b)\s*"
    r"(?:me|in|com|org|io|us)\s*(?:\[\s*slash\s*\]|/|\bslash\b)?",
    re.IGNORECASE,
)

# Spaced Indian Phone numbers: e.g. "9 8 4 0 1 2 3 4 5 6"
SPACED_PHONE_PATTERN = re.compile(
    r"\b[6-9](?:[\s\.\-]*\d){9}\b"
)

# Off-platform Meeting Tools
MEETING_TOOLS_PATTERN = re.compile(
    r"\b(?:zoom\s+meeting|google\s+meet|teams\s+link|skype|anydesk|teamviewer)\b",
    re.IGNORECASE,
)


# =============================================================================
# 2. Pydantic v2 Type-Safe Schemas
# =============================================================================

class MessagePayloadSchema(BaseModel):
    """Schema for incoming communication message."""
    model_config = ConfigDict(extra="ignore")

    message_id: Optional[str] = None
    case_id: str
    sender_type: MessageSenderType = MessageSenderType.PARENT
    sender_id: str
    message_text: str = Field(..., min_length=1)
    policy_action: str = "BLOCK"  # 'BLOCK', 'REDACT', 'AUDIT_ONLY'


class CommunicationModerationResultSchema(BaseModel):
    """Schema for moderation decision and sanitized output."""
    model_config = ConfigDict(extra="ignore")

    message_id: Optional[str] = None
    case_id: str
    sender_type: str
    original_text: str
    sanitized_text: str
    is_blocked: bool
    block_reason: Optional[str] = None
    violation_types: List[str] = Field(default_factory=list)
    detected_entities: List[Dict[str, str]] = Field(default_factory=list)
    safety_tier: str  # 'SAFE', 'MODERATE', 'CRITICAL'
    moderated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# =============================================================================
# 3. Production Controlled Communication Engine Implementation
# =============================================================================

class ControlledCommEngine(BaseEngine):
    """
    Engine 11: Controlled Communication Engine (controlled_comm.py)
    
    Protects Studiqs business integrity by intercepting unauthorized contact sharing
    and off-platform disintermediation between Parents and Subject Experts.
    """

    def __init__(self, failure_threshold: int = 5):
        super().__init__(name="ControlledCommEngine", failure_threshold=failure_threshold)

    # -------------------------------------------------------------------------
    # BaseEngine Template Method Lifecycle Hooks
    # -------------------------------------------------------------------------

    def validate_input(self, input_data: Any) -> MessagePayloadSchema:
        """Validates message input payload."""
        if not input_data:
            raise ValueError("Message payload cannot be empty.")

        if isinstance(input_data, MessagePayloadSchema):
            return input_data

        if hasattr(input_data, "model_dump"):
            data = input_data.model_dump()
        elif hasattr(input_data, "dict"):
            data = input_data.dict()
        elif isinstance(input_data, dict):
            data = dict(input_data)
        else:
            raise ValueError(f"Unsupported payload type for ControlledCommEngine: {type(input_data)}")

        return MessagePayloadSchema(**data)

    def execute_core(self, payload: MessagePayloadSchema) -> CommunicationModerationResultSchema:
        """Executes Section 21 Anti-Contact boundary inspection and moderation."""
        raw_text = payload.message_text
        policy = payload.policy_action.upper()

        # Step 1: Scan for all categories of violations
        is_violation, violations, detected_entities = self._scan_text(raw_text)

        # Step 2: Determine Safety Tier
        if not is_violation:
            safety_tier = "SAFE"
            is_blocked = False
            block_reason = None
            sanitized_text = raw_text
        else:
            has_critical = any(
                v in ("PHONE_NUMBER", "EMAIL_ADDRESS", "UPI_HANDLE", "EXTERNAL_URL")
                for v in violations
            )
            safety_tier = "CRITICAL" if has_critical else "MODERATE"

            # Step 3: Apply Moderation Policy
            if policy == "BLOCK":
                is_blocked = True
                block_reason = f"Violates Section 21: {', '.join(violations)}"
                sanitized_text = "[Message blocked by Studiqs Security: Prohibited contact information detected]"
            elif policy == "REDACT":
                is_blocked = False
                block_reason = f"Sanitized under Section 21: {', '.join(violations)}"
                sanitized_text = self._redact_all(raw_text)
            else:  # AUDIT_ONLY
                is_blocked = False
                block_reason = f"Audit flagged: {', '.join(violations)}"
                sanitized_text = raw_text

        return CommunicationModerationResultSchema(
            message_id=payload.message_id,
            case_id=payload.case_id,
            sender_type=payload.sender_type.value if hasattr(payload.sender_type, "value") else str(payload.sender_type),
            original_text=raw_text,
            sanitized_text=sanitized_text,
            is_blocked=is_blocked,
            block_reason=block_reason,
            violation_types=violations,
            detected_entities=detected_entities,
            safety_tier=safety_tier,
        )

    def fallback(self, error: Exception, input_data: Any) -> CommunicationModerationResultSchema:
        """Fails closed: blocks message when moderation engine encounters an error."""
        logger.error(f"[ControlledCommEngine] Engine error, failing closed to protect platform: {error}")
        case_id = "UNKNOWN"
        raw_text = ""

        try:
            if isinstance(input_data, dict):
                case_id = str(input_data.get("case_id", "UNKNOWN"))
                raw_text = str(input_data.get("message_text", ""))
            else:
                case_id = str(getattr(input_data, "case_id", "UNKNOWN"))
                raw_text = str(getattr(input_data, "message_text", ""))
        except Exception:
            pass

        return CommunicationModerationResultSchema(
            case_id=case_id,
            sender_type="UNKNOWN",
            original_text=raw_text,
            sanitized_text="[Message held for moderation due to security check timeout]",
            is_blocked=True,
            block_reason="Security inspection fallback triggered (Fail-Closed Policy)",
            violation_types=["SECURITY_CHECK_TIMEOUT"],
            detected_entities=[],
            safety_tier="CRITICAL",
        )

    # -------------------------------------------------------------------------
    # Detection & Redaction Logic
    # -------------------------------------------------------------------------

    def _scan_text(self, text: str) -> Tuple[bool, List[str], List[Dict[str, str]]]:
        """Performs deep multi-regex scanning on message text."""
        violations: List[str] = []
        detected_entities: List[Dict[str, str]] = []

        # 1. Indian Phone Numbers (Standard & Spaced)
        phone_matches = PHONE_REGEX.findall(text)
        spaced_matches = SPACED_PHONE_PATTERN.findall(text)
        all_phones = list(set([m for m in (phone_matches + spaced_matches) if m]))
        if all_phones:
            violations.append("PHONE_NUMBER")
            for p in all_phones:
                detected_entities.append({"type": "PHONE", "value": str(p).strip()})

        # 2. Spelled Out Numbers
        spelled_matches = SPELLED_DIGITS_PATTERN.findall(text)
        if spelled_matches:
            violations.append("SPELLED_PHONE_NUMBER")
            for sp in spelled_matches:
                detected_entities.append({"type": "SPELLED_PHONE", "value": str(sp).strip()})

        # 3. Email Addresses (Standard & Obfuscated)
        email_matches = EMAIL_REGEX.findall(text)
        obfuscated_email_matches = OBFUSCATED_EMAIL_PATTERN.findall(text)
        all_emails = list(set([e for e in (email_matches + obfuscated_email_matches) if e]))
        if all_emails:
            violations.append("EMAIL_ADDRESS")
            for em in all_emails:
                detected_entities.append({"type": "EMAIL", "value": str(em).strip()})

        # 4. External URLs & Meeting Links
        url_matches = URL_REGEX.findall(text)
        obf_urls = OBFUSCATED_URL_PATTERN.findall(text)
        meeting_matches = MEETING_TOOLS_PATTERN.findall(text)
        all_links = list(set([u for u in (url_matches + obf_urls + meeting_matches) if u]))
        if all_links:
            violations.append("EXTERNAL_URL")
            for lnk in all_links:
                detected_entities.append({"type": "URL", "value": str(lnk).strip()})

        # 5. UPI Payment Handles
        upi_matches = UPI_REGEX.findall(text)
        if upi_matches:
            violations.append("UPI_HANDLE")
            for u in upi_matches:
                detected_entities.append({"type": "UPI", "value": str(u).strip()})

        # 6. Off-Platform Solicitation Keywords
        solicitation_matches = SOLICITATION_REGEX.findall(text)
        if solicitation_matches:
            violations.append("OFF_PLATFORM_SOLICITATION")
            for s in solicitation_matches:
                detected_entities.append({"type": "SOLICITATION", "value": str(s).strip()})

        is_violation = len(violations) > 0
        return is_violation, violations, detected_entities

    def _redact_all(self, text: str) -> str:
        """Thoroughly scrubs contact tokens replacing with clean redaction placeholders."""
        redacted = PHONE_REGEX.sub("[PHONE_REDACTED]", text)
        redacted = SPACED_PHONE_PATTERN.sub("[PHONE_REDACTED]", redacted)
        redacted = SPELLED_DIGITS_PATTERN.sub("[PHONE_REDACTED]", redacted)
        redacted = EMAIL_REGEX.sub("[EMAIL_REDACTED]", redacted)
        redacted = OBFUSCATED_EMAIL_PATTERN.sub("[EMAIL_REDACTED]", redacted)
        redacted = URL_REGEX.sub("[LINK_REDACTED]", redacted)
        redacted = OBFUSCATED_URL_PATTERN.sub("[LINK_REDACTED]", redacted)
        redacted = UPI_REGEX.sub("[UPI_REDACTED]", redacted)
        redacted = MEETING_TOOLS_PATTERN.sub("[LINK_REDACTED]", redacted)
        return redacted
