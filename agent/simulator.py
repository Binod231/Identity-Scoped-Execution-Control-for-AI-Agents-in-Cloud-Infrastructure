"""
Deterministic Agent Simulator.

Simulates an AI agent's tool-calling behavior WITHOUT requiring a real LLM
API call. Takes a task definition and generates the corresponding sequence
of tool calls through the ScopeGuard proxy.

This ensures:
  - Perfect reproducibility (no LLM randomness)
  - Zero API cost for experiments
  - Full control over legitimate vs. adversarial patterns
"""

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger("scopeguard.simulator")


class TaskDefinition:
    """Represents a single task from the task set (legitimate or adversarial)."""

    def __init__(self, data: dict[str, Any]):
        self.id: str = data["id"]
        self.category: str = data["category"]
        self.declared_task: str = data["declared_task"]
        self.is_adversarial: bool = data["is_adversarial"]
        self.adversarial_type: str = data.get("adversarial_type", "")
        self.tool_calls: list[dict[str, Any]] = data["tool_calls"]
        self.expected_decisions: list[str] = data.get("expected_decisions", [])
        self.description: str = data.get("description", "")

    def __repr__(self) -> str:
        kind = "ADV" if self.is_adversarial else "LEG"
        return f"Task({self.id}, {kind}, {self.category})"


class AgentSimulator:
    """
    Simulates an AI agent executing tasks against the ScopeGuard proxy.

    For each task, generates the predefined tool call sequence and sends
    each call through the proxy's /execute-tool endpoint.
    """

    def __init__(
        self,
        proxy_url: str = "http://localhost:8000",
        agent_id: str = "simulator-agent-v1",
    ):
        self.proxy_url = proxy_url.rstrip("/")
        self.agent_id = agent_id
        self._client = httpx.Client(timeout=30.0)

    def load_tasks(self, task_file: str) -> list[TaskDefinition]:
        """Load task definitions from a JSON file."""
        with open(task_file) as f:
            raw = json.load(f)
        return [TaskDefinition(t) for t in raw]

    def load_all_tasks(self, tasks_dir: str | None = None) -> list[TaskDefinition]:
        """Load both legitimate and adversarial task sets."""
        if tasks_dir is None:
            tasks_dir = str(Path(__file__).parent / "tasks")
        tasks = []
        leg_path = Path(tasks_dir) / "legitimate.json"
        adv_path = Path(tasks_dir) / "adversarial.json"
        if leg_path.exists():
            tasks.extend(self.load_tasks(str(leg_path)))
        if adv_path.exists():
            tasks.extend(self.load_tasks(str(adv_path)))
        return tasks

    def execute_task(self, task: TaskDefinition) -> list[dict[str, Any]]:
        """
        Execute a single task: send all its tool calls through the proxy.

        Returns a list of results, one per tool call.
        """
        session_id = str(uuid.uuid4())
        results = []

        for i, call in enumerate(task.tool_calls):
            call_start = time.perf_counter()

            payload = {
                "agent_id": self.agent_id,
                "session_id": session_id,
                "declared_task": task.declared_task,
                "reasoning_excerpt": f"Task {task.id}, step {i+1}/{len(task.tool_calls)}",
                "tool_name": call["tool"],
                "tool_action": call["action"],
                "tool_params": call.get("params", {}),
            }

            try:
                response = self._client.post(
                    f"{self.proxy_url}/execute-tool",
                    json=payload,
                )
                call_latency = (time.perf_counter() - call_start) * 1000

                if response.status_code == 200:
                    resp_data = response.json()
                else:
                    resp_data = {
                        "decision": "ERROR",
                        "error": f"HTTP {response.status_code}: {response.text}",
                    }

            except Exception as e:
                call_latency = (time.perf_counter() - call_start) * 1000
                resp_data = {"decision": "ERROR", "error": str(e)}

            expected = (
                task.expected_decisions[i]
                if i < len(task.expected_decisions)
                else None
            )

            results.append({
                "task_id": task.id,
                "call_index": i,
                "tool_action": call["action"],
                "decision": resp_data.get("decision", "ERROR"),
                "expected_decision": expected,
                "is_adversarial": task.is_adversarial,
                "adversarial_type": task.adversarial_type,
                "category": task.category,
                "latency_ms": round(call_latency, 2),
                "error": resp_data.get("error"),
                "audit_id": resp_data.get("audit_id"),
            })

            logger.debug(
                "Task %s call %d: %s → %s (%.1fms)",
                task.id, i, call["action"],
                resp_data.get("decision", "ERROR"), call_latency,
            )

        return results

    def execute_all(self, tasks: list[TaskDefinition]) -> list[dict[str, Any]]:
        """Execute all tasks and return combined results."""
        all_results = []
        for task in tasks:
            results = self.execute_task(task)
            all_results.extend(results)
        return all_results

    def close(self):
        """Close the HTTP client."""
        self._client.close()
