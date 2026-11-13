"""
002_production_postgresql_rls_policies - STUDIQS® SmartParent™ Complete Enterprise RLS
================================================================================
Revision ID: 002_prod_rls_policies
Revises: 001_prod_schema
Create Date: 2026-11-09 18:00:00.000000

Provisions enterprise PostgreSQL 16 Row-Level Security (RLS) across all 35+ tables
using the Strategy Pattern via PostgreSQLRLSRegistry:
  1. Direct Subscriber Isolation (subscriber_id = current_setting('app.current_subscriber_id'))
  2. Indirect Child-Anchored Isolation (child_id in children where subscriber_id = ...)
  3. Marketplace Dual Boundary (subscriber_id = ... OR assigned_expert_id = ...)
  4. Expert Private Boundary (expert_id = current_setting('app.current_expert_id'))
  5. Public Read-Only Reference Catalogs (curriculum_nodes, tutorial_videos)
  6. Zero-Overhead Admin & System Bypass (app.bypass_rls = 'true' OR role IN ('ADMIN', 'SYSTEM'))
================================================================================
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from src.smartparent.core.rls import rls_registry

# revision identifiers, used by Alembic.
revision: str = "002_prod_rls_policies"
down_revision: Union[str, None] = "001_prod_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Applies production PostgreSQL 16 Row-Level Security across all registered tables.
    Only executes when connected to PostgreSQL dialect.
    """
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        ddl = rls_registry.generate_full_migration_ddl()
        op.execute(sa.text(ddl))


def downgrade() -> None:
    """
    Safely disables Row-Level Security on all tables.
    """
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        statements = []
        for tbl in rls_registry.list_tables():
            statements.append(f"ALTER TABLE {tbl} NO FORCE ROW LEVEL SECURITY;")
            statements.append(f"ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY;")
        op.execute(sa.text("\n".join(statements)))

