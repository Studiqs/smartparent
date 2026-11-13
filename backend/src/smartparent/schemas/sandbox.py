"""
STUDIQS® SmartParent™ - Sandbox & Demo Environment Schemas
=============================================================================
Module: src.smartparent.schemas.sandbox

Pydantic v2 schemas for the Sandbox ecosystem:
  - Mock Payment Gateway checkout & subscription simulation
  - Ask Studiqs Voice Assistant sandbox queries with read-only guarantees
  - Demo ecosystem seeding and diagnostic introspection
=============================================================================
"""

import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from src.smartparent.core.constants import SubscriptionPlan


class SandboxPaymentCheckoutRequest(BaseModel):
    """Request to simulate a payment checkout in the Razorpay sandbox."""
    subscriber_id: Optional[uuid.UUID] = Field(
        default=None,
        description="Target subscriber ID (if omitted, attaches to demo subscriber)",
    )
    plan: SubscriptionPlan = Field(
        default=SubscriptionPlan.PRO,
        description="Target subscription tier (BASIC, ADVANCED, PRO)",
    )
    duration_months: int = Field(
        default=1,
        ge=1,
        le=12,
        description="Duration in months: 1 (Monthly), 3 (Quarterly), 6 (Half-Yearly), 12 (Annual)",
    )
    payment_method: str = Field(
        default="mock_upi",
        description="Simulated payment instrument: mock_upi, mock_card, mock_netbanking",
    )
    simulate_failure: bool = Field(
        default=False,
        description="Set to true to simulate payment gateway rejection / card decline",
    )


class SandboxPaymentCheckoutResponse(BaseModel):
    """Response returned by the sandbox payment checkout simulation."""
    order_id: str
    payment_id: Optional[str] = None
    plan: str
    duration_months: int
    taxable_base: float
    cgst_amount: float
    sgst_amount: float
    total_amount: float
    invoice_number: Optional[str] = None
    subscription_id: Optional[uuid.UUID] = None
    subscription_status: str
    message: str


class SandboxAskStudiqsRequest(BaseModel):
    """Sandbox voice or natural language text query to Ask Studiqs."""
    query_text: str = Field(
        ...,
        min_length=2,
        max_length=500,
        description="Natural language query (e.g. 'Maths weak topic', 'How is my child performing?')",
    )
    subscriber_id: Optional[uuid.UUID] = Field(
        default=None,
        description="Optional subscriber context (defaults to active demo parent)",
    )
    child_id: Optional[uuid.UUID] = Field(
        default=None,
        description="Optional specific child context",
    )
    language_hint: str = Field(
        default="ta-IN",
        description="Language or dialect hint (ta-IN, en-IN)",
    )


class SandboxAskStudiqsResponse(BaseModel):
    """Response from Ask Studiqs execution inside the read-only sandbox."""
    query_text: str
    intent_pillar: str
    intent_logic: str
    resolved_child_name: str
    ui_card_narrative: str
    audio_speech_transcript: str
    remedial_recommendation: Optional[str] = None
    cognitive_root_cause: Optional[str] = None
    telemetry_source: str
    is_read_only_isolated: bool
    execution_latency_ms: float


class SandboxSeedDemoResponse(BaseModel):
    """Status of demo ecosystem activation."""
    status: str
    subscriber_id: uuid.UUID
    mobile_number: str
    parent_name: str
    email: str
    demo_password: str
    children_count: int
    sample_children: List[Dict[str, Any]]
    message: str


class SandboxStatusResponse(BaseModel):
    """Capabilities and health status of the SmartParent sandbox."""
    environment: str
    payment_sandbox_active: bool
    voice_assistant_sandbox_active: bool
    read_only_db_sandbox_enforced: bool
    supported_plans: List[str]
    supported_durations_months: List[int]
    gst_rate_percent: float
    timestamp: str

