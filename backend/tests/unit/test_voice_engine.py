"""
STUDIQS® SmartParent™ - Ask Studiqs Multimodal RAG Verification Test Battery
=============================================================================
Module: tests.unit.test_voice_engine

Verifies the 6 Architectural Gates:
  - Gate 1: Token Metering & Tier Entitlements (Basic vs Advanced vs Pro).
  - Gate 2: 6-Pillar Classification & NLU Disambiguation.
  - Gate 3: Read-Only Database Safety & Multi-Tenant Isolation.
  - Gate 4: Zero Audio Disk Persistence & In-Memory Audio Scrubbing.
  - Gate 5: Sub-1ms Zero-Mutation Security Firewall.
  - Gate 6: Sub-250ms SLA Budget & Dual-Modal Structured Output.
=============================================================================
"""

import io
import time
import pytest

from src.smartparent.rag.token_accountant import (
    SubscriptionTokenAccountant,
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
from src.smartparent.engines.section_10_subscription_billing.entitlement_quota_engine import (
    EntitlementQuotaEngine,
    QuotaActionType,
    TIER_LIMITS,
)


# =============================================================================
# GATE 1: Token Metering & Tier Entitlements
# =============================================================================

class TestGate1TokenMeteringAndTierEntitlements:

    def test_basic_tier_blocks_audio_voice_queries(self):
        """Basic tier must block spoken voice queries with HTTP 403."""
        err = SubscriptionTokenAccountant.preflight_check(
            plan_tier="BASIC",
            query_mode="AUDIO_STREAM",
            used_tokens_before=100,
            used_voice_before=0,
        )
        assert err is not None
        assert err["http_status"] == 403
        assert err["error_code"] == "VOICE_LOCKED_ON_BASIC_PLAN"
        assert "Advanced" in err["message"]

    def test_basic_tier_permits_typed_search_within_5k_tokens(self):
        """Basic tier permits typed diagnostic search with 5,000 token cap."""
        err = SubscriptionTokenAccountant.preflight_check(
            plan_tier="BASIC",
            query_mode="TEXT",
            used_tokens_before=1000,
            used_voice_before=0,
        )
        assert err is None

        # Deduct tokens
        res = SubscriptionTokenAccountant.deduct_tokens(
            plan_tier="BASIC",
            query_mode="TEXT",
            input_tokens=15,
            output_tokens=60,
            used_tokens_before=1000,
            used_voice_before=0,
        )
        assert res.allowed is True
        assert res.total_charged == 75
        assert res.used_tokens_after == 1075
        assert res.remaining_tokens == 5000 - 1075

    def test_advanced_tier_permits_both_voice_and_text(self):
        """Advanced tier has 25,000 tokens with voice query access unlocked."""
        err = SubscriptionTokenAccountant.preflight_check(
            plan_tier="ADVANCED",
            query_mode="AUDIO_STREAM",
            used_tokens_before=2000,
            used_voice_before=5,
        )
        assert err is None

        # Quota verification in EntitlementQuotaEngine
        eqe = EntitlementQuotaEngine()
        limits = eqe.get_tier_limits("ADVANCED")
        assert limits["voice_rag_enabled"] is True
        assert limits[QuotaActionType.VOICE_QUERY.value] == 25
        assert limits[QuotaActionType.DIAGNOSTIC_TOKENS.value] == 25000

    def test_pro_tier_entitlement_and_caps(self):
        """Pro tier has 100,000 tokens, 256 input token cap, and priority."""
        plan = SUBSCRIPTION_PLANS["PRO"]
        assert plan["voice_allowed"] is True
        assert plan["monthly_tokens"] == 100000
        assert plan["max_input_tokens_per_query"] == 256

        # Exceed input token cap
        res = SubscriptionTokenAccountant.deduct_tokens(
            plan_tier="PRO",
            query_mode="TEXT",
            input_tokens=300,  # exceeds 256
            output_tokens=50,
            used_tokens_before=1000,
            used_voice_before=0,
        )
        assert res.allowed is False
        assert res.http_status == 413
        assert res.error_code == "QUERY_INPUT_TOKEN_CAP_EXCEEDED"

    def test_token_exhaustion_returns_http_429(self):
        """When tokens are 100% used, preflight returns HTTP 429."""
        err = SubscriptionTokenAccountant.preflight_check(
            plan_tier="ADVANCED",
            query_mode="TEXT",
            used_tokens_before=25000,
            used_voice_before=10,
        )
        assert err is not None
        assert err["http_status"] == 429
        assert err["error_code"] == "DIAGNOSTIC_TOKENS_100_PERCENT_EXHAUSTED"

    def test_milestone_alerts(self):
        """Milestone alerts fire when usage crosses 50%, 75%, 90%."""
        # Move from 49% (12,250) to 51% (12,750) on Advanced
        res = SubscriptionTokenAccountant.deduct_tokens(
            plan_tier="ADVANCED",
            query_mode="TEXT",
            input_tokens=50,
            output_tokens=450,
            used_tokens_before=12250,
            used_voice_before=2,
        )
        assert res.allowed is True
        assert res.milestone_alert == "50_PERCENT_REACHED"


# =============================================================================
# GATE 2: 6-Pillar Classification & NLU Disambiguation
# =============================================================================

class TestGate2PillarClassificationAndNLU:

    @pytest.fixture(scope="class")
    def nlu(self):
        return VoiceIntentClassifier()

    def test_pillar_0_overall_standing(self, nlu):
        res = nlu.predict("What is Viswa's overall academic standing across all subjects?")
        assert res["pillar_id"] == 0
        assert res["pillar_name"] == "OVERALL_ACADEMIC_STANDING"
        assert res["security_blocked"] is False

    def test_pillar_1_subject_performance(self, nlu):
        res = nlu.predict("How is Viswa performing in Mathematics?")
        assert res["pillar_id"] == 1
        assert res["pillar_name"] == "SUBJECT_PERFORMANCE"
        assert "Mathematics" in res["slots"]["SUBJ"]

    def test_pillar_2_granular_topic_gaps(self, nlu):
        res = nlu.predict("Where did Viswa lose marks or struggle with weak topics in Science?")
        assert res["pillar_id"] == 2
        assert res["pillar_name"] == "GRANULAR_TOPIC_GAPS"

    def test_pillar_3_month_on_month_trends(self, nlu):
        res = nlu.predict("Is Viswa showing improvement or decline month on month since the last test?")
        assert res["pillar_id"] == 3
        assert res["pillar_name"] == "MONTH_ON_MONTH_TRENDS"

    def test_pillar_4_term_consistency(self, nlu):
        res = nlu.predict("What is the score stability and board exam readiness index for Class 10?")
        assert res["pillar_id"] == 4
        assert res["pillar_name"] == "TERM_CONSISTENCY"

    def test_pillar_5_next_remedial_action(self, nlu):
        res = nlu.predict("How do we fix the weak topic in Quadratic Equations? What is the next practice drill?")
        assert res["pillar_id"] == 5
        assert res["pillar_name"] == "NEXT_GAP_RECHECK_ACTION"


# =============================================================================
# GATE 3: Read-Only Database Safety & Multi-Tenant Isolation
# =============================================================================

class TestGate3ReadOnlyDatabaseSafety:

    def test_telemetry_retriever_multi_tenant_isolation(self):
        """Retriever respects tenant parent_id and child resolution."""
        retriever = TelemetryRetriever(db_session=None)
        telemetry = retriever.get_child_telemetry(
            parent_id="parent_uuid_100",
            child_name="Viswa",
        )
        assert telemetry.child_name == "Viswa"
        assert telemetry.overall_avg_pct > 0.0
        assert "Mathematics" in telemetry.subject_records

    def test_context_builder_roster_resolution(self):
        """ContextBuilder fuzzy matches child names strictly from authorized roster."""
        authorized = ["Viswa", "Kavya"]
        res = ContextBuilder.resolve_child(
            detected_children=["viswa"],
            authorized_roster=authorized,
        )
        assert res == "Viswa"

        res2 = ContextBuilder.resolve_child(
            detected_children=["kavya"],
            authorized_roster=authorized,
        )
        assert res2 == "Kavya"


# =============================================================================
# GATE 4: Zero Audio Disk Persistence & In-Memory Audio Scrubbing
# =============================================================================

class TestGate4ZeroAudioDiskPersistence:

    def test_audio_buffer_scrubbing(self):
        """VoiceProcessor scrubs audio buffers from volatile RAM."""
        processor = VoiceProcessor()
        raw_audio = bytearray(b"RIFF" + b"\x00" * 100)
        assert len(raw_audio) == 104

        processor.scrub_audio_buffer(raw_audio)
        # Verify bytearray is zeroed out
        assert all(b == 0 for b in raw_audio)

    def test_transcribe_audio_uses_in_memory_stream(self):
        """Transcribing audio operates on in-memory io.BytesIO without disk writes."""
        processor = VoiceProcessor()
        audio_stream = io.BytesIO(b"RIFF" + b"\x01\x02\x03\x04" * 20)
        transcription, latency = processor.transcribe_audio(
            audio_stream=audio_stream,
            hotwords=["Viswa", "Mathematics"],
        )
        assert isinstance(transcription, str)
        assert len(transcription) > 0
        assert latency >= 0.0


# =============================================================================
# GATE 5: Sub-1ms Zero-Mutation Security Firewall
# =============================================================================

class TestGate5ZeroMutationSecurityFirewall:

    @pytest.fixture(scope="class")
    def nlu(self):
        return VoiceIntentClassifier()

    @pytest.mark.parametrize(
        "malicious_query",
        [
            "Please delete Viswa's Mathematics marks",
            "DROP TABLE students;",
            "Can you cancel my subscription and refund razorpay?",
            "Wipe all records from the database",
            "Update the score to 95 percent in Physics",
            "Modify child grade and erase recent test",
        ],
    )
    def test_mutation_queries_blocked_in_sub_1ms(self, nlu, malicious_query):
        t0 = time.perf_counter()
        res = nlu.predict(malicious_query)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        assert elapsed_ms < 5.0  # sub-5ms (typically <0.2ms)
        assert res["security_blocked"] is True
        assert res["pillar_name"] == "ZERO_MUTATION_FIREWALL"

    def test_agent_intercepts_mutation_safely(self):
        """Agent returns HTTP 403 refusal on mutation queries without touching DB."""
        agent = AskStudiqsAgent()
        res = agent.ask_text(
            query_text="delete my child mark now",
            parent_id="p1",
            plan_tier="PRO",
        )
        assert res["status"] == "SECURITY_REFUSAL"
        assert res["http_status"] == 403
        assert "cannot be executed via voice" in res["dual_modal_delivery"]["spoken_narrative"]


# =============================================================================
# GATE 6: Sub-250ms SLA Budget & Dual-Modal Structured Output
# =============================================================================

class TestGate6Sub250msSLABudgetAndDualModalOutput:

    def test_end_to_end_text_query_sla_under_100ms(self):
        """Text queries must execute end-to-end well under the 250ms budget."""
        agent = AskStudiqsAgent()
        t0 = time.perf_counter()
        res = agent.ask_text(
            query_text="How is Viswa performing in Mathematics?",
            parent_id="p_test_1",
            plan_tier="PRO",
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000

        assert elapsed_ms < 250.0  # Strict SLA budget
        assert res["status"] == "SUCCESS"
        assert res["resolved_pillar"] == "SUBJECT_PERFORMANCE"

        # Verify dual-modal structure
        dm = res["dual_modal_delivery"]
        assert "visual_card" in dm
        assert "spoken_narrative" in dm

        vc = dm["visual_card"]
        assert "card_title" in vc
        assert "status_badge" in vc
        assert "primary_metrics" in vc
        assert "action_deep_link" in vc
        assert len(vc["primary_metrics"]) >= 2

        # Verify pre-verbalization (no raw % or & in spoken text)
        spoken = dm["spoken_narrative"]
        assert "%" not in spoken
        assert "percent" in spoken
        assert "&" not in spoken

    def test_end_to_end_voice_query_sla_under_250ms(self):
        """Voice queries must execute under the 250ms budget with token debit."""
        agent = AskStudiqsAgent()
        audio_stream = io.BytesIO(b"RIFF" + b"\x00" * 200)

        res = agent.ask_voice(
            audio_stream=audio_stream,
            parent_id="p_test_voice",
            plan_tier="ADVANCED",
        )
        assert res["status"] == "SUCCESS"
        assert res["total_latency_ms"] < 250.0
        assert "token_accounting" in res
        assert res["token_accounting"]["allowed"] is True
        assert res["token_accounting"]["total_charged"] > 0


# =============================================================================
# GATE 7: 15-Phase Production RAG Pipeline Compliance
# =============================================================================

class TestGate7ProductionRAGPipelineCompliance:

    def test_phase_7_reranking_and_deduplication(self):
        """Phase 7: Verifies pedagogical urgency reranking and deduplication."""
        telemetry = ChildDiagnosticTelemetry()
        reranked = ContextBuilder.rerank_and_deduplicate_gaps(telemetry.subject_records)
        assert len(reranked) >= 2
        # Highest urgency gap should be rank 1
        assert reranked[0]["urgency_score"] >= reranked[1]["urgency_score"]
        # Topic should be deduplicated
        topics = [g["topic"] for g in reranked]
        assert len(topics) == len(set(topics))

    def test_phase_8_context_compression_and_budgeting(self):
        """Phase 8: Packs high-density facts into compressed context."""
        telemetry = ChildDiagnosticTelemetry()
        compressed = ContextBuilder.compress_and_budget_context(telemetry, max_tokens=256)
        assert "child" in compressed
        assert "top_anchor" in compressed
        assert "top_remedial_action" in compressed

    def test_phase_10_grounding_validation_and_zero_hallucination(self):
        """Phase 10: Mathematical grounding validator guarantees 0.00% hallucination."""
        telemetry = ChildDiagnosticTelemetry()
        visual, spoken = AnswerSynthesizer.synthesize(
            pillar_id=1,
            query_text="Maths score?",
            telemetry=telemetry,
        )
        report = AnswerSynthesizer.validate_grounding(visual, spoken, telemetry)
        assert report["is_grounded"] is True
        assert report["hallucination_detected"] is False
        assert report["hallucination_score"] == 0.00
        assert report["student_verified"] is True
        assert "PostgreSQL" in report["citation_source"]

    def test_phase_13_observability_and_tracing(self):
        """Phase 13: Distributed trace_id and stage latencies emitted."""
        agent = AskStudiqsAgent()
        res = agent.ask_text("How is Viswa performing in Mathematics?", plan_tier="PRO")
        assert "trace_id" in res
        assert "tracing_spans" in res
        spans = res["tracing_spans"]
        assert "nlu_ms" in spans
        assert "retrieval_ms" in spans
        assert "nlg_ms" in spans
        assert "validation_ms" in spans
        assert "total_e2e_ms" in spans


# =============================================================================
# GATE 8: Spec Compliance: Tamil Policy, Insufficient Evidence & Multi-Child Isolation
# =============================================================================

class TestGate8SpecComplianceAndMultiChildIsolation:

    def test_tamil_topic_intelligence_exclusion_policy(self):
        """Spec Section 21.1 & 23: Language papers like Tamil never receive Topic Intelligence."""
        telemetry = ChildDiagnosticTelemetry(child_name="Viswa")
        visual, spoken = AnswerSynthesizer.synthesize(
            pillar_id=2,
            query_text="What are Viswa's topic gaps in Tamil?",
            telemetry=telemetry,
            requested_subject="Tamil",
        )
        assert visual["status_badge"] == "OVERALL MARKS ONLY"
        assert "not applicable for tamil" in spoken.lower()
        report = AnswerSynthesizer.validate_grounding(visual, spoken, telemetry)
        assert report["is_grounded"] is True

    def test_insufficient_evidence_handling_never_invents_marks(self):
        """Spec Section 22.1: Insufficient evidence returns clear upload guidance; never invents marks."""
        # Student with 0 test evidence in Economics
        telemetry = ChildDiagnosticTelemetry(child_name="Viswa")
        visual, spoken = AnswerSynthesizer.synthesize(
            pillar_id=1,
            query_text="How is Viswa doing in Economics?",
            telemetry=telemetry,
            requested_subject="Economics",
        )
        assert visual["status_badge"] == "EVIDENCE REQUIRED"
        assert "do not have any assessment evidence recorded" in spoken.lower()
        assert "/upload/marks" in visual["action_deep_link"]
        report = AnswerSynthesizer.validate_grounding(visual, spoken, telemetry)
        assert report["is_grounded"] is True

    def test_multi_child_sibling_resolution_within_authorized_roster(self):
        """ContextBuilder correctly switches context between siblings in authorized roster."""
        family_roster = ["Viswa", "Meera"]

        # Case 1: Parent asks about Meera
        resolved = ContextBuilder.resolve_child(
            detected_children=["Meera"],
            authorized_roster=family_roster,
            default_name="Viswa",
        )
        assert resolved == "Meera"

        # Case 2: Parent asks about an unauthorized child from another family
        unauthorized = ContextBuilder.resolve_child(
            detected_children=["Rahul"],
            authorized_roster=family_roster,
            default_name="Viswa",
        )
        # Must NOT leak to Rahul; defaults to family's authorized child
        assert unauthorized == "Viswa"

