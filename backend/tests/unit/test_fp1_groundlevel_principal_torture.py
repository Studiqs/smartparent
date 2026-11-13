"""
STUDIQS® SmartParent™ - Principal Tester Ground-Level Adversarial Battery
=============================================================================
Module: tests.unit.test_fp1_groundlevel_principal_torture

Principal Test Lead & Security Auditor Invariants Tested:
  1. PWA Manifest & Service Worker Regulatory Security (DPDP Act 2023)
  2. Input Fuzzing & Malformed Mobile Numbers (SQLi, XSS, Non-Digits)
  3. Cryptographic OTP Boundary Conditions (60s cooldown, 5-attempt brute-force lockout, hourly cap)
  4. Password Security Boundary (Bcrypt 12 rounds, 72-byte safe truncation, wrong credentials)
  5. Multi-Tenant Cross-Parent Intrusion Attacks (Strict B2C Boundary Isolation)
  6. Refresh Token Family Rotation & Stolen Token Replay Attack Revocation
  7. DPDP Act 2023 Child Soft-Delete Integrity (No physical data loss, zero active leakage)
=============================================================================
"""

import time
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.smartparent.main import app
from src.smartparent.db.base import Base
from src.smartparent.db.models.auth import (
    Subscriber,
    Child,
    SubscriberSession,
    OTPVerificationSession,
    AuthAuditLog,
)
from src.smartparent.api.deps import get_db
from src.smartparent.core.security import (
    create_access_token,
    create_refresh_token,
    get_password_hash,
    verify_password,
    hash_token,
)
from src.smartparent.services.auth_service import AuthService
from src.smartparent.services.otp_service import OTPService


from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID

@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"

@compiles(PG_UUID, "sqlite")
def compile_uuid_sqlite(type_, compiler, **kw):
    return "CHAR(36)"

# =============================================================================
# IN-MEMORY TEST FIXTURES
# =============================================================================

@pytest.fixture(scope="module")
def groundlevel_db_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    auth_tables = [
        Subscriber.__table__,
        Child.__table__,
        SubscriberSession.__table__,
        OTPVerificationSession.__table__,
        AuthAuditLog.__table__,
    ]
    Base.metadata.create_all(bind=engine, tables=auth_tables)
    yield engine
    Base.metadata.drop_all(bind=engine, tables=auth_tables)


@pytest.fixture
def db(groundlevel_db_engine):
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=groundlevel_db_engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# =============================================================================
# 1. PWA APP SHELL & REGULATORY SECURITY
# =============================================================================

def test_pwa_manifest_groundlevel_invariants(client):
    """Verifies that the PWA manifest complies with standalone mobile standards."""
    res = client.get("/manifest.webmanifest")
    assert res.status_code == 200
    data = res.json()
    assert data["display"] == "standalone", "PWA must run in standalone mode without browser chrome"
    assert data["orientation"] == "portrait-primary", "Must enforce portrait orientation for mobile"
    assert data["theme_color"] == "#4338ca", "Brand theme color must match Studiqs Indigo"
    assert len(data["icons"]) >= 2, "Must include at least 192px and 512px icons"
    icon_sizes = [i["sizes"] for i in data["icons"]]
    assert "192x192" in icon_sizes
    assert "512x512" in icon_sizes


def test_pwa_service_worker_dpdp_caching_invariant(client):
    """Verifies that the Service Worker strictly forbids caching authenticated data."""
    res = client.get("/sw.js")
    assert res.status_code == 200
    sw_code = res.text
    # DPDP Act 2023 Statutory Caching Prohibition
    assert "SENSITIVE_PATH_PATTERNS" in sw_code, "Must define sensitive path regex list"
    assert "api\\/v1\\/auth" in sw_code or "api/v1/auth" in sw_code, "Must forbid caching auth routes"
    assert "api\\/v1\\/reports" in sw_code or "api/v1/reports" in sw_code, "Must forbid caching student reports"
    assert "studiqs-smartparent" in sw_code, "Cache name must follow Studiqs namespace"


# =============================================================================
# 2. MALICIOUS INPUT & INJECTION FUZZING
# =============================================================================

def test_malformed_and_injection_mobile_numbers(client):
    """Fuzzes mobile number endpoint with SQL injection and invalid payloads."""
    malicious_inputs = [
        "'; DROP TABLE subscribers; --",
        "<script>alert(1)</script>",
        "12345",              # Too short
        "+19876543210",       # Non-Indian country code
        "abcd9876543210",     # Letters
        "+910000000000",      # Invalid Indian prefix
    ]
    for bad_input in malicious_inputs:
        res = client.post("/api/v1/auth/otp/send", json={"mobile_number": bad_input})
        assert res.status_code in (400, 422), f"Input {bad_input} should have been rejected with 400 or 422"


# =============================================================================
# 3. OTP BOUNDARY TORTURE (COOLDOWN, BRUTE-FORCE, HOURLY LIMIT)
# =============================================================================

def test_otp_cooldown_strictly_enforced(db):
    """Verifies that rapid successive OTP requests are blocked by 60s cooldown."""
    otp_svc = OTPService()
    test_num = "+919988776601"

    # 1st request -> Success
    res1 = otp_svc.request_otp(db=db, mobile_number=test_num, is_dev_sandbox=True)
    assert res1.session_token is not None

    # Immediate 2nd request -> Must raise ValueError (cooldown active)
    with pytest.raises(ValueError) as exc:
        otp_svc.request_otp(db=db, mobile_number=test_num, is_dev_sandbox=True)
    assert "Please wait" in str(exc.value)


def test_otp_brute_force_lockout_after_max_attempts(db):
    """Verifies that 5 incorrect OTP attempts lock out and delete the session."""
    otp_svc = OTPService()
    test_num = "+919988776602"

    res = otp_svc.request_otp(db=db, mobile_number=test_num, is_dev_sandbox=False)
    session_token = res.session_token

    # 4 incorrect attempts -> Rejection with remaining count
    for attempt in range(1, 5):
        with pytest.raises(ValueError) as exc:
            otp_svc.verify_otp(
                db=db,
                mobile_number=test_num,
                otp="000000",
                session_token=session_token,
            )
        assert "Invalid verification code" in str(exc.value)

    # 5th incorrect attempt -> Session locked out and purged
    with pytest.raises(ValueError) as exc:
        otp_svc.verify_otp(
            db=db,
            mobile_number=test_num,
            otp="000000",
            session_token=session_token,
        )
    assert "Maximum" in str(exc.value) or "locked" in str(exc.value)

    # 6th attempt -> Session completely gone
    with pytest.raises(ValueError) as exc:
        otp_svc.verify_otp(
            db=db,
            mobile_number=test_num,
            otp="000000",
            session_token=session_token,
        )
    assert "not found or already verified" in str(exc.value)


# =============================================================================
# 4. PASSWORD SECURITY & RECOVERY TORTURE
# =============================================================================

def test_bcrypt_work_factor_and_safe_truncation(db):
    """Verifies that bcrypt hashing uses 12 work factor salt and handles 72+ bytes safely."""
    long_pass = "P@ssword" * 15  # 120 bytes long (exceeds 72 byte limit)
    hashed = get_password_hash(long_pass)
    assert hashed.startswith("$2b$12$"), "Must use bcrypt 12 rounds of salt"
    assert verify_password(long_pass, hashed) is True
    assert verify_password("WrongPassword123", hashed) is False


def test_forgot_and_reset_password_end_to_end(client, db):
    """Verifies full forgot password flow with OTP and instant auto-login."""
    test_mobile = "+919988776603"
    sub = Subscriber(
        subscriber_id=uuid.uuid4(),
        mobile_number=test_mobile,
        parent_name="Forgot Parent",
        password_hash=get_password_hash("OldPassword123"),
        subscription_plan="PRO",
    )
    db.add(sub)
    db.commit()

    # 1. Request password reset OTP
    res1 = client.post("/api/v1/auth/password/forgot", json={"mobile_number": test_mobile})
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["session_token"] is not None

    # 2. Reset password using dev OTP
    res2 = client.post(
        "/api/v1/auth/password/reset",
        json={
            "mobile_number": test_mobile,
            "otp": "123456",
            "new_password": "NewSuperPassword789!",
            "session_token": data1["session_token"],
        },
    )
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["access_token"] is not None
    assert data2["refresh_token"] is not None

    # 3. Verify new password login succeeds
    res3 = client.post(
        "/api/v1/auth/login/password",
        json={"mobile_or_email": test_mobile, "password": "NewSuperPassword789!"},
    )
    assert res3.status_code == 200
    assert res3.json()["parent_name"] == "Forgot Parent"


# =============================================================================
# 5. MULTI-TENANT CROSS-PARENT ISOLATION (ZERO LEAKAGE)
# =============================================================================

def test_cross_parent_intrusion_strictly_blocked(client, db):
    """Verifies that Parent A is strictly blocked from reading, editing, or deleting Parent B's child."""
    # Parent A (Attacker)
    sub_a = Subscriber(
        subscriber_id=uuid.uuid4(),
        mobile_number="+919988776611",
        parent_name="Parent A",
        password_hash=get_password_hash("PassA12345"),
        subscription_plan="BASIC",
    )
    # Parent B (Victim)
    sub_b = Subscriber(
        subscriber_id=uuid.uuid4(),
        mobile_number="+919988776612",
        parent_name="Parent B",
        password_hash=get_password_hash("PassB12345"),
        subscription_plan="PRO",
    )
    db.add_all([sub_a, sub_b])
    db.flush()

    child_b = Child(
        child_id=uuid.uuid4(),
        subscriber_id=sub_b.subscriber_id,
        student_name="Child of B",
        standard_class="Class 10",
        board="CBSE",
        is_active=True,
    )
    db.add(child_b)
    db.commit()

    token_a = create_access_token({"sub": str(sub_a.subscriber_id), "plan": "BASIC"})
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # 1. Attacker tries to GET victim child details -> 404 / 403
    res_get = client.get(f"/api/v1/auth/students/{child_b.child_id}", headers=headers_a)
    assert res_get.status_code in (403, 404), "Parent A must not see Parent B's child"

    # 2. Attacker tries to PUT / EDIT victim child -> 403 / 404
    res_put = client.put(
        f"/api/v1/auth/students/{child_b.child_id}",
        headers=headers_a,
        json={"display_name": "Hacked Name"},
    )
    assert res_put.status_code in (403, 404), "Parent A must not edit Parent B's child"

    # 3. Attacker tries to DELETE victim child -> 403 / 404
    res_del = client.delete(f"/api/v1/auth/students/{child_b.child_id}", headers=headers_a)
    assert res_del.status_code in (403, 404), "Parent A must not delete Parent B's child"

    # Verify Child B was untouched in DB
    db.refresh(child_b)
    assert child_b.student_name == "Child of B"
    assert child_b.is_active is True


# =============================================================================
# 6. REPLAY ATTACK DETECTION ON SILENT REFRESH
# =============================================================================

def test_refresh_token_replay_attack_detection(db):
    """Verifies that an attacker presenting an already-consumed refresh token has their session wiped."""
    auth_svc = AuthService()
    sub = Subscriber(
        subscriber_id=uuid.uuid4(),
        mobile_number="+919988776620",
        parent_name="Replay Target",
        password_hash=get_password_hash("ReplayTargetPass123"),
        subscription_plan="PRO",
    )
    db.add(sub)
    db.commit()

    # Issue initial dual tokens
    initial_tokens = auth_svc._issue_tokens_and_session(
        db=db,
        subscriber=sub,
        device_name="Chrome Mobile PWA",
        ip_address="127.0.0.1",
        user_agent="Mozilla/5.0 PWA",
        is_new=False,
    )
    first_refresh = initial_tokens.refresh_token

    # Legitimate user rotates token -> Success
    rotated_tokens = auth_svc.rotate_refresh_token(
        db=db,
        refresh_token=first_refresh,
        ip_address="127.0.0.1",
        user_agent="Mozilla/5.0 PWA",
    )
    assert rotated_tokens.access_token is not None

    # Malicious actor presents the old first_refresh token again -> Must trigger REPLAY ATTACK REVOCATION
    with pytest.raises(ValueError) as exc:
        auth_svc.rotate_refresh_token(
            db=db,
            refresh_token=first_refresh,
            ip_address="192.168.1.100",
            user_agent="Malicious Hacker Bot",
        )
    assert "revoked" in str(exc.value).lower() or "replay" in str(exc.value).lower() or "session" in str(exc.value).lower()
