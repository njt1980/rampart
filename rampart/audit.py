"""
rampart/audit.py

Structured audit logging for Rampart. Every guard pipeline execution
produces a JSON audit record written to stdout (or a configurable IO
stream). Audit records are designed for ingestion into SIEM systems
and include the full set of guard decisions and timing metadata.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import IO, List, Optional

from rampart.models import GuardResult


class AuditLogger:
    """Writes structured JSON audit records for each pipeline execution.

    Each call to log() emits one newline-delimited JSON record. Records
    are flushed immediately so that audit trails are not lost on crash.

    Args:
        output: IO stream to write records to. Defaults to sys.stdout.
                Pass a file handle or StringIO for testing or file-based
                audit log collection.
    """

    def __init__(self, output: Optional[IO[str]] = None) -> None:
        self._output = output or sys.stdout

    def log(
        self,
        *,
        request_id: str,
        app_id: str,
        policy_version: str,
        profile: str,
        provider: str,
        model_id: str,
        direction: str,
        guard_results: List[GuardResult],
        final_decision: str,
        total_latency_ms: int,
        timestamp: Optional[str] = None,
    ) -> None:
        """Emit a JSON audit record for a single pipeline execution.

        Args:
            request_id: UUID for the request, used to correlate input
                        and output audit records.
            app_id: Identifier for the calling application.
            policy_version: Version string of the policy active at the
                            time of the request.
            profile: Name of the policy profile that was applied.
            provider: Name of the LLM provider (e.g. 'bedrock', 'cortex').
            model_id: Model identifier passed to the provider.
            direction: 'input' or 'output', indicating which pipeline ran.
            guard_results: List of GuardResult objects from all guards
                           that ran in this pipeline execution.
            final_decision: Summary outcome string: 'allowed', 'blocked',
                            'redacted', or 'warned'.
            total_latency_ms: Total wall-clock time for the pipeline run
                              in milliseconds.
            timestamp: ISO-8601 UTC timestamp string. Defaults to now if
                       not provided.
        """
        record = {
            "request_id": request_id,
            "timestamp": timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "app_id": app_id,
            "policy_version": policy_version,
            "profile": profile,
            "provider": provider,
            "model_id": model_id,
            "direction": direction,
            "guard_results": [r.to_dict() for r in guard_results],
            "final_decision": final_decision,
            "total_latency_ms": total_latency_ms,
        }
        print(json.dumps(record), file=self._output, flush=True)
