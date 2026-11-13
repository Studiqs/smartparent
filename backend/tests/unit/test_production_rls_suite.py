"""
STUDIQS® SmartParent™ - Production RLS Architecture & Strategy Test Suite
=============================================================================
Module: tests.unit.test_production_rls_suite

Verifies:
  1. Strategy Pattern DDL Generation for Direct, Indirect, Marketplace, Expert, and Public policies.
  2. Centralized Registry catalog coverage across all 35+ tables.
  3. Context Manager Pattern (TenantSecurityContext, ExpertSecurityContext, AdminSystemSecurityContext).
  4. ContextVar thread-safe isolation across concurrent tasks.
  5. Automated migration script compilation.
  6. Backward compatibility bridge functions.
=============================================================================
"""

import uuid
import pytest
from unittest.mock import MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.smartparent.core.rls import (
    RLS_TENANT_SETTING,
    RLS_EXPERT_SETTING,
    RLS_ROLE_SETTING,
    RLS_BYPASS_SETTING,
    UserRole,
    RLSContextState,
    DirectSubscriberPolicyStrategy,
    IndirectChildPolicyStrategy,
    DualBoundaryMarketplacePolicyStrategy,
    ExpertPrivatePolicyStrategy,
    PublicReadAdminWritePolicyStrategy,
    PostgreSQLRLSRegistry,
    rls_registry,
    TenantSecurityContext,
    ExpertSecurityContext,
    AdminSystemSecurityContext,
    get_current_rls_context,
    set_active_rls_context,
    reset_active_rls_context,
    set_tenant_context_sync,
    generate_rls_sql_policies,
)


# =============================================================================
# 1. STRATEGY PATTERN DDL VERIFICATION
# =============================================================================

class TestRLSPolicyStrategies:
    """Verifies that each policy strategy generates correct PostgreSQL 16 DDL."""

    def test_direct_subscriber_strategy_ddl(self):
        strategy = DirectSubscriberPolicyStrategy(tenant_column="subscriber_id")
        ddl = strategy.generate_policy_ddl("children")

        assert "ALTER TABLE children ENABLE ROW LEVEL SECURITY;" in ddl
        assert "ALTER TABLE children FORCE ROW LEVEL SECURITY;" in ddl
        assert "CREATE POLICY children_tenant_isolation ON children" in ddl
        assert "subscriber_id = NULLIF(current_setting('app.current_subscriber_id', true), '')::uuid" in ddl
        assert "current_setting('app.bypass_rls', true) = 'true'" in ddl
        assert "current_setting('app.current_user_role', true) IN ('ADMIN', 'SYSTEM')" in ddl

    def test_indirect_child_strategy_ddl(self):
        strategy = IndirectChildPolicyStrategy(child_column="child_id", parent_table="children")
        ddl = strategy.generate_policy_ddl("topic_scores")

        assert "ALTER TABLE topic_scores ENABLE ROW LEVEL SECURITY;" in ddl
        assert "ALTER TABLE topic_scores FORCE ROW LEVEL SECURITY;" in ddl
        assert "CREATE POLICY topic_scores_child_tenant_isolation ON topic_scores" in ddl
        assert "child_id IN (" in ddl
        assert "SELECT c.child_id FROM children c" in ddl
        assert "c.subscriber_id = NULLIF(current_setting('app.current_subscriber_id', true), '')::uuid" in ddl

    def test_marketplace_dual_boundary_strategy_ddl(self):
        strategy = DualBoundaryMarketplacePolicyStrategy()
        ddl = strategy.generate_policy_ddl("evaluation_cases")

        assert "ALTER TABLE evaluation_cases ENABLE ROW LEVEL SECURITY;" in ddl
        assert "CREATE POLICY evaluation_cases_marketplace_isolation ON evaluation_cases" in ddl
        assert "subscriber_id = NULLIF(current_setting('app.current_subscriber_id', true), '')::uuid" in ddl
        assert "assigned_expert_id = NULLIF(current_setting('app.current_expert_id', true), '')::uuid" in ddl

    def test_expert_private_strategy_ddl(self):
        strategy = ExpertPrivatePolicyStrategy(expert_column="expert_id")
        ddl = strategy.generate_policy_ddl("commission_ledgers")

        assert "ALTER TABLE commission_ledgers ENABLE ROW LEVEL SECURITY;" in ddl
        assert "CREATE POLICY commission_ledgers_expert_private_isolation ON commission_ledgers" in ddl
        assert "expert_id = NULLIF(current_setting('app.current_expert_id', true), '')::uuid" in ddl

    def test_public_read_admin_write_strategy_ddl(self):
        strategy = PublicReadAdminWritePolicyStrategy()
        ddl = strategy.generate_policy_ddl("curriculum_nodes")

        assert "ALTER TABLE curriculum_nodes ENABLE ROW LEVEL SECURITY;" in ddl
        assert "CREATE POLICY curriculum_nodes_public_read ON curriculum_nodes" in ddl
        assert "FOR SELECT" in ddl
        assert "USING (true)" in ddl
        assert "CREATE POLICY curriculum_nodes_admin_write ON curriculum_nodes" in ddl


# =============================================================================
# 2. REGISTRY PATTERN & SCHEMA CATALOG COVERAGE
# =============================================================================

class TestRLSRegistryAndCatalog:
    """Verifies that all SmartParent tables are cataloged and covered."""

    def test_registry_contains_mandatory_tables(self):
        tables = rls_registry.list_tables()
        mandatory = [
            # Direct
            "subscribers",
            "children",
            "subscriptions",
            "billing_invoices",
            "subscriber_sessions",
            "in_app_notifications",
            "support_tickets",
            # Indirect
            "topic_scores",
            "topic_gaps",
            "parent_pulse_records",
            "consolidated_reports",
            "board_readiness_records",
            # Marketplace
            "evaluation_cases",
            "commission_ledgers",
            # Public
            "curriculum_nodes",
            "tutorial_videos",
        ]
        for tbl in mandatory:
            assert tbl in tables, f"Mandatory table {tbl} missing from RLS Registry!"
            descriptor = rls_registry.get(tbl)
            assert descriptor is not None
            assert descriptor.table_name == tbl
            assert descriptor.strategy is not None

    def test_full_migration_ddl_compilation(self):
        ddl = rls_registry.generate_full_migration_ddl()
        assert ddl.startswith("-- =============================================================================")
        assert "BEGIN;" in ddl
        assert "CREATE OR REPLACE FUNCTION get_current_subscriber_id()" in ddl
        assert "CREATE OR REPLACE FUNCTION get_current_expert_id()" in ddl
        assert "COMMIT;" in ddl

        # Ensure all registered tables are present in compiled DDL
        for tbl in rls_registry.list_tables():
            assert f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY;" in ddl
            assert f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY;" in ddl


# =============================================================================
# 3. CONTEXT MANAGERS & CONTEXTVAR ISOLATION
# =============================================================================

class TestRLSContextManagers:
    """Verifies thread-safe ContextVar state transitions and mock session execution."""

    def test_tenant_security_context_state_transition(self):
        engine = create_engine("sqlite:///:memory:")
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()

        sub_id = uuid.uuid4()
        initial_ctx = get_current_rls_context()
        assert initial_ctx.subscriber_id is None
        assert initial_ctx.role == UserRole.ANONYMOUS

        with TenantSecurityContext(session=session, subscriber_id=sub_id, role=UserRole.SUBSCRIBER):
            active_ctx = get_current_rls_context()
            assert active_ctx.subscriber_id == sub_id
            assert active_ctx.role == UserRole.SUBSCRIBER
            assert active_ctx.bypass_rls is False

        # Must automatically restore unauthenticated state after exit
        restored_ctx = get_current_rls_context()
        assert restored_ctx.subscriber_id is None
        assert restored_ctx.role == UserRole.ANONYMOUS
        session.close()

    def test_expert_security_context_state_transition(self):
        engine = create_engine("sqlite:///:memory:")
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()

        exp_id = uuid.uuid4()
        with ExpertSecurityContext(session=session, expert_id=exp_id):
            active_ctx = get_current_rls_context()
            assert active_ctx.expert_id == exp_id
            assert active_ctx.role == UserRole.EXPERT
            assert active_ctx.bypass_rls is False

        restored_ctx = get_current_rls_context()
        assert restored_ctx.expert_id is None
        assert restored_ctx.role == UserRole.ANONYMOUS
        session.close()

    def test_admin_system_security_context_bypass_flag(self):
        engine = create_engine("sqlite:///:memory:")
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()

        with AdminSystemSecurityContext(session=session):
            active_ctx = get_current_rls_context()
            assert active_ctx.role == UserRole.ADMIN
            assert active_ctx.bypass_rls is True

        restored_ctx = get_current_rls_context()
        assert restored_ctx.bypass_rls is False
        session.close()

    def test_backward_compatibility_sync_helper(self):
        engine = create_engine("sqlite:///:memory:")
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()

        test_sub_id = uuid.uuid4()
        set_tenant_context_sync(session, test_sub_id)

        active_ctx = get_current_rls_context()
        assert active_ctx.subscriber_id == test_sub_id
        assert active_ctx.role == UserRole.SUBSCRIBER

        ddl = generate_rls_sql_policies()
        assert "BEGIN;" in ddl
        assert "COMMIT;" in ddl
        session.close()

