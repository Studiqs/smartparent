"""
STUDIQS® SmartParent™ - Password, Forgot/Reset OTP & Profile Management Test Suite
=============================================================================
Module: tests.unit.test_auth_password_and_profile_suite

Verifies:
  1. Password Login via Mobile or Email with bcrypt hash validation.
  2. Setting and Changing password for authenticated subscribers.
  3. Forgot Password workflow: Dispatching OTP to registered mobile.
  4. Reset Password workflow: OTP verification, bcrypt hashing, and immediate token issuance.
  5. Parent Subscriber Profile retrieval and updating (Name, Email).
  6. Child Profile updating (Class, Board, Stream, Name) and multi-tenant security boundary.
  7. Soft-deleting child profile.
=============================================================================
"""

import uuid
import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID

from src.smartparent.db.base import Base
from src.smartparent.db.models.auth import Subscriber, Child, OTPVerificationSession
from src.smartparent.services.auth_service import AuthService
from src.smartparent.core.security import get_password_hash, verify_password
from src.smartparent.schemas.auth import (
    AddStudentRequest,
    UpdateStudentRequest,
)

# Register SQLite dialect mappings for PostgreSQL JSONB and UUID
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
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def auth_service():
    return AuthService()


def test_password_login_flow(db_session, auth_service):
    # 1. Create subscriber with bcrypt password
    sub_id = uuid.uuid4()
    sub = Subscriber(
        subscriber_id=sub_id,
        mobile_number="+919876543210",
        parent_name="Karthik Raman",
        email="karthik@example.com",
        password_hash=get_password_hash("StrongPass123"),
        subscription_plan="ADVANCED",
    )
    db_session.add(sub)
    db_session.commit()

    # 2. Login with correct mobile number and password
    res_mobile = auth_service.login_with_password(
        db=db_session,
        mobile_or_email="9876543210",
        password="StrongPass123",
    )
    assert res_mobile.subscriber_id == str(sub_id)
    assert res_mobile.access_token is not None
    assert res_mobile.parent_name == "Karthik Raman"

    # 3. Login with email
    res_email = auth_service.login_with_password(
        db=db_session,
        mobile_or_email="karthik@example.com",
        password="StrongPass123",
    )
    assert res_email.subscriber_id == str(sub_id)

    # 4. Login with incorrect password should raise ValueError
    with pytest.raises(ValueError, match="Incorrect password"):
        auth_service.login_with_password(
            db=db_session,
            mobile_or_email="9876543210",
            password="WrongPassword999",
        )

    # 5. Login with non-existent user should raise ValueError
    with pytest.raises(ValueError, match="No subscriber account found"):
        auth_service.login_with_password(
            db=db_session,
            mobile_or_email="9999999999",
            password="StrongPass123",
        )


def test_change_password_flow(db_session, auth_service):
    sub_id = uuid.uuid4()
    sub = Subscriber(
        subscriber_id=sub_id,
        mobile_number="+919811122233",
        parent_name="Meena Sundar",
        password_hash=get_password_hash("OldPassword123"),
    )
    db_session.add(sub)
    db_session.commit()

    # Incorrect current password fails
    with pytest.raises(ValueError, match="Current password does not match"):
        auth_service.change_password(
            db=db_session,
            subscriber_id=sub_id,
            old_password="WrongOldPass1",
            new_password="NewSecurePassword1",
        )

    # Correct current password succeeds
    res = auth_service.change_password(
        db=db_session,
        subscriber_id=sub_id,
        old_password="OldPassword123",
        new_password="NewSecurePassword1",
    )
    assert res.status == "SUCCESS"

    # Verify updated password works for login
    login_res = auth_service.login_with_password(
        db=db_session,
        mobile_or_email="+919811122233",
        password="NewSecurePassword1",
    )
    assert login_res.subscriber_id == str(sub_id)


def test_forgot_and_reset_password_via_otp(db_session, auth_service):
    sub_id = uuid.uuid4()
    sub = Subscriber(
        subscriber_id=sub_id,
        mobile_number="+919777888999",
        parent_name="Anand Kumar",
        password_hash="OTP_AUTHENTICATED",
    )
    db_session.add(sub)
    db_session.commit()

    # 1. Initiate forgot password
    forgot_res = auth_service.forgot_password_request(
        db=db_session,
        mobile_number="9777888999",
    )
    assert forgot_res.status == "OTP_SENT"
    assert forgot_res.session_token is not None

    # 2. Reset password using valid test OTP (123456 in dev sandbox)
    reset_res = auth_service.reset_password_with_otp(
        db=db_session,
        mobile_number="+919777888999",
        otp="123456",
        new_password="BrandNewPass456",
        session_token=forgot_res.session_token,
    )
    assert reset_res.subscriber_id == str(sub_id)
    assert reset_res.access_token is not None

    # 3. Verify newly set password works for password login
    login_res = auth_service.login_with_password(
        db=db_session,
        mobile_or_email="9777888999",
        password="BrandNewPass456",
    )
    assert login_res.subscriber_id == str(sub_id)


def test_subscriber_profile_management(db_session, auth_service):
    sub_id = uuid.uuid4()
    sub = Subscriber(
        subscriber_id=sub_id,
        mobile_number="+919555666777",
        parent_name="Vikram Singh",
        email=None,
        password_hash="OTP_AUTHENTICATED",
        subscription_plan="PRO",
    )
    db_session.add(sub)
    db_session.commit()

    # 1. Get profile
    prof = auth_service.get_subscriber_profile(db=db_session, subscriber_id=sub_id)
    assert prof.parent_name == "Vikram Singh"
    assert prof.subscription_plan == "PRO"
    assert prof.email is None

    # 2. Update profile (Name + Email)
    updated = auth_service.update_subscriber_profile(
        db=db_session,
        subscriber_id=sub_id,
        parent_name="Vikramaditya Singh",
        email="vikram@studiqs.com",
    )
    assert updated.parent_name == "Vikramaditya Singh"
    assert updated.email == "vikram@studiqs.com"


def test_child_profile_update_and_delete(db_session, auth_service):
    sub1_id = uuid.uuid4()
    sub2_id = uuid.uuid4()

    sub1 = Subscriber(subscriber_id=sub1_id, mobile_number="+919444111222", parent_name="Parent 1", password_hash="hash")
    sub2 = Subscriber(subscriber_id=sub2_id, mobile_number="+919444333444", parent_name="Parent 2", password_hash="hash")
    db_session.add_all([sub1, sub2])
    db_session.flush()

    # Onboard a student under sub1
    add_req = AddStudentRequest(
        student_name="Ananya",
        standard_class="Class 9",
        board="CBSE",
        academic_year="2025-2026",
    )
    student_res = auth_service.add_student(db=db_session, subscriber_id=sub1_id, payload=add_req)
    child_id = uuid.UUID(student_res.child_id)

    # 1. Update child profile (Move to Class 10 CBSE)
    update_req = UpdateStudentRequest(
        standard_class="Class 10",
        student_name="Ananya Sundaram",
    )
    updated_res = auth_service.update_student(
        db=db_session,
        subscriber_id=sub1_id,
        child_id=child_id,
        payload=update_req,
    )
    assert updated_res.standard_class == "Class 10"
    assert updated_res.student_name == "Ananya Sundaram"

    # 2. Multi-tenant Isolation Check: Parent 2 CANNOT update Parent 1's child!
    with pytest.raises(PermissionError, match="Child profile not found or access denied"):
        auth_service.update_student(
            db=db_session,
            subscriber_id=sub2_id,
            child_id=child_id,
            payload=update_req,
        )

    # 3. Soft-delete child profile
    del_res = auth_service.delete_student(db=db_session, subscriber_id=sub1_id, child_id=child_id)
    assert del_res.status == "SUCCESS"

    # Profile shows is_active=False
    child_in_db = db_session.query(Child).filter(Child.child_id == child_id).first()
    assert child_in_db.is_active is False

