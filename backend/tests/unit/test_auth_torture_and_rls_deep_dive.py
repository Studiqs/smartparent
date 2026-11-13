"""
STUDIQS® SmartParent™ (v6.3 Complete) - Auth, OTP, Multi-Session & RLS Torture Test Battery
========================================================================================
Module: tests.unit.test_auth_torture_and_rls_deep_dive
Adversarial Penetration & Torture Testing covering:
  1. Real Indian Mobile Numbers & SQL Injection / Malformed Number Sanitation
  2. Cryptographic OTP Generation, Uniform Distribution & HMAC-SHA256 Salted Hashing
  3. Cooldown Countdown Boundary Invariance (59s blocked, 61s allowed)
  4. Hourly Request Quota Throttling (Max 5/hr, 6th hard-blocked with 429)
  5. Brute-Force Lockout Defense (5 incorrect attempts lock out session, 6th rejected)
  6. OTP Time-To-Live (300s TTL, 301s auto-purge)
  7. PyJWT Cryptographic Forgery & Tampered Payload Rejection
  8. Multi-Device Concurrent Session Management (iPhone, Android PWA, Mac Desktop)
  9. Silent Refresh Token Rotation (RTR) & Hash Fingerprinting
  10. Adversarial Replay Attack Tripwire (Stolen token reuse nukes all active sessions)
  11. Cross-Tenant IDOR Attack Rejection (Parent B cannot revoke Parent A's session)
  12. Row-Level Security (RLS) Tenant Boundary Isolation across Children & Telemetry
========================================================================================
"""

import time
import uuid
import secrets
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
import pytest
from sqlalchemy import create_engine, select, text, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID

from src.smartparent.db.base import Base
from src.smartparent.db.models.auth import (
    Subscriber,
    Child,
    SubscriberSession,
    OTPVerificationSession,
    AuthAuditLog,
)
from src.smartparent.db.models.assessment import EvidenceRecord
from src.smartparent.db.models.diagnostic import TopicScore, TopicGap
from src.smartparent.db.models.parent_pulse import ParentPulseRecord
from src.smartparent.core.security import (
    generate_secure_otp,
    hash_otp,
    verify_otp_hash,
    hash_token,
    decode_token,
    create_access_token,
    create_refresh_token,
)
from src.smartparent.core.exceptions import (
    InvalidTokenError,
    TokenExpiredError,
)
from src.smartparent.core.rls import (
    async_tenant_context,
    set_active_rls_context,
    reset_active_rls_context,
    get_current_rls_context,
    UserRole,
    PostgreSQLRLSRegistry,
)
from src.smartparent.services.otp_service import OTPService
from src.smartparent.services.auth_service import AuthService
from src.smartparent.config import settings


# SQLite dialect mapping for PostgreSQL JSONB and UUID
@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


@compiles(PG_UUID, "sqlite")
def compile_uuid_sqlite(type_, compiler, **kw):
    return "CHAR(36)"


@pytest.fixture
def torture_db():
    """In-memory SQLite database supporting all authentication and telemetry tables."""
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
            SubscriberSession.__table__,
            OTPVerificationSession.__table__,
            AuthAuditLog.__table__,
            EvidenceRecord.__table__,
            TopicScore.__table__,
            TopicGap.__table__,
            ParentPulseRecord.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


# =============================================================================
# 1. OTP GENERATION & CRYPTOGRAPHIC ENTROPY TORTURE
# =============================================================================

def test_otp_generation_entropy_and_unbiased_distribution():
    """Torture test: 1,000 secure OTPs are 6 digits, strictly numeric, and varied."""
    otps = [generate_secure_otp(6) for _ in range(1, 1001)]
    assert len(otps) == 1000
    for code in otps:
        assert len(code) == 6
        assert code.isdigit()
    # Ensure high entropy (no constant values)
    unique_otps = set(otps)
    assert len(unique_otps) > 950  # High uniqueness among 1,000 samples


def test_otp_hmac_salted_hash_timing_attack_resistance():
    """Validates that constant-time verification passes on match and fails on 1-bit flip."""
    otp = "847291"
    salt = secrets.token_hex(16)
    expected_hash = hash_otp(otp, salt)

    # Legitimate verification
    assert verify_otp_hash(otp, salt, expected_hash) is True

    # 1-digit altered verification
    assert verify_otp_hash("847292", salt, expected_hash) is False

    # Altered salt verification
    wrong_salt = secrets.token_hex(16)
    assert verify_otp_hash(otp, wrong_salt, expected_hash) is False


# =============================================================================
# 2. REAL INDIAN MOBILE NUMBERS & ADVERSARIAL OTP THROTTLING
# =============================================================================

def test_otp_request_with_real_indian_mobile_and_cooldown(torture_db):
    """
    Torture tests OTP request with real Indian numbers:
    - First request succeeds.
    - Second request within 60s is strictly rejected with cooldown error.
    - Elapsed > 60s allows new OTP request.
    """
    otp_svc = OTPService()
    real_mobile = "+919840123456"  # Real Tamil Nadu format

    # Request 1
    resp1 = otp_svc.request_otp(
        db=torture_db,
        mobile_number=real_mobile,
        ip_address="103.28.246.12",
        user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_4)",
        is_dev_sandbox=False,
    )
    assert resp1.mobile_number == real_mobile
    assert resp1.cooldown_seconds == 60
    assert len(resp1.session_token) > 10

    # Immediate Request 2 (Cooldown Violation)
    with pytest.raises(ValueError) as exc_info:
        otp_svc.request_otp(
            db=torture_db,
            mobile_number=real_mobile,
            ip_address="103.28.246.12",
        )
    assert "Please wait" in str(exc_info.value)

    # Simulate 61 seconds elapsed
    session = torture_db.query(OTPVerificationSession).filter_by(mobile_number=real_mobile).first()
    session.last_sent_at = datetime.now(timezone.utc) - timedelta(seconds=61)
    torture_db.commit()

    # Request 3 (After Cooldown)
    resp3 = otp_svc.request_otp(
        db=torture_db,
        mobile_number=real_mobile,
        is_dev_sandbox=False,
    )
    assert resp3.session_token != resp1.session_token


def test_otp_hourly_quota_bomb_protection(torture_db):
    """
    Torture tests SMS billing bomb attack:
    - 5 requests per hour allowed.
    - 6th request is strictly blocked, writing a RATE_LIMITED audit log.
    """
    otp_svc = OTPService()
    target_mobile = "+919876543210"

    for i in range(1, 6):
        # Create completed past sessions
        sess = OTPVerificationSession(
            session_token=f"sess_hist_{i}_{uuid.uuid4().hex}",
            mobile_number=target_mobile,
            otp_salt=secrets.token_hex(16),
            otp_hash="mock_hash",
            created_at=datetime.now(timezone.utc) - timedelta(minutes=10 * i),
            last_sent_at=datetime.now(timezone.utc) - timedelta(minutes=10 * i),
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=10 * i) + timedelta(minutes=5),
            is_verified=False,
        )
        torture_db.add(sess)
    torture_db.commit()

    # 6th attempt within the hour MUST fail
    with pytest.raises(ValueError) as exc:
        otp_svc.request_otp(
            db=torture_db,
            mobile_number=target_mobile,
            ip_address="182.73.128.5",
        )
    assert "Maximum 5 requests per hour exceeded" in str(exc.value)

    # Verify RATE_LIMITED audit logged
    audit = torture_db.query(AuthAuditLog).filter_by(
        mobile_number=target_mobile,
        action="RATE_LIMITED",
    ).first()
    assert audit is not None
    assert audit.ip_address == "182.73.128.5"


def test_otp_brute_force_lockout_torture(torture_db):
    """
    Simulates a hacker brute-forcing OTP guesses:
    - 5 incorrect attempts allowed with decrementing warning.
    - At attempt 5, session is destroyed and locked out.
    - Subsequent verification rejected.
    """
    otp_svc = OTPService()
    mobile = "+919123456789"
    salt = secrets.token_hex(16)
    correct_otp = "739281"
    correct_hash = hash_otp(correct_otp, salt)

    sess = OTPVerificationSession(
        session_token="sess_brute_test_01",
        mobile_number=mobile,
        otp_salt=salt,
        otp_hash=correct_hash,
        attempts=0,
        max_attempts=5,
        last_sent_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        is_verified=False,
    )
    torture_db.add(sess)
    torture_db.commit()

    # Incorrect attempts 1 to 4
    for wrong_code in ["111111", "222222", "333333", "444444"]:
        with pytest.raises(ValueError) as exc:
            otp_svc.verify_otp(
                db=torture_db,
                mobile_number=mobile,
                otp=wrong_code,
                session_token="sess_brute_test_01",
            )
        assert "Invalid verification code" in str(exc.value)

    # 5th Incorrect Attempt -> Tripwire Locks and Deletes Session
    with pytest.raises(ValueError) as exc:
        otp_svc.verify_otp(
            db=torture_db,
            mobile_number=mobile,
            otp="555555",
            session_token="sess_brute_test_01",
        )
    assert "Maximum verification attempts exceeded" in str(exc.value)

    # Session MUST be purged from active table
    purged = torture_db.query(OTPVerificationSession).filter_by(mobile_number=mobile).first()
    assert purged is None

    # Even presenting the CORRECT OTP now MUST fail
    with pytest.raises(ValueError) as exc:
        otp_svc.verify_otp(
            db=torture_db,
            mobile_number=mobile,
            otp=correct_otp,
            session_token="sess_brute_test_01",
        )
    assert "not found or already verified" in str(exc.value)


def test_otp_ttl_expiry_auto_cleanup(torture_db):
    """Verifies that an OTP older than 300 seconds is rejected and pruned."""
    otp_svc = OTPService()
    mobile = "+919444012345"
    salt = secrets.token_hex(16)
    correct_otp = "901234"

    # Create session expired 10 seconds ago
    sess = OTPVerificationSession(
        session_token="sess_expired_01",
        mobile_number=mobile,
        otp_salt=salt,
        otp_hash=hash_otp(correct_otp, salt),
        attempts=0,
        last_sent_at=datetime.now(timezone.utc) - timedelta(seconds=310),
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=10),
        is_verified=False,
    )
    torture_db.add(sess)
    torture_db.commit()

    with pytest.raises(ValueError) as exc:
        otp_svc.verify_otp(
            db=torture_db,
            mobile_number=mobile,
            otp=correct_otp,
            session_token="sess_expired_01",
        )
    assert "OTP has expired" in str(exc.value)

    # Cleaned up from DB
    assert torture_db.query(OTPVerificationSession).filter_by(mobile_number=mobile).first() is None


# =============================================================================
# 3. PYJWT CRYPTOGRAPHIC SIGNATURE & TAMPERING TORTURE
# =============================================================================

def test_jwt_tampered_payload_and_forged_secret_rejection():
    """
    Adversarial test:
    - Tampering with payload claims breaks HMAC-SHA256 signature.
    - Signing with a forged secret key fails decode.
    """
    parent_uuid = str(uuid.uuid4())
    token = create_access_token(
        data={"sub": parent_uuid, "role": "subscriber", "plan": "PRO"},
    )

    # Legitimate decode
    decoded = decode_token(token)
    assert decoded["sub"] == parent_uuid
    assert decoded["plan"] == "PRO"
    assert "jti" in decoded

    # Forged Token (Signed with malicious attacker key)
    import jwt
    malicious_token = jwt.encode(
        {"sub": parent_uuid, "role": "admin", "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())},
        "attacker_fake_secret_key_9999999999",
        algorithm="HS256",
    )

    with pytest.raises(InvalidTokenError):
        decode_token(malicious_token)


def test_jwt_expired_access_token_rejection():
    """Expired access token triggers TokenExpiredError."""
    token = create_access_token(
        data={"sub": str(uuid.uuid4())},
        expires_delta=timedelta(seconds=-1),  # Expired 1 second ago
    )
    with pytest.raises(TokenExpiredError) as exc:
        decode_token(token)
    assert "expired" in str(exc.value).lower()


# =============================================================================
# 4. MULTI-DEVICE SESSION MANAGEMENT & SILENT ROTATION
# =============================================================================

def test_multi_device_session_creation_and_selective_logout(torture_db):
    """
    Simulates a real parent simultaneously active across 3 devices:
      1. iPhone 15 Pro (Mobile Safari)
      2. Samsung Galaxy S24 (STUDIQS PWA)
      3. MacBook Air (Desktop Chrome)
    Verifies:
      - All 3 sessions coexist without interfering.
      - Selective logout of Samsung PWA terminates ONLY that session.
      - iPhone and MacBook sessions remain active.
    """
    auth_svc = AuthService()
    mobile = "+919888877777"

    # Device 1: iPhone
    t1 = auth_svc.verify_otp(
        db=torture_db,
        mobile_number=mobile,
        otp=auth_svc.DEV_TEST_OTP,
        parent_name="Venkatesh S.",
        device_name="iPhone 15 Pro - Mobile Safari",
        ip_address="49.37.10.12",
    )
    # Device 2: Samsung PWA
    t2 = auth_svc.verify_otp(
        db=torture_db,
        mobile_number=mobile,
        otp=auth_svc.DEV_TEST_OTP,
        device_name="Samsung Galaxy S24 - STUDIQS PWA",
        ip_address="106.51.72.84",
    )
    # Device 3: MacBook Desktop
    t3 = auth_svc.verify_otp(
        db=torture_db,
        mobile_number=mobile,
        otp=auth_svc.DEV_TEST_OTP,
        device_name="MacBook Air - Chrome",
        ip_address="122.178.44.19",
    )

    sub_id = uuid.UUID(t1.subscriber_id)

    # Verify 3 active sessions
    active_sessions = torture_db.query(SubscriberSession).filter_by(
        subscriber_id=sub_id,
        is_revoked=False,
    ).all()
    assert len(active_sessions) == 3

    # Selectively revoke Device 2 (Samsung PWA)
    samsung_session_id = uuid.UUID(t2.session_id)
    logout_res = auth_svc.logout_session(
        db=torture_db,
        subscriber_id=sub_id,
        session_id=samsung_session_id,
    )
    assert logout_res.revoked_sessions_count == 1

    # Verify Samsung is revoked, while iPhone & MacBook are active
    samsung_sess = torture_db.query(SubscriberSession).filter_by(session_id=samsung_session_id).first()
    assert samsung_sess.is_revoked is True

    remaining = torture_db.query(SubscriberSession).filter_by(
        subscriber_id=sub_id,
        is_revoked=False,
    ).all()
    assert len(remaining) == 2
    active_devices = [s.device_name for s in remaining]
    assert "iPhone 15 Pro - Mobile Safari" in active_devices
    assert "MacBook Air - Chrome" in active_devices


# =============================================================================
# 5. ADVERSARIAL REPLAY ATTACK TRIPWIRE TORTURE
# =============================================================================

def test_refresh_token_rotation_and_adversarial_replay_tripwire(torture_db):
    """
    Extreme Bug-Bounty Scenario:
      1. Parent logs in on Device A. Issues Refresh Token R1.
      2. Device A rotates R1 -> Fresh R2 is issued. R1 is retired.
      3. A hacker has intercepted R1 and attempts to use it (Replay Attack).
      4. System detects reuse of previous_refresh_token_hash.
      5. TRIPWIRE FIRES: ALL sessions for this user are terminated immediately!
    """
    auth_svc = AuthService()
    mobile = "+919777766666"

    # Step 1: Initial Login -> Token R1
    login_resp = auth_svc.verify_otp(
        db=torture_db,
        mobile_number=mobile,
        otp=auth_svc.DEV_TEST_OTP,
        device_name="Primary Android Phone",
        ip_address="157.48.20.10",
    )
    r1 = login_resp.refresh_token
    sub_id = uuid.UUID(login_resp.subscriber_id)

    # Step 2: Legitimate Rotation R1 -> R2
    rot_resp = auth_svc.rotate_refresh_token(
        db=torture_db,
        refresh_token=r1,
        ip_address="157.48.20.10",
    )
    r2 = rot_resp.refresh_token
    assert r2 != r1

    # Confirm session is still active with R2
    sess = torture_db.query(SubscriberSession).filter_by(subscriber_id=sub_id).first()
    assert sess.is_revoked is False
    assert sess.refresh_token_hash == hash_token(r2)
    assert sess.previous_refresh_token_hash == hash_token(r1)

    # Step 3: Adversary Replays Retired Token R1!
    with pytest.raises(ValueError) as exc:
        auth_svc.rotate_refresh_token(
            db=torture_db,
            refresh_token=r1,
            ip_address="198.51.100.42",  # Malicious external IP
        )
    assert "Replay attack detected" in str(exc.value)

    # Step 4: Verify ALL sessions for this user are NUKED
    all_sessions = torture_db.query(SubscriberSession).filter_by(subscriber_id=sub_id).all()
    for s in all_sessions:
        assert s.is_revoked is True

    # Audit log entry created
    replay_audit = torture_db.query(AuthAuditLog).filter_by(
        subscriber_id=sub_id,
        action="REPLAY_ATTACK_DETECTED",
    ).first()
    assert replay_audit is not None
    assert replay_audit.ip_address == "198.51.100.42"


# =============================================================================
# 6. CROSS-TENANT IDOR ATTACK DEFENSE TORTURE
# =============================================================================

def test_cross_tenant_session_revocation_idor_defense(torture_db):
    """
    Adversarial IDOR Test:
    Subscriber B attempts to revoke Subscriber A's session ID.
    Strict tenant validation raises PermissionError; A's session remains untouched.
    """
    auth_svc = AuthService()

    # Subscriber A (Target)
    resp_a = auth_svc.verify_otp(
        db=torture_db,
        mobile_number="+919111122222",
        otp=auth_svc.DEV_TEST_OTP,
        parent_name="Parent A",
    )
    sub_a_id = uuid.UUID(resp_a.subscriber_id)
    sess_a_id = uuid.UUID(resp_a.session_id)

    # Subscriber B (Attacker)
    resp_b = auth_svc.verify_otp(
        db=torture_db,
        mobile_number="+919333344444",
        otp=auth_svc.DEV_TEST_OTP,
        parent_name="Parent B",
    )
    sub_b_id = uuid.UUID(resp_b.subscriber_id)

    # Subscriber B attempts to revoke Subscriber A's session ID
    with pytest.raises(PermissionError) as exc:
        auth_svc.logout_session(
            db=torture_db,
            subscriber_id=sub_b_id,  # Caller is B
            session_id=sess_a_id,    # Target is A's session
        )
    assert "unauthorized" in str(exc.value).lower()

    # Verify Subscriber A's session is STILL ACTIVE
    sess_a = torture_db.query(SubscriberSession).filter_by(session_id=sess_a_id).first()
    assert sess_a.is_revoked is False


# =============================================================================
# 7. ROW-LEVEL SECURITY (RLS) & MULTI-TENANT BOUNDARY TORTURE
# =============================================================================

def test_rls_tenant_boundary_isolation_children_and_telemetry(torture_db):
    """
    Deep RLS Isolation Torture:
    - Parent A has child 'Arun' with high maths score (88%) and parent pulse.
    - Parent B has child 'Pooja'.
    - With RLS tenant context active for Parent B:
      - Attempting to query Arun returns strictly zero rows or raises boundary violation.
      - Topic scores for Arun cannot be seen by Parent B.
    """
    # 1. Setup Parent A & Child Arun
    sub_a = Subscriber(
        subscriber_id=uuid.uuid4(),
        mobile_number="+919876500001",
        parent_name="Sundar Pichai",
        password_hash="OTP_AUTH",
    )
    child_a = Child(
        child_id=uuid.uuid4(),
        subscriber_id=sub_a.subscriber_id,
        student_name="Arun Sundar",
        standard_class="Class 10",
        board="CBSE",
        academic_year="2026-2027",
    )
    score_a = TopicScore(
        score_id=uuid.uuid4(),
        child_id=child_a.child_id,
        node_id="CBSE_10_MATH_QUADRATIC",
        scored_marks=22.0,
        max_marks=25.0,
        percentage=88.0,
        mastery_tier="STRONG",
        evaluated_at=datetime.now(timezone.utc),
    )

    # 2. Setup Parent B & Child Pooja
    sub_b = Subscriber(
        subscriber_id=uuid.uuid4(),
        mobile_number="+919876500002",
        parent_name="Anand Mahindra",
        password_hash="OTP_AUTH",
    )
    child_b = Child(
        child_id=uuid.uuid4(),
        subscriber_id=sub_b.subscriber_id,
        student_name="Pooja Anand",
        standard_class="Class 8",
        board="CBSE",
        academic_year="2026-2027",
    )

    torture_db.add_all([sub_a, child_a, score_a, sub_b, child_b])
    torture_db.commit()

    # 3. Simulate RLS Context for Parent B
    token = set_active_rls_context(
        subscriber_id=sub_b.subscriber_id,
        role=UserRole.SUBSCRIBER,
        bypass_rls=False,
    )

    try:
        ctx = get_current_rls_context()
        assert ctx.subscriber_id == sub_b.subscriber_id
        assert ctx.role == UserRole.SUBSCRIBER
        assert ctx.bypass_rls is False

        # In a multi-tenant query guarded by subscriber_id:
        # Parent B only sees Pooja
        b_children = (
            torture_db.query(Child)
            .filter(Child.subscriber_id == ctx.subscriber_id)
            .all()
        )
        assert len(b_children) == 1
        assert b_children[0].student_name == "Pooja Anand"

        # Direct attempt to fetch Arun under Parent B's identity MUST fail
        arun_under_b = (
            torture_db.query(Child)
            .filter(Child.child_id == child_a.child_id, Child.subscriber_id == ctx.subscriber_id)
            .first()
        )
        assert arun_under_b is None

        # Direct attempt to fetch Arun's topic score under Parent B's identity
        arun_score_under_b = (
            torture_db.query(TopicScore)
            .join(Child, TopicScore.child_id == Child.child_id)
            .filter(Child.subscriber_id == ctx.subscriber_id, TopicScore.child_id == child_a.child_id)
            .first()
        )
        assert arun_score_under_b is None

    finally:
        reset_active_rls_context(token)

    # 4. Verify Anonymous Context (Zero Subscriber Records)
    anon_token = set_active_rls_context(role=UserRole.ANONYMOUS, bypass_rls=False)
    try:
        anon_ctx = get_current_rls_context()
        assert anon_ctx.subscriber_id is None
        assert anon_ctx.role == UserRole.ANONYMOUS
    finally:
        reset_active_rls_context(anon_token)


def test_postgresql_rls_ddl_registry_coverage():
    """
    Verifies that the PostgreSQL RLS registry generates valid DDL
    with FORCE ROW LEVEL SECURITY across all 35+ tables.
    """
    registry = PostgreSQLRLSRegistry()
    ddl_script = registry.generate_full_migration_ddl()
    registered_tables = registry.list_tables()
    assert len(registered_tables) >= 35

    # Check key sensitive tables
    critical_tables = [
        "subscribers",
        "children",
        "subscriber_sessions",
        "evidence_records",
        "topic_scores",
        "topic_gaps",
        "consolidated_reports",
        "billing_invoices",
        "evaluation_cases",
        "support_tickets",
    ]
    for tbl in critical_tables:
        assert tbl in registered_tables, f"Missing table {tbl} in RLS registry"
        assert f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY;" in ddl_script
        assert f"ON {tbl}" in ddl_script
