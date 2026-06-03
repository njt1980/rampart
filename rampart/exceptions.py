"""
rampart/exceptions.py

Exception hierarchy for the Rampart package. All exceptions derive from
RampartError so callers can catch the full family with a single except
clause. PolicyViolationError is the most important: it is raised by the
pipeline when a guard's action is BLOCK and carries the full set of
violations for audit purposes.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from rampart.models import GuardResult


class RampartError(Exception):
    """Base class for all Rampart exceptions."""


class PolicyViolationError(RampartError):
    """Raised when a guard's configured action is BLOCK.

    Carries the pipeline direction ('input' or 'output') and the list
    of GuardResult objects that triggered the block, so callers can
    inspect which guards fired and include the information in audit trails.

    Attributes:
        direction: The pipeline stage where the block occurred: 'input'
                   (user message) or 'output' (LLM response).
        violations: List of GuardResult objects whose action is BLOCK.
        request_id: UUID of the request, set by the Rampart client after
                    the pipeline raises. Empty string if raised directly
                    by the pipeline (before the client stamps it).
    """

    def __init__(
        self,
        direction: str,
        violations: List[GuardResult],
        request_id: str = "",
    ) -> None:
        self.request_id = request_id
        self.direction = direction
        self.violations = violations
        details = "; ".join(v.detail for v in violations)
        super().__init__(f"Policy violation on {direction}: {details}")


class PolicyLoadError(RampartError):
    """Raised when a policy cannot be loaded or parsed."""


class ProviderError(RampartError):
    """Raised when an LLM provider call fails."""
