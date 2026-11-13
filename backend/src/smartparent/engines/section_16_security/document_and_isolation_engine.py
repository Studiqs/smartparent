"""
STUDIQS® SmartParent™ (v6.2 Complete) - Document Handling & Security Isolation Engine
=============================================================================
Module: src.smartparent.engines.section_16_security.document_and_isolation_engine
Section 16: Backend, Subscriber/Expert Isolation, Security, Retention & Document Handling

Implements:
1. Cryptographically signed, expiring URLs (HMAC-SHA256, 15-min default TTL)
2. Private cloud storage path isolation (S3/GCS prefix enforcement)
3. Role field leakage scrubbers (Expert view vs Subscriber view)
4. AI context isolation boundaries (Zero cross-tenant leakage in prompts)
5. Report Retention Lifecycle (Current year all active, prior years retain only finalized Yearly Report)
6. Evaluation Statutory Retention Lifecycle (7-year financial audit ledger)
=============================================================================
"""

import hmac
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from src.smartparent.engines.section_00_core.base_engine import BaseEngine
from src.smartparent.schemas.security_isolation import (
    SignedUrlScopeEnum,
    SignedUrlResponse,
    VerifySignedUrlResponse,
    SanitizedExpertCaseView,
    SanitizedSubscriberExpertProfile,
    ReportRetentionAuditItemSchema,
    ReportRetentionAuditResponse,
    EvaluationRetentionAuditResponse,
)

logger = logging.getLogger("STUDIQS_DocumentAndIsolationEngine")

DEFAULT_SECRET_KEY = "studiqs_smartparent_secure_signing_hmac_secret_2026_production"


class DocumentAndIsolationEngine(BaseEngine):
    """
    Production Engine for Section 16 Security, Multi-Tenant Isolation & Document Retention.
    """

    def __init__(self, secret_key: Optional[str] = None):
        super().__init__(name="DocumentAndIsolationEngine")
        self.secret_key = (secret_key or DEFAULT_SECRET_KEY).encode("utf-8")

    def validate_input(self, input_data: Any) -> Any:
        """Validates generic engine input."""
        return input_data or {}

    def execute_core(self, validated_data: Any) -> Any:
        """BaseEngine core execution hook."""
        action = validated_data.get("action", "HEALTH_PING") if isinstance(validated_data, dict) else "HEALTH_PING"
        return {"action": action, "status": "executed", "timestamp": datetime.now(timezone.utc).isoformat()}

    def fallback(self, error: Exception, input_data: Any) -> Any:
        """Degraded safe fallback."""
        logger.error(f"[DocumentAndIsolationEngine] Execution failure: {error}")
        act = input_data.get("action") if isinstance(input_data, dict) else None
        return {"action": act, "status": "fallback_degraded", "error": str(error)}

    # =========================================================================
    # 1. SIGNED EXPIRING URL MANAGEMENT (HMAC-SHA256)
    # =========================================================================

    def generate_signed_url(
        self,
        resource_path: str,
        scope: SignedUrlScopeEnum,
        expires_in_seconds: int = 900,
        base_domain: str = "https://storage.studiqs.com",
    ) -> SignedUrlResponse:
        """
        Generates a cryptographically signed, expiring URL for private object access.
        Default TTL: 900s (15 minutes).
        """
        # Validate path safety
        clean_path = self.normalize_storage_path(resource_path)
        expires_at_dt = datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)
        expires_at_str = str(int(expires_at_dt.timestamp()))

        signature = self._compute_signature(clean_path, expires_at_str, scope.value)
        signed_url = f"{base_domain}/{clean_path}?scope={scope.value}&expires={expires_at_str}&signature={signature}"

        return SignedUrlResponse(
            resource_path=clean_path,
            signed_url=signed_url,
            signature=signature,
            expires_at=expires_at_dt.isoformat(),
            scope=scope.value,
            ttl_seconds=expires_in_seconds,
        )

    def verify_signed_url(
        self,
        resource_path: str,
        signature: str,
        expires_at: str,
        scope: str,
    ) -> VerifySignedUrlResponse:
        """
        Verifies signature integrity and expiration status.
        Rejects tampered, altered, or expired tokens.
        """
        clean_path = self.normalize_storage_path(resource_path)

        # 1. Parse and check expiration
        try:
            if "T" in expires_at:
                exp_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                exp_ts = int(exp_dt.timestamp())
            else:
                exp_ts = int(expires_at)
        except Exception:
            return VerifySignedUrlResponse(
                is_valid=False,
                reason="Invalid expiration timestamp format.",
                resource_path=clean_path,
                scope=scope,
            )

        now_ts = int(datetime.now(timezone.utc).timestamp())
        if now_ts > exp_ts:
            return VerifySignedUrlResponse(
                is_valid=False,
                reason="Signed URL has expired. Request a fresh download URL.",
                resource_path=clean_path,
                scope=scope,
            )

        # 2. Check cryptographic signature
        expected_sig = self._compute_signature(clean_path, str(exp_ts), scope)
        if not hmac.compare_digest(signature, expected_sig):
            return VerifySignedUrlResponse(
                is_valid=False,
                reason="Cryptographic signature mismatch. Token is forged or tampered.",
                resource_path=clean_path,
                scope=scope,
            )

        return VerifySignedUrlResponse(
            is_valid=True,
            reason=None,
            resource_path=clean_path,
            scope=scope,
        )

    def _compute_signature(self, path: str, expires_ts: str, scope: str) -> str:
        """Computes HMAC-SHA256 signature for resource string."""
        message = f"{path}|{expires_ts}|{scope}".encode("utf-8")
        return hmac.new(self.secret_key, message, hashlib.sha256).hexdigest()

    def normalize_storage_path(self, path: str) -> str:
        """Sanitizes and enforces strict path boundaries (prevents directory traversal)."""
        clean = path.strip().replace("\\", "/").lstrip("/")
        if ".." in clean or "//" in clean:
            raise ValueError(f"Path traversal attempt detected in storage path: {path}")
        return clean

    # =========================================================================
    # 2. STORAGE PATH ISOLATION BUILDERS
    # =========================================================================

    def build_family_evidence_path(self, subscriber_id: str, child_id: str, record_id: str, filename: str) -> str:
        """Constructs private storage path for family evidence."""
        return f"private/tenants/{subscriber_id}/children/{child_id}/evidence/{record_id}/{filename}"

    def build_report_path(self, subscriber_id: str, child_id: str, report_type: str, period_key: str) -> str:
        """Constructs private storage path for consolidated reports."""
        return f"private/tenants/{subscriber_id}/children/{child_id}/reports/{report_type.lower()}_{period_key}.pdf"

    def build_evaluation_path(self, evaluation_id: str, folder_type: str, filename: str) -> str:
        """Constructs case-scoped storage path for expert evaluation artifacts."""
        return f"private/evaluations/{evaluation_id}/{folder_type}/{filename}"

    # =========================================================================
    # 3. CROSS-BOUNDARY ROLE FIELD LEAKAGE SCRUBBERS
    # =========================================================================

    def sanitize_expert_case_view(self, case_dict: Dict[str, Any]) -> SanitizedExpertCaseView:
        """
        Strips all parent contact info, phone numbers, email addresses, billing,
        family history, and sibling data from the expert's view.
        """
        raw_name = case_dict.get("student_name", "Student")
        # Extract alias/first name only
        student_alias = raw_name.split()[0] if raw_name else "Student"

        return SanitizedExpertCaseView(
            evaluation_id=str(case_dict.get("evaluation_id", "")),
            student_alias=student_alias,
            standard_class=case_dict.get("standard_class", ""),
            board=case_dict.get("board", ""),
            subject=case_dict.get("subject", ""),
            status=case_dict.get("status", "ASSIGNED"),
            assigned_question_set_url=case_dict.get("assigned_question_set_url"),
            submitted_answer_sheet_url=case_dict.get("submitted_answer_sheet_url"),
            corrected_copy_url=case_dict.get("corrected_copy_url"),
            total_max_marks=float(case_dict.get("total_max_marks", 100.0)),
            turnaround_deadline=str(case_dict.get("turnaround_deadline")) if case_dict.get("turnaround_deadline") else None,
            parent_contact_masked=True,
            family_history_masked=True,
            sibling_data_masked=True,
        )

    def sanitize_subscriber_expert_profile(self, expert_dict: Dict[str, Any]) -> SanitizedSubscriberExpertProfile:
        """
        Strips expert KYC, bank details, payouts, commission %, and internal queue
        from the subscriber's view.
        """
        return SanitizedSubscriberExpertProfile(
            expert_id=str(expert_dict.get("expert_id", "")),
            display_name=expert_dict.get("display_name", expert_dict.get("name", "Verified Expert")),
            photo_url=expert_dict.get("photo_url"),
            subjects=expert_dict.get("subjects", []),
            boards=expert_dict.get("boards", []),
            classes=expert_dict.get("classes", []),
            qualifications=expert_dict.get("qualifications", "Certified Board Educator"),
            experience_years=int(expert_dict.get("experience_years", 5)),
            average_rating=float(expert_dict.get("average_rating", 5.0)),
            total_reviews_count=int(expert_dict.get("total_reviews_count", 0)),
            turnaround_hours=int(expert_dict.get("turnaround_hours", 48)),
            evaluation_fee_inr=float(expert_dict.get("evaluation_fee_inr", 500.0)),
            bank_payout_details_masked=True,
            kyc_identity_masked=True,
            commission_percentage_masked=True,
        )

    # =========================================================================
    # 4. AI CONTEXT ISOLATION BOUNDARY GUARD
    # =========================================================================

    def assert_isolated_ai_context(
        self,
        expected_subscriber_id: str,
        expected_child_id: str,
        evidence_items: List[Dict[str, Any]],
        expected_case_id: Optional[str] = None,
    ) -> None:
        """
        Verifies that every single item fed into an AI context prompt belongs
        strictly to the authenticated child/subscriber. Raises PermissionError on leakage.
        """
        for idx, item in enumerate(evidence_items):
            item_sub = str(item.get("subscriber_id", ""))
            item_child = str(item.get("child_id", ""))
            item_case = str(item.get("evaluation_id", item.get("case_id", "")))

            if item_sub and item_sub != expected_subscriber_id:
                raise PermissionError(
                    f"[AI Context Guard] Cross-tenant violation: item {idx} has foreign subscriber_id {item_sub}"
                )
            if item_child and item_child != expected_child_id:
                raise PermissionError(
                    f"[AI Context Guard] Cross-child violation: item {idx} has foreign child_id {item_child}"
                )
            if expected_case_id and item_case and item_case != expected_case_id:
                raise PermissionError(
                    f"[AI Context Guard] Cross-case violation: item {idx} has foreign case_id {item_case}"
                )

    # =========================================================================
    # 5. REPORT RETENTION LIFECYCLE EVALUATION
    # =========================================================================

    def audit_report_retention(
        self,
        child_id: str,
        current_academic_year: str,
        raw_reports: List[Dict[str, Any]],
    ) -> ReportRetentionAuditResponse:
        """
        Enforces Section 16 report retention rules:
        - Current Academic Year: All monthly, term, and yearly reports remain ACTIVE.
        - Previous Academic Years: Intermediate monthly & term reports are RETIRED;
          ONLY the finalized Yearly Consolidated Report is retained in permanent report history.
        """
        items: List[ReportRetentionAuditItemSchema] = []
        active_count = 0
        permanent_archives_count = 0
        retired_count = 0

        for r in raw_reports:
            r_id = str(r.get("report_id", ""))
            r_type = str(r.get("report_type", "MONTHLY")).upper()
            r_ay = str(r.get("academic_year", current_academic_year))
            period = str(r.get("period_key", ""))
            pdf_path = r.get("pdf_storage_path")

            if r_ay == current_academic_year:
                status = "ACTIVE_CURRENT_YEAR"
                accessible = True
                active_count += 1
            else:
                if r_type == "YEARLY":
                    status = "PERMANENT_HISTORICAL_ARCHIVE"
                    accessible = True
                    permanent_archives_count += 1
                else:
                    status = "RETIRED_INTERMEDIATE_DRAFT"
                    accessible = False
                    retired_count += 1

            items.append(
                ReportRetentionAuditItemSchema(
                    report_id=r_id,
                    report_type=r_type,
                    academic_year=r_ay,
                    period_key=period,
                    retention_status=status,
                    is_accessible_to_parent=accessible,
                    pdf_storage_path=pdf_path if accessible else None,
                )
            )

        return ReportRetentionAuditResponse(
            child_id=child_id,
            current_academic_year=current_academic_year,
            total_reports_found=len(raw_reports),
            active_current_year_reports_count=active_count,
            permanent_historical_archives_count=permanent_archives_count,
            retired_intermediate_drafts_count=retired_count,
            reports=items,
        )

    # =========================================================================
    # 6. EVALUATION STATUTORY RETENTION EVALUATION
    # =========================================================================

    def audit_evaluation_retention(
        self,
        evaluation_id: str,
        academic_year: str,
        completed_at_iso: Optional[str] = None,
        dispute_window_days: int = 90,
    ) -> EvaluationRetentionAuditResponse:
        """
        Enforces Section 16 evaluation retention rules:
        - Statutory financial ledger & commission records retained for 7 years.
        - Student/expert artifact download links retired outside active dispute window.
        """
        is_within_window = True
        artifacts_active = True

        if completed_at_iso:
            try:
                comp_dt = datetime.fromisoformat(completed_at_iso.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                delta_days = (now - comp_dt).days
                if delta_days > dispute_window_days:
                    is_within_window = False
                    artifacts_active = False
            except Exception:
                pass

        policy_text = (
            "7-year statutory financial audit ledger active. "
            + ("Artifact downloads open within 90-day dispute window." if artifacts_active else "Artifact downloads retired from active UI; audit ledger archived.")
        )

        return EvaluationRetentionAuditResponse(
            evaluation_id=evaluation_id,
            academic_year=academic_year,
            case_completed_at=completed_at_iso,
            is_within_dispute_window=is_within_window,
            statutory_financial_audit_retained=True,
            artifacts_download_active=artifacts_active,
            retention_policy=policy_text,
        )
