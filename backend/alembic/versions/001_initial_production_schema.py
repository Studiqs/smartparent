"""
001_initial_production_schema - STUDIQS® SmartParent™ Complete Production Schema
================================================================================
Revision ID: 001_prod_schema
Revises: None
Create Date: 2026-10-31 18:30:00.000000

Provisions all 37 production tables, foreign keys, unique constraints, and indexes
for Studiqs SmartParent v6.2 and v6.3 Extension on Supabase / PostgreSQL:
  1. Identity, Subscribers & Child Multi-Tenant Profiles (Section 1, 2)
  2. Master 8,034-Node Curriculum Taxonomy & Evidence Vault (Section 3, 5)
  3. Topic Diagnostic Scores & Active Gap Watchlists (Section 5)
  4. Monthly Parent Pulse 3-Card Records & Reports (Section 4, 6)
  5. Verified Subject Expert Marketplace & Escrow Ledgers (Section 11, 12)
  6. Netflix-Style Subscriptions & B2C GST Tax Invoicing (Section 10, 24)
  7. 48-Hour Continuous Hard SLA Support Desk (Section 14, 27)
  8. Usage Quotas & Audit Telemetry (Section 16, 25)
================================================================================
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# Ensure all 37 model entities are imported
from src.smartparent.db.base import Base
import src.smartparent.db.models


# revision identifiers, used by Alembic.
revision: str = "001_prod_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Creates all 37 production tables and composite indexes in Supabase / PostgreSQL.
    """
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    """
    Safely tears down all production tables.
    """
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)

