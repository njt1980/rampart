"""
rampart/guards/pii.py

PII detection and redaction guard backed by Microsoft Presidio. Scans
text for personally identifiable information and returns a redacted copy
using <REDACTED> placeholders. Entity types to detect are configurable
via the policy YAML; if omitted, Presidio's full default entity set is used.
"""
from __future__ import annotations

from typing import Any, Optional

from rampart.base_guard import BaseGuard
from rampart.models import Action, GuardResult


class PiiGuard(BaseGuard):
    """Detects and optionally redacts PII using Microsoft Presidio.

    Uses Presidio's AnalyzerEngine for detection and AnonymizerEngine for
    redaction. Both engines are loaded lazily on the first scan() call to
    avoid importing heavy ML dependencies at pipeline construction time.

    Supported config keys:
        entities (list[str]): Presidio entity types to detect, e.g.
            ``["CREDIT_CARD", "EMAIL_ADDRESS", "PHONE_NUMBER"]``.
            Omit or set to null to use Presidio's full default set.

    Args:
        config: Guard configuration dict from the policy YAML.
        engine: Detection engine mode. PiiGuard always uses Presidio
                regardless of this value; the attribute is stored for
                audit record consistency.
    """

    def __init__(self, config: Optional[dict] = None, engine: str = "classifier") -> None:
        super().__init__(config, engine)
        # Lazily loaded on first scan() call to defer heavy imports.
        self._analyzer: Any = None
        self._anonymizer: Any = None

    def _ensure_loaded(self) -> None:
        """Import and initialise Presidio engines on first use.

        Raises:
            ImportError: If presidio-analyzer or presidio-anonymizer are
                         not installed.
        """
        if self._analyzer is not None:
            return
        try:
            from presidio_analyzer import AnalyzerEngine
            from presidio_anonymizer import AnonymizerEngine
            from presidio_anonymizer.entities import OperatorConfig
        except ImportError:
            raise ImportError(
                "presidio-analyzer and presidio-anonymizer are required for PiiGuard. "
                "Install with: pip install presidio-analyzer presidio-anonymizer"
            )
        self._analyzer = AnalyzerEngine()
        self._anonymizer = AnonymizerEngine()
        # Store OperatorConfig class reference so scan() can use it without
        # re-importing on every call.
        self._OperatorConfig = OperatorConfig

    def scan(self, text: str, context: dict) -> GuardResult:
        """Scan text for PII entities using Presidio.

        If PII is detected, attempts to produce a redacted copy by replacing
        all detected entities with ``<REDACTED>``. The redacted text is
        stored in the result so the pipeline can substitute it when the
        policy action is REDACT.

        Args:
            text: Text to scan for PII.
            context: Request metadata dict (not used by PiiGuard directly).

        Returns:
            GuardResult with passed=True if no PII is found, or
            passed=False with the detected entity types and confidence
            score if PII is detected. redacted_text is populated on
            detection when anonymisation succeeds.
        """
        self._ensure_loaded()

        # entities=None tells Presidio to run its full default entity set.
        entities: Optional[list] = self.config.get("entities") or None
        results = self._analyzer.analyze(text=text, entities=entities, language="en")

        if not results:
            return GuardResult(passed=True, action=Action.ALLOW, detail="No PII detected")

        entity_types = sorted({r.entity_type for r in results})
        confidence = max(r.score for r in results)

        redacted_text: Optional[str] = None
        try:
            op_cls = getattr(self, "_OperatorConfig", None)
            kwargs: dict = {"text": text, "analyzer_results": results}
            if op_cls is not None:
                # Replace all detected entities with a uniform placeholder.
                kwargs["operators"] = {"DEFAULT": op_cls("replace", {"new_value": "<REDACTED>"})}
            anonymized = self._anonymizer.anonymize(**kwargs)
            redacted_text = anonymized.text
        except Exception:
            # Anonymisation failure is non-fatal — return the detection
            # result without a redacted copy so the pipeline can still block.
            pass

        return GuardResult(
            passed=False,
            action=Action.BLOCK,
            detail=f"PII detected: {entity_types}",
            confidence=confidence,
            redacted_text=redacted_text,
        )
