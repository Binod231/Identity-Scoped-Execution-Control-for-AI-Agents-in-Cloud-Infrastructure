"""
ScopeGuard FastAPI Application — Main Entry Point.

Implements the proxy server that intercepts AI agent tool calls,
scopes them against the declared task, and produces an audit trail.

Endpoints:
  POST /execute-tool  — Main interception endpoint (FR1-FR4)
  GET  /audit         — Query audit trail (FR6)
  GET  /audit/{id}    — Single audit entry
  GET  /health        — Health check
  GET  /metrics       — Real-time proxy statistics
"""

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from proxy.audit import AuditLogger
from proxy.classifier import TaskToScopeClassifier
from proxy.config import settings
from proxy.executor import BackendExecutor
from proxy.identity import IdentityTagger
from proxy.models import (
    AuditEntry,
    AuditQueryResponse,
    HealthResponse,
    MetricsResponse,
    ScopingDecision,
    ToolCallRequest,
    ToolCallResponse,
)
from proxy.policy import PolicyEngine

# ── Logging ─────────────────────────────────────────────

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(name)-25s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("scopeguard.main")

# ── Application State ───────────────────────────────────

_start_time: float = 0.0


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — initialize components on startup."""
    global _start_time
    _start_time = time.time()

    # Initialize components
    app.state.classifier = TaskToScopeClassifier()
    app.state.policy_engine = PolicyEngine()
    app.state.executor = BackendExecutor()
    app.state.audit_logger = AuditLogger()
    app.state.identity_tagger = IdentityTagger()

    logger.info(
        "ScopeGuard proxy started | mode=%s | fail_closed=%s | db=%s",
        settings.proxy_mode.value,
        settings.fail_closed,
        settings.db_path,
    )
    yield
    logger.info("ScopeGuard proxy shutting down")


# ── FastAPI App ─────────────────────────────────────────

app = FastAPI(
    title="ScopeGuard",
    description=(
        "Identity-Scoped Execution Control for AI Agents in Cloud Infrastructure. "
        "Intercepts agent tool calls, scopes them against declared tasks, "
        "and produces a queryable audit trail."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Main Interception Endpoint ──────────────────────────


@app.post("/execute-tool", response_model=ToolCallResponse)
async def execute_tool(request: ToolCallRequest) -> ToolCallResponse:
    """
    Main interception endpoint (FR1-FR4).

    Flow:
      1. Validate and extract identity metadata
      2. Compute scope from declared task (classifier)
      3. Evaluate policy (allow/block/warn)
      4. Execute if allowed (backend executor)
      5. Log everything to audit trail
      6. Return structured response
    """
    call_start = time.perf_counter()

    # ── Step 1: Identity extraction & validation ────────
    tagger: IdentityTagger = app.state.identity_tagger
    is_valid, error_msg = tagger.validate_identity(request)
    if not is_valid:
        raise HTTPException(status_code=422, detail=error_msg)

    identity = tagger.extract_identity(request)
    tracking_id = identity["tracking_id"]

    # ── Step 2: Compute scope from declared task ────────
    classifier: TaskToScopeClassifier = app.state.classifier
    scope = classifier.classify(request.declared_task)

    # ── Step 3: Evaluate policy ─────────────────────────
    policy: PolicyEngine = app.state.policy_engine
    decision = policy.evaluate(request, scope)

    # ── Step 4: Execute if allowed ──────────────────────
    execution_result = None
    execution_error = None

    if decision == ScopingDecision.ALLOWED:
        executor: BackendExecutor = app.state.executor
        exec_result = await executor.execute(
            request.tool_name, request.tool_action, request.tool_params
        )
        if exec_result["success"]:
            execution_result = exec_result["result"]
        else:
            execution_error = exec_result["error"]
    elif decision == ScopingDecision.WARNED:
        # WARNED: execute but flag for review
        executor = app.state.executor
        exec_result = await executor.execute(
            request.tool_name, request.tool_action, request.tool_params
        )
        if exec_result["success"]:
            execution_result = exec_result["result"]
        else:
            execution_error = exec_result["error"]
    else:
        execution_error = (
            f"BLOCKED: Action '{request.tool_action}' is not within the computed scope "
            f"for declared task. Allowed actions: {sorted(scope.allowed_actions)[:5]}"
        )

    # ── Step 5: Compute latency and log to audit trail ──
    latency_ms = (time.perf_counter() - call_start) * 1000

    audit_entry = AuditEntry(
        id=tracking_id,
        agent_id=identity["agent_id"],
        session_id=identity["session_id"],
        declared_task=identity["declared_task"],
        reasoning_excerpt=identity["reasoning_excerpt"],
        tool_name=identity["tool_name"],
        tool_action=identity["tool_action"],
        tool_params_sanitized=identity["tool_params_sanitized"],
        scoping_decision=decision,
        allowed_actions=sorted(scope.allowed_actions),
        risk_level=scope.risk_level.value,
        classifier_confidence=scope.confidence,
        matched_keywords=scope.matched_keywords,
        latency_ms=round(latency_ms, 2),
        execution_result=execution_result,
        error=execution_error,
        proxy_mode=settings.proxy_mode.value,
    )

    audit_logger: AuditLogger = app.state.audit_logger
    audit_logger.log(audit_entry)

    logger.info(
        "%s | agent=%s | session=%s | action=%s | latency=%.1fms",
        decision.value,
        request.agent_id,
        request.session_id[:8],
        request.tool_action,
        latency_ms,
    )

    # ── Step 6: Return response ─────────────────────────
    return ToolCallResponse(
        audit_id=tracking_id,
        decision=decision,
        result=execution_result if decision != ScopingDecision.BLOCKED else None,
        error=execution_error,
        risk_level=scope.risk_level.value,
        latency_ms=round(latency_ms, 2),
    )


# ── Audit Query Endpoints ──────────────────────────────


@app.get("/audit", response_model=AuditQueryResponse)
async def query_audit(
    agent_id: str | None = Query(None, description="Filter by agent ID"),
    session_id: str | None = Query(None, description="Filter by session ID"),
    decision: str | None = Query(None, description="Filter by decision: ALLOWED/BLOCKED/WARNED"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> AuditQueryResponse:
    """Query the audit trail with optional filters (FR6)."""
    audit_logger: AuditLogger = app.state.audit_logger
    return audit_logger.query(
        agent_id=agent_id,
        session_id=session_id,
        decision=decision,
        limit=limit,
        offset=offset,
    )


@app.get("/audit/{audit_id}", response_model=AuditEntry)
async def get_audit_entry(audit_id: str) -> AuditEntry:
    """Retrieve a single audit entry by its tracking ID."""
    audit_logger: AuditLogger = app.state.audit_logger
    entry = audit_logger.get_by_id(audit_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Audit entry {audit_id} not found")
    return entry


# ── Health & Metrics ────────────────────────────────────


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    audit_logger: AuditLogger = app.state.audit_logger
    metrics = audit_logger.get_metrics()
    return HealthResponse(
        status="healthy",
        version="0.1.0",
        proxy_mode=settings.proxy_mode.value,
        total_calls_processed=metrics["total_calls"],
        uptime_seconds=round(time.time() - _start_time, 1),
    )


@app.get("/metrics", response_model=MetricsResponse)
async def get_metrics() -> MetricsResponse:
    """Real-time proxy metrics."""
    audit_logger: AuditLogger = app.state.audit_logger
    metrics = audit_logger.get_metrics()
    return MetricsResponse(
        total_calls=metrics["total_calls"],
        allowed_calls=metrics["allowed_calls"],
        blocked_calls=metrics["blocked_calls"],
        warned_calls=metrics["warned_calls"],
        avg_latency_ms=metrics["avg_latency_ms"],
        block_rate=metrics["block_rate"],
        proxy_mode=settings.proxy_mode.value,
    )
