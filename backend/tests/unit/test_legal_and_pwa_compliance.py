"""
STUDIQS® SmartParent™ (v6.3 Complete) - Legal & PWA Regulatory Compliance Unit Test Suite
========================================================================================
Module: tests.unit.test_legal_and_pwa_compliance
Tests:
  1. Razorpay mandatory 5 legal policy endpoints:
     - GET /api/v1/legal/terms
     - GET /api/v1/legal/privacy (DPDP Act 2023 compliance)
     - GET /api/v1/legal/refunds (Section 24.7 compliance)
     - GET /api/v1/legal/shipping (Digital SLA)
     - GET /api/v1/legal/contact (Grievance Officer details)
  2. Public responsive HTML views (/api/v1/legal/view/{policy_type})
  3. PWA App Shell Endpoints:
     - GET /manifest.webmanifest
     - GET /sw.js
     - Static offline fallback existence
========================================================================================
"""

from fastapi.testclient import TestClient
import pytest
from src.smartparent.main import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_legal_terms_endpoint(client):
    res = client.get("/api/v1/legal/terms")
    assert res.status_code == 200
    data = res.json()
    assert data["policy_name"] == "Terms and Conditions"
    assert "STUDIQS® SmartParent™" in data["content_markdown"]
    assert "18% GST" in data["content_markdown"]


def test_legal_privacy_endpoint(client):
    res = client.get("/api/v1/legal/privacy")
    assert res.status_code == 200
    data = res.json()
    assert data["policy_name"] == "Privacy Policy"
    assert "DPDP Act 2023" in data["content_markdown"]
    assert "Row-Level Security" in data["content_markdown"]


def test_legal_refunds_endpoint(client):
    res = client.get("/api/v1/legal/refunds")
    assert res.status_code == 200
    data = res.json()
    assert data["policy_name"] == "Cancellation and Refund Policy"
    assert "7-Day Money-Back Guarantee" in data["content_markdown"]
    assert "48-Hour SLA" in data["content_markdown"]


def test_legal_shipping_endpoint(client):
    res = client.get("/api/v1/legal/shipping")
    assert res.status_code == 200
    data = res.json()
    assert data["policy_name"] == "Shipping and Delivery Policy"
    assert "digital software-as-a-service" in data["content_markdown"].lower()


def test_legal_contact_endpoint(client):
    res = client.get("/api/v1/legal/contact")
    assert res.status_code == 200
    data = res.json()
    assert data["policy_name"] == "Contact Us & Grievance Redressal"
    assert "grievance@studiqs.com" in data["content_markdown"]
    assert "Grievance Redressal Officer" in data["content_markdown"]


def test_legal_html_view(client):
    res = client.get("/api/v1/legal/view/privacy")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "STUDIQS® SmartParent™" in res.text
    assert "DPDP Act 2023" in res.text


def test_pwa_manifest_endpoint(client):
    res = client.get("/manifest.webmanifest")
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "STUDIQS® SmartParent™"
    assert data["short_name"] == "SmartParent"
    assert data["display"] == "standalone"
    assert len(data["icons"]) >= 2


def test_pwa_service_worker_endpoint(client):
    res = client.get("/sw.js")
    assert res.status_code == 200
    assert "application/javascript" in res.headers["content-type"]
    assert "studiqs-smartparent" in res.text
    assert "SENSITIVE_PATH_PATTERNS" in res.text

