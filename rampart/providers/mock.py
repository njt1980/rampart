"""
rampart/providers/mock.py

A mock LLM provider for testing and local development. Returns a
configurable static response without making any external API calls.
Never use in production.
"""
from rampart.providers.base import BaseProvider


class MockProvider(BaseProvider):
    """Mock provider that returns a static response.

    Use for testing the full Rampart client flow without requiring
    cloud provider credentials. Can also be used in local development
    environments to simulate LLM responses without API access.

    Args:
        response: The static text to return from invoke().
                  Defaults to a generic acknowledgement string.

    Example:
        client = Rampart(
            policy_registry="file://./policies/banking.yaml",
            provider="mock",
            app_id="my-app",
            provider_kwargs={"response": "Mock LLM response here"},
        )
    """

    name = "mock"

    def __init__(self, response: str = "This is a mock LLM response.") -> None:
        self._response = response

    def invoke(self, model_id: str, messages: list, **kwargs) -> str:
        """Return the configured static response.

        Args:
            model_id: Ignored. Present for interface compatibility.
            messages: Ignored. Present for interface compatibility.
            **kwargs: Ignored. Present for interface compatibility.

        Returns:
            The static response string configured at construction time.
        """
        return self._response
