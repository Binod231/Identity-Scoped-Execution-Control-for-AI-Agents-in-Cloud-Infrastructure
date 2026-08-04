"""
Pytest Fixtures for ScopeGuard Test Suite.
"""

import os
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from proxy.audit import AuditLogger
from proxy.classifier import TaskToScopeClassifier
from proxy.config import ProxyMode, settings
from proxy.identity import IdentityTagger
from proxy.main import app
from proxy.policy import PolicyEngine


@pytest.fixture(autouse=True)
def setup_test_env(tmp_path):
    """Setup temporary database path for tests."""
    db_file = tmp_path / "test_scopeguard.db"
    settings.db_path = str(db_file)
    settings.proxy_mode = ProxyMode.FULL
    yield
    if db_file.exists():
        os.remove(db_file)


@pytest.fixture
def classifier():
    return TaskToScopeClassifier()


@pytest.fixture
def policy_engine():
    return PolicyEngine(mode=ProxyMode.FULL)


@pytest.fixture
def identity_tagger():
    return IdentityTagger()


@pytest.fixture
def audit_logger(tmp_path):
    db_file = str(tmp_path / "audit_test.db")
    return AuditLogger(db_path=db_file)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
