"""
STUDIQS® SmartParent™ Intelligence Engines Package
=============================================================================
Organized into Section-Aligned Packages:
  - section_00_core: Foundation, BaseEngine, MLflow Telemetry
  - section_03_qp_intelligence: Section 3 Evidence Intake & Topic Intelligence
  - section_04_consolidated_reports: Section 4 Consolidated Report Lifecycle & PDF
  - section_05_performance_intelligence: Section 5 Consistency Curves & Gap Rechecks
  - section_06_parent_pulse: Section 6 Monthly Parent Pulse Triad
  - section_07_09_academic_handoff: Section 7 & 9 Academic Handoff & PTM Pack
  - section_08_board_readiness: Section 8 Board Readiness & Stream Alignment
  - section_11_12_marketplace: Section 11, 12, 21 Expert Marketplace & Anti-Contact
=============================================================================
"""

# Re-export subpackages
from . import section_00_core
from . import section_03_qp_intelligence
from . import section_04_consolidated_reports
from . import section_05_performance_intelligence
from . import section_06_parent_pulse
from . import section_07_09_academic_handoff
from . import section_08_board_readiness
from . import section_10_subscription_billing
from . import section_11_12_marketplace

# Re-export core classes & functions for direct engines package imports
from .section_00_core.base_engine import (
    BaseEngine,
    EngineHealthStatus,
    CircuitBreaker,
    CircuitState,
    resilient_engine_step,
)
from .section_00_core.mlflow_tracker import get_mlops_tracker

from .section_03_qp_intelligence.quick_marks_engine import (
    QuickMarksEngine,
    QuickMarksBatchInput,
    SubjectMarkInput,
    QuickMarksResult,
    SubjectTelemetry,
)
from .section_03_qp_intelligence.result_parser import (
    ResultParserEngine,
    ResultParserOutput,
    ExtractedSubjectMark,
)
from .section_03_qp_intelligence.qp_parser import QuestionExtractor
from .section_03_qp_intelligence.topic_mapper import QPTopicMapperV3
from .section_03_qp_intelligence.marks_entry_engine import MarksEntryEngine
from .section_03_qp_intelligence.marks_grid_service import MarksGridService
from .section_03_qp_intelligence.topic_scoring_engine import TopicScoringEngine
from .section_03_qp_intelligence.topic_mastery_engine import TopicMasteryEngine
from .section_03_qp_intelligence.topic_gap_engine import TopicGapEngine
from .section_03_qp_intelligence.topic_intelligence_engine import TopicIntelligenceEngine
from .section_03_qp_intelligence.topic_coverage_engine import TopicCoverageEngine
from .section_03_qp_intelligence.nlp_preprocessor import NLPPreprocessor, NLPPreprocessorEngine
from .section_03_qp_intelligence.novel_topic_discovery_engine import NovelTopicDiscoveryEngine

from .section_04_consolidated_reports.report_generator import ReportGenerator

from .section_05_performance_intelligence.performance_consistency_engine import PerformanceConsistencyEngine
from .section_05_performance_intelligence.consistency_engine import (
    ConsistencyEngine,
    AssessmentRecordSchema,
    TrajectoryEvaluationResult,
    MultiSubjectConsistencyResult,
)
from .section_05_performance_intelligence.gap_recheck_engine import GapRecheckEngine

from .section_06_parent_pulse.parent_pulse_engine import ParentPulseEngine
from .section_06_parent_pulse.parent_satisfaction_engine import calculate_parent_satisfaction

from .section_07_09_academic_handoff.academic_handoff_engine import AcademicHandoffEngine

from .section_08_board_readiness.board_readiness_engine import BoardReadinessEngine
from .section_08_board_readiness.achievement_engine import AchievementEngine, calculate_achievement
from .section_08_board_readiness.stream_readiness_engine import (
    calculate_stream_readiness,
    classify_readiness,
    normalize_subject,
    build_stream_subject_map,
)
from .section_08_board_readiness.projected_cutoff_engine import calculate_projected_cutoff
from .section_08_board_readiness.projected_score_engine import calculate_projected_score, get_mastery_level
from .section_08_board_readiness.career_readiness_engine import calculate_career_readiness
from .section_08_board_readiness.college_recommendation_engine import get_recommendations, find_best_path
from .section_08_board_readiness.future_readiness_engine import generate_report, determine_best_path

from .section_10_subscription_billing.subscription_pricing_engine import SubscriptionPricingEngine
from .section_10_subscription_billing.calendar_validity_engine import CalendarValidityEngine
from .section_10_subscription_billing.entitlement_quota_engine import EntitlementQuotaEngine
from .section_10_subscription_billing.subscriber_intelligence_engine import SubscriberIntelligenceEngine
from .section_10_subscription_billing.invoice_generator_engine import InvoiceGeneratorEngine

from .section_11_12_marketplace.case_workflow import CaseWorkflowEngine
from .section_11_12_marketplace.controlled_comm import ControlledCommEngine
from .section_11_12_marketplace.question_bank_engine import QuestionBankEngine
from .section_11_12_marketplace.recommendation_engine import RecommendationEngine

__all__ = [
    # Subpackages
    "section_00_core",
    "section_03_qp_intelligence",
    "section_04_consolidated_reports",
    "section_05_performance_intelligence",
    "section_06_parent_pulse",
    "section_07_09_academic_handoff",
    "section_08_board_readiness",
    "section_10_subscription_billing",
    "section_11_12_marketplace",
    # Core Engines
    "BaseEngine",
    "EngineHealthStatus",
    "QuickMarksEngine",
    "QuickMarksBatchInput",
    "SubjectMarkInput",
    "QuickMarksResult",
    "SubjectTelemetry",
    "ResultParserEngine",
    "ResultParserOutput",
    "ExtractedSubjectMark",
    "calculate_stream_readiness",
    "classify_readiness",
    "normalize_subject",
    "build_stream_subject_map",
    "calculate_projected_cutoff",
    "calculate_projected_score",
    "get_mastery_level",
    "calculate_career_readiness",
    "get_recommendations",
    "find_best_path",
    "generate_report",
    "determine_best_path",
    "calculate_achievement",
    "calculate_parent_satisfaction",
    "PerformanceConsistencyEngine",
    "ConsistencyEngine",
    "GapRecheckEngine",
    "AcademicHandoffEngine",
    "BoardReadinessEngine",
    "AchievementEngine",
    "ParentPulseEngine",
    "ReportGenerator",
    "CaseWorkflowEngine",
    "ControlledCommEngine",
    "QuestionBankEngine",
    "RecommendationEngine",
    "SubscriptionPricingEngine",
    "CalendarValidityEngine",
    "EntitlementQuotaEngine",
    "SubscriberIntelligenceEngine",
    "InvoiceGeneratorEngine",
]
