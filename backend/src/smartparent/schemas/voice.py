"""
STUDIQS® SmartParent™ - Ask Studiqs Multimodal Voice & Text Schemas
=============================================================================
Module: src.smartparent.schemas.voice

Pydantic v2 schemas for Ask Studiqs API endpoints:
  - VoiceTextQueryRequest
  - VoiceQueryResponse
  - VoiceTokenBalanceResponse
  - VoicePillarsResponse
=============================================================================
"""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, ConfigDict


class VoiceTextQueryRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    query_text: str = Field(..., min_length=1, max_length=1000, description="Parent diagnostic question")
    child_id: Optional[str] = Field(None, description="Target child UUID")
    child_name: Optional[str] = Field(None, description="Optional child name override")
    language: str = Field("en", description="Query language code (en, ta, tanglish)")


class DualModalDelivery(BaseModel):
    model_config = ConfigDict(extra="ignore")
    visual_card: Dict[str, Any] = Field(..., description="Structured visual card payload for mobile UI")
    spoken_narrative: str = Field(..., description="Pre-verbalized text for Native Mobile TTS")


class TokenAccountingInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")
    allowed: bool
    http_status: int = 200
    plan_tier: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_charged: int = 0
    used_tokens_after: int = 0
    remaining_tokens: int = 0
    monthly_token_quota: int = 0
    usage_percentage: float = 0.0
    voice_queries_used: int = 0
    max_voice_queries: int = 0
    milestone_alert: Optional[str] = None
    error_code: Optional[str] = None
    message: Optional[str] = None


class VoiceQueryResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    status: str = "SUCCESS"
    http_status: int = 200
    resolved_pillar: str
    pillar_id: int
    logic_mode: str
    confidence: float
    extracted_slots: Dict[str, List[str]]
    resolved_child: str
    dual_modal_delivery: DualModalDelivery
    token_accounting: TokenAccountingInfo
    latency_ms: float
    transcribed_query: Optional[str] = None
    stt_latency_ms: Optional[float] = None
    total_latency_ms: Optional[float] = None


class VoiceTokenBalanceResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    plan_tier: str
    voice_allowed: bool
    monthly_tokens: int
    used_tokens: int
    remaining_tokens: int
    usage_percentage: float
    voice_queries_used: int
    max_voice_queries: int
    milestones: List[int]


class PillarItem(BaseModel):
    id: int
    name: str
    description: str
    example_query: str


class VoicePillarsResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    total_pillars: int
    pillars: List[PillarItem]

