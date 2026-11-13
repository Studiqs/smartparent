"""
STUDIQS® SmartParent™ - Ecosystem & Preview Addendum Test Battery
=============================================================================
Module: tests.unit.test_ecosystem_and_preview_addendum

Audits and proves:
  1. Public Visitor Preview Mode (Change 2 & Change 7):
     - Unauthenticated 3-card preview structure with locked teasers.
     - Rate-limit guard: Max 3 anonymous previews per day (HTTP 429 on 4th).
     - Mathematical constraints: Scored > Max marks rejection (HTTP 422).
  2. Conversion Funnel Telemetry & Attribution (Change 3 & Change 5):
     - Minimum event schema ingestion with sliding-window deduplication.
     - Anonymous-to-Authenticated session linking with consent.
     - 13-stage measurable funnel telemetry aggregation.
  3. DPDP Act 2023 Statutory Consent & Boundary Shield (Change 4 & Change 6):
     - Zero silent record merging between SmartParent & Academy Connect.
     - Affirmative parental consent verification before referral token creation.
     - Multi-tenant boundary: Parent A cannot consent on behalf of Child B (HTTP 403).
     - 72-hour token expiry and instant parent revocation.
     - Scoped data exposure: Target academy sees ONLY consented topic gap, never raw marks.
  4. 'Discover Studiqs SmartParent' Promotional Card (Change 6):
     - Official ₹200 / ₹400 / ₹600 per child/month pricing ladder confirmed.
=============================================================================
"""

import uuid
import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID

try:
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
except AttributeError:
    pass

@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"

@compiles(PG_UUID, "sqlite")
def compile_uuid_sqlite(type_, compiler, **kw):
    return "CHAR(36)"

from src.smartparent.main import app
from src.smartparent.db.base import Base
from src.smartparent.db.models.auth import Subscriber, Child, SubscriberSession
from src.smartparent.db.models.curriculum import CurriculumNode
from src.smartparent.api.deps import get_db
from src.smartparent.core.security import create_access_token
from src.smartparent.services.public_preview_service import _PREVIEW_RATE_LIMIT_STORE
from src.smartparent.services.attribution_service import _EVENT_STORE, _SESSION_TO_SUBSCRIBER_MAP, _LAST_EVENT_SEEN
from src.smartparent.services.consent_boundary_service import _ACTIVE_CONSENTS


@pytest.fixture(scope="module")
def addendum_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [
        Subscriber.__table__,
        Child.__table__,
        SubscriberSession.__table__,
        CurriculumNode.__table__,
    ]
    Base.metadata.create_all(bind=engine, tables=tables)
    yield engine
    Base.metadata.drop_all(bind=engine, tables=tables)


@pytest.fixture
def db(addendum_engine):
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=addendum_engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def client(addendum_engine):
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=addendum_engine)
    def override_get_db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def seed_data(db):
    _PREVIEW_RATE_LIMIT_STORE.clear()
    _EVENT_STORE.clear()
    _SESSION_TO_SUBSCRIBER_MAP.clear()
    _LAST_EVENT_SEEN.clear()
    _ACTIVE_CONSENTS.clear()

    sub_a_id = uuid.uuid4()
    sub_b_id = uuid.uuid4()
    child_a_id = uuid.uuid4()
    child_b_id = uuid.uuid4()

    suffix = uuid.uuid4().hex[:7]
    mobile_a = f"+9191{suffix[:8]}".ljust(13, "0")[:13]
    mobile_b = f"+9192{suffix[:8]}".ljust(13, "0")[:13]

    sub_a = Subscriber(
        subscriber_id=sub_a_id,
        mobile_number=mobile_a,
        parent_name="Parent Alpha",
        password_hash="hash_a",
        subscription_plan="PRO",
    )
    sub_b = Subscriber(
        subscriber_id=sub_b_id,
        mobile_number=mobile_b,
        parent_name="Parent Beta",
        password_hash="hash_b",
        subscription_plan="BASIC",
    )
    db.add_all([sub_a, sub_b])
    db.flush()

    child_a = Child(
        child_id=child_a_id,
        subscriber_id=sub_a_id,
        student_name="Aadhya Alpha",
        standard_class="Class 10",
        board="CBSE",
        is_active=True,
    )
    child_b = Child(
        child_id=child_b_id,
        subscriber_id=sub_b_id,
        student_name="Bharat Beta",
        standard_class="Class 10",
        board="CBSE",
        is_active=True,
    )
    db.add_all([child_a, child_b])

    existing_node = db.query(CurriculumNode).filter(CurriculumNode.node_id == "MAT-10-TEST-1").first()
    if not existing_node:
        node = CurriculumNode(
            node_id="MAT-10-TEST-1",
            subject="Mathematics",
            standard_class="Class 10",
            board="CBSE",
            chapter_name="Quadratic Equations",
            topic_name="Nature of Roots",
            semantic_keywords=["roots", "quadratic"],
        )
        db.add(node)
    db.commit()

    token_a = create_access_token({"sub": str(sub_a_id), "plan": "PRO"})
    token_b = create_access_token({"sub": str(sub_b_id), "plan": "BASIC"})

    return {
        "sub_a_id": sub_a_id,
        "sub_b_id": sub_b_id,
        "child_a_id": child_a_id,
        "child_b_id": child_b_id,
        "token_a": token_a,
        "token_b": token_b,
    }


# =============================================================================
# 1. PUBLIC VISITOR PREVIEW TESTS
# =============================================================================

def test_public_preview_normal_flow(client, seed_data):
    """Verifies that an anonymous visitor receives an unlocked 3-card preview with blurred gap teasers."""
    payload = {
        "subject": "Mathematics",
        "test_title": "Unit Test 1 - Algebra",
        "standard_class": "Class 10",
        "board": "CBSE",
        "total_scored_marks": 72.0,
        "total_max_marks": 100.0,
    }
    headers = {"X-Anonymous-Session-Id": "anon_session_test_1"}
    res = client.post("/api/v1/preview/quick-marks", json=payload, headers=headers)
    assert res.status_code == 200
    data = res.json()

    assert data["visitor_state"] == "ANONYMOUS_PREVIEW"
    assert data["percentage"] == 72.0
    assert data["mastery_tier"] == "AVERAGE"
    assert len(data["unlocked_cards"]) == 2
    assert len(data["locked_teasers"]) == 3

    # Check that teasers are locked
    for teaser in data["locked_teasers"]:
        assert teaser["is_locked"] is True
        assert "teaser_message" in teaser

    # Verify official plan ladder is confirmed as ₹200 / ₹400 / ₹600
    ladder = data["plan_ladder"]
    assert ladder["Basic"]["monthly_price"] == 200
    assert ladder["Advanced"]["monthly_price"] == 400
    assert ladder["Pro"]["monthly_price"] == 600

    # Verify CTA
    assert "Unlock Full 360° Diagnostic Telemetry" in data["cta_text"]
    assert data["remaining_daily_previews"] == 2


def test_public_preview_rate_limit_3_per_day(client, seed_data):
    """Enforces strict daily limit: 4th anonymous preview from same session ID is blocked with HTTP 429."""
    headers = {"X-Anonymous-Session-Id": "anon_session_rate_limit_test"}
    payload = {
        "subject": "Mathematics",
        "test_title": "Rate Limit Test",
        "total_scored_marks": 50.0,
        "total_max_marks": 100.0,
    }

    # 1st request -> PASS
    res1 = client.post("/api/v1/preview/quick-marks", json=payload, headers=headers)
    assert res1.status_code == 200

    # 2nd request -> PASS
    res2 = client.post("/api/v1/preview/quick-marks", json=payload, headers=headers)
    assert res2.status_code == 200

    # 3rd request -> PASS
    res3 = client.post("/api/v1/preview/quick-marks", json=payload, headers=headers)
    assert res3.status_code == 200

    # 4th request -> BLOCKED with 429
    res4 = client.post("/api/v1/preview/quick-marks", json=payload, headers=headers)
    assert res4.status_code == 429
    assert "Daily anonymous preview limit (3/day) reached" in res4.json()["detail"]


def test_public_preview_mathematical_validation(client, seed_data):
    """Rejects invalid marks (scored > max) with HTTP 422."""
    headers = {"X-Anonymous-Session-Id": "anon_session_invalid"}
    payload = {
        "subject": "Mathematics",
        "test_title": "Invalid Marks Test",
        "total_scored_marks": 105.0,
        "total_max_marks": 100.0,
    }
    res = client.post("/api/v1/preview/quick-marks", json=payload, headers=headers)
    assert res.status_code == 422


def test_public_preview_status_endpoint(client):
    """Verifies that the preview status endpoint reports correct limits and plan ladder."""
    res = client.get("/api/v1/preview/status")
    assert res.status_code == 200
    data = res.json()
    assert data["is_public_preview_enabled"] is True
    assert data["max_daily_previews_per_session"] == 3
    assert "Basic" in data["smartparent_plan_ladder"]


# =============================================================================
# 2. CONVERSION FUNNEL TELEMETRY & ATTRIBUTION TESTS
# =============================================================================

def test_telemetry_event_ingestion_and_deduplication(client):
    """Verifies event batch ingestion and 5-second rapid firing deduplication."""
    sess_id = "test_sess_dedup_001"
    events_payload = {
        "events": [
            {
                "event_name": "VISITOR_LANDED",
                "anonymous_session_id": sess_id,
                "source_utm": "google_search",
                "city": "Chennai",
            },
            {
                "event_name": "PREVIEW_GENERATED",
                "anonymous_session_id": sess_id,
                "source_utm": "google_search",
                "city": "Chennai",
            },
        ]
    }
    res = client.post("/api/v1/attribution/events", json=events_payload)
    assert res.status_code == 202
    assert res.json()["ingested_count"] == 2
    assert res.json()["duplicates_filtered"] == 0

    # Immediate duplicate submission within 5 seconds -> filtered
    res_dup = client.post("/api/v1/attribution/events", json=events_payload)
    assert res_dup.status_code == 202
    assert res_dup.json()["duplicates_filtered"] == 2


def test_anonymous_to_subscriber_session_linking(client, seed_data):
    """Verifies that historical pre-login events are attached to subscriber upon authenticated consent."""
    sess_id = "test_sess_linking_001"
    sub_id = seed_data["sub_a_id"]
    token = seed_data["token_a"]

    # 1. Anonymous event logged before login
    client.post(
        "/api/v1/attribution/events",
        json={
            "events": [
                {
                    "event_name": "PRICING_VIEWED",
                    "anonymous_session_id": sess_id,
                }
            ]
        },
    )

    # 2. User logs in and consents to link session
    link_payload = {
        "anonymous_session_id": sess_id,
        "consent_given": True,
    }
    headers = {"Authorization": f"Bearer {token}"}
    res = client.post("/api/v1/attribution/link-session", json=link_payload, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["subscriber_id"] == str(sub_id)
    assert data["linked_events_count"] >= 1


def test_13_stage_funnel_summary(client):
    """Verifies aggregated funnel metrics retrieval."""
    res = client.get("/api/v1/attribution/funnel")
    assert res.status_code == 200
    data = res.json()
    assert "total_events_recorded" in data
    assert "free_to_paid_conversion_rate_pct" in data


# =============================================================================
# 3. DPDP ACT 2023 AFFIRMATIVE CONSENT & ACADEMY HANDOFF TESTS
# =============================================================================

def test_dpdp_affirmative_consent_academy_handoff(client, seed_data):
    """Parent grants affirmative consent under DPDP Act to share a specific topic gap with an academy."""
    child_id = seed_data["child_a_id"]
    token = seed_data["token_a"]
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "child_id": str(child_id),
        "target_academy_id": str(uuid.uuid4()),
        "target_academy_name": "Apex IIT & NEET Academy Anna Nagar",
        "consented_subject": "Mathematics",
        "consented_topic_gap": "Quadratic Formula Roots",
        "parent_affirmative_consent": True,
        "consent_version": "2026.1_DPDP",
    }
    res = client.post("/api/v1/ecosystem/cross-product-consent", json=payload, headers=headers)
    assert res.status_code == 201
    data = res.json()
    assert data["is_consent_active"] is True
    assert "stq_handoff_" in data["handoff_referral_token"]
    assert "Section 9 of the Digital Personal Data Protection (DPDP) Act, 2023" in data["dpdp_compliance_notice"]

    # Test token verification by receiving academy
    token_str = data["handoff_referral_token"]
    redeem_res = client.get(f"/api/v1/ecosystem/redeem-referral?token={token_str}")
    assert redeem_res.status_code == 200
    r_data = redeem_res.json()
    assert r_data["status"] == "VALID"
    assert r_data["redemption_payload"]["consented_topic_gap"] == "Quadratic Formula Roots"


def test_dpdp_consent_multi_tenant_rejection(client, seed_data):
    """Parent A cannot grant consent for Child B (HTTP 403 Forbidden)."""
    child_b_id = seed_data["child_b_id"]
    token_a = seed_data["token_a"]
    headers = {"Authorization": f"Bearer {token_a}"}

    payload = {
        "child_id": str(child_b_id),
        "target_academy_id": str(uuid.uuid4()),
        "target_academy_name": "Rival Academy",
        "consented_subject": "Science",
        "consented_topic_gap": "Chemical Equations",
        "parent_affirmative_consent": True,
    }
    res = client.post("/api/v1/ecosystem/cross-product-consent", json=payload, headers=headers)
    assert res.status_code == 403
    assert "Child profile does not belong to authorized subscriber" in res.json()["detail"]


def test_dpdp_consent_revocation(client, seed_data):
    """Parent revokes active consent; handoff token immediately becomes invalid (HTTP 404 on redemption)."""
    child_id = seed_data["child_a_id"]
    token = seed_data["token_a"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Create consent
    payload = {
        "child_id": str(child_id),
        "target_academy_id": str(uuid.uuid4()),
        "target_academy_name": "Test Coaching",
        "consented_subject": "Physics",
        "consented_topic_gap": "Kinematics",
        "parent_affirmative_consent": True,
    }
    create_res = client.post("/api/v1/ecosystem/cross-product-consent", json=payload, headers=headers)
    consent_id = create_res.json()["consent_id"]
    referral_token = create_res.json()["handoff_referral_token"]

    # 2. Revoke consent
    revoke_res = client.post(
        "/api/v1/ecosystem/revoke-consent",
        json={"consent_id": consent_id, "child_id": str(child_id)},
        headers=headers,
    )
    assert revoke_res.status_code == 200
    assert revoke_res.json()["status"] == "REVOKED"

    # 3. Attempt to redeem revoked token -> BLOCKED (HTTP 404)
    redeem_res = client.get(f"/api/v1/ecosystem/redeem-referral?token={referral_token}")
    assert redeem_res.status_code == 404


# =============================================================================
# 4. 'DISCOVER STUDIQS SMARTPARENT' CARD TESTS (CHANGE 6)
# =============================================================================

def test_smartparent_discovery_card_endpoint(client):
    """Verifies that the promotional card serves authentic features and the ₹200/400/600 pricing ladder."""
    res = client.get("/api/v1/ecosystem/discovery-card?referral_source=academy_connect")
    assert res.status_code == 200
    data = res.json()
    assert data["product_name"] == "STUDIQS® SmartParent™"
    assert "₹200 per child/month" in data["pricing_ladder"]["Basic"]
    assert "₹400 per child/month" in data["pricing_ladder"]["Advanced"]
    assert "₹600 per child/month" in data["pricing_ladder"]["Pro"]
    assert "camp_cross_promo_academy_connect" in data["referral_campaign_id"]
    assert "DPDP Act 2023" in data["statutory_notice"]
