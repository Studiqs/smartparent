"""
STUDIQS® SmartParent™ (v6.2 Complete) - Database Engine & Session Management
High-Concurrency Async Sessions with Dedicated Voice Read-Only Role Separation
"""

from collections.abc import AsyncGenerator
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker
from src.smartparent.config import settings

# ==============================================================================
# 1. PRIMARY ASYNC DATABASE POOL (Read / Write Application Operations)
# ==============================================================================
async_engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


# ==============================================================================
# 2. DEDICATED READ-ONLY POOL (Pro Voice Assistant: "Ask Studiqs")
# Enforces Zero-Mutation Database Security at PostgreSQL Role Level (Section 22.1)
# ==============================================================================
async_readonly_engine = create_async_engine(
    settings.DB_READONLY_URL,
    echo=False,
    pool_size=10,
    max_overflow=5,
    pool_timeout=15,
    pool_pre_ping=True,
)

AsyncReadonlySessionLocal = async_sessionmaker(
    bind=async_readonly_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


# ==============================================================================
# 3. SYNCHRONOUS DATABASE POOL (For Alembic, Ingestion & Data Migrations)
# ==============================================================================
sync_engine = create_engine(
    settings.DATABASE_SYNC_URL,
    echo=False,
    pool_pre_ping=True,
)

SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    autoflush=False,
    autocommit=False,
)


# ==============================================================================
# 4. FASTAPI DEPENDENCY INJECTION PROVIDERS
# ==============================================================================
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for standard API endpoints requiring read/write database transactions."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_readonly_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dedicated dependency for Pro Voice Engine ("Ask Studiqs").
    Physically prevents any INSERT, UPDATE, DELETE, or TRUNCATE.
    """
    async with AsyncReadonlySessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


# ==============================================================================
# 5. CONVENIENCE ALIASES (Standard SQLAlchemy & Script Interoperability)
# ==============================================================================
engine = async_engine
async_session_factory = AsyncSessionLocal
sync_session_factory = SyncSessionLocal
SessionLocal = SyncSessionLocal

