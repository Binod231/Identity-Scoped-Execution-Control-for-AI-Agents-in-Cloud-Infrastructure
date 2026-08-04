"""
ScopeGuard Policy Engine (FR4).

Evaluates whether a tool call should be ALLOWED, BLOCKED, or WARNED
based on the scoping result from the classifier. Supports three
operational modes for the ablation study (Section 5.4):

  1. PASSTHROUGH — forward everything, no enforcement
  2. TAGGING_ONLY — log and attribute, never block
  3. FULL — log, attribute, and enforce allow/block/warn

Fail-closed by default (NFR2): any internal error results in BLOCKED.
"""

import logging

from proxy.config import ProxyMode, settings
from proxy.models import RiskLevel, ScopingDecision, ScopeResult, ToolCallRequest

logger = logging.getLogger("scopeguard.policy")


class PolicyEngine:
    """
    Evaluates tool calls against computed scope and makes allow/block/warn decisions.
    """

    def __init__(self, mode: ProxyMode | None = None, fail_closed: bool | None = None):
        self.mode = mode or settings.proxy_mode
        self.fail_closed = fail_closed if fail_closed is not None else settings.fail_closed

    def evaluate(
        self,
        request: ToolCallRequest,
        scope: ScopeResult,
    ) -> ScopingDecision:
        """
        Evaluate a tool call against the computed scope.

        Args:
            request: The intercepted tool call
            scope: The computed scope from the classifier

        Returns:
            ScopingDecision (ALLOWED, BLOCKED, or WARNED)
        """
        # Passthrough mode: always allow (baseline — no enforcement)
        if self.mode == ProxyMode.PASSTHROUGH:
            return ScopingDecision.ALLOWED

        # Tagging-only mode: always allow (logs but never blocks — for ablation)
        if self.mode == ProxyMode.TAGGING_ONLY:
            return ScopingDecision.ALLOWED

        # Full mode: enforce scoping
        try:
            return self._enforce(request, scope)
        except Exception as e:
            # NFR2: Fail closed on internal errors
            logger.error(
                "Policy engine internal error (fail_closed=%s): %s",
                self.fail_closed,
                str(e),
            )
            if self.fail_closed:
                return ScopingDecision.BLOCKED
            return ScopingDecision.WARNED

    def _enforce(
        self,
        request: ToolCallRequest,
        scope: ScopeResult,
    ) -> ScopingDecision:
        """
        Core enforcement logic for FULL mode.

        Decision matrix:
          - Action in scope + LOW/MEDIUM risk → ALLOWED
          - Action in scope + HIGH/CRITICAL risk → WARNED (logged with alert)
          - Action NOT in scope → BLOCKED
          - No scope computed (confidence = 0) → BLOCKED (deny-by-default)
        """
        action = request.tool_action

        # If the classifier found no matching keywords, deny by default
        if scope.confidence == 0.0 and len(scope.allowed_actions) == 0:
            logger.warning(
                "BLOCKED: No scope could be computed for task '%s' (action: %s)",
                request.declared_task[:100],
                action,
            )
            return ScopingDecision.BLOCKED

        # Check if the action is within the computed scope
        if action in scope.allowed_actions:
            # Action is in scope — check risk level for warnings
            action_risk = self._get_action_risk_from_scope(action, scope)
            if action_risk in (RiskLevel.HIGH, RiskLevel.CRITICAL):
                logger.info(
                    "WARNED: Action %s is in scope but risk level is %s",
                    action,
                    action_risk.value,
                )
                return ScopingDecision.WARNED
            return ScopingDecision.ALLOWED

        # Action is NOT in scope → BLOCKED
        logger.warning(
            "BLOCKED: Action %s is not in computed scope for task '%s'. "
            "Allowed: %s",
            action,
            request.declared_task[:100],
            sorted(scope.allowed_actions)[:5],
        )
        return ScopingDecision.BLOCKED

    @staticmethod
    def _get_action_risk_from_scope(action: str, scope: ScopeResult) -> RiskLevel:
        """Determine risk level of an action within the scope context."""
        # The scope.risk_level represents the maximum risk across all allowed actions.
        # For individual action risk, we use a lookup approach.
        # This is a simplified version — the classifier tracks per-action risk.
        return scope.risk_level

    def get_mode_description(self) -> str:
        """Return a human-readable description of the current mode."""
        descriptions = {
            ProxyMode.FULL: "Full enforcement (identity + scoping + allow/block/warn)",
            ProxyMode.TAGGING_ONLY: "Tagging only (identity + logging, no blocking)",
            ProxyMode.PASSTHROUGH: "Passthrough (no interception, baseline)",
        }
        return descriptions.get(self.mode, "Unknown mode")
