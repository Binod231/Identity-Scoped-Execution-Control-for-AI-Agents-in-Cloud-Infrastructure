"""
ScopeGuard Audit Logger (FR5, FR6).

Persists structured audit records to SQLite with full identity metadata,
scoping decisions, and execution results. Provides query API for
incident response and experiment analysis.

No credentials or secrets are stored in the audit trail (NFR5).
"""

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

from proxy.config import settings
from proxy.models import AuditEntry, AuditQueryResponse

logger = logging.getLogger("scopeguard.audit")

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS audit_log (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    declared_task TEXT,
    reasoning_excerpt TEXT DEFAULT '',
    tool_name TEXT NOT NULL,
    tool_action TEXT NOT NULL,
    tool_params_sanitized TEXT DEFAULT '{}',
    scoping_decision TEXT NOT NULL,
    allowed_actions TEXT DEFAULT '[]',
    risk_level TEXT DEFAULT '',
    classifier_confidence REAL DEFAULT 0.0,
    matched_keywords TEXT DEFAULT '[]',
    latency_ms REAL DEFAULT 0.0,
    execution_result TEXT,
    error TEXT,
    proxy_mode TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_agent_id ON audit_log(agent_id);
CREATE INDEX IF NOT EXISTS idx_session_id ON audit_log(session_id);
CREATE INDEX IF NOT EXISTS idx_timestamp ON audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_scoping_decision ON audit_log(scoping_decision);
"""


class AuditLogger:
    """
    Persistent audit logger backed by SQLite.

    Stores every intercepted tool call with full identity metadata and
    scoping decisions. Provides query methods for analysis and API use.
    """

    def __init__(self, db_path: str | None = None):
        self._db_path = db_path or str(settings.db_full_path)
        self._ensure_db()

    def _ensure_db(self):
        """Create the database and tables if they don't exist."""
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            conn.executescript(_CREATE_TABLE_SQL)
            conn.commit()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a new database connection."""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def log(self, entry: AuditEntry) -> None:
        """
        Persist an audit entry to the database.

        Args:
            entry: Complete audit record for a single tool call
        """
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO audit_log (
                        id, timestamp, agent_id, session_id, declared_task,
                        reasoning_excerpt, tool_name, tool_action,
                        tool_params_sanitized, scoping_decision, allowed_actions,
                        risk_level, classifier_confidence, matched_keywords,
                        latency_ms, execution_result, error, proxy_mode
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry.id,
                        entry.timestamp,
                        entry.agent_id,
                        entry.session_id,
                        entry.declared_task,
                        entry.reasoning_excerpt,
                        entry.tool_name,
                        entry.tool_action,
                        json.dumps(entry.tool_params_sanitized),
                        entry.scoping_decision.value,
                        json.dumps(entry.allowed_actions),
                        entry.risk_level,
                        entry.classifier_confidence,
                        json.dumps(entry.matched_keywords),
                        entry.latency_ms,
                        entry.execution_result,
                        entry.error,
                        entry.proxy_mode,
                    ),
                )
                conn.commit()
        except Exception as e:
            logger.error("Failed to write audit entry %s: %s", entry.id, str(e))
            raise

    def query(
        self,
        agent_id: str | None = None,
        session_id: str | None = None,
        decision: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> AuditQueryResponse:
        """
        Query audit entries with optional filters.

        Args:
            agent_id: Filter by agent ID
            session_id: Filter by session ID
            decision: Filter by scoping decision (ALLOWED, BLOCKED, WARNED)
            limit: Max entries to return
            offset: Pagination offset

        Returns:
            AuditQueryResponse with total count and matching entries
        """
        conditions: list[str] = []
        params: list[Any] = []

        if agent_id:
            conditions.append("agent_id = ?")
            params.append(agent_id)
        if session_id:
            conditions.append("session_id = ?")
            params.append(session_id)
        if decision:
            conditions.append("scoping_decision = ?")
            params.append(decision)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        with self._get_connection() as conn:
            # Get total count
            count_row = conn.execute(
                f"SELECT COUNT(*) FROM audit_log WHERE {where_clause}", params
            ).fetchone()
            total = count_row[0] if count_row else 0

            # Get entries
            rows = conn.execute(
                f"""
                SELECT * FROM audit_log
                WHERE {where_clause}
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
                """,
                params + [limit, offset],
            ).fetchall()

        entries = [self._row_to_entry(row) for row in rows]
        return AuditQueryResponse(total=total, entries=entries)

    def get_by_id(self, audit_id: str) -> AuditEntry | None:
        """Retrieve a single audit entry by its tracking ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM audit_log WHERE id = ?", (audit_id,)
            ).fetchone()
        return self._row_to_entry(row) if row else None

    def get_metrics(self) -> dict[str, Any]:
        """Compute aggregate metrics across all audit entries."""
        with self._get_connection() as conn:
            total = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
            allowed = conn.execute(
                "SELECT COUNT(*) FROM audit_log WHERE scoping_decision = 'ALLOWED'"
            ).fetchone()[0]
            blocked = conn.execute(
                "SELECT COUNT(*) FROM audit_log WHERE scoping_decision = 'BLOCKED'"
            ).fetchone()[0]
            warned = conn.execute(
                "SELECT COUNT(*) FROM audit_log WHERE scoping_decision = 'WARNED'"
            ).fetchone()[0]
            avg_latency = conn.execute(
                "SELECT AVG(latency_ms) FROM audit_log"
            ).fetchone()[0]

        return {
            "total_calls": total,
            "allowed_calls": allowed,
            "blocked_calls": blocked,
            "warned_calls": warned,
            "avg_latency_ms": round(avg_latency, 2) if avg_latency else 0.0,
            "block_rate": round(blocked / total, 4) if total > 0 else 0.0,
        }

    def clear(self) -> None:
        """Clear all audit entries (for test cleanup only)."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM audit_log")
            conn.commit()

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> AuditEntry:
        """Convert a database row to an AuditEntry model."""
        return AuditEntry(
            id=row["id"],
            timestamp=row["timestamp"],
            agent_id=row["agent_id"],
            session_id=row["session_id"],
            declared_task=row["declared_task"] or "",
            reasoning_excerpt=row["reasoning_excerpt"] or "",
            tool_name=row["tool_name"],
            tool_action=row["tool_action"],
            tool_params_sanitized=json.loads(row["tool_params_sanitized"] or "{}"),
            scoping_decision=row["scoping_decision"],
            allowed_actions=json.loads(row["allowed_actions"] or "[]"),
            risk_level=row["risk_level"] or "",
            classifier_confidence=row["classifier_confidence"] or 0.0,
            matched_keywords=json.loads(row["matched_keywords"] or "[]"),
            latency_ms=row["latency_ms"] or 0.0,
            execution_result=row["execution_result"],
            error=row["error"],
            proxy_mode=row["proxy_mode"],
        )
