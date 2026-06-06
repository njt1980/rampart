"""
rampart/guards/_prompt_injection_classifier.py

Local DeBERTa-based prompt-injection classifier used by PromptInjectionGuard
in 'classifier' and 'hybrid' engine modes.

PromptInjectionGuard previously delegated to llm_guard.input_scanners.
PromptInjection, constructed with its defaults (the v2 model, MatchType.FULL,
internal threshold 0.92). That scanner is a thin wrapper around `transformers`
— the chunking/sentence-splitting match types it also supports are never
exercised at those defaults. This module ports just the FULL-match code path
directly against `transformers`, so the same model, inputs, and scoring
formula produce identical results without depending on llm-guard, whose
pinned transitive requirements (fuzzysearch, regex, FlagEmbedding) have no
Python 3.13 wheels.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Tuple

MODEL_PATH = "protectai/deberta-v3-base-prompt-injection-v2"
MODEL_REVISION = "89b085cd330414d3e7d9dd787870f315957e1e9f"

# llm_guard.input_scanners.PromptInjection defaults to threshold=0.92 when
# constructed with no arguments, as PromptInjectionGuard does. That internal
# threshold (not the policy's configured one) decides is_valid/risk_score,
# which PromptInjectionGuard then re-checks against the policy threshold —
# both numbers participate in the final decision, so this must match
# llm-guard's default for results to stay identical.
INTERNAL_THRESHOLD = 0.92


@lru_cache(maxsize=None)
def _device():
    import torch

    if torch.cuda.is_available():
        return torch.device("cuda:0")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def _calculate_risk_score(score: float, threshold: float) -> float:
    """Maps a [0, 1] classifier score to a [-1, 1] risk score around `threshold`.

    Ported from llm_guard.util.calculate_risk_score so identical inputs
    produce identical outputs.
    """
    if score > threshold:
        risk_score = (score - threshold) / (1 - threshold)
    else:
        risk_score = (score - threshold) / threshold

    return min(max(round(risk_score, 1), -1), 1)


class PromptInjectionClassifier:
    """Thin wrapper around the DeBERTa-v3 prompt-injection model.

    Mirrors the single code path llm_guard.input_scanners.PromptInjection
    takes at its defaults (MatchType.FULL): the prompt is classified whole,
    in one pass — no chunking or sentence-splitting, which are dead code at
    those defaults and intentionally not ported.
    """

    def __init__(self) -> None:
        import transformers

        tokenizer = transformers.AutoTokenizer.from_pretrained(
            MODEL_PATH, revision=MODEL_REVISION
        )
        model = transformers.AutoModelForSequenceClassification.from_pretrained(
            MODEL_PATH, revision=MODEL_REVISION
        )
        self._pipeline = transformers.pipeline(
            "text-classification",
            model=model,
            tokenizer=tokenizer,
            return_token_type_ids=False,
            max_length=512,
            truncation=True,
            batch_size=1,
            device=_device(),
        )

    def scan(self, prompt: str) -> Tuple[str, bool, float]:
        """Returns (prompt, is_valid, risk_score) — the same contract llm-guard's
        PromptInjection.scan() returns, so PromptInjectionGuard needs no changes
        beyond how this scanner is constructed."""
        if prompt.strip() == "":
            return prompt, True, -1.0

        result = self._pipeline([prompt])[0]
        injection_score = round(
            result["score"] if result["label"] == "INJECTION" else 1 - result["score"],
            2,
        )

        is_valid = injection_score <= INTERNAL_THRESHOLD
        return prompt, is_valid, _calculate_risk_score(injection_score, INTERNAL_THRESHOLD)
