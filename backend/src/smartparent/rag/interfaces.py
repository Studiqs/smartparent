"""
STUDIQS® SmartParent™ - Ask Studiqs RAG Abstract Interfaces & Protocols
=============================================================================
Module: src.smartparent.rag.interfaces

Defines formal structural typing contracts (Protocols & ABCs) conforming to:
  - Single Responsibility Principle (SRP)
  - Open / Closed Principle (OCP)
  - Liskov Substitution Principle (LSP)
  - Interface Segregation Principle (ISP)
  - Dependency Inversion Principle (DIP)

Enables full dependency injection, test double isolation, and modular upgrades.
=============================================================================
"""

from __future__ import annotations

import io
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple, Any, Protocol, runtime_checkable, TYPE_CHECKING

if TYPE_CHECKING:
    from src.smartparent.rag.telemetry_retriever import (
        ChildDiagnosticTelemetry,
        SubjectTelemetry,
    )
    from src.smartparent.rag.token_accountant import TokenAccountingResult


@runtime_checkable
class IIntentClassifier(Protocol):
    """
    Protocol contract for Neuro-Symbolic NLU Intent Classification and BIO Slot Tagging.
    """

    def predict(
        self,
        text: str,
        authorized_family_children: Optional[List[str]] = None,
        previous_session_state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Classify input text across 6 academic pillars + security firewall + entity slots."""
        ...

    def security_check(self, text: str) -> Tuple[bool, Optional[str]]:
        """Evaluate zero-mutation security firewall against destructive or financial intent."""
        ...

    def resolve_child_entity(
        self,
        tokens: List[str],
        tags: List[str],
        authorized_children: Optional[List[str]] = None,
    ) -> Optional[str]:
        """Resolve child name from tagged tokens against authorized roster."""
        ...


@runtime_checkable
class ITelemetryRetriever(Protocol):
    """
    Protocol contract for multi-tenant read-only student academic telemetry retrieval.
    """

    def retrieve(
        self,
        subscriber_id: str,
        child_id: Optional[str] = None,
    ) -> ChildDiagnosticTelemetry:
        """Fetch verified student diagnostic telemetry with strict tenant isolation."""
        ...

    def get_child_telemetry(
        self,
        parent_id: str,
        child_id: Optional[str] = None,
        child_name: Optional[str] = None,
    ) -> ChildDiagnosticTelemetry:
        """Fetch child telemetry by name and parent ID."""
        ...


@runtime_checkable
class IContextBuilder(Protocol):
    """
    Protocol contract for dynamic context assembly, taxonomy mapping, and reranking.
    """

    def resolve_topic(
        self,
        query_text: str,
        subject: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Resolve raw textual query into canonical syllabus curriculum node."""
        ...

    def rerank_and_deduplicate_gaps(
        self,
        telemetry: ChildDiagnosticTelemetry,
        requested_subject: Optional[str] = None,
        max_k: int = 3,
    ) -> List[Dict[str, Any]]:
        """Pedagogical severity reranking based on dynamic marks lost and mastery deficit."""
        ...

    def build_context(
        self,
        telemetry: ChildDiagnosticTelemetry,
        nlu_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Construct grounded context envelope for 5D tensor generation."""
        ...


@runtime_checkable
class IAnswerSynthesizer(Protocol):
    """
    Protocol contract for 5D Compositional Tensor NLG dual-modal response generation.
    """

    def synthesize(
        self,
        pillar_id: int,
        query_text: str,
        telemetry: ChildDiagnosticTelemetry,
        requested_subject: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], str]:
        """Generate (visual_card, spoken_narrative) deterministically from verified telemetry."""
        ...

    def verbalize_for_tts(self, text: str) -> str:
        """Phonetic pre-verbalization for native mobile TTS."""
        ...

    def validate_grounding(
        self,
        spoken_text: str,
        telemetry: ChildDiagnosticTelemetry,
        pillar_id: int,
    ) -> bool:
        """Verify mathematical fact-checking against underlying telemetry (0.00% hallucination)."""
        ...


@runtime_checkable
class ITokenAccountant(Protocol):
    """
    Protocol contract for Diagnostic Token metering, tier entitlement, and quota accounting.
    """

    def preflight_check(
        self,
        plan_tier: str,
        query_mode: str,
        used_tokens_before: int,
        used_voice_before: int,
    ) -> Optional[Dict[str, Any]]:
        """Pre-execution quota verification."""
        ...

    def settle(
        self,
        plan_tier: str,
        query_mode: str,
        input_text: str,
        spoken_output: str,
        visual_card: Dict[str, Any],
        used_tokens_before: int,
        used_voice_before: int,
    ) -> TokenAccountingResult:
        """Post-execution deterministic subword token settlement."""
        ...


@runtime_checkable
class IVoiceProcessor(Protocol):
    """
    Protocol contract for self-hosted Speech-to-Text and in-memory zero-disk retention audio processing.
    """

    def transcribe_audio(
        self,
        audio_stream: io.BytesIO,
        hotwords: Optional[List[str]] = None,
        language: str = "en",
    ) -> Tuple[str, float]:
        """In-memory transcription with hotword biasing. Returns (text, latency_ms)."""
        ...

    def scrub_audio_buffer(self, audio_bytes: bytes) -> None:
        """Cryptographic / memory scrub of volatile audio RAM (DPDP Act / COPPA compliance)."""
        ...


@runtime_checkable
class IAssistantAgent(Protocol):
    """
    Protocol contract for the Master Ask Studiqs Multimodal Assistant.
    """

    def ask_text(
        self,
        query_text: str,
        parent_id: str = "parent_001",
        plan_tier: str = "PRO",
        child_id: Optional[str] = None,
        authorized_children: Optional[List[str]] = None,
        used_tokens_before: int = 0,
        used_voice_before: int = 0,
        previous_session_state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute typed query lifecycle."""
        ...

    def ask_voice(
        self,
        audio_stream: io.BytesIO,
        parent_id: str = "parent_001",
        plan_tier: str = "PRO",
        child_id: Optional[str] = None,
        authorized_children: Optional[List[str]] = None,
        used_tokens_before: int = 0,
        used_voice_before: int = 0,
        previous_session_state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute spoken voice query lifecycle."""
        ...
