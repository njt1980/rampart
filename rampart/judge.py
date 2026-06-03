"""
rampart/judge.py

LLM-based binary judge used by guards operating in 'llm' or 'hybrid'
engine modes. LLMJudge wraps any configured Rampart provider into a
simple yes/no interface, enabling guards to escalate uncertain
classifier results to a language model for a final determination.
"""
from __future__ import annotations

from typing import Any

from rampart.providers import create_provider


class LLMJudge:
    """Wraps a provider into a simple yes/no interface for use by guards.

    Guards that support 'llm' or 'hybrid' engine modes receive an
    LLMJudge instance in their context dict. They call ask() with a
    natural language question; the judge appends a forced-format
    instruction and interprets the model's response as a boolean.

    Args:
        provider: Name of the Rampart provider to use (e.g. 'bedrock').
        model_id: Model identifier to pass to the provider's invoke().
                  Must be non-empty.
        max_tokens: Maximum tokens to generate. Kept small (default 100)
                    since the model only needs to output 'yes' or 'no'.
        **provider_kwargs: Additional keyword arguments forwarded to
                           create_provider().

    Raises:
        ValueError: If model_id is empty.
    """

    def __init__(self, provider: str, model_id: str, max_tokens: int = 100, **provider_kwargs: Any) -> None:
        if not model_id:
            raise ValueError("model_id is required for LLMJudge")
        self.model_id = model_id
        self.max_tokens = max_tokens
        self._provider = create_provider(provider, **provider_kwargs)

    def ask(self, question: str) -> bool:
        """Ask a yes/no question. Returns True if the LLM answers 'yes'.

        Appends a forced-format instruction to the question so the model
        returns only 'yes' or 'no'. The response is checked by stripping
        whitespace and comparing the lowercase prefix — robust to models
        that add trailing punctuation or capitalisation.

        Args:
            question: The yes/no question to pose to the LLM.

        Returns:
            True if the model's response starts with 'yes' (case-insensitive),
            False otherwise.
        """
        messages = [
            {
                "role": "user",
                "content": (
                    f"{question}\n\n"
                    "Answer with a single word: yes or no. No explanation."
                ),
            }
        ]
        response = self._provider.invoke(self.model_id, messages, max_tokens=self.max_tokens)
        return response.strip().lower().startswith("yes")
