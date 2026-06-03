"""
rampart/providers/base.py

Abstract base class that all Rampart LLM providers must implement.
The interface is intentionally minimal: a class-level name attribute
and a single invoke() method that takes a model identifier, a messages
list, and optional keyword arguments, and returns the model's text
response as a plain string.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class BaseProvider(ABC):
    """Abstract base class for Rampart LLM providers.

    Implement this class to add support for a new LLM backend. Register
    the provider in ``rampart/providers/__init__.py`` by adding it to
    the registry dict in ``create_provider()``.

    Class attributes:
        name: Short identifier string for the provider. Must match the
              key used in the create_provider registry (e.g. 'bedrock').
    """

    name: str = "base"

    @abstractmethod
    def invoke(self, model_id: str, messages: list, **kwargs) -> str:
        """Send a chat request to the LLM and return the text response.

        Args:
            model_id: Provider-specific model identifier.
            messages: List of message dicts with 'role' and 'content'
                      keys in standard chat format.
            **kwargs: Provider-specific optional arguments (e.g. max_tokens,
                      system prompt, temperature).

        Returns:
            The model's text response as a plain string.

        Raises:
            ProviderError: If the provider API call fails.
        """
        ...
