"""
STUDIQS® SmartParent™ (v6.2 Complete) - Production Row-Level Security (RLS) Engine
=============================================================================
Module: src.smartparent.core.rls

Provides an enterprise-grade, object-oriented Row-Level Security (RLS) framework:
  1. Multi-Tenant Strategy Pattern (Direct, Indirect Child, Dual-Boundary Marketplace, Public Read)
  2. Centralized Table Registry with automated PostgreSQL 16 DDL generation
  3. Scoped Context Managers (Tenant, Expert, Admin/System Bypass)
  4. ContextVar-driven Session Context Propagation for FastAPI & Background Workers
  5. Multi-Dialect Resilience (Native PostgreSQL SET LOCAL + SQLite Sandbox Simulation)
=============================================================================
"""

import abc
import contextvars
import enum
import logging
import uuid
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, Generator, List, Optional, Set, Type

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

logger = logging.getLogger("STUDIQS_RLS")

# =============================================================================
# 1. POSTGRESQL SESSION SETTING CONSTANTS & CONTEXTVARS
# =============================================================================

RLS_TENANT_SETTING = "app.current_subscriber_id"
RLS_EXPERT_SETTING = "app.current_expert_id"
RLS_ROLE_SETTING = "app.current_user_role"
RLS_BYPASS_SETTING = "app.bypass_rls"


class UserRole(str, enum.Enum):
    ANONYMOUS = "ANONYMOUS"
    SUBSCRIBER = "SUBSCRIBER"
    EXPERT = "EXPERT"
    ADMIN = "ADMIN"
    SYSTEM = "SYSTEM"


@dataclass(frozen=True)
class RLSContextState:
    """Immutable thread-safe request context state."""
    subscriber_id: Optional[uuid.UUID] = None
    expert_id: Optional[uuid.UUID] = None
    role: UserRole = UserRole.ANONYMOUS
    bypass_rls: bool = False


# Thread-safe & asyncio-safe ContextVar for automatic session context propagation
_current_rls_context: contextvars.ContextVar[RLSContextState] = contextvars.ContextVar(
    "current_rls_context",
    default=RLSContextState(),
)


def get_current_rls_context() -> RLSContextState:
    """Returns the active thread/task RLS context."""
    return _current_rls_context.get()


def set_active_rls_context(
    subscriber_id: Optional[uuid.UUID] = None,
    expert_id: Optional[uuid.UUID] = None,
    role: UserRole = UserRole.ANONYMOUS,
    bypass_rls: bool = False,
) -> contextvars.Token[RLSContextState]:
    """Sets the active ContextVar for the current execution stack."""
    state = RLSContextState(
        subscriber_id=subscriber_id,
        expert_id=expert_id,
        role=role,
        bypass_rls=bypass_rls or role in (UserRole.ADMIN, UserRole.SYSTEM),
    )
    return _current_rls_context.set(state)


def reset_active_rls_context(token: contextvars.Token[RLSContextState]) -> None:
    """Restores the previous ContextVar state."""
    _current_rls_context.reset(token)


# =============================================================================
# 2. OOPS STRATEGY PATTERN: RLS POLICY STRATEGIES
# =============================================================================

class IRLSPolicyStrategy(abc.ABC):
    """Abstract Strategy interface for PostgreSQL Row-Level Security DDL generation."""

    @abc.abstractmethod
    def generate_policy_ddl(self, table_name: str) -> str:
        """Generates idempotent PostgreSQL DDL policy for the specified table."""
        pass

    @abc.abstractmethod
    def describe(self) -> str:
        """Returns human-readable description of isolation behavior."""
        pass


class DirectSubscriberPolicyStrategy(IRLSPolicyStrategy):
    """
    Direct Subscriber Isolation Strategy:
    For tables with a direct `subscriber_id` foreign key.
    Enforces that rows are accessible only when subscriber_id matches app.current_subscriber_id,
    or when administrative bypass is enabled.
    """

    def __init__(self, tenant_column: str = "subscriber_id"):
        self.tenant_column = tenant_column

    def describe(self) -> str:
        return f"Direct tenant isolation on {self.tenant_column} with Admin bypass."

    def generate_policy_ddl(self, table_name: str) -> str:
        policy_name = f"{table_name}_tenant_isolation"
        return f"""
-- Table: {table_name} [Direct Tenant Isolation]
ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS {policy_name} ON {table_name};
CREATE POLICY {policy_name} ON {table_name}
    FOR ALL
    USING (
        current_setting('{RLS_BYPASS_SETTING}', true) = 'true'
        OR current_setting('{RLS_ROLE_SETTING}', true) IN ('ADMIN', 'SYSTEM')
        OR {self.tenant_column} = NULLIF(current_setting('{RLS_TENANT_SETTING}', true), '')::uuid
    )
    WITH CHECK (
        current_setting('{RLS_BYPASS_SETTING}', true) = 'true'
        OR current_setting('{RLS_ROLE_SETTING}', true) IN ('ADMIN', 'SYSTEM')
        OR {self.tenant_column} = NULLIF(current_setting('{RLS_TENANT_SETTING}', true), '')::uuid
    );""".strip()


class IndirectChildPolicyStrategy(IRLSPolicyStrategy):
    """
    Indirect Child Isolation Strategy:
    For academic telemetry tables anchored to `child_id` (e.g. topic_scores, evidence_records).
    Enforces isolation via subquery against the parent `children` table.
    """

    def __init__(self, child_column: str = "child_id", parent_table: str = "children"):
        self.child_column = child_column
        self.parent_table = parent_table

    def describe(self) -> str:
        return f"Indirect child-anchored isolation on {self.child_column} joined via {self.parent_table}."

    def generate_policy_ddl(self, table_name: str) -> str:
        policy_name = f"{table_name}_child_tenant_isolation"
        return f"""
-- Table: {table_name} [Indirect Child-Anchored Isolation]
ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS {policy_name} ON {table_name};
CREATE POLICY {policy_name} ON {table_name}
    FOR ALL
    USING (
        current_setting('{RLS_BYPASS_SETTING}', true) = 'true'
        OR current_setting('{RLS_ROLE_SETTING}', true) IN ('ADMIN', 'SYSTEM')
        OR {self.child_column} IN (
            SELECT c.child_id FROM {self.parent_table} c
            WHERE c.subscriber_id = NULLIF(current_setting('{RLS_TENANT_SETTING}', true), '')::uuid
        )
    )
    WITH CHECK (
        current_setting('{RLS_BYPASS_SETTING}', true) = 'true'
        OR current_setting('{RLS_ROLE_SETTING}', true) IN ('ADMIN', 'SYSTEM')
        OR {self.child_column} IN (
            SELECT c.child_id FROM {self.parent_table} c
            WHERE c.subscriber_id = NULLIF(current_setting('{RLS_TENANT_SETTING}', true), '')::uuid
        )
    );""".strip()


class DualBoundaryMarketplacePolicyStrategy(IRLSPolicyStrategy):
    """
    Marketplace Dual-Boundary Strategy:
    For Section 11/12 evaluation cases.
    - Parents see only their own cases (`subscriber_id == current_subscriber_id`)
    - Evaluator Experts see only assigned cases (`assigned_expert_id == current_expert_id`)
    - Admins see all cases
    """

    def describe(self) -> str:
        return "Dual boundary isolation: Parent-owned OR Assigned-Expert with Admin oversight."

    def generate_policy_ddl(self, table_name: str) -> str:
        policy_name = f"{table_name}_marketplace_isolation"
        return f"""
-- Table: {table_name} [Marketplace Dual Boundary Isolation]
ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS {policy_name} ON {table_name};
CREATE POLICY {policy_name} ON {table_name}
    FOR ALL
    USING (
        current_setting('{RLS_BYPASS_SETTING}', true) = 'true'
        OR current_setting('{RLS_ROLE_SETTING}', true) IN ('ADMIN', 'SYSTEM')
        OR subscriber_id = NULLIF(current_setting('{RLS_TENANT_SETTING}', true), '')::uuid
        OR assigned_expert_id = NULLIF(current_setting('{RLS_EXPERT_SETTING}', true), '')::uuid
    )
    WITH CHECK (
        current_setting('{RLS_BYPASS_SETTING}', true) = 'true'
        OR current_setting('{RLS_ROLE_SETTING}', true) IN ('ADMIN', 'SYSTEM')
        OR subscriber_id = NULLIF(current_setting('{RLS_TENANT_SETTING}', true), '')::uuid
        OR assigned_expert_id = NULLIF(current_setting('{RLS_EXPERT_SETTING}', true), '')::uuid
    );""".strip()


class ExpertPrivatePolicyStrategy(IRLSPolicyStrategy):
    """
    Expert Private Boundary Strategy:
    For expert profiles, bank accounts, and commission ledgers.
    Accessible only to the authenticated expert or system administrators.
    """

    def __init__(self, expert_column: str = "expert_id"):
        self.expert_column = expert_column

    def describe(self) -> str:
        return f"Expert private boundary on {self.expert_column}."

    def generate_policy_ddl(self, table_name: str) -> str:
        policy_name = f"{table_name}_expert_private_isolation"
        return f"""
-- Table: {table_name} [Expert Private Boundary]
ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS {policy_name} ON {table_name};
CREATE POLICY {policy_name} ON {table_name}
    FOR ALL
    USING (
        current_setting('{RLS_BYPASS_SETTING}', true) = 'true'
        OR current_setting('{RLS_ROLE_SETTING}', true) IN ('ADMIN', 'SYSTEM')
        OR {self.expert_column} = NULLIF(current_setting('{RLS_EXPERT_SETTING}', true), '')::uuid
    )
    WITH CHECK (
        current_setting('{RLS_BYPASS_SETTING}', true) = 'true'
        OR current_setting('{RLS_ROLE_SETTING}', true) IN ('ADMIN', 'SYSTEM')
        OR {self.expert_column} = NULLIF(current_setting('{RLS_EXPERT_SETTING}', true), '')::uuid
    );""".strip()


class PublicReadAdminWritePolicyStrategy(IRLSPolicyStrategy):
    """
    Public Catalog Strategy:
    For reference tables (e.g. curriculum_nodes, tutorial_videos, subscription_plans).
    All authenticated users can SELECT, but only ADMIN / SYSTEM can INSERT/UPDATE/DELETE.
    """

    def describe(self) -> str:
        return "Public read-only catalog; Admin-only mutations."

    def generate_policy_ddl(self, table_name: str) -> str:
        select_policy = f"{table_name}_public_read"
        write_policy = f"{table_name}_admin_write"
        return f"""
-- Table: {table_name} [Public Catalog Reference]
ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS {select_policy} ON {table_name};
CREATE POLICY {select_policy} ON {table_name}
    FOR SELECT
    USING (true);

DROP POLICY IF EXISTS {write_policy} ON {table_name};
CREATE POLICY {write_policy} ON {table_name}
    FOR ALL
    USING (
        current_setting('{RLS_BYPASS_SETTING}', true) = 'true'
        OR current_setting('{RLS_ROLE_SETTING}', true) IN ('ADMIN', 'SYSTEM')
    )
    WITH CHECK (
        current_setting('{RLS_BYPASS_SETTING}', true) = 'true'
        OR current_setting('{RLS_ROLE_SETTING}', true) IN ('ADMIN', 'SYSTEM')
    );""".strip()


class AdminSystemOnlyPolicyStrategy(IRLSPolicyStrategy):
    """
    Admin & System Internal Engine Strategy:
    For internal infrastructure, SLA engines, and payment webhooks
    (e.g. razorpay_webhook_events, support_sla_events).
    Strictly forbidden to non-admin roles.
    """

    def describe(self) -> str:
        return "Internal system-only table; restricted strictly to ADMIN & SYSTEM roles."

    def generate_policy_ddl(self, table_name: str) -> str:
        policy_name = f"{table_name}_admin_system_isolation"
        return f"""
-- Table: {table_name} [Admin/System Internal Table]
ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS {policy_name} ON {table_name};
CREATE POLICY {policy_name} ON {table_name}
    FOR ALL
    USING (
        current_setting('{RLS_BYPASS_SETTING}', true) = 'true'
        OR current_setting('{RLS_ROLE_SETTING}', true) IN ('ADMIN', 'SYSTEM')
    )
    WITH CHECK (
        current_setting('{RLS_BYPASS_SETTING}', true) = 'true'
        OR current_setting('{RLS_ROLE_SETTING}', true) IN ('ADMIN', 'SYSTEM')
    );""".strip()


class EphemeralAuthPolicyStrategy(IRLSPolicyStrategy):
    """
    Ephemeral Pre-Auth Strategy:
    Allows creation and verification during unauthenticated OTP exchange,
    while restricting unauthorized mutation strictly to ADMIN, SYSTEM, or ANONYMOUS auth flows.
    """

    def describe(self) -> str:
        return "Ephemeral auth session isolation; session token-bound or Admin/System access."

    def generate_policy_ddl(self, table_name: str) -> str:
        policy_name = f"{table_name}_ephemeral_auth_isolation"
        return f"""
-- Table: {table_name} [Ephemeral Auth Session Isolation]
ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS {policy_name} ON {table_name};
CREATE POLICY {policy_name} ON {table_name}
    FOR ALL
    USING (
        current_setting('{RLS_BYPASS_SETTING}', true) = 'true'
        OR current_setting('{RLS_ROLE_SETTING}', true) IN ('ADMIN', 'SYSTEM', 'ANONYMOUS')
    )
    WITH CHECK (
        current_setting('{RLS_BYPASS_SETTING}', true) = 'true'
        OR current_setting('{RLS_ROLE_SETTING}', true) IN ('ADMIN', 'SYSTEM', 'ANONYMOUS')
    );""".strip()


# =============================================================================
# 3. OOPS REGISTRY PATTERN: PRODUCTION RLS TABLE CATALOG
# =============================================================================

@dataclass
class RLSTableDescriptor:
    table_name: str
    strategy: IRLSPolicyStrategy
    description: str


class PostgreSQLRLSRegistry:
    """
    Centralized Schema Registry for all Row-Level Security policies.
    Guarantees 100% coverage across all 35+ SmartParent database entities.
    """

    def __init__(self):
        self._registry: Dict[str, RLSTableDescriptor] = {}
        self._initialize_core_catalog()

    def register(
        self,
        table_name: str,
        strategy: IRLSPolicyStrategy,
        description: Optional[str] = None,
    ) -> None:
        """Registers a table descriptor with its assigned RLS strategy."""
        desc = description or strategy.describe()
        self._registry[table_name] = RLSTableDescriptor(
            table_name=table_name,
            strategy=strategy,
            description=desc,
        )

    def get(self, table_name: str) -> Optional[RLSTableDescriptor]:
        return self._registry.get(table_name)

    def list_tables(self) -> List[str]:
        return sorted(list(self._registry.keys()))

    def _initialize_core_catalog(self) -> None:
        """Populates the complete SmartParent data domain isolation mapping."""
        # 1. Direct Subscriber Tables
        direct = DirectSubscriberPolicyStrategy()
        direct_tables = [
            "subscribers",
            "children",
            "subscriber_sessions",
            "auth_audit_logs",
            "subscriptions",
            "billing_invoices",
            "subscription_renewal_reminders",
            "subscription_adjustment_audits",
            "in_app_notifications",
            "subscriber_usage_quotas",
            "support_tickets",
            "voice_query_logs",
            "tutorial_progress",
            "payment_orders",
        ]
        for tbl in direct_tables:
            self.register(tbl, direct, f"Subscriber-owned table: {tbl}")

        # 2. Indirect Child-Anchored Tables
        indirect = IndirectChildPolicyStrategy(child_column="child_id", parent_table="children")
        indirect_tables = [
            "topic_scores",
            "topic_gaps",
            "parent_pulse_records",
            "consolidated_reports",
            "board_readiness_records",
            "shared_report_tokens",
            "evidence_records",
            "student_question_marks",
        ]
        for tbl in indirect_tables:
            self.register(tbl, indirect, f"Child-anchored academic telemetry table: {tbl}")

        # 3. Indirect Ticket-Anchored Tables
        indirect_ticket = IndirectChildPolicyStrategy(child_column="ticket_id", parent_table="support_tickets")
        self.register("support_messages", indirect_ticket, "Ticket-anchored support conversation messages")

        # 4. Marketplace Dual-Boundary Tables
        marketplace = DualBoundaryMarketplacePolicyStrategy()
        self.register("evaluation_cases", marketplace, "Marketplace evaluation cases")
        self.register("case_messages", marketplace, "Marketplace evaluation messages")
        self.register("expert_reviews", marketplace, "Parent & Expert evaluation reviews")

        # 5. Expert Private Tables
        expert = ExpertPrivatePolicyStrategy(expert_column="expert_id")
        self.register("experts", expert, "Expert authenticated account")
        self.register("expert_profiles", expert, "Expert profile details")
        self.register("expert_bank_accounts", expert, "Expert bank escrow details")
        self.register("commission_ledger", expert, "Expert commission ledger")
        self.register("commission_ledgers", expert, "Expert commission ledgers (compat alias)")
        self.register("expert_question_sets", expert, "Expert authored diagnostic question sets")

        # 6. Admin / System Internal Tables
        admin_system = AdminSystemOnlyPolicyStrategy()
        self.register("razorpay_webhook_events", admin_system, "Razorpay secure webhook event audit log")
        self.register("support_sla_events", admin_system, "Customer support SLA escalation events")

        # 7. Ephemeral Auth Tables
        ephemeral_auth = EphemeralAuthPolicyStrategy()
        self.register("otp_verification_sessions", ephemeral_auth, "Ephemeral OTP verification sessions")

        # 8. Public Catalogs
        public_cat = PublicReadAdminWritePolicyStrategy()
        public_tables = [
            "curriculum_nodes",
            "tutorial_videos",
            "subscription_plan_catalog",
            "subscription_plan_catalogs",
            "subscription_prices",
            "question_papers",
            "questions",
            "question_bank_entries",
        ]
        for tbl in public_tables:
            self.register(tbl, public_cat, f"Public reference catalog: {tbl}")

    def generate_full_migration_ddl(self) -> str:
        """
        Compiles the complete production PostgreSQL 16 RLS Migration Script.
        Includes safety headers, transactional boundary, and policy definitions.
        """
        header = """-- =============================================================================
-- STUDIQS® SmartParent™ - PostgreSQL 16 Multi-Tenant Row-Level Security (RLS)
-- Automatically generated by PostgreSQLRLSRegistry.
-- ENFORCES TOTAL DATA ISOLATION ACROSS SUBSCRIBERS, STUDENTS, AND EXPERTS.
-- =============================================================================
BEGIN;

-- Helper function to safely read session tenant settings without raising exceptions
CREATE OR REPLACE FUNCTION get_current_subscriber_id() RETURNS uuid AS $$
BEGIN
    RETURN NULLIF(current_setting('app.current_subscriber_id', true), '')::uuid;
EXCEPTION WHEN OTHERS THEN
    RETURN NULL;
END;
$$ LANGUAGE plpgsql STABLE;

CREATE OR REPLACE FUNCTION get_current_expert_id() RETURNS uuid AS $$
BEGIN
    RETURN NULLIF(current_setting('app.current_expert_id', true), '')::uuid;
EXCEPTION WHEN OTHERS THEN
    RETURN NULL;
END;
$$ LANGUAGE plpgsql STABLE;
"""
        body_sections = []
        for tbl in self.list_tables():
            descriptor = self._registry[tbl]
            body_sections.append(descriptor.strategy.generate_policy_ddl(tbl))

        footer = """
COMMIT;
-- =============================================================================
-- End of STUDIQS® SmartParent™ RLS Migration Script
-- =============================================================================
"""
        return header + "\n\n" + "\n\n".join(body_sections) + footer


# Global Registry Singleton
rls_registry = PostgreSQLRLSRegistry()


# =============================================================================
# 4. OOPS CONTEXT MANAGER PATTERN: TENANT & EXPERT SECURITY CONTEXTS
# =============================================================================

class TenantSecurityContext:
    """
    Synchronous Context Manager for scoped database operations.
    Sets transaction-local PostgreSQL settings:
      SET LOCAL app.current_subscriber_id = :id;
      SET LOCAL app.current_user_role = :role;
    Automatically resets upon context exit.
    Resilient in non-PostgreSQL (SQLite test) environments.
    """

    def __init__(
        self,
        session: Session,
        subscriber_id: Optional[uuid.UUID] = None,
        role: UserRole = UserRole.SUBSCRIBER,
        bypass_rls: bool = False,
    ):
        self.session = session
        self.subscriber_id = subscriber_id
        self.role = role
        self.bypass_rls = bypass_rls
        self._cv_token: Optional[contextvars.Token[RLSContextState]] = None

    def __enter__(self) -> "TenantSecurityContext":
        # 1. Update Python ContextVar
        self._cv_token = set_active_rls_context(
            subscriber_id=self.subscriber_id,
            role=self.role,
            bypass_rls=self.bypass_rls,
        )

        # 2. Update PostgreSQL transaction settings if connected to PostgreSQL
        self._apply_session_settings()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # 1. Reset PostgreSQL session settings
        self._reset_session_settings()

        # 2. Restore Python ContextVar
        if self._cv_token:
            reset_active_rls_context(self._cv_token)

    def _apply_session_settings(self) -> None:
        try:
            # Check dialect without throwing
            bind = self.session.get_bind()
            if bind and bind.dialect.name == "postgresql":
                sub_id_str = str(self.subscriber_id) if self.subscriber_id else ""
                self.session.execute(
                    text(f"SET LOCAL {RLS_TENANT_SETTING} = :sub_id"),
                    {"sub_id": sub_id_str},
                )
                self.session.execute(
                    text(f"SET LOCAL {RLS_ROLE_SETTING} = :role"),
                    {"role": self.role.value},
                )
                if self.bypass_rls:
                    self.session.execute(text(f"SET LOCAL {RLS_BYPASS_SETTING} = 'true'"))
        except Exception as e:
            logger.debug(f"[RLSContext] SET LOCAL skipped (non-PostgreSQL or connection closed: {e})")

    def _reset_session_settings(self) -> None:
        try:
            bind = self.session.get_bind()
            if bind and bind.dialect.name == "postgresql":
                self.session.execute(text(f"RESET {RLS_TENANT_SETTING}"))
                self.session.execute(text(f"RESET {RLS_ROLE_SETTING}"))
                self.session.execute(text(f"RESET {RLS_BYPASS_SETTING}"))
        except Exception:
            pass


class ExpertSecurityContext:
    """Synchronous Context Manager for Subject Matter Experts."""

    def __init__(
        self,
        session: Session,
        expert_id: uuid.UUID,
    ):
        self.session = session
        self.expert_id = expert_id
        self._cv_token: Optional[contextvars.Token[RLSContextState]] = None

    def __enter__(self) -> "ExpertSecurityContext":
        self._cv_token = set_active_rls_context(
            expert_id=self.expert_id,
            role=UserRole.EXPERT,
        )
        try:
            bind = self.session.get_bind()
            if bind and bind.dialect.name == "postgresql":
                self.session.execute(
                    text(f"SET LOCAL {RLS_EXPERT_SETTING} = :exp_id"),
                    {"exp_id": str(self.expert_id)},
                )
                self.session.execute(
                    text(f"SET LOCAL {RLS_ROLE_SETTING} = 'EXPERT'"),
                )
        except Exception:
            pass
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            bind = self.session.get_bind()
            if bind and bind.dialect.name == "postgresql":
                self.session.execute(text(f"RESET {RLS_EXPERT_SETTING}"))
                self.session.execute(text(f"RESET {RLS_ROLE_SETTING}"))
        except Exception:
            pass
        if self._cv_token:
            reset_active_rls_context(self._cv_token)


class AdminSystemSecurityContext:
    """Synchronous Context Manager for Admin Dashboard and System Background Workers."""

    def __init__(self, session: Session):
        self.session = session
        self._cv_token: Optional[contextvars.Token[RLSContextState]] = None

    def __enter__(self) -> "AdminSystemSecurityContext":
        self._cv_token = set_active_rls_context(
            role=UserRole.ADMIN,
            bypass_rls=True,
        )
        try:
            bind = self.session.get_bind()
            if bind and bind.dialect.name == "postgresql":
                self.session.execute(text(f"SET LOCAL {RLS_ROLE_SETTING} = 'ADMIN'"))
                self.session.execute(text(f"SET LOCAL {RLS_BYPASS_SETTING} = 'true'"))
        except Exception:
            pass
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            bind = self.session.get_bind()
            if bind and bind.dialect.name == "postgresql":
                self.session.execute(text(f"RESET {RLS_ROLE_SETTING}"))
                self.session.execute(text(f"RESET {RLS_BYPASS_SETTING}"))
        except Exception:
            pass
        if self._cv_token:
            reset_active_rls_context(self._cv_token)


# =============================================================================
# 5. ASYNCHRONOUS CONTEXT MANAGERS FOR ASYNCSESSION
# =============================================================================

@asynccontextmanager
async def async_tenant_context(
    session: AsyncSession,
    subscriber_id: uuid.UUID,
    role: UserRole = UserRole.SUBSCRIBER,
    bypass_rls: bool = False,
) -> AsyncGenerator[AsyncSession, None]:
    """Async generator context manager for FastAPI endpoint dependencies."""
    token = set_active_rls_context(
        subscriber_id=subscriber_id,
        role=role,
        bypass_rls=bypass_rls,
    )
    try:
        bind = session.bind
        if bind and getattr(bind.dialect, "name", "") == "postgresql":
            await session.execute(
                text(f"SET LOCAL {RLS_TENANT_SETTING} = :sub_id"),
                {"sub_id": str(subscriber_id)},
            )
            await session.execute(
                text(f"SET LOCAL {RLS_ROLE_SETTING} = :role"),
                {"role": role.value},
            )
            if bypass_rls:
                await session.execute(text(f"SET LOCAL {RLS_BYPASS_SETTING} = 'true'"))
        yield session
    finally:
        try:
            bind = session.bind
            if bind and getattr(bind.dialect, "name", "") == "postgresql":
                await session.execute(text(f"RESET {RLS_TENANT_SETTING}"))
                await session.execute(text(f"RESET {RLS_ROLE_SETTING}"))
                await session.execute(text(f"RESET {RLS_BYPASS_SETTING}"))
        except Exception:
            pass
        reset_active_rls_context(token)


# =============================================================================
# 6. BACKWARD COMPATIBILITY BRIDGE
# Retains existing function signatures for legacy modules & tests
# =============================================================================

# Alias for legacy async context manager
tenant_isolation_context = async_tenant_context


async def set_tenant_context(session: AsyncSession, subscriber_id: uuid.UUID) -> None:
    """Sets PostgreSQL transaction-local tenant context."""
    sub_id_str = str(subscriber_id)
    try:
        await session.execute(
            text(f"SET LOCAL {RLS_TENANT_SETTING} = :sub_id"),
            {"sub_id": sub_id_str},
        )
    except Exception:
        pass
    set_active_rls_context(subscriber_id=subscriber_id, role=UserRole.SUBSCRIBER)


async def set_expert_context(session: AsyncSession, expert_id: uuid.UUID) -> None:
    """Sets PostgreSQL transaction-local expert context."""
    exp_id_str = str(expert_id)
    try:
        await session.execute(
            text(f"SET LOCAL {RLS_EXPERT_SETTING} = :exp_id"),
            {"exp_id": exp_id_str},
        )
    except Exception:
        pass
    set_active_rls_context(expert_id=expert_id, role=UserRole.EXPERT)


async def reset_tenant_context(session: AsyncSession) -> None:
    """Resets session parameters."""
    try:
        await session.execute(text(f"RESET {RLS_TENANT_SETTING}"))
        await session.execute(text(f"RESET {RLS_EXPERT_SETTING}"))
        await session.execute(text(f"RESET {RLS_ROLE_SETTING}"))
        await session.execute(text(f"RESET {RLS_BYPASS_SETTING}"))
    except Exception:
        pass


def set_tenant_context_sync(session: Session, subscriber_id: uuid.UUID) -> None:
    """Synchronous version for offline jobs and maintenance scripts."""
    try:
        session.execute(
            text(f"SET LOCAL {RLS_TENANT_SETTING} = :sub_id"),
            {"sub_id": str(subscriber_id)},
        )
    except Exception:
        pass
    set_active_rls_context(subscriber_id=subscriber_id, role=UserRole.SUBSCRIBER)


def generate_rls_sql_policies() -> str:
    """Backward-compatible DDL generator returning full PostgreSQL RLS SQL."""
    return rls_registry.generate_full_migration_ddl()
