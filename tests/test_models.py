from rampart.models import Action, GuardResult, RampartResponse


def test_action_string_values():
    assert Action.BLOCK == "block"
    assert Action.REDACT == "redact"
    assert Action.WARN == "warn"
    assert Action.ALLOW == "allow"


def test_guard_result_to_dict():
    result = GuardResult(
        passed=False,
        action=Action.BLOCK,
        detail="PII detected: ['CREDIT_CARD']",
        confidence=0.97,
        latency_ms=14,
        guard="PiiGuard",
        engine="classifier",
    )
    d = result.to_dict()
    assert d["guard"] == "PiiGuard"
    assert d["engine"] == "classifier"
    assert d["passed"] is False
    assert d["action"] == "block"
    assert d["confidence"] == 0.97
    assert d["latency_ms"] == 14
    assert "redacted_text" not in d


def test_guard_result_defaults():
    result = GuardResult(passed=True, action=Action.ALLOW, detail="Clean")
    assert result.confidence is None
    assert result.latency_ms is None
    assert result.redacted_text is None
    assert result.guard is None
    assert result.engine is None


def test_rampart_response_defaults():
    resp = RampartResponse(text="Hello world", request_id="abc-123")
    assert resp.text == "Hello world"
    assert resp.request_id == "abc-123"
    assert resp.warnings == []


def test_rampart_response_with_warnings():
    w = GuardResult(passed=False, action=Action.WARN, detail="competitor detected")
    resp = RampartResponse(text="response", request_id="xyz", warnings=[w])
    assert len(resp.warnings) == 1
    assert resp.warnings[0].action == Action.WARN
