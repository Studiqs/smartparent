"""
STUDIQS® SmartParent™ - Ultra-Robust Multimodal RAG Package
=============================================================================
Package: src.smartparent.rag

Exports public interfaces:
  - AskStudiqsAgent: Master Multimodal RAG orchestrator.
  - VoiceIntentClassifier: 3-Head Neuro-Symbolic NLU Engine.
  - TelemetryRetriever: Live PostgreSQL Student Telemetry Retriever.
  - ContextBuilder: 2-Stage Entity & Syllabus Taxonomy Resolver.
  - AnswerSynthesizer: 5D Compositional Tensor NLG Engine.
  - VoiceProcessor: In-Memory STT & Audio Scrubber.
  - SubscriptionTokenAccountant: LLM-Style Diagnostic Token Metering.
=============================================================================
"""

from src.smartparent.rag.interfaces import (
    IIntentClassifier,
    ITelemetryRetriever,
    IContextBuilder,
    IAnswerSynthesizer,
    ITokenAccountant,
    IVoiceProcessor,
    IAssistantAgent,
)
from src.smartparent.rag.model_registry import NLUModelRegistry, SpeechModelRegistry
from src.smartparent.rag.container import RAGContainer
from src.smartparent.rag.token_accountant import (
    SubscriptionTokenAccountant,
    TokenAccountingResult,
    SUBSCRIPTION_PLANS,
)
from src.smartparent.rag.intent_classifier import VoiceIntentClassifier
from src.smartparent.rag.telemetry_retriever import (
    TelemetryRetriever,
    ChildDiagnosticTelemetry,
    SubjectTelemetry,
)
from src.smartparent.rag.context_builder import ContextBuilder
from src.smartparent.rag.voice_processor import VoiceProcessor
from src.smartparent.rag.answer_synthesizer import AnswerSynthesizer
from src.smartparent.rag.assistant_engine import AskStudiqsAgent

__all__ = [
    "IIntentClassifier",
    "ITelemetryRetriever",
    "IContextBuilder",
    "IAnswerSynthesizer",
    "ITokenAccountant",
    "IVoiceProcessor",
    "IAssistantAgent",
    "NLUModelRegistry",
    "SpeechModelRegistry",
    "RAGContainer",
    "AskStudiqsAgent",
    "VoiceIntentClassifier",
    "TelemetryRetriever",
    "ChildDiagnosticTelemetry",
    "SubjectTelemetry",
    "ContextBuilder",
    "VoiceProcessor",
    "AnswerSynthesizer",
    "SubscriptionTokenAccountant",
    "TokenAccountingResult",
    "SUBSCRIPTION_PLANS",
]

