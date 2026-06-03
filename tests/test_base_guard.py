import pytest
from rampart.base_guard import BaseGuard
from rampart.models import Action, GuardResult


class _ConcreteGuard(BaseGuard):
    def scan(self, text: str, context: dict) -> GuardResult:
        if "bad" in text:
            return GuardResult(passed=False, action=Action.BLOCK, detail="bad word found")
        return GuardResult(passed=True, action=Action.ALLOW, detail="clean")


def test_config_default():
    guard = _ConcreteGuard()
    assert guard.config == {}


def test_config_passed():
    guard = _ConcreteGuard(config={"threshold": 0.9})
    assert guard.config["threshold"] == 0.9


def test_engine_default():
    guard = _ConcreteGuard()
    assert guard.engine == "classifier"


def test_engine_custom():
    guard = _ConcreteGuard(engine="hybrid")
    assert guard.engine == "hybrid"


def test_scan_pass():
    guard = _ConcreteGuard()
    result = guard.scan("hello world", {})
    assert result.passed is True
    assert result.action == Action.ALLOW


def test_scan_fail():
    guard = _ConcreteGuard()
    result = guard.scan("bad request", {})
    assert result.passed is False
    assert result.action == Action.BLOCK


def test_abstract_cannot_instantiate():
    with pytest.raises(TypeError):
        BaseGuard()  # type: ignore[abstract]
