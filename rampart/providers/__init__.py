"""
rampart/providers/__init__.py

Provider registry and factory for Rampart's pluggable LLM backends.
create_provider() maps provider name strings from the policy or client
constructor to concrete provider classes. Add new providers here after
implementing the BaseProvider interface.
"""
from __future__ import annotations

from rampart.providers.base import BaseProvider
from rampart.providers.bedrock import BedrockProvider
from rampart.providers.cortex import CortexProvider
from rampart.providers.mock import MockProvider

__all__ = ["BaseProvider", "BedrockProvider", "CortexProvider", "MockProvider", "create_provider"]


def create_provider(name: str, **kwargs) -> BaseProvider:
    """Instantiate a provider by name.

    Args:
        name: Provider identifier string. Supported values: 'bedrock',
              'cortex', 'mock'.
        **kwargs: Constructor keyword arguments forwarded to the provider
                  class (e.g. ``region_name`` for BedrockProvider,
                  ``response`` for MockProvider).

    Returns:
        Configured BaseProvider instance.

    Raises:
        ValueError: If the provider name is not registered.
    """
    registry = {
        "bedrock": BedrockProvider,
        "cortex": CortexProvider,
        "mock": MockProvider,
    }
    if name not in registry:
        raise ValueError(
            f"Unknown provider {name!r}. Supported providers: {list(registry)}"
        )
    return registry[name](**kwargs)
