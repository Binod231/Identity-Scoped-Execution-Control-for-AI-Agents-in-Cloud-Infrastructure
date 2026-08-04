"""
Integration tests for FastAPI Proxy API endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from proxy.main import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_health_check(client: TestClient):
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"


def test_execute_tool_allowed(client: TestClient):
    payload = {
        "agent_id": "integration-agent",
        "session_id": "session-001",
        "declared_task": "Create S3 bucket for assets storage",
        "tool_name": "aws_s3_operation",
        "tool_action": "s3:CreateBucket",
        "tool_params": {"Bucket": "integration-bucket"},
    }
    res = client.post("/execute-tool", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["decision"] == "ALLOWED"
    assert data["audit_id"] is not None


def test_execute_tool_blocked(client: TestClient):
    payload = {
        "agent_id": "integration-agent",
        "session_id": "session-002",
        "declared_task": "Read logs from cloudwatch",
        "tool_name": "aws_iam_operation",
        "tool_action": "iam:DeletePolicy",
        "tool_params": {"PolicyArn": "arn:aws:iam::123:policy/Admin"},
    }
    res = client.post("/execute-tool", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["decision"] == "BLOCKED"
    assert "BLOCKED" in data["error"]


def test_query_audit_endpoint(client: TestClient):
    res = client.get("/audit")
    assert res.status_code == 200
    data = res.json()
    assert "total" in data
    assert "entries" in data
