"""
ScopeGuard Backend Executor.

Routes intercepted tool calls to the appropriate backend:
  - boto3 calls → LocalStack (http://localhost:4566) or real AWS
  - Terraform calls → subprocess with LocalStack provider config
  - GitHub Actions → mock/stub for experiment purposes

Endpoint switching is config-driven (NFR3 — portability).
"""

import json
import logging
from typing import Any

import boto3
from botocore.config import Config as BotoConfig

from proxy.config import settings

logger = logging.getLogger("scopeguard.executor")


class BackendExecutor:
    """
    Dispatches tool calls to the appropriate cloud backend
    and captures execution results.
    """

    def __init__(self):
        self._boto_clients: dict[str, Any] = {}
        self._boto_config = BotoConfig(
            region_name=settings.aws_region,
            retries={"max_attempts": 2, "mode": "standard"},
        )

    def _get_boto_client(self, service_name: str):
        """Get or create a boto3 client for the given service."""
        if service_name not in self._boto_clients:
            kwargs = {
                "service_name": service_name,
                "config": self._boto_config,
                "region_name": settings.aws_region,
            }
            if settings.use_localstack:
                kwargs["endpoint_url"] = settings.localstack_endpoint
                kwargs["aws_access_key_id"] = "test"
                kwargs["aws_secret_access_key"] = "test"

            self._boto_clients[service_name] = boto3.client(**kwargs)
        return self._boto_clients[service_name]

    async def execute(
        self,
        tool_name: str,
        tool_action: str,
        tool_params: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Execute a tool call against the configured backend.

        Args:
            tool_name: Tool identifier (e.g., 'aws_s3_operation')
            tool_action: Specific action (e.g., 's3:CreateBucket')
            tool_params: Parameters for the call

        Returns:
            dict with 'success', 'result', and optionally 'error'
        """
        try:
            if tool_name.startswith("aws_") or ":" in tool_action:
                return await self._execute_boto3(tool_action, tool_params)
            elif tool_name.startswith("terraform"):
                return await self._execute_terraform(tool_action, tool_params)
            elif tool_name.startswith("github"):
                return await self._execute_github_stub(tool_action, tool_params)
            else:
                return {
                    "success": False,
                    "result": None,
                    "error": f"Unknown tool: {tool_name}",
                }
        except Exception as e:
            logger.error("Execution error for %s: %s", tool_action, str(e))
            return {
                "success": False,
                "result": None,
                "error": str(e),
            }

    async def _execute_boto3(
        self, tool_action: str, tool_params: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute a boto3 API call against LocalStack or real AWS."""
        # Parse action: "s3:CreateBucket" → service="s3", method="create_bucket"
        parts = tool_action.split(":")
        if len(parts) != 2:
            return {"success": False, "result": None, "error": f"Invalid action format: {tool_action}"}

        service_name = parts[0].lower()
        api_action = parts[1]

        # Convert PascalCase action to snake_case method name
        method_name = self._pascal_to_snake(api_action)

        try:
            client = self._get_boto_client(service_name)

            if not hasattr(client, method_name):
                return {
                    "success": False,
                    "result": None,
                    "error": f"Method {method_name} not found on {service_name} client",
                }

            method = getattr(client, method_name)
            result = method(**tool_params)

            # Serialize the response (remove non-serializable metadata)
            if isinstance(result, dict):
                result.pop("ResponseMetadata", None)
                serialized = json.dumps(result, default=str, indent=2)
            else:
                serialized = str(result)

            return {"success": True, "result": serialized, "error": None}

        except Exception as e:
            return {"success": False, "result": None, "error": str(e)}

    async def _execute_terraform(
        self, tool_action: str, tool_params: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Stub for Terraform execution.
        In a full implementation, this would invoke terraform CLI as a subprocess
        with the LocalStack provider configured.
        """
        logger.info("Terraform stub: %s with params %s", tool_action, tool_params)
        return {
            "success": True,
            "result": json.dumps({
                "action": tool_action,
                "status": "simulated",
                "message": "Terraform execution simulated (stub)",
            }),
            "error": None,
        }

    async def _execute_github_stub(
        self, tool_action: str, tool_params: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Stub for GitHub Actions API.
        Returns a simulated response for experiment purposes.
        """
        logger.info("GitHub Actions stub: %s with params %s", tool_action, tool_params)
        return {
            "success": True,
            "result": json.dumps({
                "action": tool_action,
                "status": "simulated",
                "message": "GitHub Actions execution simulated (stub)",
            }),
            "error": None,
        }

    @staticmethod
    def _pascal_to_snake(name: str) -> str:
        """Convert PascalCase to snake_case (e.g., CreateBucket → create_bucket)."""
        import re
        s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
        return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()
