from rampart.exceptions import PolicyLoadError, PolicyViolationError, ProviderError, RampartError
from rampart.models import Action, GuardResult


def test_rampart_error_is_exception():
    err = RampartError("something went wrong")
    assert isinstance(err, Exception)
    assert "something went wrong" in str(err)


def test_policy_violation_error_fields():
    violation = GuardResult(
        passed=False, action=Action.BLOCK, detail="PII detected", guard="PiiGuard"
    )
    err = PolicyViolationError(direction="input", violations=[violation], request_id="req-123")
    assert err.request_id == "req-123"
    assert err.direction == "input"
    assert err.violations == [violation]
    assert "input" in str(err)
    assert "PII detected" in str(err)


def test_policy_violation_error_default_request_id():
    err = PolicyViolationError(direction="output", violations=[])
    assert err.request_id == ""


def test_policy_violation_is_rampart_error():
    err = PolicyViolationError(direction="input", violations=[])
    assert isinstance(err, RampartError)


def test_policy_load_error_is_rampart_error():
    err = PolicyLoadError("bad yaml")
    assert isinstance(err, RampartError)


def test_provider_error_is_rampart_error():
    err = ProviderError("boto3 timeout")
    assert isinstance(err, RampartError)
