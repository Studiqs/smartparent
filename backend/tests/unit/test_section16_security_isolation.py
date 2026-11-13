"""
STUDIQS® SmartParent™ (v6.2 Complete) - Unit Tests for Section 16 Security, Isolation & Document Retention
=============================================================================
Tests all Section 16 requirements:
1. BaseEngine health & circuit state
2. Cryptographic HMAC-SHA256 Signed URLs (15-min TTL default)
3. Expiration enforcement & tampering rejection
4. Private cloud storage path isolation & directory traversal defense
5. Role field leakage scrubbers (Expert view vs Subscriber view)
6. AI context isolation boundaries (zero cross-tenant leakage in prompts)
7. Report retention lifecycle (current year active, prior years retain only finalized yearly report)
8. Evaluation statutory retention policy (7-year financial audit ledger)
9. Family row-level isolation & "Never authorize from child_id alone" rule
10. Expert case-level isolation & case assignment boundary
11. FastAPI REST API endpoints via TestClient
=============================================================================
"""

import uuid
from datetime import date, datetime, timedelta, timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.pool import StaticPool
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.smartparent.db.base import Base
from src.smartparent.db.models.auth import Subscriber, Child
from src.smartparent.db.models.consolidated_report import ConsolidatedReport
from src.smartparent.db.models.marketplace import EvaluationCase, ExpertProfile, Expert
from src.smartparent.engines.section_16_security.document_and_isolation_engine import DocumentAndIsolationEngine
from src.smartparent.services.isolation_security_service import IsolationSecurityService
from src.smartparent.schemas.security_isolation import (
    SignedUrlScopeEnum,
    GenerateSignedUrlRequest,
    VerifySignedUrlRequest,
)
from src.smartparent.api.v1.security_isolation import (
    router as isolation_router,
    get_db,
    get_current_subscriber_id,
    get_current_expert_id,
)


# PostgreSQL JSONB & UUID SQLite dialect compability
@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


@compiles(PG_UUID, "sqlite")
def compile_uuid_sqlite(type_, compiler, **kw):
    return "CHAR(36)"


@pytest.fixture
def db_session():
    """In-memory SQLite session with full schema support."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[
            Subscriber.__table__,
            Child.__table__,
            ConsolidatedReport.__table__,
            Expert.__table__,
            ExpertProfile.__table__,
            EvaluationCase.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def setup_isolation_data(db_session):
    """Seed authenticated subscribers, children, reports, experts, and cases."""
    # Subscriber A (Family 1)
    sub_a = Subscriber(
        subscriber_id=uuid.uuid4(),
        mobile_number="+919876543210",
        parent_name="Venkatesh S.",
        email="venkatesh.s@example.com",
        password_hash="mock_hash_a",
    )
    child_a = Child(
        child_id=uuid.uuid4(),
        subscriber_id=sub_a.subscriber_id,
        student_name="Naveen Venkatesh",
        standard_class="Class 10",
        board="CBSE",
        academic_year="2026-2027",
    )

    # Subscriber B (Family 2)
    sub_b = Subscriber(
        subscriber_id=uuid.uuid4(),
        mobile_number="+919123456789",
        parent_name="Lakshmi M.",
        email="lakshmi.m@example.com",
        password_hash="mock_hash_b",
    )
    child_b = Child(
        child_id=uuid.uuid4(),
        subscriber_id=sub_b.subscriber_id,
        student_name="Kavya Lakshmi",
        standard_class="Class 9",
        board="ICSE",
        academic_year="2026-2027",
    )

    # Consolidated Reports for Child A (Current year & Prior year)
    report_cur_month = ConsolidatedReport(
        report_id=uuid.uuid4(),
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        report_type="MONTHLY",
        period_key="2026-10",
        report_title="Monthly Report - Oct 2026",
        academic_year="2026-2027",
        pdf_storage_path="private/tenants/child_a/reports/monthly_2026-10.pdf",
    )
    report_cur_term = ConsolidatedReport(
        report_id=uuid.uuid4(),
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        report_type="TERM",
        period_key="term_1",
        report_title="Term 1 Consolidated Report",
        academic_year="2026-2027",
        pdf_storage_path="private/tenants/child_a/reports/term_1.pdf",
    )
    report_prior_month = ConsolidatedReport(
        report_id=uuid.uuid4(),
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        report_type="MONTHLY",
        period_key="2025-11",
        report_title="Monthly Report - Nov 2025",
        academic_year="2025-2026",
        pdf_storage_path="private/tenants/child_a/reports/monthly_2025-11.pdf",
    )
    report_prior_yearly = ConsolidatedReport(
        report_id=uuid.uuid4(),
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        report_type="YEARLY",
        period_key="2025-2026",
        report_title="Annual Consolidated Report 2025-2026",
        academic_year="2025-2026",
        pdf_storage_path="private/tenants/child_a/reports/yearly_2025-2026.pdf",
    )

    # Experts
    expert_x = Expert(
        expert_id=uuid.uuid4(),
        full_name="Dr. Raghavan Raman",
        mobile_number="+919840123456",
        email="raghavan.raman@example.com",
        password_hash="mock_hash_x",
        kyc_status="VERIFIED",
        is_active=True,
    )
    expert_x_prof = ExpertProfile(
        profile_id=uuid.uuid4(),
        expert_id=expert_x.expert_id,
        display_alias="Prof. R. Raman",
        bio="Ph.D. in Mathematics, 20 Yrs CBSE Senior Examiner",
        qualified_subjects=["Mathematics"],
        qualified_boards=["CBSE"],
        qualified_classes=["Class 10"],
        sla_turnaround_hours=48,
        per_case_fee=500.0,
    )

    expert_y = Expert(
        expert_id=uuid.uuid4(),
        full_name="Anitha Sundaram",
        mobile_number="+919840987654",
        email="anitha.s@example.com",
        password_hash="mock_hash_y",
        kyc_status="VERIFIED",
        is_active=True,
    )
    expert_y_prof = ExpertProfile(
        profile_id=uuid.uuid4(),
        expert_id=expert_y.expert_id,
        display_alias="Anitha S.",
        bio="M.Sc. Physics, Board Specialist",
        qualified_subjects=["Physics"],
        qualified_boards=["CBSE"],
        qualified_classes=["Class 10"],
        sla_turnaround_hours=48,
        per_case_fee=500.0,
    )

    # Evaluation Case assigned to Expert X for Child A
    case_x = EvaluationCase(
        case_id=uuid.uuid4(),
        subscriber_id=sub_a.subscriber_id,
        child_id=child_a.child_id,
        expert_id=expert_x.expert_id,
        subject="Mathematics",
        test_title="Mid-Term Math Exam",
        case_status="UNDER_REVIEW",
        gross_fee=500.0,
        question_paper_path="private/evaluations/case_x/qp.pdf",
        answer_sheet_path="private/evaluations/case_x/ans.pdf",
    )

    db_session.add_all([
        sub_a, child_a, sub_b, child_b,
        report_cur_month, report_cur_term, report_prior_month, report_prior_yearly,
        expert_x, expert_x_prof, expert_y, expert_y_prof, case_x,
    ])
    db_session.commit()

    return {
        "sub_a": sub_a,
        "child_a": child_a,
        "sub_b": sub_b,
        "child_b": child_b,
        "expert_x": expert_x,
        "expert_y": expert_y,
        "case_x": case_x,
    }


# =============================================================================
# 1. BaseEngine Health & Signed URLs
# =============================================================================

def test_document_and_isolation_engine_health():
    engine = DocumentAndIsolationEngine()
    health = engine.health_check()
    assert health["status"] == "healthy"
    assert health["circuit_state"] == "CLOSED"


def test_hmac_signed_url_generation_and_verification():
    engine = DocumentAndIsolationEngine()
    path = "private/tenants/sub-123/children/c-456/evidence/rec-789/sheet.pdf"
    signed_resp = engine.generate_signed_url(
        resource_path=path,
        scope=SignedUrlScopeEnum.FAMILY_EVIDENCE,
        expires_in_seconds=900,
    )

    assert signed_resp.resource_path == path
    assert "signature=" in signed_resp.signed_url
    assert signed_resp.scope == "FAMILY_EVIDENCE"
    assert signed_resp.ttl_seconds == 900

    # Verify signature
    verify_resp = engine.verify_signed_url(
        resource_path=path,
        signature=signed_resp.signature,
        expires_at=signed_resp.expires_at,
        scope="FAMILY_EVIDENCE",
    )
    assert verify_resp.is_valid is True
    assert verify_resp.reason is None


def test_hmac_signed_url_expired_token():
    engine = DocumentAndIsolationEngine()
    path = "private/tenants/reports/monthly.pdf"
    # Past timestamp (1 hour ago)
    past_ts = int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp())
    sig = engine._compute_signature(path, str(past_ts), "REPORT_DOWNLOAD")

    verify_resp = engine.verify_signed_url(
        resource_path=path,
        signature=sig,
        expires_at=str(past_ts),
        scope="REPORT_DOWNLOAD",
    )
    assert verify_resp.is_valid is False
    assert "expired" in verify_resp.reason.lower()


def test_hmac_signed_url_tamper_rejected():
    engine = DocumentAndIsolationEngine()
    path = "private/tenants/reports/monthly.pdf"
    future_ts = int((datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp())
    sig = engine._compute_signature(path, str(future_ts), "REPORT_DOWNLOAD")

    # Tamper with path
    verify_resp = engine.verify_signed_url(
        resource_path="private/tenants/reports/forged.pdf",
        signature=sig,
        expires_at=str(future_ts),
        scope="REPORT_DOWNLOAD",
    )
    assert verify_resp.is_valid is False
    assert "mismatch" in verify_resp.reason.lower()


def test_storage_path_traversal_detection():
    engine = DocumentAndIsolationEngine()
    with pytest.raises(ValueError, match="Path traversal"):
        engine.normalize_storage_path("../etc/passwd")

    with pytest.raises(ValueError, match="Path traversal"):
        engine.normalize_storage_path("private//tenants/../root.key")


def test_storage_path_builders():
    engine = DocumentAndIsolationEngine()
    f_path = engine.build_family_evidence_path("sub-1", "child-2", "rec-3", "exam.pdf")
    assert f_path == "private/tenants/sub-1/children/child-2/evidence/rec-3/exam.pdf"

    r_path = engine.build_report_path("sub-1", "child-2", "monthly", "2026-10")
    assert r_path == "private/tenants/sub-1/children/child-2/reports/monthly_2026-10.pdf"

    e_path = engine.build_evaluation_path("case-99", "student_original", "paper.pdf")
    assert e_path == "private/evaluations/case-99/student_original/paper.pdf"


# =============================================================================
# 2. Field Leakage Scrubbers (Expert view vs Subscriber view)
# =============================================================================

def test_expert_case_view_field_leakage_scrubbed():
    engine = DocumentAndIsolationEngine()
    raw_case = {
        "evaluation_id": "eval-101",
        "student_name": "Aditya Ramanathan",
        "parent_name": "Ramanathan Sundaram",
        "parent_phone": "+919876543210",
        "parent_email": "ramanathan@example.com",
        "parent_address": "Flat 4B, Chennai",
        "sibling_data": [{"name": "Ananya", "class": "Class 6"}],
        "fee_paid_by_parent": 600.0,
        "standard_class": "Class 10",
        "board": "CBSE",
        "subject": "Mathematics",
        "status": "ASSIGNED",
    }
    sanitized = engine.sanitize_expert_case_view(raw_case)

    # Student alias must be first name only
    assert sanitized.student_alias == "Aditya"
    # Ensure sensitive fields are excluded from model dict
    data_dict = sanitized.model_dump()
    assert "parent_phone" not in data_dict
    assert "parent_email" not in data_dict
    assert "parent_address" not in data_dict
    assert "sibling_data" not in data_dict
    assert "fee_paid_by_parent" not in data_dict
    assert sanitized.parent_contact_masked is True
    assert sanitized.family_history_masked is True


def test_subscriber_expert_profile_field_leakage_scrubbed():
    engine = DocumentAndIsolationEngine()
    raw_expert = {
        "expert_id": "exp-202",
        "name": "Dr. Sivakumar Natarajan",
        "display_name": "Dr. N. Sivakumar",
        "kyc_aadhaar_last4": "8899",
        "kyc_pan_number": "ABCDE1234F",
        "bank_account_number": "123456789012",
        "bank_ifsc_code": "HDFC0001234",
        "platform_commission_pct": 20.0,
        "expert_net_payout_inr": 400.0,
        "internal_case_queue_count": 8,
        "subjects": ["Mathematics"],
        "qualifications": "Ph.D. IIT Madras",
        "experience_years": 15,
        "average_rating": 4.9,
    }
    sanitized = engine.sanitize_subscriber_expert_profile(raw_expert)

    data_dict = sanitized.model_dump()
    assert "kyc_aadhaar_last4" not in data_dict
    assert "bank_account_number" not in data_dict
    assert "bank_ifsc_code" not in data_dict
    assert "platform_commission_pct" not in data_dict
    assert "expert_net_payout_inr" not in data_dict
    assert sanitized.bank_payout_details_masked is True
    assert sanitized.kyc_identity_masked is True


# =============================================================================
# 3. AI Context Isolation Boundary Guard
# =============================================================================

def test_ai_context_isolation_clean():
    engine = DocumentAndIsolationEngine()
    clean_evidence = [
        {"subscriber_id": "sub-1", "child_id": "c-1", "topic": "Algebra"},
        {"subscriber_id": "sub-1", "child_id": "c-1", "topic": "Geometry"},
    ]
    # Sould pass silently
    engine.assert_isolated_ai_context("sub-1", "c-1", clean_evidence)


def test_ai_context_isolation_cross_tenant_blocked():
    engine = DocumentAndIsolationEngine()
    tainted_evidence = [
        {"subscriber_id": "sub-1", "child_id": "c-1", "topic": "Algebra"},
        {"subscriber_id": "sub-2", "child_id": "c-2", "topic": "Foreign Topic"},  # Tainted!
    ]
    with pytest.raises(PermissionError, match="Cross-tenant violation"):
        engine.assert_isolated_ai_context("sub-1", "c-1", tainted_evidence)


# =============================================================================
# 4. Report & Evaluation Document Retention Lifecycle
# =============================================================================

def test_report_retention_lifecycle_audit():
    engine = DocumentAndIsolationEngine()
    reports = [
        {"report_id": "r-1", "report_type": "MONTHLY", "academic_year": "2026-2027", "period_key": "2026-10"},
        {"report_id": "r-2", "report_type": "TERM", "academic_year": "2026-2027", "period_key": "term_1"},
        {"report_id": "r-3", "report_type": "MONTHLY", "academic_year": "2025-2026", "period_key": "2025-10"},
        {"report_id": "r-4", "report_type": "YEARLY", "academic_year": "2025-2026", "period_key": "2025-2026"},
    ]
    audit = engine.audit_report_retention("child-1", "2026-2027", reports)

    assert audit.active_current_year_reports_count == 2
    assert audit.permanent_historical_archives_count == 1
    assert audit.retired_intermediate_drafts_count == 1

    # Check individual item flags
    cur_m = next(r for r in audit.reports if r.report_id == "r-1")
    assert cur_m.retention_status == "ACTIVE_CURRENT_YEAR"
    assert cur_m.is_accessible_to_parent is True

    prior_m = next(r for r in audit.reports if r.report_id == "r-3")
    assert prior_m.retention_status == "RETIRED_INTERMEDIATE_DRAFT"
    assert prior_m.is_accessible_to_parent is False

    prior_y = next(r for r in audit.reports if r.report_id == "r-4")
    assert prior_y.retention_status == "PERMANENT_HISTORICAL_ARCHIVE"
    assert prior_y.is_accessible_to_parent is True


def test_evaluation_statutory_retention():
    engine = DocumentAndIsolationEngine()
    # Case completed 10 days ago (within 90-day dispute window)
    recent_dt = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    recent_audit = engine.audit_evaluation_retention("case-1", "2026-2027", recent_dt)
    assert recent_audit.is_within_dispute_window is True
    assert recent_audit.artifacts_download_active is True
    assert recent_audit.statutory_financial_audit_retained is True

    # Case completed 120 days ago (outside 90-day dispute window)
    old_dt = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
    old_audit = engine.audit_evaluation_retention("case-2", "2025-2026", old_dt)
    assert old_audit.is_within_dispute_window is False
    assert old_audit.artifacts_download_active is False
    assert old_audit.statutory_financial_audit_retained is True


# =============================================================================
# 5. Service Layer Isolation & Boundary Enforcement
# =============================================================================

def test_service_family_row_level_isolation(db_session, setup_isolation_data):
    data = setup_isolation_data
    service = IsolationSecurityService()

    # Subscriber A accessing own child succeeds
    child = service.verify_subscriber_child_boundary(
        db=db_session,
        subscriber_id=data["sub_a"].subscriber_id,
        child_id=data["child_a"].child_id,
    )
    assert child.student_name == "Naveen Venkatesh"

    # Subscriber A accessing foreign Child B raises PermissionError
    with pytest.raises(PermissionError, match="not authorized"):
        service.verify_subscriber_child_boundary(
            db=db_session,
            subscriber_id=data["sub_a"].subscriber_id,
            child_id=data["child_b"].child_id,
        )


def test_service_never_authorize_from_child_id_alone(db_session, setup_isolation_data):
    data = setup_isolation_data
    service = IsolationSecurityService()

    # Omission of subscriber_id must raise PermissionError
    with pytest.raises(PermissionError, match="Both subscriber_id and child_id are required"):
        service.verify_subscriber_child_boundary(
            db=db_session,
            subscriber_id=None,
            child_id=data["child_a"].child_id,
        )


def test_service_expert_case_isolation(db_session, setup_isolation_data):
    data = setup_isolation_data
    service = IsolationSecurityService()

    # Assigned expert X can access case_x
    case = service.verify_expert_evaluation_boundary(
        db=db_session,
        expert_id=data["expert_x"].expert_id,
        evaluation_id=data["case_x"].case_id,
    )
    assert case.subject == "Mathematics"

    # Foreign expert Y cannot access case_x
    with pytest.raises(PermissionError, match="not assigned to this expert"):
        service.verify_expert_evaluation_boundary(
            db=db_session,
            expert_id=data["expert_y"].expert_id,
            evaluation_id=data["case_x"].case_id,
        )


def test_service_subscriber_evaluation_boundary(db_session, setup_isolation_data):
    data = setup_isolation_data
    service = IsolationSecurityService()

    # Subscriber A booked case_x -> succeeds
    case = service.verify_subscriber_evaluation_boundary(
        db=db_session,
        subscriber_id=data["sub_a"].subscriber_id,
        evaluation_id=data["case_x"].case_id,
    )
    assert case.subject == "Mathematics"

    # Foreign subscriber B cannot access case_x
    with pytest.raises(PermissionError, match="not authorized for this subscriber"):
        service.verify_subscriber_evaluation_boundary(
            db=db_session,
            subscriber_id=data["sub_b"].subscriber_id,
            evaluation_id=data["case_x"].case_id,
        )


# =============================================================================
# 6. FastAPI Router Endpoints via TestClient
# =============================================================================

@pytest.fixture
def test_app(db_session, setup_isolation_data):
    data = setup_isolation_data
    app = FastAPI()
    app.include_router(isolation_router)

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_subscriber_id] = lambda: data["sub_a"].subscriber_id
    app.dependency_overrides[get_current_expert_id] = lambda: data["expert_x"].expert_id

    return app


def test_api_generate_and_verify_signed_url(test_app, setup_isolation_data):
    data = setup_isolation_data
    client = TestClient(test_app)

    # 1. Generate signed URL for Child A evidence
    payload = {
        "scope": "FAMILY_EVIDENCE",
        "resource_path": "private/tenants/child_a/exam.pdf",
        "child_id": str(data["child_a"].child_id),
        "expires_in_seconds": 900,
    }
    resp = client.post("/isolation/signed-url", json=payload)
    assert resp.status_code == 200
    res_data = resp.json()
    assert "signature" in res_data
    assert "signed_url" in res_data

    # 2. Verify URL token
    verify_payload = {
        "resource_path": res_data["resource_path"],
        "signature": res_data["signature"],
        "expires_at": res_data["expires_at"],
        "scope": res_data["scope"],
    }
    v_resp = client.post("/isolation/verify-url", json=verify_payload)
    assert v_resp.status_code == 200
    assert v_resp.json()["is_valid"] is True


def test_api_generate_signed_url_cross_tenant_forbidden(test_app, setup_isolation_data):
    data = setup_isolation_data
    client = TestClient(test_app)

    # Subscriber A attempting to sign URL targeting foreign Child B
    payload = {
        "scope": "FAMILY_EVIDENCE",
        "resource_path": "private/tenants/child_b/secret.pdf",
        "child_id": str(data["child_b"].child_id),
        "expires_in_seconds": 900,
    }
    resp = client.post("/isolation/signed-url", json=payload)
    assert resp.status_code == 403
    assert "not authorized" in resp.json()["detail"].lower()


def test_api_audit_report_retention_endpoint(test_app, setup_isolation_data):
    data = setup_isolation_data
    client = TestClient(test_app)

    resp = client.get(f"/isolation/retention/reports/{data['child_a'].child_id}")
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["child_id"] == str(data["child_a"].child_id)
    assert res_data["current_academic_year"] == "2026-2027"
    assert res_data["active_current_year_reports_count"] == 2
    assert res_data["permanent_historical_archives_count"] == 1
    assert res_data["retired_intermediate_drafts_count"] == 1


def test_api_sanitized_case_for_expert(test_app, setup_isolation_data):
    data = setup_isolation_data
    client = TestClient(test_app)

    resp = client.get(f"/isolation/sanitized/case/{data['case_x'].case_id}")
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["student_alias"] == "Naveen"  # Surname Venkatesh scrubbed
    assert res_data["parent_contact_masked"] is True
    assert res_data["family_history_masked"] is True
    assert "parent_phone" not in res_data
