"""
Unit tests for IdentityTagger.
"""

from proxy.identity import IdentityTagger
from proxy.models import ToolCallRequest


def test_sanitize_params_redacts_secrets(identity_tagger: IdentityTagger):
    params = {
        "Bucket": "my-bucket",
        "aws_secret_access_key": "supersecret123",
        "api_key": "key-456",
        "nested": {"password": "pass"},
    }
    sanitized = identity_tagger.sanitize_params(params)
    assert sanitized["Bucket"] == "my-bucket"
    assert sanitized["aws_secret_access_key"] == "[REDACTED]"
    assert sanitized["api_key"] == "[REDACTED]"
    assert sanitized["nested"]["password"] == "[REDACTED]"


def test_validate_identity(identity_tagger: IdentityTagger):
    req = ToolCallRequest(
        agent_id="agent-1",
        session_id="session-1",
        declared_task="task",
        tool_name="tool",
        tool_action="action",
    )
    valid, err = identity_tagger.validate_identity(req)
    assert valid is True
    assert err == ""
