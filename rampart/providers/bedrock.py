"""
rampart/providers/bedrock.py

AWS Bedrock provider implementation. Wraps the boto3 bedrock-runtime
Converse API to provide a standard Rampart provider interface. The AWS
client is created lazily on the first invoke() call to avoid failing at
Rampart construction time when the request might be blocked by guards
before the provider is ever called.
"""
from __future__ import annotations

from typing import Any, Optional

from rampart.exceptions import ProviderError
from rampart.providers.base import BaseProvider


class BedrockProvider(BaseProvider):
    """LLM provider backed by AWS Bedrock Converse API.

    Supports all Bedrock models that implement the Converse API
    (Claude, Titan, Llama, Mistral, etc.). The underlying boto3 client
    is created lazily on the first invoke() call.

    Args:
        region_name: AWS region for the bedrock-runtime endpoint.
                     Defaults to the region configured in the AWS
                     environment (AWS_DEFAULT_REGION or ~/.aws/config).
    """

    name = "bedrock"

    def __init__(self, region_name: Optional[str] = None) -> None:
        # Validate boto3 is available at construction time
        # but do not create the AWS client yet.
        try:
            import boto3
            self._boto3 = boto3
        except ImportError:
            raise ImportError(
                "boto3 is required for the Bedrock provider. "
                "Install with: pip install rampart[bedrock]"
            )
        self._region = region_name
        self._client = None  # created lazily on first invoke

    def invoke(self, model_id: str, messages: list, **kwargs) -> str:
        """Invoke a Bedrock model via the Converse API.

        Args:
            model_id: Bedrock model identifier, e.g.
                      ``"anthropic.claude-3-5-sonnet-20241022-v2:0"``.
            messages: List of message dicts with 'role' and 'content'
                      keys. String content is converted to Converse format
                      automatically.
            **kwargs:
                system (str): Optional system prompt text.
                max_tokens (int): Maximum tokens to generate. Default 1024.

        Returns:
            The model's text response as a plain string.

        Raises:
            ProviderError: If the Bedrock API call fails.
        """
        # Create the AWS client on first use to avoid eager credential
        # resolution when guards may block before the provider is needed.
        if self._client is None:
            self._client = self._boto3.client(
                "bedrock-runtime",
                region_name=self._region,
            )

        system_prompt: Optional[str] = kwargs.pop("system", None)
        max_tokens: int = kwargs.pop("max_tokens", 1024)

        request: dict[str, Any] = {
            "modelId": model_id,
            "messages": self._to_converse_messages(messages),
            "inferenceConfig": {"maxTokens": max_tokens},
        }
        if system_prompt:
            request["system"] = [{"text": system_prompt}]

        try:
            response = self._client.converse(**request)
        except Exception as e:
            raise ProviderError(f"Bedrock invoke failed for model {model_id!r}: {e}") from e

        return response["output"]["message"]["content"][0]["text"]

    @staticmethod
    def _to_converse_messages(messages: list) -> list:
        """Convert Rampart message format to Bedrock Converse format.

        Bedrock Converse requires content to be a list of content blocks
        rather than a plain string. This normalises string content to
        ``[{"text": "..."}]`` while leaving already-formatted content unchanged.

        Args:
            messages: List of message dicts in Rampart format.

        Returns:
            List of message dicts in Bedrock Converse format.
        """
        result = []
        for msg in messages:
            content = msg["content"]
            if isinstance(content, str):
                result.append({"role": msg["role"], "content": [{"text": content}]})
            else:
                result.append(msg)
        return result
