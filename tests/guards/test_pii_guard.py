from unittest.mock import MagicMock, patch
import pytest
from rampart.models import Action


def _make_guard(entities=None):
    from rampart.guards.pii import PiiGuard
    guard = PiiGuard(config={"entities": entities or ["CREDIT_CARD"]})
    guard._analyzer = MagicMock()
    guard._anonymizer = MagicMock()
    return guard


def test_no_pii_detected():
    guard = _make_guard()
    guard._analyzer.analyze.return_value = []

    result = guard.scan("Hello, how can I help you today?", {})

    assert result.passed is True
    assert result.action == Action.ALLOW
    assert result.detail == "No PII detected"


def test_pii_detected_returns_fail():
    guard = _make_guard()

    mock_finding = MagicMock()
    mock_finding.entity_type = "CREDIT_CARD"
    mock_finding.score = 0.97
    guard._analyzer.analyze.return_value = [mock_finding]

    mock_anon = MagicMock()
    mock_anon.text = "My card is <REDACTED>"
    guard._anonymizer.anonymize.return_value = mock_anon
    guard._OperatorConfig = MagicMock()  # simulate presidio available

    result = guard.scan("My credit card is 4111 1111 1111 1111", {})

    assert result.passed is False
    assert result.action == Action.BLOCK
    assert "CREDIT_CARD" in result.detail
    assert result.confidence == 0.97
    assert result.redacted_text == "My card is <REDACTED>"


def test_multiple_entity_types():
    guard = _make_guard(entities=["CREDIT_CARD", "EMAIL_ADDRESS"])

    cc = MagicMock()
    cc.entity_type = "CREDIT_CARD"
    cc.score = 0.95
    email = MagicMock()
    email.entity_type = "EMAIL_ADDRESS"
    email.score = 0.88
    guard._analyzer.analyze.return_value = [cc, email]

    mock_anon = MagicMock()
    mock_anon.text = "<REDACTED> <REDACTED>"
    guard._anonymizer.anonymize.return_value = mock_anon

    result = guard.scan("Card 4111..., email foo@bar.com", {})

    assert result.passed is False
    assert "CREDIT_CARD" in result.detail
    assert "EMAIL_ADDRESS" in result.detail
    assert result.confidence == 0.95  # max score


def test_redacted_text_none_on_anonymizer_error():
    guard = _make_guard()

    mock_finding = MagicMock()
    mock_finding.entity_type = "CREDIT_CARD"
    mock_finding.score = 0.9
    guard._analyzer.analyze.return_value = [mock_finding]
    guard._anonymizer.anonymize.side_effect = Exception("anonymizer failure")

    result = guard.scan("card 4111 1111 1111 1111", {})

    assert result.passed is False
    assert result.redacted_text is None


def test_engine_stored():
    from rampart.guards.pii import PiiGuard
    guard = PiiGuard(config={}, engine="classifier")
    assert guard.engine == "classifier"
