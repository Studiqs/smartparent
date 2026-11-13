"""
STUDIQS® SmartParent™ (v6.3 Complete) - Enterprise Role-Based Access Control (RBAC)
====================================================================================
Module: src.smartparent.core.rbac

Implements Industry-Standard 3-Role Unified Access Control:
  1. SUPERADMIN   - Platform owner, security, billing audit, system administrator
  2. PARENT       - Family account holder & student subscriber (child management, diagnostics, pulse, billing)
  3. EXPERT       - Certified subject teacher & answer sheet evaluator

Includes seamless backward-compatibility mapping for existing audit trails and tokens.
====================================================================================
"""

from enum import Enum
from typing import Dict, FrozenSet, Iterable, List, Optional, Set, Union


# =============================================================================
# 1. System Roles (Consolidated 3-Role Architecture)
# =============================================================================

class UserRole(str, Enum):
    """
    Core Actor Roles in the Studiqs Ecosystem:
      - SUPERADMIN: Full system governance, curriculum control, and executive billing
      - PARENT: Family Account Holder & Learner subscriber (Unified Parent + Student)
      - EXPERT: Certified Subject Teacher & Answer Sheet Evaluator
    """
    SUPERADMIN = "superadmin"
    PARENT = "parent"
    EXPERT = "expert"

    # Backward-compatibility aliases so existing references resolve seamlessly
    SUBSCRIBER = "parent"
    STUDENT = "parent"
    ADMIN = "superadmin"
    SUPPORT_AGENT = "superadmin"

    @classmethod
    def from_str(cls, role_str: Union["UserRole", str, None]) -> "UserRole":
        """
        Converts string or enum safely to canonical UserRole enum or defaults to PARENT.
        Maps historical/synonym strings to the 3 canonical roles:
          - "superadmin", "admin", "support_agent", "support", "system" -> SUPERADMIN
          - "parent", "subscriber", "student", "user", "family"        -> PARENT
          - "expert", "teacher", "evaluator"                           -> EXPERT
        """
        if isinstance(role_str, cls):
            return role_str
        if not role_str:
            return cls.PARENT
        val = getattr(role_str, "value", str(role_str))
        normalized = str(val).lower().strip()
        if normalized.startswith("userrole."):
            normalized = normalized.split(".", 1)[1]
        if normalized in ("superadmin", "admin", "support_agent", "support", "system"):
            return cls.SUPERADMIN
        elif normalized in ("parent", "subscriber", "student", "user", "family"):
            return cls.PARENT
        elif normalized in ("expert", "teacher", "evaluator"):
            return cls.EXPERT
        try:
            return cls(normalized)
        except (ValueError, AttributeError):
            return cls.PARENT


# =============================================================================
# 2. Granular Domain Permissions
# =============================================================================

class Permission(str, Enum):
    """
    Fine-Grained Capability Keys enforced at API endpoint boundaries.
    """
    # --- Identity & Family Management ---
    SUBSCRIBER_READ = "subscriber:read"
    SUBSCRIBER_UPDATE = "subscriber:update"
    SUBSCRIBER_DELETE = "subscriber:delete"

    CHILD_CREATE = "child:create"
    CHILD_READ = "child:read"
    CHILD_UPDATE = "child:update"
    CHILD_DELETE = "child:delete"

    # --- Evidence & Assessment Ingestion ---
    EVIDENCE_UPLOAD = "evidence:upload"
    EVIDENCE_READ = "evidence:read"
    EVIDENCE_DELETE = "evidence:delete"
    MARKS_GRID_SUBMIT = "marks_grid:submit"

    # --- Diagnostics & Reporting ---
    DIAGNOSTIC_READ = "diagnostic:read"
    DIAGNOSTIC_RECHECK = "diagnostic:recheck"
    REPORT_READ = "report:read"
    REPORT_EXPORT = "report:export"
    PULSE_READ = "pulse:read"
    PULSE_ACTION_UPDATE = "pulse:action_update"

    # --- Subject Expert Marketplace ---
    CASE_BOOK = "case:book"
    CASE_READ_OWN = "case:read_own"
    CASE_DISPUTE = "case:dispute"
    CASE_REVIEW = "case:review"

    # Expert-Specific Capabilities
    EXPERT_READ_ASSIGNED = "expert:read_assigned"
    EXPERT_EVALUATE = "expert:evaluate"
    EXPERT_ANNOTATE = "expert:annotate"
    EXPERT_PAYOUT_READ = "expert:payout_read"

    # --- Subscription & Billing Management ---
    SUBSCRIPTION_CREATE = "subscription:create"
    SUBSCRIPTION_READ = "subscription:read"
    SUBSCRIPTION_CANCEL = "subscription:cancel"
    INVOICE_READ = "invoice:read"
    INVOICE_DOWNLOAD = "invoice:download"

    # --- Customer Support Desk ---
    SUPPORT_TICKET_CREATE = "support:ticket_create"
    SUPPORT_TICKET_READ_OWN = "support:ticket_read_own"
    SUPPORT_TICKET_REPLY = "support:ticket_reply"
    SUPPORT_TICKET_MANAGE = "support:ticket_manage"
    SUPPORT_TICKET_RESOLVE = "support:ticket_resolve"

    # --- Curriculum & Academic Administration ---
    CURRICULUM_READ = "curriculum:read"
    CURRICULUM_MANAGE = "curriculum:manage"

    # --- Voice Assistant (Pro Only) ---
    VOICE_QUERY = "voice:query"

    # --- Administrative Privileges ---
    ADMIN_TELEMETRY_READ = "admin:telemetry_read"
    ADMIN_USER_MANAGE = "admin:user_manage"
    ADMIN_BILLING_AUDIT = "admin:billing_audit"
    ADMIN_ALL = "admin:all"


# =============================================================================
# 3. Role-to-Permission Mapping Matrix (3 Roles)
# =============================================================================

ROLE_PERMISSIONS: Dict[UserRole, FrozenSet[Permission]] = {
    # 1. PARENT (Family Account Holder & Student Subscriber)
    UserRole.PARENT: frozenset({
        Permission.SUBSCRIBER_READ,
        Permission.SUBSCRIBER_UPDATE,
        Permission.CHILD_CREATE,
        Permission.CHILD_READ,
        Permission.CHILD_UPDATE,
        Permission.CHILD_DELETE,
        Permission.EVIDENCE_UPLOAD,
        Permission.EVIDENCE_READ,
        Permission.EVIDENCE_DELETE,
        Permission.MARKS_GRID_SUBMIT,
        Permission.DIAGNOSTIC_READ,
        Permission.DIAGNOSTIC_RECHECK,
        Permission.REPORT_READ,
        Permission.REPORT_EXPORT,
        Permission.PULSE_READ,
        Permission.PULSE_ACTION_UPDATE,
        Permission.CASE_BOOK,
        Permission.CASE_READ_OWN,
        Permission.CASE_DISPUTE,
        Permission.CASE_REVIEW,
        Permission.SUBSCRIPTION_CREATE,
        Permission.SUBSCRIPTION_READ,
        Permission.SUBSCRIPTION_CANCEL,
        Permission.INVOICE_READ,
        Permission.INVOICE_DOWNLOAD,
        Permission.SUPPORT_TICKET_CREATE,
        Permission.SUPPORT_TICKET_READ_OWN,
        Permission.SUPPORT_TICKET_REPLY,
        Permission.CURRICULUM_READ,
        Permission.VOICE_QUERY,
    }),

    # 2. EXPERT (Certified Subject Teacher & Answer Sheet Evaluator)
    UserRole.EXPERT: frozenset({
        Permission.EXPERT_READ_ASSIGNED,
        Permission.EXPERT_EVALUATE,
        Permission.EXPERT_ANNOTATE,
        Permission.EXPERT_PAYOUT_READ,
        Permission.CASE_READ_OWN,
        Permission.SUPPORT_TICKET_CREATE,
        Permission.SUPPORT_TICKET_READ_OWN,
        Permission.SUPPORT_TICKET_REPLY,
        Permission.CURRICULUM_READ,
    }),

    # 3. SUPERADMIN (Executive Platform Governance - All Permissions)
    UserRole.SUPERADMIN: frozenset(Permission),
}


# =============================================================================
# 4. Role Hierarchy & Inheritance
# =============================================================================

ROLE_HIERARCHY: Dict[UserRole, Set[UserRole]] = {
    # SUPERADMIN can act in any role capacity across the platform
    UserRole.SUPERADMIN: {
        UserRole.SUPERADMIN,
        UserRole.PARENT,
        UserRole.EXPERT,
    },
    # PARENT domain is strictly for family subscriber capabilities
    UserRole.PARENT: {
        UserRole.PARENT,
    },
    # EXPERT domain is strictly for evaluation & assessment capabilities
    UserRole.EXPERT: {
        UserRole.EXPERT,
    },
}


# =============================================================================
# 5. RBAC Evaluation Engine
# =============================================================================

def get_permissions_for_role(role: Union[UserRole, str]) -> List[str]:
    """
    Returns the complete list of permission string identifiers granted to a role.
    """
    role_enum = UserRole.from_str(role)
    perms = ROLE_PERMISSIONS.get(role_enum, frozenset())
    return sorted([p.value for p in perms])


def has_role(
    user_role: Union[UserRole, str],
    allowed_roles: Iterable[Union[UserRole, str]],
) -> bool:
    """
    Evaluates whether the user's role satisfies any of the allowed roles,
    accounting for 3-role hierarchical inheritance and alias normalization.
    """
    user_role_enum = UserRole.from_str(user_role)
    effective_roles = ROLE_HIERARCHY.get(user_role_enum, {user_role_enum})

    for allowed in allowed_roles:
        allowed_enum = UserRole.from_str(allowed)
        if allowed_enum in effective_roles:
            return True

    return False


def has_permission(
    user_role: Union[UserRole, str],
    permission: Union[Permission, str],
    explicit_user_permissions: Optional[Iterable[str]] = None,
) -> bool:
    """
    Checks if a user role (or explicit permission grant) possesses a required permission.
    Superadmin automatically satisfies all permissions.
    """
    user_role_enum = UserRole.from_str(user_role)

    if user_role_enum == UserRole.SUPERADMIN:
        return True

    perm_value = permission.value if isinstance(permission, Permission) else str(permission)

    # Check explicit custom permissions
    if explicit_user_permissions and perm_value in explicit_user_permissions:
        return True

    # Check role-based matrix
    role_perms = ROLE_PERMISSIONS.get(user_role_enum, frozenset())
    return any(p.value == perm_value for p in role_perms)
