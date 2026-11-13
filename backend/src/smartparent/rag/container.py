"""
STUDIQS® SmartParent™ - Ask Studiqs Dependency Injection Container & Service Factory
=============================================================================
Module: src.smartparent.rag.container

Implements enterprise Inversion of Control (IoC) and Dependency Injection (DI):
  - Centralizes lifecycle management of heavy ML models, NLU classifiers,
    telemetry retrievers, context builders, and synthesis engines.
  - Guarantees Singletons for stateless or heavy components.
  - Provides Scoped / Factory construction for session-dependent components.
  - Decouples API endpoints, background workers, and test fixtures from concrete
    implementations adhering to SOLID & Dependency Inversion Principle.
=============================================================================
"""

import threading
from typing import Optional
from sqlalchemy.orm import Session

from src.smartparent.rag.interfaces import (
    IIntentClassifier,
    ITelemetryRetriever,
    IContextBuilder,
    IAnswerSynthesizer,
    ITokenAccountant,
    IVoiceProcessor,
    IAssistantAgent,
)
from src.smartparent.rag.intent_classifier import VoiceIntentClassifier
from src.smartparent.rag.voice_processor import VoiceProcessor
from src.smartparent.rag.token_accountant import SubscriptionTokenAccountant
from src.smartparent.rag.context_builder import ContextBuilder
from src.smartparent.rag.answer_synthesizer import AnswerSynthesizer
from src.smartparent.rag.telemetry_retriever import TelemetryRetriever
from src.smartparent.rag.model_registry import NLUModelRegistry, SpeechModelRegistry


class RAGContainer:
    """
    Production Dependency Injection Container for Ask Studiqs Multimodal RAG.
    """

    _lock = threading.Lock()
    _nlu_instance: Optional[IIntentClassifier] = None
    _voice_instance: Optional[IVoiceProcessor] = None
    _token_accountant_instance: Optional[ITokenAccountant] = None
    _context_builder_class = ContextBuilder
    _synthesizer_class = AnswerSynthesizer

    @classmethod
    def get_nlu_classifier(cls, bundle_dir: Optional[str] = None) -> IIntentClassifier:
        """Returns the singleton NLU intent classifier."""
        if cls._nlu_instance is None:
            with cls._lock:
                if cls._nlu_instance is None:
                    cls._nlu_instance = VoiceIntentClassifier(bundle_dir=bundle_dir)
        return cls._nlu_instance

    @classmethod
    def get_voice_processor(cls) -> IVoiceProcessor:
        """Returns the singleton Speech-to-Text voice processor."""
        if cls._voice_instance is None:
            with cls._lock:
                if cls._voice_instance is None:
                    cls._voice_instance = VoiceProcessor()
        return cls._voice_instance

    @classmethod
    def get_token_accountant(cls) -> ITokenAccountant:
        """Returns the singleton token accounting engine."""
        if cls._token_accountant_instance is None:
            with cls._lock:
                if cls._token_accountant_instance is None:
                    cls._token_accountant_instance = SubscriptionTokenAccountant()
        return cls._token_accountant_instance

    @classmethod
    def get_context_builder(cls) -> IContextBuilder:
        """Returns the context builder service."""
        return cls._context_builder_class()

    @classmethod
    def get_answer_synthesizer(cls) -> IAnswerSynthesizer:
        """Returns the answer synthesizer service."""
        return cls._synthesizer_class()

    @classmethod
    def create_telemetry_retriever(cls, db_session: Optional[Session] = None) -> ITelemetryRetriever:
        """Factory for scoped TelemetryRetriever instances bound to active DB session."""
        return TelemetryRetriever(db_session=db_session)

    @classmethod
    def create_agent(
        cls,
        db_session: Optional[Session] = None,
        bundle_dir: Optional[str] = None,
        enable_mlops: bool = True,
    ) -> IAssistantAgent:
        """
        Factory method to construct a fully wired AskStudiqsAgent instance.
        """
        from src.smartparent.rag.assistant_engine import AskStudiqsAgent

        return AskStudiqsAgent(
            nlu=cls.get_nlu_classifier(bundle_dir=bundle_dir),
            retriever=cls.create_telemetry_retriever(db_session=db_session),
            context_builder=cls.get_context_builder(),
            synthesizer=cls.get_answer_synthesizer(),
            token_accountant=cls.get_token_accountant(),
            voice_processor=cls.get_voice_processor(),
            bundle_dir=bundle_dir,
            db_session=db_session,
            enable_mlops=enable_mlops,
        )

    @classmethod
    def warm_up(cls, bundle_dir: Optional[str] = None) -> None:
        """
        Eager warm-up hook for production container lifecycle startup probes.
        """
        registry = NLUModelRegistry.get_instance(bundle_dir=bundle_dir)
        registry.warm_up()
        cls.get_nlu_classifier(bundle_dir=bundle_dir)
        cls.get_voice_processor()

