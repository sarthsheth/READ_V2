"""
Unit and integration tests for FastAPI application health check.
Can be run via pytest or directly as a script (python tests/test_health.py).
"""

import os
import sys

# Ensure project root is in sys.path when running directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_health_check_status_code():
    """Verify that /health returns HTTP 200 OK."""
    response = client.get("/health")
    assert response.status_code == 200


def test_health_check_payload():
    """Verify the payload structure of the health check response."""
    response = client.get("/health")
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "read-v2-api"
    assert data["version"] == "0.1.0"
    assert "region" in data
    assert "mock_gcp" in data


def test_root_endpoint():
    """Verify that the root endpoint returns API links."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert data["docs_url"] == "/docs"


if __name__ == "__main__":
    print("--- Running tests/test_health.py directly ---")
    test_health_check_status_code()
    print("[OK] test_health_check_status_code passed")
    test_health_check_payload()
    print("[OK] test_health_check_payload passed")
    test_root_endpoint()
    print("[OK] test_root_endpoint passed")
    print("\n[ALL TESTS PASSED]")

