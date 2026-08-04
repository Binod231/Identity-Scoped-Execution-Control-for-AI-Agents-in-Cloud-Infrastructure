"""
Unit tests for PolicyEngine.
"""

from proxy.config import ProxyMode
from proxy.models import RiskLevel, ScopingDecision, ScopeResult, ToolCallRequest
from proxy.policy import PolicyEngine


def _make_req(action: str, task: str = "Deploy EC2 instance") -> ToolCallRequest:
    return ToolCallRequest(
        agent_id="test-agent",
        session_id="session-123",
        declared_task=task,
        tool_name="aws_ec2_operation",
        tool_action=action,
    )


def test_policy_full_allowed():
    policy = PolicyEngine(mode=ProxyMode.FULL)
    req = _make_req("ec2:RunInstances")
    scope = ScopeResult(
        allowed_actions={"ec2:RunInstances"},
        risk_level=RiskLevel.MEDIUM,
        confidence=0.8,
    )
    decision = policy.evaluate(req, scope)
    assert decision == ScopingDecision.ALLOWED


def test_policy_full_blocked():
    policy = PolicyEngine(mode=ProxyMode.FULL)
    req = _make_req("iam:DeletePolicy")
    scope = ScopeResult(
        allowed_actions={"ec2:RunInstances"},
        risk_level=RiskLevel.MEDIUM,
        confidence=0.8,
    )
    decision = policy.evaluate(req, scope)
    assert decision == ScopingDecision.BLOCKED


def test_policy_tagging_only():
    policy = PolicyEngine(mode=ProxyMode.TAGGING_ONLY)
    req = _make_req("iam:DeletePolicy")
    scope = ScopeResult(allowed_actions=set(), risk_level=RiskLevel.LOW, confidence=0.0)
    decision = policy.evaluate(req, scope)
    assert decision == ScopingDecision.ALLOWED


def test_policy_passthrough():
    policy = PolicyEngine(mode=ProxyMode.PASSTHROUGH)
    req = _make_req("iam:DeletePolicy")
    scope = ScopeResult(allowed_actions=set(), risk_level=RiskLevel.LOW, confidence=0.0)
    decision = policy.evaluate(req, scope)
    assert decision == ScopingDecision.ALLOWED
