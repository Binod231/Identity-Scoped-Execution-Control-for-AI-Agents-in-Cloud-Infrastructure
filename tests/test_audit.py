"""
Unit tests for AuditLogger.
"""

from proxy.audit import AuditLogger
from proxy.models import AuditEntry, ScopingDecision


def test_audit_log_and_query(audit_logger: AuditLogger):
    entry = AuditEntry(
        id="test-uuid-1234",
        agent_id="test-agent",
        session_id="test-session",
        declared_task="Create bucket",
        tool_name="aws_s3_operation",
        tool_action="s3:CreateBucket",
        scoping_decision=ScopingDecision.ALLOWED,
        proxy_mode="full",
    )
    audit_logger.log(entry)

    res = audit_logger.query(agent_id="test-agent")
    assert res.total == 1
    assert res.entries[0].id == "test-uuid-1234"
    assert res.entries[0].scoping_decision == ScopingDecision.ALLOWED


def test_audit_metrics(audit_logger: AuditLogger):
    entry = AuditEntry(
        id="test-uuid-5678",
        agent_id="test-agent",
        session_id="test-session",
        declared_task="Delete bucket",
        tool_name="aws_s3_operation",
        tool_action="s3:DeleteBucket",
        scoping_decision=ScopingDecision.BLOCKED,
        proxy_mode="full",
    )
    audit_logger.log(entry)

    metrics = audit_logger.get_metrics()
    assert metrics["total_calls"] == 1
    assert metrics["blocked_calls"] == 1
    assert metrics["block_rate"] == 1.0
