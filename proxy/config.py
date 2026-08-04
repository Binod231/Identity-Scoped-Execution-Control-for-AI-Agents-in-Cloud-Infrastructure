"""
ScopeGuard Configuration Management.

Loads settings from environment variables / .env file.
Supports three proxy modes for the ablation study:
  - full: identity tagging + active scoping (allow/block/warn)
  - tagging_only: identity tagging + logging, never blocks
  - passthrough: no interception (baseline)
"""

from enum import Enum
from pathlib import Path

from pydantic_settings import BaseSettings


class ProxyMode(str, Enum):
    """Operating mode for the ScopeGuard proxy (maps to ablation configurations)."""
    FULL = "full"                  # Identity tagging + active scoping + enforcement
    TAGGING_ONLY = "tagging_only"  # Identity tagging + logging, never blocks
    PASSTHROUGH = "passthrough"    # No interception — raw baseline


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # ── Proxy Configuration ─────────────────────────────
    proxy_mode: ProxyMode = ProxyMode.FULL
    fail_closed: bool = True  # NFR2: block on internal errors, never fail open
    log_level: str = "INFO"

    # ── Database ────────────────────────────────────────
    db_path: str = "data/scopeguard_audit.db"

    # ── LocalStack / AWS ────────────────────────────────
    localstack_endpoint: str = "http://localhost:4566"
    aws_region: str = "us-east-1"
    use_localstack: bool = True  # Toggle between LocalStack and real AWS

    # ── Server ──────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000

    model_config = {
        "env_prefix": "SCOPEGUARD_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
    }

    @property
    def db_full_path(self) -> Path:
        """Resolve and ensure the database directory exists."""
        path = Path(self.db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


# Singleton settings instance
settings = Settings()
