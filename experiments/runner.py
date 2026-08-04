"""
ScopeGuard Experiment Runner.

Executes the complete 200-task evaluation set (100 legitimate + 100 adversarial)
across three ablation configurations:
  1. passthrough (raw baseline, no proxy)
  2. tagging_only (identity tagging & logging, no enforcement)
  3. full (identity tagging + task scoping + allow/block/warn enforcement)

Saves detailed call records to CSV and SQLite for statistical analysis.
"""

import asyncio
import json
import logging
import time
from pathlib import Path
import pandas as pd
from httpx import ASGITransport, AsyncClient

from agent.simulator import TaskDefinition
from proxy.config import ProxyMode, settings
from proxy.main import app, lifespan

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scopeguard.experiment_runner")


class ExperimentRunner:
    """
    Drives ablation experiments by feeding task tool calls into the FastAPI app
    under different proxy modes.
    """

    def __init__(self, output_dir: str = "experiments/results"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def load_tasks(self) -> list[TaskDefinition]:
        """Load 100 legitimate and 100 adversarial tasks."""
        tasks_dir = Path(__file__).parent.parent / "agent" / "tasks"
        with open(tasks_dir / "legitimate.json") as f:
            legit_raw = json.load(f)
        with open(tasks_dir / "adversarial.json") as f:
            adv_raw = json.load(f)

        tasks = [TaskDefinition(t) for t in legit_raw] + [TaskDefinition(t) for t in adv_raw]
        logger.info("Loaded %d total evaluation tasks (%d legit, %d adv)",
                    len(tasks), len(legit_raw), len(adv_raw))
        return tasks

    async def run_mode(
        self, mode: ProxyMode, tasks: list[TaskDefinition]
    ) -> list[dict]:
        """Run all tasks under a specific proxy mode."""
        settings.proxy_mode = mode
        if hasattr(app.state, "policy_engine"):
            app.state.policy_engine.mode = mode

        results = []
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for task in tasks:
                session_id = f"exp-{mode.value}-{task.id}"
                for i, call in enumerate(task.tool_calls):
                    payload = {
                        "agent_id": "eval-agent-v1",
                        "session_id": session_id,
                        "declared_task": task.declared_task,
                        "reasoning_excerpt": f"Executing task {task.id} step {i+1}",
                        "tool_name": call["tool"],
                        "tool_action": call["action"],
                        "tool_params": call.get("params", {}),
                    }

                    t0 = time.perf_counter()
                    response = await client.post("/execute-tool", json=payload)
                    t_delta_ms = (time.perf_counter() - t0) * 1000

                    if response.status_code == 200:
                        data = response.json()
                        decision = data["decision"]
                    else:
                        decision = "ERROR"

                    results.append({
                        "mode": mode.value,
                        "task_id": task.id,
                        "category": task.category,
                        "is_adversarial": task.is_adversarial,
                        "adversarial_type": task.adversarial_type,
                        "tool_action": call["action"],
                        "decision": decision,
                        "expected": "BLOCKED" if task.is_adversarial else "ALLOWED",
                        "latency_ms": round(t_delta_ms, 3),
                        "server_latency_ms": data.get("latency_ms", 0.0) if response.status_code == 200 else 0.0,
                    })

        return results

    async def run_all(self):
        """Run all 3 ablation modes and export results."""
        tasks = self.load_tasks()
        all_results = []

        async with lifespan(app):
            modes = [ProxyMode.PASSTHROUGH, ProxyMode.TAGGING_ONLY, ProxyMode.FULL]

            for mode in modes:
                logger.info("Starting evaluation in mode: %s", mode.value)
                res = await self.run_mode(mode, tasks)
                all_results.extend(res)
                logger.info("Completed %s mode (%d call records)", mode.value, len(res))

        df = pd.DataFrame(all_results)
        csv_path = self.output_dir / "ablation_results.csv"
        df.to_csv(csv_path, index=False)
        logger.info("Saved ablation experiment results to %s", csv_path)
        return df


def main():
    runner = ExperimentRunner()
    asyncio.run(runner.run_all())


if __name__ == "__main__":
    main()
