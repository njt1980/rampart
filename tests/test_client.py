from unittest.mock import MagicMock, patch
import pytest
from rampart.exceptions import PolicyViolationError
from rampart.models import Action, GuardResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_client(policy_uri, provider_mock):
    from rampart.client import Rampart
    with patch("rampart.client.create_provider", return_value=provider_mock):
        client = Rampart(
            policy_registry=policy_uri,
            provider="bedrock",
            app_id="test-app",
            reload_interval=0,
        )
    return client


def _make_provider(response_text: str = "LLM response"):
    provider = MagicMock()
    provider.name = "bedrock"
    provider.invoke.return_value = response_text
    return provider


def _make_pass_pipeline():
    pipeline = MagicMock()
    pipeline.run.return_value = ("input text", [], [], 10)
    return pipeline


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_successful_invoke(policy_uri):
    provider = _make_provider("Hello from LLM")
    client = _make_client(policy_uri, provider)

    # Patch pipelines to bypass real guard loading
    pass_pipeline = MagicMock()
    pass_pipeline.run.side_effect = [
        ("user message", [], [], 5),   # input pipeline
        ("Hello from LLM", [], [], 3), # output pipeline
    ]
    client._get_pipeline = MagicMock(return_value=pass_pipeline)

    response = client.invoke(
        model_id="anthropic.claude-sonnet-4-6",
        messages=[{"role": "user", "content": "user message"}],
        profile="minimal",
    )

    assert response.text == "Hello from LLM"
    assert response.request_id
    assert response.warnings == []
    provider.invoke.assert_called_once()


def test_input_block_raises_policy_violation(policy_uri):
    provider = _make_provider()
    client = _make_client(policy_uri, provider)

    violation = GuardResult(passed=False, action=Action.BLOCK, detail="PII detected")
    block_pipeline = MagicMock()
    block_pipeline.run.side_effect = PolicyViolationError(
        direction="input", violations=[violation]
    )
    pass_pipeline = MagicMock()
    pass_pipeline.run.return_value = ("text", [], [], 0)

    def get_pipeline(profile, direction, policy):
        return block_pipeline if direction == "input" else pass_pipeline

    client._get_pipeline = get_pipeline

    with pytest.raises(PolicyViolationError) as exc_info:
        client.invoke(
            model_id="anthropic.claude-sonnet-4-6",
            messages=[{"role": "user", "content": "my card is 4111 1111 1111 1111"}],
            profile="default",
        )

    err = exc_info.value
    assert err.direction == "input"
    assert err.request_id != ""
    provider.invoke.assert_not_called()


def test_output_block_raises_policy_violation(policy_uri):
    provider = _make_provider("Response with 4111 1111 1111 1111")
    client = _make_client(policy_uri, provider)

    violation = GuardResult(passed=False, action=Action.BLOCK, detail="PII in output")
    input_pipeline = MagicMock()
    input_pipeline.run.return_value = ("user msg", [], [], 5)
    output_pipeline = MagicMock()
    output_pipeline.run.side_effect = PolicyViolationError(
        direction="output", violations=[violation]
    )

    def get_pipeline(profile, direction, policy):
        return input_pipeline if direction == "input" else output_pipeline

    client._get_pipeline = get_pipeline

    with pytest.raises(PolicyViolationError) as exc_info:
        client.invoke(
            model_id="anthropic.claude-sonnet-4-6",
            messages=[{"role": "user", "content": "user msg"}],
            profile="default",
        )

    assert exc_info.value.direction == "output"


def test_warnings_collected(policy_uri):
    provider = _make_provider("response")
    client = _make_client(policy_uri, provider)

    warn_result = GuardResult(passed=False, action=Action.WARN, detail="competitor mention")
    input_pipeline = MagicMock()
    input_pipeline.run.return_value = ("user msg", [warn_result], [warn_result], 5)
    output_pipeline = MagicMock()
    output_pipeline.run.return_value = ("response", [], [], 3)

    def get_pipeline(profile, direction, policy):
        return input_pipeline if direction == "input" else output_pipeline

    client._get_pipeline = get_pipeline

    response = client.invoke(
        model_id="anthropic.claude-sonnet-4-6",
        messages=[{"role": "user", "content": "user msg"}],
        profile="default",
    )

    assert len(response.warnings) == 1
    assert response.warnings[0].action == Action.WARN


def test_extract_last_user_text_string():
    from rampart.client import Rampart
    messages = [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "reply"},
        {"role": "user", "content": "second"},
    ]
    assert Rampart._extract_last_user_text(messages) == "second"


def test_extract_last_user_text_list_content():
    from rampart.client import Rampart
    messages = [{"role": "user", "content": [{"text": "hello"}, {"text": " world"}]}]
    assert Rampart._extract_last_user_text(messages) == "hello  world"


def test_update_last_user_text_replaces():
    from rampart.client import Rampart
    messages = [{"role": "user", "content": "original"}]
    updated = Rampart._update_last_user_text(messages, "original", "redacted")
    assert updated[0]["content"] == "redacted"
    # original list not mutated
    assert messages[0]["content"] == "original"


def test_update_last_user_text_no_change():
    from rampart.client import Rampart
    messages = [{"role": "user", "content": "same"}]
    result = Rampart._update_last_user_text(messages, "same", "same")
    assert result is messages  # returns original list unchanged
