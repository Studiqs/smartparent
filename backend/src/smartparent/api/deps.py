"""
STUDIQS® SmartParent™ (v6.2 & v6.3 Extension) - API Dependencies
=============================================================================
Module: src.smartparent.api.deps
Provides FastAPI dependency injection providers for:
  1. Database Sessions (Sync & Async)
  2. Authentication & JWT Validation (Subscriber & Admin)
  3. Tenant Context & Isolation
=============================================================================
"""

import uuid
from typing import Callable, Generator, Iterable, List, Optional, Set, Union
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.smartparent.config import settings
from src.smartparent.core.exceptions import InvalidTokenError, TokenExpiredError
from src.smartparent.core.security import decode_token
from src.smartparent.core.rbac import (
    UserRole,
    Permission,
    get_permissions_for_role,
    has_role,
    has_permission,
)
from src.smartparent.db.session import SyncSessionLocal
from src.smartparent.db.models.auth import Subscriber, AuthAuditLog

security_bearer = HTTPBearer(auto_error=False)


# =============================================================================
# 0. RBAC Authenticated Principal Model
# =============================================================================

class AuthenticatedUser(BaseModel):
    """
    Decoded and verified security principal representing the current request caller.
    """
    model_config = ConfigDict(extra="ignore")
    user_id: uuid.UUID
    role: UserRole
    permissions: List[str]
    subscription_plan: str = "BASIC"
    mobile_number: Optional[str] = None
    is_active: bool = True

    def can(self, permission: Union[Permission, str]) -> bool:
        perm_str = permission.value if isinstance(permission, Permission) else str(permission)
        return has_permission(self.role, perm_str, self.permissions)

    def has_any_role(self, *roles: Union[UserRole, str]) -> bool:
        return has_role(self.role, roles)


# =============================================================================
# 1. Database Session Dependency
# =============================================================================

def get_db() -> Generator[Session, None, None]:
    """Yields a synchronous SQLAlchemy session with guaranteed cleanup."""
    db = SyncSessionLocal()
    try:
        yield db
    finally:
        db.close()


# =============================================================================
# 2. RBAC Security Principal & Guard Dependencies
# =============================================================================

def get_current_user(
    auth: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    x_subscriber_id: Optional[str] = Header(None, alias="X-Subscriber-Id"),
    x_admin_id: Optional[str] = Header(None, alias="X-Admin-Id"),
    x_expert_id: Optional[str] = Header(None, alias="X-Expert-Id"),
    x_user_role: Optional[str] = Header(None, alias="X-User-Role"),
    db: Session = Depends(get_db),
) -> AuthenticatedUser:
    """
    Extracts, validates, and decodes the security principal from Bearer JWT or service headers.
    Resolves role, active status, and granular domain permissions.
    """
    # 1. Fast path: X-Admin-Id header
    if x_admin_id:
        try:
            admin_uuid = uuid.UUID(x_admin_id)
            role_val = UserRole.from_str(x_user_role or "admin")
            perms = get_permissions_for_role(role_val)
            return AuthenticatedUser(
                user_id=admin_uuid,
                role=role_val,
                permissions=perms,
                subscription_plan="PRO",
                is_active=True,
            )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Malformed X-Admin-Id header; valid UUID expected.",
            )

    # 2. Fast path: X-Expert-Id header
    if x_expert_id:
        try:
            expert_uuid = uuid.UUID(x_expert_id)
            role_val = UserRole.from_str(x_user_role or "expert")
            perms = get_permissions_for_role(role_val)
            return AuthenticatedUser(
                user_id=expert_uuid,
                role=role_val,
                permissions=perms,
                subscription_plan="BASIC",
                is_active=True,
            )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Malformed X-Expert-Id header; valid UUID expected.",
            )

    # 3. Fast path: X-Subscriber-Id header
    if x_subscriber_id:
        try:
            user_uuid = uuid.UUID(x_subscriber_id)
            subscriber = db.scalar(select(Subscriber).where(Subscriber.subscriber_id == user_uuid))
            if subscriber:
                if hasattr(subscriber, "is_active") and not subscriber.is_active:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Account has been deactivated. Please contact support.",
                    )
                role_val = UserRole.from_str(x_user_role or getattr(subscriber, "role", "parent") or "parent")
                plan = getattr(subscriber, "subscription_plan", "BASIC")
                mobile = getattr(subscriber, "mobile_number", None)
            else:
                role_val = UserRole.from_str(x_user_role or "parent")
                plan = "BASIC"
                mobile = None

            perms = get_permissions_for_role(role_val)
            return AuthenticatedUser(
                user_id=user_uuid,
                role=role_val,
                permissions=perms,
                subscription_plan=plan,
                mobile_number=mobile,
                is_active=True,
            )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Malformed X-Subscriber-Id header; valid UUID expected.",
            )

    # 4. Standard Bearer Token path
    if auth and auth.credentials:
        try:
            payload = decode_token(auth.credentials)
            sub = payload.get("sub")
            if not sub:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token missing 'sub' subject claim.",
                )
            user_uuid = uuid.UUID(sub)
            role_str = payload.get("role", "parent")
            role_val = UserRole.from_str(role_str)
            token_perms = payload.get("permissions")
            if not token_perms:
                token_perms = get_permissions_for_role(role_val)

            plan = payload.get("plan", "BASIC")
            mobile = payload.get("mobile")

            return AuthenticatedUser(
                user_id=user_uuid,
                role=role_val,
                permissions=token_perms,
                subscription_plan=plan,
                mobile_number=mobile,
                is_active=True,
            )
        except (InvalidTokenError, TokenExpiredError) as te:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(te),
            )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token subject is not a valid UUID.",
            )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Provide Authorization Bearer token or service identity header.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_roles(*allowed_roles: Union[UserRole, str]) -> Callable:
    """
    FastAPI dependency factory enforcing that caller role satisfies at least one allowed role.
    """
    def role_guard(
        user: AuthenticatedUser = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> AuthenticatedUser:
        if not user.has_any_role(*allowed_roles):
            role_strings = [r.value if isinstance(r, UserRole) else str(r) for r in allowed_roles]
            try:
                audit = AuthAuditLog(
                    subscriber_id=user.user_id,
                    mobile_number=user.mobile_number or "UNKNOWN",
                    action="RBAC_ROLE_DENIED",
                )
                db.add(audit)
                db.commit()
            except Exception:
                db.rollback()

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: Operation requires one of the following roles: {role_strings}. Caller has role '{user.role.value}'.",
            )
        return user
    return role_guard


def require_permissions(*required_permissions: Union[Permission, str]) -> Callable:
    """
    FastAPI dependency factory enforcing that caller possesses all specified permissions.
    """
    def permission_guard(
        user: AuthenticatedUser = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> AuthenticatedUser:
        missing = [p for p in required_permissions if not user.can(p)]
        if missing:
            missing_strings = [p.value if isinstance(p, Permission) else str(p) for p in missing]
            try:
                audit = AuthAuditLog(
                    subscriber_id=user.user_id,
                    mobile_number=user.mobile_number or "UNKNOWN",
                    action="RBAC_PERMISSION_DENIED",
                )
                db.add(audit)
                db.commit()
            except Exception:
                db.rollback()

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: Missing required permissions: {missing_strings}.",
            )
        return user
    return permission_guard


# =============================================================================
# 3. Role-Specialized Identity Extractors
# =============================================================================

def get_current_subscriber_id(
    user: AuthenticatedUser = Depends(require_roles(UserRole.PARENT, UserRole.SUPERADMIN)),
) -> uuid.UUID:
    """
    Extracts and validates that current caller has subscriber/parent authority.
    """
    return user.user_id


get_current_parent_id = get_current_subscriber_id


def get_current_subscriber(
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
    db: Session = Depends(get_db),
) -> Subscriber:
    """Fetches and verifies the active Subscriber entity."""
    subscriber = db.scalar(
        select(Subscriber).where(Subscriber.subscriber_id == subscriber_id)
    )
    if not subscriber:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subscriber {subscriber_id} not found.",
        )
    if hasattr(subscriber, "is_active") and not subscriber.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Subscriber account has been deactivated.",
        )
    return subscriber


get_current_parent = get_current_subscriber


def get_current_admin_id(
    user: AuthenticatedUser = Depends(require_roles(UserRole.SUPERADMIN)),
) -> uuid.UUID:
    """
    Validates administrative caller identity.
    """
    return user.user_id


def get_current_expert_id(
    user: AuthenticatedUser = Depends(require_roles(UserRole.EXPERT, UserRole.SUPERADMIN)),
) -> uuid.UUID:
    """
    Extracts and validates that current caller has expert evaluator authority.
    """
    return user.user_id
