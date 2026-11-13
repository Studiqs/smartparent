"""
STUDIQS® SmartParent™ (v6.3 Complete) - DPDP Act 2023 & RBI E-Mandate Consent Audit Service
============================================================================================
Module: src.smartparent.services.payment_consent_service

Handles statutory legal consent verification and immutable audit logging:
  - Parent Terms of Service & Cancellation/Refund Policy
  - Minor Child Data Processing Consent (DPDP Act 2023 Section 9)
  - Unbundled Optional Auto-Renewal Recurring Mandate Authorization
  - Subject Expert Platform, Anti-Contact & 20% Commission Agreement
============================================================================================
"""

import hashlib
import logging
import uuid
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session

from src.smartparent.db.models.subscription import ConsentAuditLog
from src.smartparent.schemas.subscription import ConsentItemSchema

logger = logging.getLogger("STUDIQS_ConsentService")

# Canonical Policy Texts & Hashes (Version 1.0 - 12 Nov 2026)
POLICY_REGISTRY: Dict[str, Dict[str, str]] = {
    "TERMS_AND_REFUND": {
        "version": "v1.0-20261112",
        "text": (
            "I have read and agree to the Studiqs SmartParent Terms of Service and acknowledge the "
            "Privacy Notice and Refund/Cancellation Policy. I understand that Studiqs Intelligence LLP "
            "provides evidence-based academic analytics and outcomes are informational without grade guarantees."
        ),
    },
    "CHILD_DATA_DPDP": {
        "version": "v1.0-20261112",
        "text": (
            "As the lawful parent/legal guardian, I give affirmative consent under Section 9 of the Digital Personal "
            "Data Protection (DPDP) Act 2023 for Studiqs Intelligence LLP to process my minor child's educational, "
            "academic test marks, and diagnostic telemetry strictly for learning gap identification."
        ),
    },
    "AUTO_RENEWAL_MANDATE": {
        "version": "v1.0-20261112",
        "text": (
            "I authorize recurring charges of the displayed subscription amount at the stated interval until I cancel, "
            "subject to the mandate terms. I understand auto-renewal is optional and can be cancelled anytime under "
            "Profile > Subscription while retaining paid access until the current billing period ends."
        ),
    },
    "EXPERT_COMMISSION_AND_TERMS": {
        "version": "v1.0-20261112",
        "text": (
            "I accept the Expert Service, Confidentiality, Platform-only Communication and Commercial/Payout Terms, "
            "including the 20% Studiqs platform commission deducted from gross evaluation fees."
        ),
    },
}

# Pre-compute SHA-256 hashes
for k, v in POLICY_REGISTRY.items():
    v["hash"] = hashlib.sha256(v["text"].encode("utf-8")).hexdigest()


class PaymentConsentService:
    """Enterprise Legal Consent Management & Audit Service."""

    @staticmethod
    def get_policy_definitions() -> Dict[str, Dict[str, str]]:
        """Returns active policy versions, presented texts, and SHA-256 hashes."""
        return POLICY_REGISTRY

    @classmethod
    def record_consent(
        cls,
        db: Session,
        actor_id: uuid.UUID,
        actor_role: str,
        consent_type: str,
        policy_version: str,
        status: str = "ACCEPTED",
        child_id: Optional[uuid.UUID] = None,
        source_screen: str = "CHECKOUT_SCREEN",
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> ConsentAuditLog:
        """
        Persists an immutable affirmative consent or revocation event.
        """
        policy_meta = POLICY_REGISTRY.get(consent_type, {
            "version": policy_version,
            "text": f"Affirmative acknowledgment for {consent_type}",
            "hash": hashlib.sha256(consent_type.encode("utf-8")).hexdigest(),
        })

        entry = ConsentAuditLog(
            actor_id=actor_id,
            actor_role=actor_role,
            child_id=child_id,
            consent_type=consent_type,
            status=status,
            policy_version=policy_version or policy_meta.get("version", "v1.0-20261112"),
            policy_hash=policy_meta.get("hash", ""),
            presented_text=policy_meta.get("text", ""),
            source_screen=source_screen,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        logger.info(f"[ConsentService] Logged {status} for {consent_type} by {actor_role} {actor_id}")
        return entry

    @classmethod
    def validate_and_record_checkout_consents(
        cls,
        db: Session,
        subscriber_id: uuid.UUID,
        child_id: uuid.UUID,
        consents: List[ConsentItemSchema],
        opt_in_auto_renewal: bool = False,
        source_screen: str = "CHECKOUT_SCREEN",
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> bool:
        """
        Verifies that all mandatory consents are present and affirmatively accepted:
        1. TERMS_AND_REFUND (Mandatory)
        2. CHILD_DATA_DPDP (Mandatory for child profile)
        3. AUTO_RENEWAL_MANDATE (Mandatory only if opt_in_auto_renewal == True)
        """
        consent_map = {c.consent_type: c.accepted for c in consents}

        # 1. Mandatory Parent Terms & Refund Policy
        if not consent_map.get("TERMS_AND_REFUND"):
            raise ValueError("Affirmative acceptance of Terms of Service and Refund Policy is legally required.")

        # 2. Mandatory Minor Child Data Consent (DPDP Act 2023)
        if not consent_map.get("CHILD_DATA_DPDP"):
            raise ValueError("Guardian consent for minor child data processing under DPDP Act 2023 is mandatory.")

        # 3. Optional Auto-Renewal Mandate Consent
        if opt_in_auto_renewal and not consent_map.get("AUTO_RENEWAL_MANDATE"):
            raise ValueError("Explicit mandate authorization is required when opting in to Auto-Renewal.")

        # Record all affirmative consents
        for item in consents:
            if item.accepted:
                cls.record_consent(
                    db=db,
                    actor_id=subscriber_id,
                    actor_role="PARENT",
                    child_id=child_id if item.consent_type in ("CHILD_DATA_DPDP", "AUTO_RENEWAL_MANDATE") else None,
                    consent_type=item.consent_type,
                    policy_version=item.policy_version,
                    status="ACCEPTED",
                    source_screen=source_screen,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )

        return True


payment_consent_service = PaymentConsentService()

