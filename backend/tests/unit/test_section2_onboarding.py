"""
STUDIQS® SmartParent™ (v6.2 Complete) - Section 2 Unit & Integration Test Suite
=============================================================================
Working Specification v6.0 / v6.1 Section 2:
Validates:
1. Mobile number validation & Indian E.164 normalization
2. OTP dispatch, TTL (300s), and verification lifecycle
3. Auto-creation of Subscriber account with BASIC plan entitlement
4. Canonical Board (CBSE, ICSE, TN State Board) and Class (1-12) normalization
5. Auto-suggested Subject Catalogs across all boards and senior secondary streams
6. Ultra-simple student onboarding (< 5 mins target)
7. Optional school fields (school_name, section) never block onboarding
8. Multi-child family support (single parent with multiple registered children)
9. Strict B2C Multi-Tenant Boundary: Foreign subscriber cannot access child profile
10. FastAPI REST Endpoints Integration via TestClient (/api/v1/auth/*)
=============================================================================
"""

import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.smartparent.db.base import Base
from src.smartparent.db.models.auth import Subscriber, Child
from src.smartparent.schemas.auth import (
    SendOTPRequest,
    VerifyOTPRequest,
    AddStudentRequest,
)
from src.smartparent.engines.section_02_onboarding.curriculum_catalog import CurriculumCatalogEngine
from src.smartparent.services.auth_service import AuthService
from src.smartparent.api.v1.auth import (
    router as auth_router,
    get_db,
    get_current_subscriber_id,
)


# SQLite dialect mapping for JSONB and UUID
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
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


# =============================================================================
# 1. MOBILE NUMBER & OTP VERIFICATION TESTS
# =============================================================================

def test_mobile_number_validation_and_clean_format():
    """Validates that valid Indian mobile numbers are normalized to E.164 (+91...)."""
    req1 = SendOTPRequest(mobile_number="9876543210")
    assert req1.mobile_number == "+919876543210"

    req2 = SendOTPRequest(mobile_number="+91 94444 12345")
    assert req2.mobile_number == "+919444412345"

    req3 = SendOTPRequest(mobile_number="08765432109")
    assert req3.mobile_number == "+918765432109"

    # Invalid cases
    with pytest.raises(ValueError, match="Invalid Indian mobile number"):
        SendOTPRequest(mobile_number="12345")  # Too short

    with pytest.raises(ValueError, match="Invalid Indian mobile number"):
        SendOTPRequest(mobile_number="5876543210")  # Invalid start digit (5)


def test_otp_dispatch_and_ttl():
    """Validates OTP generation with 300-second expiry and session token."""
    service = AuthService()
    resp = service.send_otp("+919876543210")

    assert resp.status == "OTP_SENT"
    assert resp.mobile_number == "+919876543210"
    assert resp.expires_in_seconds == 300
    assert resp.session_token.startswith("sess_")
    assert resp.dev_otp == "123456"


def test_otp_verify_and_subscriber_creation(db_session):
    """
    Validates that a new subscriber is automatically provisioned on first OTP verify,
    and subsequent logins recognize the existing subscriber without duplicate creation.
    """
    service = AuthService()
    mobile = "+919840011111"

    # Step 1: Request OTP
    service.send_otp(mobile)

    # Step 2: First-time verification -> Creates new subscriber
    auth_resp = service.verify_otp(
        db=db_session,
        mobile_number=mobile,
        otp="123456",
        parent_name="Karthik Sundaram",
    )
    assert auth_resp.is_new_subscriber is True
    assert auth_resp.parent_name == "Karthik Sundaram"
    assert auth_resp.subscription_plan == "BASIC"
    assert auth_resp.access_token is not None and len(auth_resp.access_token) > 20

    # Verify record in DB
    sub = db_session.query(Subscriber).filter(Subscriber.mobile_number == mobile).first()
    assert sub is not None
    assert sub.parent_name == "Karthik Sundaram"

    # Step 3: Subsequent login -> Reuses existing subscriber
    service.send_otp(mobile)
    auth_resp2 = service.verify_otp(
        db=db_session,
        mobile_number=mobile,
        otp="123456",
    )
    assert auth_resp2.is_new_subscriber is False
    assert auth_resp2.subscriber_id == str(sub.subscriber_id)


def test_otp_verify_invalid_code_rejected(db_session):
    """Asserts that wrong OTP is rejected with descriptive ValueError."""
    service = AuthService()
    mobile = "+919840022222"
    service.send_otp(mobile)

    with pytest.raises(ValueError, match="Invalid verification"):
        service.verify_otp(db=db_session, mobile_number=mobile, otp="999999")


# =============================================================================
# 2. CURRICULUM CATALOG & AUTO-SUGGESTION TESTS
# =============================================================================

def test_curriculum_catalog_board_and_class_normalization():
    """Validates flexible fuzzy normalization for board names and class grades."""
    engine = CurriculumCatalogEngine()

    # Board normalization
    assert engine.normalize_board("cbse") == "CBSE"
    assert engine.normalize_board("Central Board (CBSE)") == "CBSE"
    assert engine.normalize_board("icse") == "ICSE"
    assert engine.normalize_board("CISCE") == "ICSE"
    assert engine.normalize_board("TN State Board") == "TN State Board"
    assert engine.normalize_board("Tamil Nadu State Board") == "TN State Board"
    assert engine.normalize_board("Samacheer Kalvi") == "TN State Board"

    with pytest.raises(ValueError, match="Unsupported curriculum board"):
        engine.normalize_board("Unknown Foreign Board")

    # Class normalization
    assert engine.normalize_class("10") == "Class 10"
    assert engine.normalize_class("10th") == "Class 10"
    assert engine.normalize_class("Grade 10") == "Class 10"
    assert engine.normalize_class("Class X") == "Class 10"
    assert engine.normalize_class("Class 12") == "Class 12"
    assert engine.normalize_class("Class XII") == "Class 12"

    with pytest.raises(ValueError, match="Invalid class/grade"):
        engine.normalize_class("Grade 15")


def test_auto_suggest_subjects_multi_board():
    """Validates authoritative subject roster auto-suggestion across boards and streams."""
    engine = CurriculumCatalogEngine()

    # 1. CBSE Class 10 (Secondary)
    cbse_10 = engine.get_suggested_subjects("CBSE", "Class 10")
    assert "Mathematics" in cbse_10
    assert "Science" in cbse_10
    assert "Social Science" in cbse_10
    assert len(cbse_10) == 5

    # 2. ICSE Class 10 (7-9 core subjects)
    icse_10 = engine.get_suggested_subjects("ICSE", "Class 10")
    assert "English Language" in icse_10
    assert "History & Civics" in icse_10
    assert "Physics" in icse_10
    assert len(icse_10) >= 7

    # 3. TN State Board Class 10
    tn_10 = engine.get_suggested_subjects("TN State Board", "Class 10")
    assert "Tamil" in tn_10
    assert "English" in tn_10
    assert "Mathematics" in tn_10
    assert len(tn_10) == 5

    # 4. CBSE Class 11 Bio-Maths Stream
    cbse_11_bio = engine.get_suggested_subjects("CBSE", "Class 11", stream_id="BIO_MATHS")
    assert "Biology" in cbse_11_bio
    assert "Mathematics" in cbse_11_bio
    assert "Physics" in cbse_11_bio

    # 5. CBSE Class 12 Commerce Stream
    cbse_12_comm = engine.get_suggested_subjects("CBSE", "Class 12", stream_id="COMMERCE")
    assert "Accountancy" in cbse_12_comm
    assert "Business Studies" in cbse_12_comm
    assert "Economics" in cbse_12_comm


# =============================================================================
# 3. ULTRA-SIMPLE ONBOARDING & TENANT ISOLATION TESTS
# =============================================================================

def test_ultra_simple_student_onboarding(db_session):
    """
    Validates ultra-simple onboarding: Single student name, class dropdown,
    board dropdown, auto-suggested subjects, and under 5-minute target indicator.
    """
    service = AuthService()
    sub_id = uuid.uuid4()
    sub = Subscriber(
        subscriber_id=sub_id,
        mobile_number="+919840033333",
        parent_name="Lakshmi Narayanan",
        password_hash="mock_hash",
        subscription_plan="BASIC",
    )
    db_session.add(sub)
    db_session.commit()

    onboard_payload = AddStudentRequest(
        student_name="Arun Kumar",
        standard_class="Class 10",
        board="CBSE",
        academic_year="2026-2027",
    )

    resp = service.add_student(
        db=db_session,
        subscriber_id=sub_id,
        payload=onboard_payload,
    )

    assert resp.student_name == "Arun Kumar"
    assert resp.standard_class == "Class 10"
    assert resp.board == "CBSE"
    assert resp.academic_year == "2026-2027"
    assert resp.onboarding_status == "ONBOARDED"
    assert resp.time_to_onboard_target == "UNDER_5_MINUTES"
    assert resp.next_step == "RECORD_FIRST_RESULT"
    assert "Mathematics" in resp.subjects
    assert "Science" in resp.subjects

    # Verify Child in DB
    child = db_session.query(Child).filter(Child.child_id == uuid.UUID(resp.child_id)).first()
    assert child is not None
    assert child.subscriber_id == sub_id


def test_optional_fields_never_block_onboarding(db_session):
    """
    Per PDF Page 4: School name / section are optional and must NEVER block onboarding.
    """
    service = AuthService()
    sub_id = uuid.uuid4()
    sub = Subscriber(
        subscriber_id=sub_id,
        mobile_number="+919840044444",
        parent_name="Meena Raman",
        password_hash="mock_hash",
    )
    db_session.add(sub)
    db_session.commit()

    # Case A: Without optional fields -> Onboards smoothly
    resp_a = service.add_student(
        db=db_session,
        subscriber_id=sub_id,
        payload=AddStudentRequest(
            student_name="Pooja Raman",
            standard_class="Class 9",
            board="CBSE",
        ),
    )
    assert resp_a.school_name is None
    assert resp_a.section is None

    # Case B: With optional fields -> Preserves fields cleanly
    resp_b = service.add_student(
        db=db_session,
        subscriber_id=sub_id,
        payload=AddStudentRequest(
            student_name="Kavya Raman",
            standard_class="Class 7",
            board="CBSE",
            school_name="DAV Public School",
            section="B",
        ),
    )
    assert resp_b.school_name == "DAV Public School"
    assert resp_b.section == "B"


def test_multi_child_family_onboarding(db_session):
    """Validates single subscriber onboarding multiple siblings (Arun in Class 10, Ananya in Class 8)."""
    service = AuthService()
    sub_id = uuid.uuid4()
    sub = Subscriber(
        subscriber_id=sub_id,
        mobile_number="+919840055555",
        parent_name="Suresh Kumar",
        password_hash="mock_hash",
    )
    db_session.add(sub)
    db_session.commit()

    # Add Child 1
    resp1 = service.add_student(
        db=db_session,
        subscriber_id=sub_id,
        payload=AddStudentRequest(student_name="Arun Kumar", standard_class="Class 10", board="CBSE"),
    )

    # Add Child 2
    resp2 = service.add_student(
        db=db_session,
        subscriber_id=sub_id,
        payload=AddStudentRequest(student_name="Ananya Kumar", standard_class="Class 8", board="ICSE"),
    )

    children_list = service.list_children(db=db_session, subscriber_id=sub_id)
    assert len(children_list) == 2
    names = [c.student_name for c in children_list]
    assert "Arun Kumar" in names
    assert "Ananya Kumar" in names


def test_strict_b2c_tenant_isolation(db_session):
    """Asserts that Parent B cannot query or access Parent A's child profile."""
    service = AuthService()

    # Parent A and Child A
    sub_a = Subscriber(
        subscriber_id=uuid.uuid4(),
        mobile_number="+919840066661",
        parent_name="Parent Alpha",
        password_hash="mock_hash",
    )
    child_a = Child(
        child_id=uuid.uuid4(),
        subscriber_id=sub_a.subscriber_id,
        student_name="Arun Alpha",
        standard_class="Class 10",
        board="CBSE",
    )

    # Parent B
    sub_b = Subscriber(
        subscriber_id=uuid.uuid4(),
        mobile_number="+919840066662",
        parent_name="Parent Beta",
        password_hash="mock_hash",
    )

    db_session.add_all([sub_a, child_a, sub_b])
    db_session.commit()

    # Parent A accessing own child -> Allowed
    profile = service.get_child_profile(db=db_session, subscriber_id=sub_a.subscriber_id, child_id=child_a.child_id)
    assert profile.student_name == "Arun Alpha"

    # Parent B attempting to access Child A -> REJECTED with PermissionError
    with pytest.raises(PermissionError, match="not authorized for this subscriber"):
        service.get_child_profile(db=db_session, subscriber_id=sub_b.subscriber_id, child_id=child_a.child_id)


# =============================================================================
# 4. FASTAPI API ROUTER ENDPOINTS INTEGRATION TEST
# =============================================================================

def test_api_v1_auth_router_e2e(db_session):
    """
    End-to-End integration test covering the entire Section 2 consumer journey:
    1. POST /otp/send -> 2. POST /otp/verify -> 3. GET /curriculum/subjects
    -> 4. POST /student -> 5. GET /students -> 6. GET /students/{child_id}
    -> 7. Foreign tenant isolation check.
    """
    sub_id = uuid.uuid4()
    sub = Subscriber(
        subscriber_id=sub_id,
        mobile_number="+919840077777",
        parent_name="API Test Parent",
        password_hash="mock_hash",
    )
    db_session.add(sub)
    db_session.commit()

    app = FastAPI()
    app.include_router(auth_router, prefix="/api/v1")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_subscriber_id] = lambda: sub_id

    client = TestClient(app)

    # 1. POST /api/v1/auth/otp/send
    res_send = client.post("/api/v1/auth/otp/send", json={"mobile_number": "9840077777"})
    assert res_send.status_code == 200
    assert res_send.json()["status"] == "OTP_SENT"

    # 2. POST /api/v1/auth/otp/verify
    res_verify = client.post("/api/v1/auth/otp/verify", json={"mobile_number": "9840077777", "otp": "123456"})
    assert res_verify.status_code == 200
    data_auth = res_verify.json()
    assert data_auth["token_type"] == "bearer"
    assert data_auth["mobile_number"] == "+919840077777"

    # 3. GET /api/v1/auth/curriculum/subjects
    res_subj = client.get("/api/v1/auth/curriculum/subjects?board=CBSE&standard_class=Class 10")
    assert res_subj.status_code == 200
    assert "Mathematics" in res_subj.json()["subjects"]

    # 4. POST /api/v1/auth/student (Ultra-simple onboarding)
    student_payload = {
        "student_name": "Siddharth Karthik",
        "standard_class": "Class 10",
        "board": "CBSE",
        "academic_year": "2026-2027",
    }
    res_onboard = client.post("/api/v1/auth/student", json=student_payload)
    assert res_onboard.status_code == 201
    child_id = res_onboard.json()["child_id"]
    assert res_onboard.json()["time_to_onboard_target"] == "UNDER_5_MINUTES"

    # 5. GET /api/v1/auth/students
    res_list = client.get("/api/v1/auth/students")
    assert res_list.status_code == 200
    assert len(res_list.json()) >= 1
    assert res_list.json()[0]["student_name"] == "Siddharth Karthik"

    # 6. GET /api/v1/auth/students/{child_id}
    res_child = client.get(f"/api/v1/auth/students/{child_id}")
    assert res_child.status_code == 200
    assert res_child.json()["student_name"] == "Siddharth Karthik"

    # 7. Foreign subscriber isolation check (Rejection)
    foreign_sub_id = uuid.uuid4()
    app.dependency_overrides[get_current_subscriber_id] = lambda: foreign_sub_id
    res_unauth = client.get(f"/api/v1/auth/students/{child_id}")
    assert res_unauth.status_code == 403
    assert "not authorized" in res_unauth.json()["detail"]

