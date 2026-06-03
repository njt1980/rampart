"""
rampart/providers/cortex.py

Snowflake Cortex provider implementation. Uses the Snowflake Cortex
Complete function to route requests to Cortex-hosted models (Llama,
Mistral, Arctic, etc.). The Snowflake session is created lazily on
the first invoke() call to keep Rampart construction fast and avoid
requiring Snowflake credentials when guards may block before the
provider is reached.
"""
from __future__ import annotations

from rampart.exceptions import ProviderError
from rampart.providers.base import BaseProvider


class CortexProvider(BaseProvider):
    """LLM provider backed by Snowflake Cortex Complete.

    Supports Cortex-hosted models. A Snowflake session is either supplied
    directly (for use in Streamlit or Snowpark contexts) or created lazily
    on the first invoke() call via Session.builder.getOrCreate().

    Args:
        session: An existing ``snowflake.snowpark.Session`` to reuse.
                 When ``None``, the session is obtained lazily on the
                 first invoke() call.
    """

    name = "cortex"

    def __init__(self, session=None) -> None:
        if session is not None:
            # Use the caller-supplied session directly; no library import needed.
            self._session = session
            return
        # Validate the optional dependency is installed without building
        # the session yet — session creation is deferred to first invoke.
        try:
            from snowflake.snowpark import Session
            self._Session = Session
        except ImportError:
            raise ImportError(
                "snowflake-snowpark-python is required for the Cortex provider. "
                "Install with: pip install rampart[cortex]"
            )
        self._session = None  # created lazily on first invoke

    def invoke(self, model_id: str, messages: list, **kwargs) -> str:
        """Invoke a Snowflake Cortex model.

        Args:
            model_id: Cortex model name, e.g. ``"llama3.1-70b"``
                      or ``"mistral-large"``.
            messages: List of message dicts with 'role' and 'content'
                      keys in Cortex Complete format.
            **kwargs: Additional keyword arguments passed through to
                      ``Complete``.

        Returns:
            The model's text response as a plain string.

        Raises:
            ProviderError: If the Cortex Complete call fails.
            ImportError: If snowflake-ml-python is not installed.
        """
        try:
            from snowflake.cortex import Complete
        except ImportError:
            raise ImportError(
                "snowflake-ml-python is required for the Cortex provider. "
                "Install with: pip install rampart[cortex]"
            )
        # Build the Snowflake session lazily on first use.
        if self._session is None:
            self._session = self._Session.builder.getOrCreate()
        try:
            return Complete(model=model_id, messages=messages, session=self._session)
        except Exception as e:
            raise ProviderError(f"Cortex invoke failed for model {model_id!r}: {e}") from e
