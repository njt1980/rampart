import pytest
from rampart.policy.loader import PolicyLoader


def test_loader_loads_policy(policy_uri):
    loader = PolicyLoader(policy_uri, reload_interval=0)
    assert loader.policy.version == "1.0.0"


def test_loader_get_profile(policy_uri):
    loader = PolicyLoader(policy_uri, reload_interval=0)
    profile = loader.get_profile("default")
    assert len(profile.input) == 1
    assert profile.input[0].guard == "PiiGuard"


def test_loader_missing_profile(policy_uri):
    loader = PolicyLoader(policy_uri, reload_interval=0)
    with pytest.raises(KeyError, match="nonexistent"):
        loader.get_profile("nonexistent")


def test_loader_minimal_profile(policy_uri):
    loader = PolicyLoader(policy_uri, reload_interval=0)
    profile = loader.get_profile("minimal")
    assert profile.input == []
    assert profile.output == []
