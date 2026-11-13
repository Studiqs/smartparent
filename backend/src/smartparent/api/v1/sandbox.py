"""
STUDIQS® SmartParent™ - Sandbox & Demo Environment Endpoints
=============================================================================
Module: src.smartparent.api.v1.sandbox

Endpoints for developer, QA, and sales sandbox validation:
  - GET  /api/v1/sandbox/status
  - POST /api/v1/sandbox/seed-demo
  - POST /api/v1/sandbox/payments/mock-checkout
  - POST /api/v1/sandbox/voice/ask-studiqs
=============================================================================
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.smartparent.api.deps import get_db
from src.smartparent.schemas.sandbox import (
    SandboxPaymentCheckoutRequest,
    SandboxPaymentCheckoutResponse,
    SandboxAskStudiqsRequest,
    SandboxAskStudiqsResponse,
    SandboxSeedDemoResponse,
    SandboxStatusResponse,
)
from src.smartparent.services.sandbox_service import (
    SandboxService,
    DEMO_MOBILE,
    DEMO_EMAIL,
    DEMO_PARENT_NAME,
)

router = APIRouter(prefix="/sandbox", tags=["Sandbox & Demo Environment"])


@router.get(
    "/status",
    response_model=SandboxStatusResponse,
    summary="Get Sandbox Environment Status",
    description="Returns current sandbox capabilities, payment test mode status, and GST parameters.",
)
def get_sandbox_status() -> SandboxStatusResponse:
    """Returns active sandbox capabilities and configuration."""
    return SandboxService.get_sandbox_status()


@router.post(
    "/seed-demo",
    response_model=SandboxSeedDemoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Seed Verified Demo Parent & Student Ecosystem",
    description="Creates a rich demo family (Karthik Subramanian, Ananya & Rohan) with diagnostic telemetry.",
)
def seed_demo_ecosystem(db: Session = Depends(get_db)) -> SandboxSeedDemoResponse:
    """Provisions or retrieves the demo sandbox family with diagnostic marks and gaps."""
    try:
        sub, children = SandboxService.get_or_seed_demo_parent(db)
        child_summary = [
            {
                "child_id": str(c.child_id),
                "name": c.student_name,
                "board": c.board,
                "class": c.standard_class,
            }
            for c in children
        ]
        return SandboxSeedDemoResponse(
            status="INITIALIZED",
            subscriber_id=sub.subscriber_id,
            mobile_number=DEMO_MOBILE,
            parent_name=DEMO_PARENT_NAME,
            email=DEMO_EMAIL,
            demo_password="DemoSecret@2026",
            children_count=len(children),
            sample_children=child_summary,
            message="Demo ecosystem successfully initialized. Ready for sandbox tests & UI exploration.",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to seed demo sandbox ecosystem: {str(e)}",
        )


@router.post(
    "/payments/mock-checkout",
    response_model=SandboxPaymentCheckoutResponse,
    summary="Simulate Razorpay Payment Sandbox Checkout",
    description="Simulates plan checkout (Basic, Advanced, Pro) across 1/3/6/12 months with 18% GST and invoice generation.",
)
def simulate_sandbox_payment(
    request: SandboxPaymentCheckoutRequest,
    db: Session = Depends(get_db),
) -> SandboxPaymentCheckoutResponse:
    """Executes a zero-cost sandbox payment flow with tax invoices and subscription activation."""
    try:
        return SandboxService.simulate_payment_checkout(db=db, request=request)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sandbox payment error: {str(e)}",
        )


@router.post(
    "/voice/ask-studiqs",
    response_model=SandboxAskStudiqsResponse,
    summary="Ask Studiqs Voice Assistant Sandbox",
    description="Executes a voice or natural language text query inside a strict Read-Only SQL transaction sandbox.",
)
def ask_studiqs_sandbox(
    request: SandboxAskStudiqsRequest,
    db: Session = Depends(get_db),
) -> SandboxAskStudiqsResponse:
    """Executes natural language queries with read-only SQL safety and 0.00% hallucination."""
    try:
        return SandboxService.execute_voice_query_sandbox(db=db, request=request)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ask Studiqs sandbox error: {str(e)}",
        )

