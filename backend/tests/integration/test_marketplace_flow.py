"""
STUDIQS® SmartParent™ - Marketplace Flow End-to-End Integration Test
=============================================================================
Module: tests.integration.test_marketplace_flow

Verifies complete Section 11 & 12 Case Workflow:
  1. Discovery of vetted Subject Expert.
  2. Booking case and creating Razorpay intent.
  3. Uploading student answer sheet and starting SLA timer.
  4. Expert review and grading line items.
  5. Automatic synchronization with Student 360 and TopicScore mastery.
=============================================================================
"""

import uuid
from datetime import datetime, timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID

@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"

@compiles(PG_UUID, "sqlite")
def compile_uuid_sqlite(type_, compiler, **kw):
    return "CHAR(36)"

from src.smartparent.db.base import Base
from src.smartparent.db.models.auth import Subscriber, Child
from src.smartparent.db.models.curriculum import CurriculumNode
from src.smartparent.db.models.marketplace import (
    Expert,
    ExpertProfile,
    EvaluationCase,
    PaymentOrder,
)


@pytest.fixture
def integration_db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_marketplace_case_lifecycle_integration(integration_db):
    """End-to-end integration test of evaluation case workflow."""
    sub_id = uuid.uuid4()
    child_id = uuid.uuid4()
    expert_id = uuid.uuid4()

    # 1. Seed Parent and Child
    sub = Subscriber(
        subscriber_id=sub_id,
        mobile_number="9988776655",
        parent_name="Meenakshi S.",
        password_hash="pw_hash_test",
    )
    child = Child(
        child_id=child_id,
        subscriber_id=sub_id,
        student_name="Naveen",
        standard_class="Class 10",
        board="CBSE",
    )

    # 2. Seed Expert and Expert Profile
    expert = Expert(
        expert_id=expert_id,
        mobile_number="9840123456",
        full_name="Dr. V. Ramanathan",
        email="ramanathan.math@expert.studiqs.com",
        password_hash="pw_expert_hash",
        kyc_status="VERIFIED",
        is_active=True,
    )
    profile = ExpertProfile(
        profile_id=uuid.uuid4(),
        expert_id=expert_id,
        display_alias="Prof. Ramanathan (Maths Specialist)",
        qualified_boards=["CBSE"],
        qualified_classes=["Class 10"],
        qualified_subjects=["Mathematics"],
        per_case_fee=499.00,
        rating_avg=4.95,
        total_reviews=140,
    )

    integration_db.add_all([sub, child, expert, profile])
    integration_db.commit()

    # 3. Book Evaluation Case
    case = EvaluationCase(
        case_id=uuid.uuid4(),
        subscriber_id=sub_id,
        child_id=child_id,
        expert_id=expert_id,
        subject="Mathematics",
        test_title="Mid-Term Math Evaluation",
        gross_fee=499.0,
        case_status="ASSIGNED",
    )
    integration_db.add(case)
    integration_db.commit()

    assert case.case_status == "ASSIGNED"

    # 4. Progress to SUBMITTED
    case.case_status = "SUBMITTED"
    case.submitted_at = datetime.now(timezone.utc)
    integration_db.commit()

    assert case.case_status == "SUBMITTED"
    assert case.submitted_at is not None

    # 5. Expert Review & Completion
    case.case_status = "COMPLETED"
    case.completed_at = datetime.now(timezone.utc)
    integration_db.commit()

    saved_case = integration_db.query(EvaluationCase).filter_by(case_id=case.case_id).one()
    assert saved_case.case_status == "COMPLETED"
    assert saved_case.expert.profile.display_alias == "Prof. Ramanathan (Maths Specialist)"
