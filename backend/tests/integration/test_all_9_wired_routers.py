import uuid
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID

from src.smartparent.main import app
from src.smartparent.db.base import Base
from src.smartparent.db.models.auth import Subscriber, Child
from src.smartparent.api.deps import get_db, get_current_subscriber_id, get_current_expert_id

# Register SQLite dialect mappings for PostgreSQL JSONB and UUID
@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"

@compiles(PG_UUID, "sqlite")
def compile_uuid_sqlite(type_, compiler, **kw):
    return "CHAR(36)"

# Set up test in-memory SQLite DB with StaticPool so all connections share the same memory DB
engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    echo=False
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

TEST_SUBSCRIBER_ID = uuid.uuid4()
TEST_EXPERT_ID = uuid.uuid4()
TEST_CHILD_ID = uuid.uuid4()

# Seed basic subscriber and child
db = TestingSessionLocal()
sub = Subscriber(
    subscriber_id=TEST_SUBSCRIBER_ID,
    mobile_number="+919876543210",
    parent_name="Test Parent",
    email="test@example.com",
    password_hash="hash",
)
db.add(sub)
db.flush()

child = Child(
    child_id=TEST_CHILD_ID,
    subscriber_id=TEST_SUBSCRIBER_ID,
    student_name="Rohan Test",
    standard_class="Class 10",
    board="CBSE",
    is_active=True,
)
db.add(child)
db.commit()
db.close()


def override_get_db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


def override_subscriber_id():
    return TEST_SUBSCRIBER_ID


def override_expert_id():
    return TEST_EXPERT_ID


app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[get_current_subscriber_id] = override_subscriber_id
app.dependency_overrides[get_current_expert_id] = override_expert_id

client = TestClient(app)

HEADERS_SUBSCRIBER = {
    "X-Subscriber-Id": str(TEST_SUBSCRIBER_ID),
}

HEADERS_EXPERT = {
    "X-Expert-Id": str(TEST_EXPERT_ID),
}


def test_actions_router():
    res = client.get(f"/api/v1/actions/{TEST_CHILD_ID}", headers=HEADERS_SUBSCRIBER)
    assert res.status_code in [200, 404], f"Unexpected status: {res.status_code}, {res.text}"


def test_analytics_ai_router():
    res = client.get(f"/api/v1/analytics/trends/{TEST_CHILD_ID}?subject=Mathematics", headers=HEADERS_SUBSCRIBER)
    assert res.status_code in [200, 404], f"Unexpected status: {res.status_code}, {res.text}"


def test_handoff_router():
    res = client.get(f"/api/v1/handoff/brief/{TEST_CHILD_ID}", headers=HEADERS_SUBSCRIBER)
    assert res.status_code in [200, 404], f"Unexpected status: {res.status_code}, {res.text}"


def test_marketplace_router():
    res = client.get("/api/v1/marketplace/search", headers=HEADERS_SUBSCRIBER)
    assert res.status_code in [200, 404], f"Unexpected status: {res.status_code}, {res.text}"


def test_parent_pulse_router():
    res = client.get(f"/api/v1/pulse/student/{TEST_CHILD_ID}", headers=HEADERS_SUBSCRIBER)
    assert res.status_code in [200, 404], f"Unexpected status: {res.status_code}, {res.text}"


def test_performance_router():
    res = client.get(f"/api/v1/performance/{TEST_CHILD_ID}", headers=HEADERS_SUBSCRIBER)
    assert res.status_code in [200, 404], f"Unexpected status: {res.status_code}, {res.text}"


def test_readiness_router():
    res = client.get(f"/api/v1/readiness/student/{TEST_CHILD_ID}/board", headers=HEADERS_SUBSCRIBER)
    assert res.status_code in [200, 404], f"Unexpected status: {res.status_code}, {res.text}"


def test_reports_router():
    res = client.get(f"/api/v1/reports/student-360/{TEST_CHILD_ID}", headers=HEADERS_SUBSCRIBER)
    assert res.status_code in [200, 404], f"Unexpected status: {res.status_code}, {res.text}"


def test_security_isolation_router():
    payload = {
        "resource_path": "reports/sample.pdf",
        "scope": "REPORT_DOWNLOAD",
        "action": "read",
        "ttl_seconds": 3600
    }
    res = client.post("/api/v1/isolation/signed-url", json=payload, headers=HEADERS_SUBSCRIBER)
    assert res.status_code in [200, 400, 403, 404], f"Unexpected status: {res.status_code}, {res.text}"
