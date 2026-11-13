"""
STUDIQS® SmartParent™ (v6.2 & v6.3 Extension) - FastAPI Application Entry Point
=============================================================================
Module: src.smartparent.main
High-Concurrency B2C Family Intelligence, Learning Diagnostics & Support Platform.

Features:
  1. Section 14 & 27: Self-Service Help Centre, Ticketing & 48-Hour Hard SLA Support
  2. Section 7 & 9: Parent Actions & Academic Handoff
  3. Section 11 & 12: Subject Expert Marketplace & Case Workflows
  4. Section 6: Monthly Parent Pulse & Learning Cycle
  5. Section 5: Performance Consistency & Diagnostic Gap Watchlist
  6. Section 8: Board Exam Readiness & Academic Share Mode
  7. Section 4: Mandatory Student Consolidated Reports & Student 360
  8. Section 10: Netflix-Style Subscriptions & Invoicing
=============================================================================
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError

from src.smartparent.config import settings
from src.smartparent.core.exceptions import SmartParentException
from src.smartparent.core.logger import setup_logger
from src.smartparent.api.router import api_router

logger = setup_logger("smartparent.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manages application lifecycle events (startup & shutdown)."""
    logger.info("Initializing STUDIQS® SmartParent™ Backend v6.3...")
    yield
    logger.info("Shutting down STUDIQS® SmartParent™ Backend gracefully.")


# =============================================================================
# 1. FastAPI Application Initializer
# =============================================================================

app = FastAPI(
    title="STUDIQS® SmartParent™ API",
    version="6.3.0",
    description=(
        "High-Concurrency B2C Family Intelligence & Academic Telemetry Backend. "
        "Enforces 48-Hour Escrow Dispute Freezes, Continuous Hard SLA Support, "
        "and Zero-Mutation Voice Assistant Database Security."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)


# =============================================================================
# 2. Middleware Stack
# =============================================================================

origins = settings.CORS_ORIGINS if isinstance(settings.CORS_ORIGINS, list) else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# 3. Global Exception Handlers
# =============================================================================

@app.exception_handler(SmartParentException)
async def smartparent_exception_handler(request: Request, exc: SmartParentException):
    """Translates domain-specific exceptions into structured JSON responses."""
    logger.warning(f"Domain Exception [{exc.error_code}]: {exc.message} on {request.url.path}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "error_code": exc.error_code,
            "message": exc.message,
            "details": exc.details,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Formats Pydantic request body validation failures cleanly."""
    errors = exc.errors()
    clean_errors = [
        {"field": " -> ".join(str(loc) for loc in err["loc"]), "msg": err["msg"]}
        for err in errors
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": True,
            "error_code": "VALIDATION_ERROR",
            "message": "Request payload failed schema validation.",
            "details": clean_errors,
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Safeguard for unhandled exceptions to prevent process crash."""
    logger.exception(f"Unhandled Server Error on {request.url.path}: {str(exc)}")
    detail_msg = str(exc) if settings.DEBUG else "An unexpected internal server error occurred."
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": True,
            "error_code": "INTERNAL_SERVER_ERROR",
            "message": detail_msg,
        },
    )


# =============================================================================
# 4. Root & Operational Endpoints
# =============================================================================

STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/manifest.webmanifest", include_in_schema=False)
async def get_manifest():
    manifest_file = STATIC_DIR / "manifest.webmanifest"
    if manifest_file.exists():
        return FileResponse(str(manifest_file), media_type="application/manifest+json")
    return JSONResponse(status_code=404, content={"error": "Manifest not found"})


@app.get("/sw.js", include_in_schema=False)
async def get_service_worker():
    sw_file = STATIC_DIR / "sw.js"
    if sw_file.exists():
        return FileResponse(str(sw_file), media_type="application/javascript")
    return JSONResponse(status_code=404, content={"error": "Service worker not found"})


@app.get(
    "/",
    tags=["Operational Telemetry"],
    summary="Root Service Index",
    description="Returns service metadata and interactive OpenAPI documentation links.",
)
async def root():
    return {
        "service": "STUDIQS® SmartParent™ API",
        "version": "6.3.0",
        "status": "online",
        "docs": "/docs",
        "redoc": "/redoc",
    }


@app.get(
    "/health",
    tags=["Operational Telemetry"],
    summary="Operational Liveness & Readiness Probe",
    description="Kubernetes / Docker healthcheck endpoint.",
)
async def health_check():
    return {
        "status": "healthy",
        "environment": settings.APP_ENV,
        "version": "6.3.0",
    }


# =============================================================================
# 5. Mount API v1 Central Router
# =============================================================================

app.include_router(api_router)
