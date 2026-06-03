"""
rampart/pipeline.py

Implements the guard pipeline that runs input and output guards
sequentially against LLM request and response text. The pipeline
is the core execution engine of Rampart — it loads guard classes
dynamically from policy configuration, runs each guard in order,
and handles the four possible actions: block, redact, warn, allow.
"""
from __future__ import annotations

import importlib
import time
from typing import List, Optional, Tuple

from rampart.base_guard import BaseGuard
from rampart.exceptions import PolicyViolationError
from rampart.models import Action, GuardResult
from rampart.policy.schema import GuardConfig


class Pipeline:
    """Executes a sequence of guards against text.

    Loads guard classes dynamically via importlib based on the
    GuardConfig objects provided at construction. Guards run
    sequentially — a BLOCK action raises PolicyViolationError
    immediately, a REDACT action passes modified_text to the
    next guard, WARN and ALLOW let text through unchanged.

    The pipeline is stateless with respect to individual requests —
    the same Pipeline instance can safely handle concurrent requests.

    Args:
        guard_configs: Ordered list of GuardConfig objects loaded
                       from the policy YAML profile.
    """

    def __init__(self, guard_configs: List[GuardConfig]) -> None:
        self._guard_configs = guard_configs
        # Instantiate all guards at construction time so ML models are
        # loaded once per pipeline, not once per request.
        self._entries: List[Tuple[BaseGuard, Optional[object]]] = [
            self._load_entry(gc) for gc in guard_configs
        ]

    def _load_entry(self, gc: GuardConfig) -> Tuple[BaseGuard, Optional[object]]:
        """Load and instantiate a single guard from its GuardConfig.

        Args:
            gc: GuardConfig describing the guard module, class, engine,
                and configuration dict.

        Returns:
            Tuple of (guard instance, LLMJudge instance or None).
            The judge is only created when the guard config contains
            an 'llm' block.

        Raises:
            ImportError: If the guard's module cannot be imported.
            AttributeError: If the guard class is not found in the module.
        """
        try:
            module = importlib.import_module(gc.module)
        except ImportError as e:
            raise ImportError(
                f"Cannot import guard module {gc.module!r}. "
                f"Ensure the required package is installed. Error: {e}"
            ) from e
        try:
            cls = getattr(module, gc.guard)
        except AttributeError:
            raise AttributeError(
                f"Guard class {gc.guard!r} not found in module {gc.module!r}"
            )
        guard = cls(config=gc.config, engine=gc.engine)
        # Only build a judge when the guard config declares an 'llm' block,
        # since LLMJudge construction creates a provider (which may validate
        # credentials or import optional dependencies).
        judge = self._build_judge(gc) if gc.config.get("llm") else None
        return guard, judge

    def _build_judge(self, gc: GuardConfig) -> object:
        """Construct an LLMJudge for a guard that uses 'llm' or 'hybrid' engine.

        Args:
            gc: GuardConfig containing an 'llm' sub-dict with provider,
                model_id, and optional max_tokens keys.

        Returns:
            Configured LLMJudge instance.
        """
        from rampart.judge import LLMJudge
        llm_cfg: dict = gc.config.get("llm", {})
        return LLMJudge(
            provider=llm_cfg.get("provider", "bedrock"),
            model_id=llm_cfg.get("model_id", ""),
            max_tokens=llm_cfg.get("max_tokens", 100),
        )

    def run(
        self,
        text: str,
        context: dict,
    ) -> Tuple[str, List[GuardResult], List[GuardResult], int]:
        """Run all guards sequentially against the provided text.

        Guards execute in the order they are declared in the policy
        YAML. On the first BLOCK result, execution stops immediately
        and PolicyViolationError is raised. REDACT results pass the
        modified text to subsequent guards. WARN results are collected
        and returned alongside the final text.

        Args:
            text: The text to scan — either the user's input message
                  or the LLM's response, depending on pipeline direction.
            context: Request metadata dict containing:
                - request_id (str): UUID for audit trail correlation.
                - app_id (str): Identifying the calling application.
                - policy_version (str): Version of the loaded policy.
                - profile (str): Name of the active policy profile.
                - direction (str): 'input' or 'output'.
                - user_id (str, optional): Pseudonymised user identifier.
                - session_id (str, optional): Session identifier.
                - llm_judge: LLMJudge instance if hybrid mode configured.

        Returns:
            Tuple of:
                - final_text (str): Text after any redactions applied.
                - warnings (List[GuardResult]): Non-blocking findings.
                - all_results (List[GuardResult]): Every guard's result.
                - total_latency_ms (int): Total pipeline execution time.

        Raises:
            PolicyViolationError: If any guard returns action=BLOCK.
                                  Contains the violating GuardResult
                                  and the request direction.
        """
        warnings: List[GuardResult] = []
        all_results: List[GuardResult] = []
        current_text = text
        t_start = time.monotonic()

        for gc, (guard, judge) in zip(self._guard_configs, self._entries):
            # Inject the per-guard LLMJudge into context so guards that
            # support hybrid/llm modes can call it without extra setup.
            guard_context = {**context, "llm_judge": judge}
            t0 = time.monotonic()
            result = guard.scan(current_text, guard_context)
            result.latency_ms = int((time.monotonic() - t0) * 1000)
            result.guard = gc.guard
            result.engine = gc.engine

            if not result.passed:
                # Policy action is authoritative — override whatever the
                # guard returned so the policy YAML controls enforcement.
                result.action = gc.action

                if gc.action == Action.BLOCK:
                    all_results.append(result)
                    raise PolicyViolationError(
                        direction=context.get("direction", "input"),
                        violations=[result],
                    )

                if gc.action == Action.REDACT:
                    # Pass redacted text to the next guard, not original.
                    if result.redacted_text is not None:
                        current_text = result.redacted_text
                    warnings.append(result)
                elif gc.action == Action.WARN:
                    warnings.append(result)
                # ALLOW: record finding in audit log, no enforcement action.
            else:
                result.action = Action.ALLOW

            all_results.append(result)

        total_latency = int((time.monotonic() - t_start) * 1000)
        return current_text, warnings, all_results, total_latency
