"""
ScopeGuard Identity Tagger.

Extracts, validates, and attaches identity metadata to every intercepted tool call.
Ensures:
  - Every call has a unique tracking UUID4
  - Agent ID and session ID are present and non-empty
  - Credentials/secrets are stripped from logged parameters (NFR5)
  - Declared task and reasoning excerpts are captured for attribution
"""

import re
import uuid
from typing import Any

from proxy.models import ToolCallRequest


# Patterns that indicate sensitive values to redact from audit logs
_SECRET_PATTERNS = re.compile(
    r"(password|secret|token|key|credential|auth|api.?key|access.?key|private)",
    re.IGNORECASE,
)

# Maximum length for reasoning excerpts stored in audit
_MAX_REASONING_LENGTH = 500


class IdentityTagger:
    """
    Attaches identity metadata to intercepted tool calls and sanitizes
    parameters to prevent credential leakage into audit logs.
    """

    @staticmethod
    def generate_tracking_id() -> str:
        """Generate a unique UUID4 tracking ID for this interception."""
        return str(uuid.uuid4())

    @staticmethod
    def validate_identity(request: ToolCallRequest) -> tuple[bool, str]:
        """
        Validate that the request contains required identity fields.

        Returns:
            (is_valid, error_message)
        """
        if not request.agent_id or not request.agent_id.strip():
            return False, "agent_id is required and must be non-empty"
        if not request.session_id or not request.session_id.strip():
            return False, "session_id is required and must be non-empty"
        if not request.declared_task or not request.declared_task.strip():
            return False, "declared_task is required and must be non-empty"
        if not request.tool_name or not request.tool_name.strip():
            return False, "tool_name is required and must be non-empty"
        if not request.tool_action or not request.tool_action.strip():
            return False, "tool_action is required and must be non-empty"
        return True, ""

    @staticmethod
    def sanitize_params(params: dict[str, Any]) -> dict[str, Any]:
        """
        Strip credentials and secrets from tool parameters before logging.

        Recursively traverses the parameter dict, redacting any values
        whose keys match secret patterns (NFR5).
        """
        sanitized = {}
        for key, value in params.items():
            if _SECRET_PATTERNS.search(key):
                sanitized[key] = "[REDACTED]"
            elif isinstance(value, dict):
                sanitized[key] = IdentityTagger.sanitize_params(value)
            elif isinstance(value, list):
                sanitized[key] = [
                    IdentityTagger.sanitize_params(item)
                    if isinstance(item, dict)
                    else item
                    for item in value
                ]
            else:
                sanitized[key] = value
        return sanitized

    @staticmethod
    def truncate_reasoning(reasoning: str) -> str:
        """Truncate reasoning excerpt to a reasonable length for storage."""
        if len(reasoning) > _MAX_REASONING_LENGTH:
            return reasoning[:_MAX_REASONING_LENGTH] + "... [truncated]"
        return reasoning

    @staticmethod
    def extract_identity(request: ToolCallRequest) -> dict[str, Any]:
        """
        Extract and package all identity metadata from a tool call request.

        Returns a dict with:
          - tracking_id: unique UUID4 for this specific call
          - agent_id, session_id: identity of the calling agent
          - declared_task: what the agent says it's trying to do
          - reasoning_excerpt: snippet of agent's reasoning chain
          - tool_params_sanitized: parameters with secrets stripped
        """
        return {
            "tracking_id": IdentityTagger.generate_tracking_id(),
            "agent_id": request.agent_id.strip(),
            "session_id": request.session_id.strip(),
            "declared_task": request.declared_task.strip(),
            "reasoning_excerpt": IdentityTagger.truncate_reasoning(
                request.reasoning_excerpt.strip()
            ),
            "tool_name": request.tool_name.strip(),
            "tool_action": request.tool_action.strip(),
            "tool_params_sanitized": IdentityTagger.sanitize_params(request.tool_params),
        }
