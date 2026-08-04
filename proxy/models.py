"""
ScopeGuard Pydantic Models.

Defines the data structures for tool call interception, scoping decisions,
audit entries, and API responses. These models form the contract between
all proxy components.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Enums ───────────────────────────────────────────────────────


class ScopingDecision(str, Enum):
    """Outcome of the policy engine's evaluation."""
    ALLOWED = "ALLOWED"
    BLOCKED = "BLOCKED"
    WARNED = "WARNED"


class RiskLevel(str, Enum):
    """Risk classification for an infrastructure action."""
    LOW = "LOW"          # Read-only operations
    MEDIUM = "MEDIUM"    # Create / update operations
    HIGH = "HIGH"        # Delete, IAM mutation, security-critical
    CRITICAL = "CRITICAL"  # Cross-account, wildcard IAM, root-level


# ── Request Models ──────────────────────────────────────────────


class ToolCallRequest(BaseModel):
    """
    Incoming tool call from the AI agent to be intercepted by ScopeGuard.

    Represents a single infrastructure action the agent wants to execute.
    """
    agent_id: str = Field(..., description="Unique identifier for the AI agent instance")
    session_id: str = Field(..., description="Unique identifier for this agent session/conversation")
    declared_task: str = Field(..., description="The agent's stated task / objective in natural language")
    reasoning_excerpt: str = Field(
        default="",
        description="Short excerpt from the agent's reasoning chain (for audit attribution)"
    )
    tool_name: str = Field(..., description="Tool being invoked (e.g., 'aws_s3_operation')")
    tool_action: str = Field(
        ...,
        description="Specific action within the tool (e.g., 's3:CreateBucket', 'ec2:RunInstances')"
    )
    tool_params: dict[str, Any] = Field(
        default_factory=dict,
        description="Parameters for the tool call (secrets will be stripped before logging)"
    )


# ── Scoping Models ──────────────────────────────────────────────


class ScopeResult(BaseModel):
    """
    Output of the task-to-scope classifier.

    Describes what the agent's declared task should be allowed to do.
    """
    allowed_actions: set[str] = Field(
        default_factory=set,
        description="Set of AWS actions permitted for the declared task"
    )
    risk_level: RiskLevel = Field(
        default=RiskLevel.LOW,
        description="Overall risk level of the allowed action set"
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0, le=1.0,
        description="Classifier confidence (1.0 = all keywords matched precisely)"
    )
    matched_keywords: list[str] = Field(
        default_factory=list,
        description="Keywords from the declared task that triggered scope rules"
    )


# ── Audit Models ────────────────────────────────────────────────


class AuditEntry(BaseModel):
    """
    Complete audit log record for a single intercepted tool call.

    Contains identity metadata, scoping decision, execution result,
    and timing information. No credentials or secrets are stored.
    """
    id: str = Field(..., description="UUID4 tracking ID for this audit entry")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO-8601 UTC timestamp of the interception"
    )
    # Identity metadata
    agent_id: str
    session_id: str
    declared_task: str
    reasoning_excerpt: str = ""
    # Call details
    tool_name: str
    tool_action: str
    tool_params_sanitized: dict[str, Any] = Field(
        default_factory=dict,
        description="Tool parameters with secrets/credentials stripped"
    )
    # Scoping
    scoping_decision: ScopingDecision
    allowed_actions: list[str] = Field(default_factory=list)
    risk_level: str = ""
    classifier_confidence: float = 0.0
    matched_keywords: list[str] = Field(default_factory=list)
    # Execution
    latency_ms: float = 0.0
    execution_result: str | None = None
    error: str | None = None
    # Configuration
    proxy_mode: str = "full"


# ── Response Models ─────────────────────────────────────────────


class ToolCallResponse(BaseModel):
    """Response returned to the agent after ScopeGuard processes a tool call."""
    audit_id: str = Field(..., description="UUID4 tracking ID for this call")
    decision: ScopingDecision
    result: Any | None = Field(
        default=None,
        description="Execution result (only populated if decision is ALLOWED)"
    )
    error: str | None = Field(
        default=None,
        description="Error message (populated if decision is BLOCKED or execution failed)"
    )
    risk_level: str = ""
    latency_ms: float = 0.0


class AuditQueryResponse(BaseModel):
    """Response for audit trail queries."""
    total: int
    entries: list[AuditEntry]


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "healthy"
    version: str = "0.1.0"
    proxy_mode: str
    total_calls_processed: int = 0
    uptime_seconds: float = 0.0


class MetricsResponse(BaseModel):
    """Real-time proxy metrics."""
    total_calls: int = 0
    allowed_calls: int = 0
    blocked_calls: int = 0
    warned_calls: int = 0
    avg_latency_ms: float = 0.0
    block_rate: float = 0.0
    proxy_mode: str = "full"
