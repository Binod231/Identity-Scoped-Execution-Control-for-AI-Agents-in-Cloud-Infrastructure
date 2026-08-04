"""
ScopeGuard Rule-Based Task-to-Scope Classifier (FR3).

Parses the agent's declared task description and computes the minimal set of
AWS actions that task requires. Uses keyword matching against the action
taxonomy defined in schemas/permissions.json.

This is explicitly a keyword/rule-based baseline classifier — not a
semantic/embedding-based or LLM-assisted system. That distinction is
important for honest positioning in the paper (Section 6.3, FR3).
"""

import json
import re
from pathlib import Path

from proxy.models import RiskLevel, ScopeResult


class TaskToScopeClassifier:
    """
    Rule-based classifier that maps a declared task description
    to a minimal set of permitted AWS actions.
    """

    def __init__(self, taxonomy_path: str | None = None):
        """Load the action taxonomy from JSON."""
        if taxonomy_path is None:
            taxonomy_path = str(
                Path(__file__).parent / "schemas" / "permissions.json"
            )
        with open(taxonomy_path) as f:
            self._taxonomy = json.load(f)

        self._resource_types = self._taxonomy["resource_types"]
        self._meta_rules = self._taxonomy["meta_rules"]

        # Pre-compile keyword patterns for fast matching
        self._compiled_rules: list[dict] = []
        for _resource_type, resource_data in self._resource_types.items():
            for action_name, action_data in resource_data["actions"].items():
                for keyword in action_data["kw"]:
                    self._compiled_rules.append({
                        "pattern": re.compile(re.escape(keyword), re.IGNORECASE),
                        "keyword": keyword,
                        "action": action_name,
                        "risk": action_data["risk"],
                        "operation": action_data["op"],
                        "resource_type": _resource_type,
                    })

    def classify(self, declared_task: str) -> ScopeResult:
        """
        Classify a declared task and return the allowed action scope.

        Args:
            declared_task: Natural language description of the agent's task.

        Returns:
            ScopeResult with allowed_actions, risk_level, confidence, and matched keywords.
        """
        if not declared_task or not declared_task.strip():
            return ScopeResult(
                allowed_actions=set(),
                risk_level=RiskLevel.LOW,
                confidence=0.0,
                matched_keywords=[],
            )

        task_lower = declared_task.lower().strip()
        allowed_actions: set[str] = set()
        matched_keywords: list[str] = []
        max_risk = RiskLevel.LOW
        matched_resource_types: set[str] = set()

        # Phase 1: Direct keyword matching
        for rule in self._compiled_rules:
            if rule["pattern"].search(task_lower):
                allowed_actions.add(rule["action"])
                matched_keywords.append(rule["keyword"])
                matched_resource_types.add(rule["resource_type"])

                # Track the highest risk level encountered
                rule_risk = RiskLevel(rule["risk"])
                if self._risk_ordinal(rule_risk) > self._risk_ordinal(max_risk):
                    max_risk = rule_risk

        # Phase 2: Apply meta-rules
        if self._meta_rules.get("implicit_read_grant"):
            allowed_actions = self._grant_implicit_reads(
                allowed_actions, matched_resource_types
            )

        # Phase 3: Compute confidence
        # Confidence = ratio of matched keywords to total keywords checked,
        # weighted by specificity (longer keywords = more specific)
        if matched_keywords:
            avg_keyword_len = sum(len(kw) for kw in matched_keywords) / len(matched_keywords)
            specificity_bonus = min(avg_keyword_len / 20.0, 0.3)
            base_confidence = min(len(matched_keywords) / 5.0, 0.7)
            confidence = min(base_confidence + specificity_bonus, 1.0)
        else:
            confidence = 0.0

        return ScopeResult(
            allowed_actions=allowed_actions,
            risk_level=max_risk,
            confidence=round(confidence, 3),
            matched_keywords=sorted(set(matched_keywords)),
        )

    def is_action_in_scope(self, action: str, scope: ScopeResult) -> bool:
        """Check whether a specific action is within the computed scope."""
        return action in scope.allowed_actions

    def get_action_risk(self, action: str) -> RiskLevel:
        """Look up the risk level for a specific action."""
        for resource_data in self._resource_types.values():
            if action in resource_data["actions"]:
                return RiskLevel(resource_data["actions"][action]["risk"])
        return RiskLevel.HIGH  # Unknown actions default to HIGH risk

    def _grant_implicit_reads(
        self, actions: set[str], resource_types: set[str]
    ) -> set[str]:
        """
        When a create/update action is allowed, implicitly grant
        the corresponding describe/list action for that resource type.
        """
        implicit_reads: set[str] = set()
        for rt in resource_types:
            if rt in self._resource_types:
                for action_name, action_data in self._resource_types[rt]["actions"].items():
                    if action_data["op"] == "read":
                        implicit_reads.add(action_name)
        return actions | implicit_reads

    @staticmethod
    def _risk_ordinal(risk: RiskLevel) -> int:
        """Map risk levels to ordinals for comparison."""
        return {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}.get(risk.value, 2)
