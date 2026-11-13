"""
STUDIQS® SmartParent™ - Ask Studiqs Multimodal Voice Service Facade
=============================================================================
Module: src.smartparent.services.voice_service

Provides enterprise service methods for the Ask Studiqs API layer:
  - Text-based and Audio-based diagnostic querying.
  - LLM-Style Diagnostic Token accounting and quota enforcement.
  - Dual-modal response delivery (UI card + Native Mobile TTS narrative).
  - Pillar metadata discovery for UI hint chips.
=============================================================================
"""

import io
from typing import Dict, List, Optional, Tuple, Any
from sqlalchemy.orm import Session

from src.smartparent.rag import (
    AskStudiqsAgent,
    IAssistantAgent,
    RAGContainer,
    SubscriptionTokenAccountant,
    SUBSCRIPTION_PLANS,
)
from src.smartparent.schemas.voice import (
    VoiceTextQueryRequest,
    VoiceQueryResponse,
    VoiceTokenBalanceResponse,
    VoicePillarsResponse,
    PillarItem,
)


class VoiceService:
    """
    Unified Voice & Multimodal Diagnostic Service Facade.
    Connects FastAPI routers to the Ask Studiqs RAG engine.
    """

    # In-memory subscriber token balance simulation/cache (backed by DB/Redis in prod)
    _SUBSCRIBER_LEDGER: Dict[str, Dict[str, int]] = {}

    def __init__(
        self,
        db_session: Optional[Session] = None,
        agent: Optional[IAssistantAgent] = None,
    ):
        self.db_session = db_session
        self.agent = agent or RAGContainer.create_agent(db_session=db_session)

    @classmethod
    def _get_usage(cls, parent_id: str) -> Tuple[int, int]:
        ledger = cls._SUBSCRIBER_LEDGER.setdefault(parent_id, {"used_tokens": 0, "used_voice": 0})
        return ledger["used_tokens"], ledger["used_voice"]

    @classmethod
    def _update_usage(cls, parent_id: str, new_tokens: int, new_voice: int):
        cls._SUBSCRIBER_LEDGER[parent_id] = {
            "used_tokens": new_tokens,
            "used_voice": new_voice,
        }

    def process_text_query(
        self,
        parent_id: str,
        plan_tier: str,
        request: VoiceTextQueryRequest,
        authorized_children: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Executes a typed diagnostic query and tracks token consumption.
        """
        used_tokens, used_voice = self._get_usage(parent_id)

        result = self.agent.ask_text(
            query_text=request.query_text,
            parent_id=parent_id,
            plan_tier=plan_tier,
            child_id=request.child_id,
            authorized_children=authorized_children,
            used_tokens_before=used_tokens,
            used_voice_before=used_voice,
        )

        if result.get("token_accounting") and result["token_accounting"].get("allowed"):
            ta = result["token_accounting"]
            self._update_usage(parent_id, ta["used_tokens_after"], ta["voice_queries_used"])

        return result

    def process_audio_query(
        self,
        parent_id: str,
        plan_tier: str,
        audio_stream: io.BytesIO,
        child_id: Optional[str] = None,
        authorized_children: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Executes a voice diagnostic query and tracks token consumption.
        """
        used_tokens, used_voice = self._get_usage(parent_id)

        result = self.agent.ask_voice(
            audio_stream=audio_stream,
            parent_id=parent_id,
            plan_tier=plan_tier,
            child_id=child_id,
            authorized_children=authorized_children,
            used_tokens_before=used_tokens,
            used_voice_before=used_voice,
        )

        if result.get("token_accounting") and result["token_accounting"].get("allowed"):
            ta = result["token_accounting"]
            self._update_usage(parent_id, ta["used_tokens_after"], ta["voice_queries_used"])

        return result

    def get_token_balance(self, parent_id: str, plan_tier: str) -> VoiceTokenBalanceResponse:
        """
        Returns real-time Diagnostic Token balance and quota usage.
        """
        plan = SubscriptionTokenAccountant.get_plan(plan_tier)
        used_tokens, used_voice = self._get_usage(parent_id)
        remaining = max(0, plan["monthly_tokens"] - used_tokens)
        pct = round((used_tokens / plan["monthly_tokens"]) * 100.0, 2)

        return VoiceTokenBalanceResponse(
            plan_tier=plan_tier.upper(),
            voice_allowed=plan["voice_allowed"],
            monthly_tokens=plan["monthly_tokens"],
            used_tokens=used_tokens,
            remaining_tokens=remaining,
            usage_percentage=pct,
            voice_queries_used=used_voice,
            max_voice_queries=plan["max_voice_queries"],
            milestones=plan["milestones"],
        )

    @staticmethod
    def get_pillars_metadata() -> VoicePillarsResponse:
        """
        Returns descriptions and example queries for all 6 Diagnostic Pillars.
        """
        pillars = [
            PillarItem(
                id=0,
                name="OVERALL_ACADEMIC_STANDING",
                description="Holistic Student 360 overview, average percentage, and primary strengths/watch areas.",
                example_query="How is Viswa performing overall across all subjects?",
            ),
            PillarItem(
                id=1,
                name="SUBJECT_PERFORMANCE",
                description="Subject-specific score, 60-day acceleration or dip, and topic mastery level.",
                example_query="What is Kavya's latest score in Mathematics?",
            ),
            PillarItem(
                id=2,
                name="GRANULAR_TOPIC_GAPS",
                description="Line-item weak and critical topic gaps, marks lost, and root cause analysis.",
                example_query="Where did Viswa lose marks in Science?",
            ),
            PillarItem(
                id=3,
                name="MONTH_ON_MONTH_TRENDS",
                description="30 to 60-day velocity, acceleration slope, and term-over-term comparison.",
                example_query="Is Viswa improving compared to last month?",
            ),
            PillarItem(
                id=4,
                name="TERM_CONSISTENCY",
                description="Score stability classification, variance band, and Class 10/12 Board Readiness Index.",
                example_query="How consistent is Viswa's performance for Board exams?",
            ),
            PillarItem(
                id=5,
                name="NEXT_GAP_RECHECK_ACTION",
                description="Targeted 5-minute remedial practice drill and question bank links.",
                example_query="How do we fix Viswa's weak topic in Quadratic Equations?",
            ),
        ]
        return VoicePillarsResponse(total_pillars=len(pillars), pillars=pillars)
