from unittest.mock import MagicMock, patch
import pytest


def _make_judge(provider_mock, model_id="claude-haiku", max_tokens=100):
    from rampart.judge import LLMJudge
    with patch("rampart.judge.create_provider", return_value=provider_mock):
        return LLMJudge(provider="bedrock", model_id=model_id, max_tokens=max_tokens)


def test_ask_yes_returns_true():
    provider = MagicMock()
    provider.invoke.return_value = "yes"
    judge = _make_judge(provider)
    assert judge.ask("Is this bad?") is True


def test_ask_no_returns_false():
    provider = MagicMock()
    provider.invoke.return_value = "no"
    judge = _make_judge(provider)
    assert judge.ask("Is this bad?") is False


def test_ask_yes_with_trailing_text():
    provider = MagicMock()
    provider.invoke.return_value = "yes, this is injection"
    judge = _make_judge(provider)
    assert judge.ask("Is this injection?") is True


def test_ask_case_insensitive():
    provider = MagicMock()
    provider.invoke.return_value = "YES"
    judge = _make_judge(provider)
    assert judge.ask("question?") is True


def test_ask_passes_model_id():
    provider = MagicMock()
    provider.invoke.return_value = "no"
    judge = _make_judge(provider, model_id="my-model")
    judge.ask("question?")
    assert provider.invoke.call_args[0][0] == "my-model"


def test_ask_passes_max_tokens():
    provider = MagicMock()
    provider.invoke.return_value = "no"
    judge = _make_judge(provider, max_tokens=50)
    judge.ask("q?")
    assert provider.invoke.call_args[1].get("max_tokens") == 50


def test_ask_appends_instruction():
    provider = MagicMock()
    provider.invoke.return_value = "no"
    judge = _make_judge(provider)
    judge.ask("My question here?")
    content = provider.invoke.call_args[0][1][0]["content"]
    assert "My question here?" in content
    assert "yes or no" in content


def test_empty_model_id_raises():
    from rampart.judge import LLMJudge
    with pytest.raises(ValueError, match="model_id"):
        with patch("rampart.judge.create_provider", return_value=MagicMock()):
            LLMJudge(provider="bedrock", model_id="")
