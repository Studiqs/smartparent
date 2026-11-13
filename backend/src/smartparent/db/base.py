"""
STUDIQS® SmartParent™ (v6.2 Complete) - Database Declarative Base & Mixins
SQLAlchemy 2.0 Modern Declarative Architecture
"""

import uuid
from datetime import datetime
from typing import Any
from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base declarative class for all Studiqs SmartParent relational models."""
    
    # Generate clean dictionary representation of model instances
    def to_dict(self) -> dict[str, Any]:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class TimestampMixin:
    """Standard timestamp mixin enforcing UTC timezone on creation and mutation."""
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class UUIDPrimaryKeyMixin:
    """Standard UUID v4 primary key mixin for distributed multi-tenant scalability."""
    
    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
