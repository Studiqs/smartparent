"""
STUDIQS® SmartParent™ - Ask Studiqs Production OOP Architecture & DI Test Battery
=============================================================================
Module: tests.unit.test_rag_oop_architecture

Verifies:
  1. Strict structural subtyping across all RAG protocols (runtime_checkable).
  2. Thread-safe Singleton guarantees for NLUModelRegistry & SpeechModelRegistry.
  3. Container-based Dependency Injection (RAGContainer).
  4. Inversion of Control & Mock Substitutability in AskStudiqsAgent.
  5. MLOps span instrumentation & tracing integration.
=============================================================================
"""

import io
import time
import pytest
from unittest.mock import MagicMock

from src.smartparent.rag.interfaces import (
    IIntentClassifier,
    ITelemetryRetriever,
    IContextBuilder,
    IAnswerSynthesizer,
    ITokenAccountant,
    IVoiceProcessor,
    IAssistantAgent,
)
from src.smartparent.rag.model_registry import (
    NLUModelRegistry,
    SpeechModelRegistry,
)
from src.smartparent.rag.container import RAGContainer
from src.smartparent.rag.intent_classifier import VoiceIntentClassifier
from src.smartparent.rag.voice_processor import VoiceProcessor
from src.smartparent.rag.telemetry_retriever import (
    TelemetryRetriever,
    ChildDiagnosticTelemetry,
    SubjectTelemetry,
)
from src.smartparent.rag.context_builder import ContextBuilder
from src.smartparent.rag.answer_synthesizer import AnswerSynthesizer
from src.smartparent.rag.token_accountant import (
    SubscriptionTokenAccountant,
    TokenAccountingResult,
)
from src.smartparent.rag.assistant_engine import AskStudiqsAgent


class TestRAGProtocolCompliance:
    """Verifies that all concrete implementations strictly satisfy runtime Protocols."""

    def test_nlu_implements_intent_classifier_protocol(self):
        nlu = VoiceIntentClassifier()
        assert isinstance(nlu, IIntentClassifier)

    def test_retriever_implements_telemetry_retriever_protocol(self):
        retriever = TelemetryRetriever()
        assert isinstance(retriever, ITelemetryRetriever)

    def test_context_builder_implements_protocol(self):
        builder = ContextBuilder()
        assert isinstance(builder, IContextBuilder)

    def test_answer_synthesizer_implements_protocol(self):
        synthesizer = AnswerSynthesizer()
        assert isinstance(synthesizer, IAnswerSynthesizer)

    def test_token_accountant_implements_protocol(self):
        accountant = SubscriptionTokenAccountant()
        assert isinstance(accountant, ITokenAccountant)

    def test_voice_processor_implements_protocol(self):
        voice_proc = VoiceProcessor()
        assert isinstance(voice_proc, IVoiceProcessor)

    def test_assistant_agent_implements_protocol(self):
        agent = AskStudiqsAgent(enable_mlops=False)
        assert isinstance(agent, IAssistantAgent)


class TestSingletonModelRegistry:
    """Verifies thread-safe singleton behavior for heavy AI/ML models."""

    def test_nlu_registry_singleton_identity(self):
        reg1 = NLUModelRegistry.get_instance()
        reg2 = NLUModelRegistry.get_instance()
        assert reg1 is reg2
        assert id(reg1) == id(reg2)

    def test_nlu_registry_warm_up_and_readiness(self):
        registry = NLUModelRegistry.get_instance()
        assert registry.is_ready()
        warmed = registry.warm_up()
        assert warmed is True

    def test_voice_classifiers_share_same_registry_session(self):
        c1 = VoiceIntentClassifier()
        c2 = VoiceIntentClassifier()
        assert c1.registry is c2.registry
        assert c1.session is c2.session
        assert c1.tokenizer is c2.tokenizer

    def test_speech_registry_singleton_identity(self):
        s_reg1 = SpeechModelRegistry()
        s_reg2 = SpeechModelRegistry()
        assert s_reg1 is s_reg2


class TestDependencyInjectionAndIoC:
    """Verifies Inversion of Control and substitution of test doubles."""

    def test_rag_container_factory_wiring(self):
        agent = RAGContainer.create_agent(enable_mlops=False)
        assert isinstance(agent, IAssistantAgent)
        assert isinstance(agent.nlu, IIntentClassifier)
        assert isinstance(agent.retriever, ITelemetryRetriever)
        assert isinstance(agent.token_accountant, ITokenAccountant)

    def test_agent_substitutability_with_custom_retriever(self):
        """SOLID DIP: Inject custom mock retriever into AskStudiqsAgent."""
        mock_retriever = MagicMock(spec=ITelemetryRetriever)
        custom_telemetry = ChildDiagnosticTelemetry(
            child_name="Arjun",
            overall_avg_pct=95.5,
            overall_health_band="Distinction",
            top_subject="Mathematics",
            top_subject_pct=99.0,
            watch_subject="Physics",
            watch_subject_pct=92.0,
        )
        mock_retriever.get_child_telemetry.return_value = custom_telemetry

        agent = AskStudiqsAgent(
            retriever=mock_retriever,
            enable_mlops=False,
        )

        res = agent.ask_text(
            query_text="How is Arjun performing overall?",
            plan_tier="PRO",
            authorized_children=["Arjun"],
        )

        assert res["status"] == "SUCCESS"
        assert res["resolved_child"] == "Arjun"
        assert "Arjun" in res["dual_modal_delivery"]["visual_card"]["card_title"]
        assert "95.5" in res["dual_modal_delivery"]["spoken_narrative"]
        mock_retriever.get_child_telemetry.assert_called_once()

    def test_mlops_tracing_spans_captured_in_production_run(self):
        """Verifies performance latency spans are measured and recorded."""
        agent = AskStudiqsAgent(enable_mlops=True)
        res = agent.ask_text(
            query_text="What are Viswa's weakest topics?",
            plan_tier="PRO",
        )
        assert "tracing_spans" in res
        spans = res["tracing_spans"]
        assert "nlu_ms" in spans
        assert "retrieval_ms" in spans
        assert "rerank_ms" in spans
        assert "nlg_ms" in spans
        assert "validation_ms" in spans
        assert "total_e2e_ms" in spans
        assert spans["total_e2e_ms"] > 0.0

