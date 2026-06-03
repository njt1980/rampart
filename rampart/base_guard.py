"""
rampart/base_guard.py

Defines the BaseGuard abstract base class that every guard must extend.
Guards are the unit of policy enforcement in Rampart — each guard scans
text and returns a GuardResult indicating whether the text passed, and
what action the pipeline should take if it did not.

The ABC pattern enforces that custom guards implement scan() and allows
the pipeline to treat all guard instances uniformly without knowing their
concrete types.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from rampart.models import GuardResult


class BaseGuard(ABC):
    """Abstract base class for all Rampart guards.

    Subclass this and implement scan() to create a custom guard. Register
    the guard by pointing a GuardConfig.module at its containing module
    and GuardConfig.guard at the class name.

    Args:
        config: Guard-specific configuration dict from the policy YAML.
                Each guard defines its own recognised keys (e.g. 'entities'
                for PiiGuard, 'threshold' for PromptInjectionGuard).
        engine: The detection engine mode. Standard values are 'classifier',
                'llm', and 'hybrid'. Guards use this to select their
                internal detection strategy.
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        engine: str = "classifier",
    ) -> None:
        self.config: Dict[str, Any] = config or {}
        self.engine: str = engine

    @abstractmethod
    def scan(self, text: str, context: dict) -> GuardResult:
        """Scan text for policy violations.

        Args:
            text: The text to inspect — either the user's input message
                  or the LLM's response, depending on pipeline direction.
            context: Request metadata dict injected by the pipeline.
                     Standard keys: request_id, app_id, policy_version,
                     profile, direction, llm_judge.

        Returns:
            GuardResult describing whether the text passed and what
            action the pipeline should take. Guards should set
            action=Action.BLOCK on failure; the pipeline overrides
            this with the policy's configured action.
        """
        ...
