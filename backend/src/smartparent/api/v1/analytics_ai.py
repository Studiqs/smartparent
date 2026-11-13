"""
STUDIQS® SmartParent™ (v6.2 Complete) - Section 17 Analytics, AI & Topic-Repository Router
=============================================================================
Module: src.smartparent.api.v1.analytics_ai
Section 17: Analytics, AI and Topic-Repository Rules

Endpoints:
1. POST /api/v1/analytics/deterministic-calculate    -> Pure server-side math calculations
2. POST /api/v1/analytics/grounded-explain           -> Grounded AI pedagogical explanations
3. POST /api/v1/analytics/map-expert-provenance      -> Map expert evaluation to Student 360
4. POST /api/v1/analytics/validate-topic-node        -> Curriculum topic node taxonomy validation
5. POST /api/v1/analytics/gate2-check                -> Gate 2 Zero-Fake-Mastery eligibility check
6. GET  /api/v1/analytics/provenance/{child_id}      -> Audit trail of expert evaluations
=============================================================================
"""

import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.smartparent.schemas.analytics_ai_rules import (
    DeterministicCalculationRequest,
    DeterministicCalculationResponse,
    GroundedAiExplanationRequest,
    GroundedAiExplanationResponse,
    MapExpertEvaluationToIntelligenceRequest,
    MapExpertEvaluationToIntelligenceResponse,
    TopicNodeValidationRequest,
    TopicNodeValidationResponse,
    Gate2TopicIntelligenceCheckRequest,
    Gate2TopicIntelligenceCheckResponse,
)
from src.smartparent.services.analytics_ai_service import AnalyticsAiService
from src.smartparent.api.deps import get_db, get_current_subscriber_id

router = APIRouter(prefix="/analytics", tags=["Section 17: Analytics, AI & Topic-Repository Rules"])


@router.post(
    "/deterministic-calculate",
    response_model=DeterministicCalculationResponse,
    summary="Deterministic Server-Owned Math Calculation",
    description="Computes score percentages, trajectory deltas, rolling averages, and mastery tiers with 100% server determinism.",
)
def calculate_deterministic_metrics(request: DeterministicCalculationRequest):
    service = AnalyticsAiService()
    try:
        return service.calculate_deterministic_metrics(request)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/grounded-explain",
    response_model=GroundedAiExplanationResponse,
    summary="Grounded AI Pedagogical Explanation",
    description="Generates AI explanations grounded in verified deltas. Enforces 'No new evidence means no fabricated change'.",
)
def generate_grounded_explanation(request: GroundedAiExplanationRequest):
    service = AnalyticsAiService()
    try:
        return service.generate_grounded_explanation(request)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/map-expert-provenance",
    response_model=MapExpertEvaluationToIntelligenceResponse,
    summary="Map Expert Evaluation into Student 360 with Source Provenance",
    description="Ingests human expert line-item grading into Student 360 Topic Intelligence, preserving immutable source provenance.",
)
def map_expert_evaluation_to_intelligence(
    request: MapExpertEvaluationToIntelligenceRequest,
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    service = AnalyticsAiService()
    try:
        return service.map_expert_evaluation_to_intelligence(
            db=db,
            subscriber_id=subscriber_id,
            request=request,
        )
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/validate-topic-node",
    response_model=TopicNodeValidationResponse,
    summary="Validate Topic-Repository Node Taxonomy",
    description="Validates curriculum node hierarchy: Board -> Class -> Stream -> Subject -> Chapter -> Topic.",
)
def validate_topic_node(request: TopicNodeValidationRequest):
    service = AnalyticsAiService()
    return service.validate_topic_node(request)


@router.post(
    "/gate2-check",
    response_model=Gate2TopicIntelligenceCheckResponse,
    summary="Gate 2 Zero-Fake-Mastery Check",
    description="Verifies if evidence type is eligible to unlock topic-level mastery. Aggregate marks cards only update subject-level movement.",
)
def check_gate2_topic_intelligence(request: Gate2TopicIntelligenceCheckRequest):
    service = AnalyticsAiService()
    return service.check_gate2_topic_intelligence(request)


@router.get(
    "/provenance/{child_id}",
    summary="Get Child Expert Evaluation Provenance Trail",
    description="Retrieves all human expert evaluation records and immutable audit provenance for a child.",
)
def get_child_provenance_records(
    child_id: uuid.UUID,
    db: Session = Depends(get_db),
    subscriber_id: uuid.UUID = Depends(get_current_subscriber_id),
):
    service = AnalyticsAiService()
    try:
        return service.get_child_provenance_records(db=db, subscriber_id=subscriber_id, child_id=child_id)
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

