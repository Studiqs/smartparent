"""
STUDIQS® SmartParent™ (v6.3 Complete) - Section 2 & Enterprise RBAC Test Suite
================================================================================
Comprehensive Industry-Standard Verification for 3-Role Architecture:
  1. Role & Permission Matrix (NIST/OWASP Least Privilege for 3 Roles)
  2. Hierarchical Role Inheritance (Superadmin, Parent, Expert)
  3. PyJWT Claims Generation (Role & Permissions embedding)
  4. Declarative Dependency Guards (require_roles & require_permissions)
  5. 403 Forbidden Rejections & Security Audit Logging (AuthAuditLog)
  6. Deactivated Account Quarantine
  7. Cross-Role Isolation (Expert vs Parent vs Superadmin)
  8. Tampered Token Signature Rejection
================================================================================
"""

import uuid
import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from fastapi import FastAPI, Depends, status
from fastapi.testclient import TestClient

@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"

@compiles(PG_UUID, "sqlite")
def compile_uuid_sqlite(type_, compiler, **kw):
    return "CHAR(36)"

from src.smartparent.db.base import Base
import src.smartparent.db.models  # load all models into Base.metadata
from src.smartparent.db.models.auth import (
    Subscriber,
    Child,
    SubscriberSession,
    AuthAuditLog,
)
from src.smartparent.core.security import (
    create_access_token,
    decode_token,
    get_password_hash,
)
from src.smartparent.core.rbac import (
    UserRole,
    Permission,
    ROLE_PERMISSIONS,
    ROLE_HIERARCHY,
    get_permissions_for_role,
    has_role,
    has_permission,
)
from src.smartparent.api.deps import (
    get_db,
    get_current_user,
    require_roles,
    require_permissions,
    AuthenticatedUser,
    get_current_subscriber_id,
    get_current_parent_id,
    get_current_admin_id,
    get_current_expert_id,
)
from src.smartparent.services.auth_service import auth_service
from src.smartparent.schemas.auth import (
    AddStudentRequest,
    PasswordLoginRequest,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(scope="module")
def rbac_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture(scope="function")
def rbac_session(rbac_engine):
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=rbac_engine)
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()


@pytest.fixture(scope="module")
def rbac_test_app(rbac_engine):
    """Mini FastAPI application testing declarative 3-role RBAC dependencies."""
    app = FastAPI(title="RBAC Guard Test App")
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=rbac_engine)

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    # Protected Endpoints
    @app.get("/api/v1/protected/parent-only")
    def parent_route(user: AuthenticatedUser = Depends(require_roles(UserRole.PARENT))):
        return {"status": "SUCCESS", "message": "Welcome parent", "user_id": str(user.user_id), "role": user.role.value}

    @app.get("/api/v1/protected/admin-only")
    def admin_route(user: AuthenticatedUser = Depends(require_roles(UserRole.SUPERADMIN))):
        return {"status": "SUCCESS", "message": "Welcome superadmin", "role": user.role.value}

    @app.get("/api/v1/protected/expert-only")
    def expert_route(user: AuthenticatedUser = Depends(require_roles(UserRole.EXPERT))):
        return {"status": "SUCCESS", "message": "Welcome expert", "role": user.role.value}

    @app.post("/api/v1/protected/evidence-upload")
    def upload_route(user: AuthenticatedUser = Depends(require_permissions(Permission.EVIDENCE_UPLOAD))):
        return {"status": "SUCCESS", "message": "Upload permitted"}

    @app.post("/api/v1/protected/expert-evaluate")
    def evaluate_route(user: AuthenticatedUser = Depends(require_permissions(Permission.EXPERT_EVALUATE))):
        return {"status": "SUCCESS", "message": "Evaluation permitted"}

    @app.delete("/api/v1/protected/delete-child")
    def delete_child_route(user: AuthenticatedUser = Depends(require_permissions(Permission.CHILD_DELETE))):
        return {"status": "SUCCESS", "message": "Child deleted"}

    return app


@pytest.fixture(scope="module")
def rbac_client(rbac_test_app):
    return TestClient(rbac_test_app)


# =============================================================================
# Test Suite: Principal Verification of 3-Role Architecture
# =============================================================================

class TestSection2RBACProductionSuite:

    # -------------------------------------------------------------------------
    # 1. NIST/OWASP 3-Role & Permission Matrix Integrity
    # -------------------------------------------------------------------------
    def test_tc1_role_permission_definitions(self):
        """TC1: Every role in the 3-role model has comprehensive and mutually exclusive capabilities."""
        # 1. Superadmin has full wildcard access
        assert len(ROLE_PERMISSIONS[UserRole.SUPERADMIN]) == len(Permission)
        assert has_permission(UserRole.SUPERADMIN, Permission.CHILD_DELETE) is True
        assert has_permission(UserRole.SUPERADMIN, Permission.ADMIN_ALL) is True
        assert has_permission(UserRole.SUPERADMIN, Permission.EXPERT_EVALUATE) is True

        # 2. Parent has family & diagnostic capabilities, but zero expert evaluation or admin telemetry
        parent_perms = ROLE_PERMISSIONS[UserRole.PARENT]
        assert Permission.CHILD_CREATE in parent_perms
        assert Permission.CHILD_DELETE in parent_perms
        assert Permission.EVIDENCE_UPLOAD in parent_perms
        assert Permission.REPORT_READ in parent_perms
        assert Permission.SUBSCRIPTION_CREATE in parent_perms
        assert Permission.VOICE_QUERY in parent_perms
        assert Permission.EXPERT_EVALUATE not in parent_perms
        assert Permission.ADMIN_TELEMETRY_READ not in parent_perms
        assert Permission.ADMIN_ALL not in parent_perms

        # 3. Expert has evaluation permissions, zero parent child management or billing operations
        expert_perms = ROLE_PERMISSIONS[UserRole.EXPERT]
        assert Permission.EXPERT_EVALUATE in expert_perms
        assert Permission.EXPERT_ANNOTATE in expert_perms
        assert Permission.EXPERT_PAYOUT_READ in expert_perms
        assert Permission.CHILD_CREATE not in expert_perms
        assert Permission.CHILD_DELETE not in expert_perms
        assert Permission.SUBSCRIPTION_CANCEL not in expert_perms

    # -------------------------------------------------------------------------
    # 2. Hierarchical Role Inheritance in 3-Role Model
    # -------------------------------------------------------------------------
    def test_tc2_hierarchical_role_inheritance(self):
        """TC2: Superadmin satisfies Parent and Expert; Parent and Expert are strictly isolated."""
        # 1. Superadmin can act in any role
        assert has_role(UserRole.SUPERADMIN, [UserRole.PARENT]) is True
        assert has_role(UserRole.SUPERADMIN, [UserRole.EXPERT]) is True
        assert has_role(UserRole.SUPERADMIN, [UserRole.SUPERADMIN]) is True
        assert has_role(UserRole.SUPERADMIN, ["admin"]) is True

        # 2. Parent satisfies Parent and backward-compatible aliases (Subscriber, Student)
        assert has_role(UserRole.PARENT, [UserRole.PARENT]) is True
        assert has_role(UserRole.PARENT, [UserRole.SUBSCRIBER]) is True
        assert has_role(UserRole.PARENT, ["subscriber"]) is True
        assert has_role(UserRole.PARENT, ["student"]) is True
        assert has_role("subscriber", [UserRole.PARENT]) is True

        # 3. Parent CANNOT act as Expert or Superadmin
        assert has_role(UserRole.PARENT, [UserRole.EXPERT]) is False
        assert has_role(UserRole.PARENT, [UserRole.SUPERADMIN]) is False
        assert has_role(UserRole.PARENT, ["superadmin"]) is False

        # 4. Expert CANNOT act as Parent or Superadmin
        assert has_role(UserRole.EXPERT, [UserRole.PARENT]) is False
        assert has_role(UserRole.EXPERT, [UserRole.SUPERADMIN]) is False

    # -------------------------------------------------------------------------
    # 3. PyJWT Claims Generation & Introspection
    # -------------------------------------------------------------------------
    def test_tc3_token_generation_embeds_rbac_claims(self, rbac_session):
        """TC3: OTP login issues JWT containing canonical 'parent' role and fine-grained permissions."""
        mobile = "+919876543210"
        otp_res = auth_service.send_otp(mobile_number=mobile, db=rbac_session, is_dev_sandbox=True)
        assert otp_res.dev_otp is not None

        # Verify OTP
        verify_res = auth_service.verify_otp(
            mobile_number=mobile,
            otp=otp_res.dev_otp,
            session_token=otp_res.session_token,
            db=rbac_session,
        )

        assert verify_res.role == "parent"
        assert len(verify_res.permissions) > 0
        assert "child:create" in verify_res.permissions
        assert "evidence:upload" in verify_res.permissions

        # Inspect decoded JWT payload
        payload = decode_token(verify_res.access_token)
        assert payload["role"] == "parent"
        assert "child:create" in payload["permissions"]
        assert payload["sub"] == verify_res.subscriber_id

    # -------------------------------------------------------------------------
    # 4. Declarative Role Guard (require_roles)
    # -------------------------------------------------------------------------
    def test_tc4_require_roles_success_and_forbidden(self, rbac_client, rbac_session):
        """TC4: Parent accesses parent-only route; Expert access to parent-only is rejected with 403."""
        parent_id = uuid.uuid4()
        parent_token = create_access_token({
            "sub": str(parent_id),
            "role": "parent",
            "permissions": get_permissions_for_role(UserRole.PARENT),
        })

        expert_id = uuid.uuid4()
        expert_token = create_access_token({
            "sub": str(expert_id),
            "role": "expert",
            "permissions": get_permissions_for_role(UserRole.EXPERT),
        })

        # 1. Parent accesses parent route -> 200 OK
        res1 = rbac_client.get(
            "/api/v1/protected/parent-only",
            headers={"Authorization": f"Bearer {parent_token}"},
        )
        assert res1.status_code == status.HTTP_200_OK
        assert res1.json()["status"] == "SUCCESS"
        assert res1.json()["role"] == "parent"

        # 2. Expert attempts to access parent route -> 403 FORBIDDEN
        res2 = rbac_client.get(
            "/api/v1/protected/parent-only",
            headers={"Authorization": f"Bearer {expert_token}"},
        )
        assert res2.status_code == status.HTTP_403_FORBIDDEN
        assert "Access denied: Operation requires one of the following roles" in res2.json()["detail"]

        # 3. Verify security audit log record created for rejection
        audit = rbac_session.query(AuthAuditLog).filter_by(
            subscriber_id=expert_id,
            action="RBAC_ROLE_DENIED",
        ).first()
        assert audit is not None

    # -------------------------------------------------------------------------
    # 5. Declarative Permission Guard (require_permissions)
    # -------------------------------------------------------------------------
    def test_tc5_require_permissions_guard(self, rbac_client, rbac_session):
        """TC5: Parent attempting to access expert-only evaluation endpoint is rejected with 403."""
        parent_id = uuid.uuid4()
        parent_token = create_access_token({
            "sub": str(parent_id),
            "role": "parent",
            "permissions": get_permissions_for_role(UserRole.PARENT),
        })

        expert_id = uuid.uuid4()
        expert_token = create_access_token({
            "sub": str(expert_id),
            "role": "expert",
            "permissions": get_permissions_for_role(UserRole.EXPERT),
        })

        # 1. Parent attempts to call expert evaluation endpoint -> 403 Forbidden
        res = rbac_client.post(
            "/api/v1/protected/expert-evaluate",
            headers={"Authorization": f"Bearer {parent_token}"},
        )
        assert res.status_code == status.HTTP_403_FORBIDDEN
        assert "Missing required permissions" in res.json()["detail"]

        # 2. Audit record verification
        audit = rbac_session.query(AuthAuditLog).filter_by(
            subscriber_id=parent_id,
            action="RBAC_PERMISSION_DENIED",
        ).first()
        assert audit is not None

        # 3. Expert calls expert evaluation endpoint -> 200 OK
        res_expert = rbac_client.post(
            "/api/v1/protected/expert-evaluate",
            headers={"Authorization": f"Bearer {expert_token}"},
        )
        assert res_expert.status_code == status.HTTP_200_OK
        assert res_expert.json()["message"] == "Evaluation permitted"

    # -------------------------------------------------------------------------
    # 6. Deactivated Account Quarantine
    # -------------------------------------------------------------------------
    def test_tc6_deactivated_account_quarantine(self, rbac_session):
        """TC6: Account marked is_active=False cannot authenticate or access endpoints."""
        sub_id = uuid.uuid4()
        pwd_hash = get_password_hash("ValidPass123")
        deactivated_sub = Subscriber(
            subscriber_id=sub_id,
            mobile_number="+919999990001",
            parent_name="Deactivated User",
            password_hash=pwd_hash,
            subscription_plan="BASIC",
            role="parent",
            is_active=False,  # DEACTIVATED
        )
        rbac_session.add(deactivated_sub)
        rbac_session.commit()

        # Attempt password login
        with pytest.raises(ValueError, match="Account has been deactivated"):
            auth_service.login_with_password(
                db=rbac_session,
                mobile_or_email="+919999990001",
                password="ValidPass123",
            )

    # -------------------------------------------------------------------------
    # 7. Tampered Role Invalidation
    # -------------------------------------------------------------------------
    def test_tc7_tampered_role_token_rejected(self, rbac_client):
        """TC7: Attacker modifying JWT payload string without secret fails signature check (401)."""
        valid_token = create_access_token({
            "sub": str(uuid.uuid4()),
            "role": "parent",
        })

        # Tamper payload
        parts = valid_token.split(".")
        # Replace middle part with a forged base64 string claiming superadmin
        tampered_token = f"{parts[0]}.eyJyZXNlcnZlZCI6ICJmb3JnZWQiLCAncm9sZSc6ICdzdXBlcmFkbWluJ30.{parts[2]}"

        res = rbac_client.get(
            "/api/v1/protected/admin-only",
            headers={"Authorization": f"Bearer {tampered_token}"},
        )
        assert res.status_code == status.HTTP_401_UNAUTHORIZED

    # -------------------------------------------------------------------------
    # 8. Profile Endpoint Returns 3-Role Metadata
    # -------------------------------------------------------------------------
    def test_tc8_profile_endpoint_returns_rbac_metadata(self, rbac_session):
        """TC8: get_subscriber_profile exposes canonical role ('parent'), permissions, and active status."""
        sub_id = uuid.uuid4()
        sub = Subscriber(
            subscriber_id=sub_id,
            mobile_number=f"+9198{uuid.uuid4().hex[:8]}",
            parent_name="Meenakshi Sundaram",
            password_hash="fake",
            subscription_plan="ADVANCED",
            role="parent",
            is_active=True,
        )
        rbac_session.add(sub)
        rbac_session.commit()

        profile = auth_service.get_subscriber_profile(db=rbac_session, subscriber_id=sub_id)
        assert profile.role == "parent"
        assert profile.is_active is True
        assert len(profile.permissions) > 0
        assert "child:create" in profile.permissions
