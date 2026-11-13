"""
STUDIQS® SmartParent™ (v6.2 Complete) - Production Configuration Settings
Powered by Pydantic v2 & Pydantic-Settings
"""

import os
from pathlib import Path
from typing import List, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ==========================================================================
    # 1. APPLICATION RUNTIME & NETWORK
    # ==========================================================================
    APP_ENV: str = "development"
    DEBUG: bool = True
    PORT: int = 8000

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug_value(cls, v):
        if isinstance(v, str):
            if v.lower() in ("true", "1", "yes", "on", "dev", "development"):
                return True
            if v.lower() in ("false", "0", "no", "off", "release", "prod", "production"):
                return False
        return bool(v)
    HOST: str = "0.0.0.0"
    PROJECT_NAME: str = "Studiqs SmartParent Backend"
    API_V1_STR: str = "/api/v1"

    # ==========================================================================
    # 2. SECURITY, CRYPTOGRAPHY & JWT AUTH
    # ==========================================================================
    # In production, inject a 64-character hex string generated via: openssl rand -hex 32
    SECRET_KEY: str = "dev_secret_key_change_in_production_min_32_characters_studiqs_v6_2"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24   # 24 Hours
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30          # 30 Days

    # ==========================================================================
    # 3. POSTGRESQL 16 HIGH-CONCURRENCY DATABASE POOLS
    # ==========================================================================
    # Async pool for primary application mutations and business logic
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/smartparent_db"
    
    # Synchronous pool for Alembic migrations and utility scripts
    DATABASE_SYNC_URL: str = "postgresql://postgres:postgres@localhost:5432/smartparent_db"
    
    # Strictly isolated read-only pool for Pro Voice Assistant ("Ask Studiqs")
    # Enforces 100% Zero-Mutation database security at PostgreSQL role level
    DB_READONLY_URL: str = (
        "postgresql+asyncpg://studiqs_voice_readonly:voice_secret@localhost:5432/smartparent_db"
    )

    # Database Pool Tuning
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30

    # ==========================================================================
    # 4. REDIS CACHE & TEMPORARY SESSION STORE
    # ==========================================================================
    REDIS_URL: str = "redis://localhost:6379/0"

    # ==========================================================================
    # 5. CROSS-ORIGIN RESOURCE SHARING (CORS)
    # ==========================================================================
    CORS_ORIGINS: Union[List[str], str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        elif isinstance(v, list):
            return v
        return ["*"]

    # ==========================================================================
    # 6. STORAGE, UPLOADS & MEDIA ATTACHMENTS
    # ==========================================================================
    UPLOAD_DIR: str = str(Path(__file__).resolve().parent.parent.parent / "uploads")
    MAX_UPLOAD_SIZE_MB: int = 25
    ALLOWED_EXTENSIONS: List[str] = [".pdf", ".xlsx", ".xls", ".png", ".jpg", ".jpeg"]

    # ==========================================================================
    # 7. COMMERCIAL MARKETPLACE & ESCROW RULES
    # ==========================================================================
    PLATFORM_COMMISSION_PERCENT: float = 20.0   # 20% Studiqs Platform Commission
    EXPERT_NET_PAYOUT_PERCENT: float = 80.0     # 80% Expert Net Payout
    ESCROW_DISPUTE_WINDOW_HOURS: int = 48       # 48-hour post-completion escrow hold

    # ==========================================================================
    # 8. PRO VOICE ENGINE FIREWALL & SLA
    # ==========================================================================
    VOICE_MAX_TURNAROUND_MS: int = 350
    VOICE_READONLY_ROLE: str = "studiqs_voice_readonly"

    # ==========================================================================
    # 9. CURRICULUM TAXONOMY DATA ASSET (8,034 Verified Topics)
    # ==========================================================================
    CURRICULUM_EXCEL_PATH: str = str(
        Path(__file__).resolve().parent / "db" / "smartparent_master_repository_kb.xlsx"
    )

    # ==========================================================================
    # 10. RAZORPAY PAYMENT GATEWAY (Section 24 - v6.3)
    # ==========================================================================
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""

    # ==========================================================================
    # 11. GST TAXATION CONFIGURATION (Section 24 - v6.3)
    # ==========================================================================
    GST_RATE_PERCENT: float = 18.0       # Total GST rate (CGST 9% + SGST 9%)
    COMPANY_GST_NUMBER: str = ""         # Studiqs GSTIN for invoice headers

    # ==========================================================================
    # 12. VIDEO TUTORIAL STORAGE (Section 26 - v6.3)
    # ==========================================================================
    VIDEO_STORAGE_BUCKET: str = "studiqs-smartparent-videos"
    VIDEO_SIGNED_URL_EXPIRY_SECONDS: int = 900  # 15-minute signed URL expiry

    # ==========================================================================
    # 13. SUPPORT CENTRE SLA (Section 27 - v6.3)
    # ==========================================================================
    SUPPORT_SLA_HOURS: int = 48          # Hard SLA deadline in hours (continuous clock)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


# Global settings singleton
settings = Settings()
