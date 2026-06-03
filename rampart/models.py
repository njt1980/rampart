"""
rampart/models.py

Core data models shared across the Rampart package. Defines the Action
enum (the four possible guard outcomes), the GuardResult dataclass
(the output of a single guard's scan), and RampartResponse (the final
result returned to the caller after all guards and the LLM provider
have run).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class Action(str, Enum):
    """The four possible outcomes a guard can signal to the pipeline.

    The pipeline uses the policy's configured action (not the guard's
    default) to decide how to handle a failed scan. Guards return BLOCK
    as a sentinel; the policy overrides this at runtime.

    Values:
        BLOCK: Halt the request immediately and raise PolicyViolationError.
        REDACT: Replace the offending text with the guard's redacted_text,
                then continue running subsequent guards.
        WARN: Record the finding in the response's warnings list but pass
              the original text through unchanged.
        ALLOW: Record the finding for audit but take no enforcement action.
    """

    BLOCK = "block"
    REDACT = "redact"
    WARN = "warn"
    ALLOW = "allow"


@dataclass
class GuardResult:
    """Output produced by a single guard's scan() call.

    The pipeline stamps guard, engine, and latency_ms onto each result
    after scan() returns so guards themselves do not need to know their
    own name or timing.

    Attributes:
        passed: True if the guard found no issue; False if a policy
                finding was detected.
        action: The enforcement action. Guards set this to BLOCK by
                convention; the pipeline overrides it with the policy's
                configured action before the result is stored.
        detail: Human-readable description of the finding, included in
                audit logs and PolicyViolationError messages.
        confidence: Optional float in [0, 1] indicating detection
                    confidence. Populated by ML-based guards.
        latency_ms: Time taken by this guard's scan() call in milliseconds,
                    stamped by the pipeline after the call returns.
        guard: Name of the guard class, stamped by the pipeline.
        engine: Engine mode used ('classifier', 'llm', 'hybrid'), stamped
                by the pipeline from GuardConfig.
        redacted_text: The sanitised version of the scanned text, populated
                       by guards that support REDACT (e.g. PiiGuard).
    """

    passed: bool
    action: Action
    detail: str
    confidence: Optional[float] = None
    latency_ms: Optional[int] = None
    guard: Optional[str] = None
    engine: Optional[str] = None
    redacted_text: Optional[str] = None

    def to_dict(self) -> dict:
        """Serialise the result to a JSON-compatible dictionary.

        Returns:
            Dictionary with all fields except redacted_text (which is
            not included in audit records for privacy reasons).
        """
        return {
            "guard": self.guard,
            "engine": self.engine,
            "passed": self.passed,
            "action": self.action.value if self.action else None,
            "confidence": self.confidence,
            "detail": self.detail,
            "latency_ms": self.latency_ms,
        }


@dataclass
class RampartResponse:
    """The result returned to the caller after a successful Rampart.invoke() call.

    A response is only returned when no guard raised a BLOCK action.
    Warnings from WARN and REDACT actions are collected here for the
    caller to inspect or log.

    Attributes:
        text: The (potentially redacted) LLM response text.
        request_id: UUID assigned to this request, matching the audit log.
        warnings: List of non-blocking guard findings from both the input
                  and output pipelines.
    """

    text: str
    request_id: str
    warnings: List[GuardResult] = field(default_factory=list)
