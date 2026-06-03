"""
rampart/client.py

The top-level Rampart client that orchestrates the full LLM request
lifecycle: loading policy, running input guards, calling the configured
LLM provider, running output guards, and emitting structured audit records.
This is the primary entry point for applications integrating Rampart.
"""
from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from rampart.audit import AuditLogger
from rampart.exceptions import PolicyViolationError
from rampart.models import Action, GuardResult, RampartResponse
from rampart.pipeline import Pipeline
from rampart.policy.loader import PolicyLoader
from rampart.policy.schema import Policy
from rampart.providers import BaseProvider, create_provider


class Rampart:
    """Orchestrates the full LLM request lifecycle with policy-based guardrails.

    On construction, Rampart loads the policy from the configured registry
    and sets up the provider. On each invoke() call it runs the input
    pipeline, calls the provider, runs the output pipeline, and returns
    the (possibly redacted) response.

    Pipeline instances are cached per (profile, direction) pair and
    invalidated automatically when the policy version changes.

    Args:
        policy_registry: URI pointing to the policy YAML. Use
                         ``file://./path/to/policy.yaml`` for local files
                         or ``https://...`` for HTTP-served policies.
        provider: Provider name string ('bedrock', 'cortex', 'mock').
        app_id: Application identifier written to every audit record.
        reload_interval: Seconds between background policy reload checks
                         for HTTP registries. Set to 0 to disable. Default 300.
        provider_kwargs: Optional keyword arguments forwarded to the
                         provider constructor (e.g. region_name for Bedrock).
    """

    def __init__(
        self,
        policy_registry: str,
        provider: str,
        app_id: str,
        reload_interval: int = 300,
        provider_kwargs: Optional[dict] = None,
    ) -> None:
        self.app_id = app_id
        self._provider: BaseProvider = create_provider(provider, **(provider_kwargs or {}))
        self._policy_loader = PolicyLoader(policy_registry, reload_interval)
        self._audit = AuditLogger()
        # Pipeline instances are keyed by profile name and reused across
        # requests. They are cleared when the policy version changes.
        self._input_pipelines: Dict[str, Pipeline] = {}
        self._output_pipelines: Dict[str, Pipeline] = {}
        self._cached_version: Optional[str] = None

    def invoke(
        self,
        model_id: str,
        messages: list,
        profile: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        **kwargs,
    ) -> RampartResponse:
        """Run the full Rampart lifecycle for a single LLM request.

        Runs the input guard pipeline on the last user message, calls the
        provider, runs the output guard pipeline on the LLM response, and
        returns the final (possibly redacted) text alongside any non-blocking
        warnings. If any guard returns BLOCK, PolicyViolationError is raised
        and no response is returned.

        Args:
            model_id: Model identifier forwarded to the provider.
            messages: Conversation messages in standard chat format
                      (list of dicts with 'role' and 'content' keys).
                      The last message with role='user' is scanned by
                      the input pipeline.
            profile: Policy profile name to apply. Must exist in the
                     loaded policy YAML.
            user_id: Optional pseudonymised user identifier written to
                     audit records.
            session_id: Optional session identifier written to audit records.
            **kwargs: Additional keyword arguments forwarded to the
                      provider's invoke() method (e.g. max_tokens, system).

        Returns:
            RampartResponse with the LLM's text (after any output
            redactions), the request UUID, and any non-blocking warnings.

        Raises:
            PolicyViolationError: If any input or output guard triggers
                                  a BLOCK action.
            KeyError: If the profile name is not found in the policy.
        """
        request_id = str(uuid.uuid4())
        policy = self._policy_loader.policy
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        context: dict = {
            "request_id": request_id,
            "app_id": self.app_id,
            "policy_version": policy.version,
            "profile": profile,
            "provider": self._provider.name,
            "model_id": model_id,
            "timestamp": timestamp,
        }
        if user_id:
            context["user_id"] = user_id
        if session_id:
            context["session_id"] = session_id

        input_text = self._extract_last_user_text(messages)

        # --- input pipeline ---
        context["direction"] = "input"
        input_pipeline = self._get_pipeline(profile, "input", policy)
        try:
            clean_input, _, input_results, input_latency = input_pipeline.run(
                input_text, context
            )
        except PolicyViolationError as e:
            e.request_id = request_id
            self._audit.log(
                request_id=request_id,
                app_id=self.app_id,
                policy_version=policy.version,
                profile=profile,
                provider=self._provider.name,
                model_id=model_id,
                direction="input",
                guard_results=e.violations,
                final_decision="blocked",
                total_latency_ms=0,
                timestamp=timestamp,
            )
            raise

        self._audit.log(
            request_id=request_id,
            app_id=self.app_id,
            policy_version=policy.version,
            profile=profile,
            provider=self._provider.name,
            model_id=model_id,
            direction="input",
            guard_results=input_results,
            final_decision=_decision(input_results),
            total_latency_ms=input_latency,
            timestamp=timestamp,
        )

        # --- provider call ---
        # Substitute redacted text into the messages before sending to the
        # LLM so the provider never sees the original PII or injected text.
        clean_messages = self._update_last_user_text(messages, input_text, clean_input)
        llm_response = self._provider.invoke(model_id, clean_messages, **kwargs)

        # --- output pipeline ---
        context["direction"] = "output"
        output_pipeline = self._get_pipeline(profile, "output", policy)
        try:
            clean_output, output_warnings, output_results, output_latency = output_pipeline.run(
                llm_response, context
            )
        except PolicyViolationError as e:
            e.request_id = request_id
            self._audit.log(
                request_id=request_id,
                app_id=self.app_id,
                policy_version=policy.version,
                profile=profile,
                provider=self._provider.name,
                model_id=model_id,
                direction="output",
                guard_results=e.violations,
                final_decision="blocked",
                total_latency_ms=0,
                timestamp=timestamp,
            )
            raise

        self._audit.log(
            request_id=request_id,
            app_id=self.app_id,
            policy_version=policy.version,
            profile=profile,
            provider=self._provider.name,
            model_id=model_id,
            direction="output",
            guard_results=output_results,
            final_decision=_decision(output_results),
            total_latency_ms=output_latency,
            timestamp=timestamp,
        )

        input_warnings = [r for r in input_results if not r.passed and r.action != Action.BLOCK]
        return RampartResponse(
            text=clean_output,
            request_id=request_id,
            warnings=input_warnings + output_warnings,
        )

    def warmup(self, profile: str) -> None:
        """Pre-load ML models for the specified profile.

        Instantiates all guards configured in the profile's input and
        output pipelines, triggering any ML model downloads and loading
        models into RAM. Call this on application startup to avoid
        cold-start latency on the first user request.

        Args:
            profile: Name of the policy profile to warm up. Must match
                     a profile name in the loaded policy.

        Example:
            client = Rampart(
                policy_registry="file://./policies/banking.yaml",
                provider="bedrock",
                app_id="my-app",
            )
            client.warmup("customer_support")  # call on startup
            # first invoke() is now fast
        """
        policy = self._policy_loader.policy
        self._get_pipeline(profile, "input", policy)
        self._get_pipeline(profile, "output", policy)

    def _get_pipeline(self, profile: str, direction: str, policy: Policy) -> Pipeline:
        """Return a cached Pipeline for the given profile and direction.

        Pipelines are keyed by profile name. If the policy version has
        changed since the last request, all cached pipelines are discarded
        and new ones are built from the updated policy.

        Args:
            profile: Policy profile name.
            direction: 'input' or 'output'.
            policy: The currently active Policy object.

        Returns:
            Pipeline instance for the given profile and direction.
        """
        if self._cached_version != policy.version:
            # Policy has been reloaded — discard all cached pipelines so
            # they are rebuilt from the new guard configuration.
            self._input_pipelines.clear()
            self._output_pipelines.clear()
            self._cached_version = policy.version

        cache = self._input_pipelines if direction == "input" else self._output_pipelines
        if profile not in cache:
            profile_config = self._policy_loader.get_profile(profile)
            guards = profile_config.input if direction == "input" else profile_config.output
            cache[profile] = Pipeline(guards)
        return cache[profile]

    @staticmethod
    def _extract_last_user_text(messages: list) -> str:
        """Extract the text content of the most recent user message.

        Walks the messages list in reverse to find the last message with
        role='user'. Handles both string content and multi-part content
        blocks (as used by Bedrock Converse API).

        Args:
            messages: List of message dicts with 'role' and 'content' keys.

        Returns:
            The extracted text string, or an empty string if no user
            message is found.
        """
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg["content"]
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    # Multi-part content block: concatenate all text parts.
                    return " ".join(
                        part.get("text", "")
                        for part in content
                        if isinstance(part, dict)
                    )
        return ""

    @staticmethod
    def _update_last_user_text(messages: list, original: str, replacement: str) -> list:
        """Replace the last user message text with the (possibly redacted) text.

        Returns the original messages list unchanged if no redaction
        occurred. Otherwise deep-copies the list before modification to
        avoid mutating the caller's data.

        Args:
            messages: Original messages list.
            original: The text that was scanned (before redaction).
            replacement: The text to substitute (after redaction).

        Returns:
            Updated messages list, or the original list if no change needed.
        """
        if original == replacement:
            return messages
        messages = copy.deepcopy(messages)
        for msg in reversed(messages):
            if msg.get("role") == "user":
                if isinstance(msg["content"], str):
                    msg["content"] = replacement
                elif isinstance(msg["content"], list):
                    for part in msg["content"]:
                        if isinstance(part, dict) and part.get("text") == original:
                            part["text"] = replacement
                            break
                return messages
        return messages


def _decision(results: List[GuardResult]) -> str:
    """Derive the final_decision string for an audit record.

    Args:
        results: List of GuardResult objects from a completed pipeline run.

    Returns:
        'redacted' if any guard redacted text, 'warned' if any guard
        issued a warning, 'allowed' if all guards passed.
    """
    for r in results:
        if not r.passed:
            if r.action == Action.REDACT:
                return "redacted"
            if r.action == Action.WARN:
                return "warned"
    return "allowed"
