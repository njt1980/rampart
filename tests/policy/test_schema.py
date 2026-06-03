import pytest
from rampart.models import Action
from rampart.policy.schema import GuardConfig, Policy, ProfileConfig


def test_guard_config_defaults():
    gc = GuardConfig(guard="PiiGuard", module="rampart.guards.pii")
    assert gc.engine == "classifier"
    assert gc.action == Action.BLOCK
    assert gc.config == {}


def test_guard_config_custom():
    gc = GuardConfig(
        guard="PiiGuard",
        module="rampart.guards.pii",
        engine="hybrid",
        action=Action.REDACT,
        config={"entities": ["CREDIT_CARD"]},
    )
    assert gc.engine == "hybrid"
    assert gc.action == Action.REDACT
    assert gc.config["entities"] == ["CREDIT_CARD"]


def test_profile_config_defaults():
    pc = ProfileConfig()
    assert pc.input == []
    assert pc.output == []


def test_policy_minimal():
    policy = Policy(version="1.0.0", profiles={})
    assert policy.version == "1.0.0"
    assert policy.description == ""
    assert policy.profiles == {}


def test_policy_full_parse():
    data = {
        "version": "1.0.0",
        "description": "Banking policy",
        "profiles": {
            "customer_support": {
                "input": [
                    {
                        "guard": "PiiGuard",
                        "module": "rampart.guards.pii",
                        "action": "block",
                        "config": {"entities": ["CREDIT_CARD", "AADHAAR"]},
                    },
                    {
                        "guard": "PromptInjectionGuard",
                        "module": "rampart.guards.prompt_injection",
                        "action": "block",
                        "config": {"threshold": 0.8},
                    },
                ],
                "output": [
                    {
                        "guard": "PiiGuard",
                        "module": "rampart.guards.pii",
                        "action": "redact",
                        "config": {"entities": ["CREDIT_CARD"]},
                    }
                ],
            },
            "internal_analyst": {
                "input": [
                    {
                        "guard": "PromptInjectionGuard",
                        "module": "rampart.guards.prompt_injection",
                        "action": "block",
                        "config": {"threshold": 0.9},
                    }
                ]
            },
        },
    }
    policy = Policy(**data)
    assert policy.version == "1.0.0"
    assert "customer_support" in policy.profiles
    assert "internal_analyst" in policy.profiles

    cs = policy.profiles["customer_support"]
    assert len(cs.input) == 2
    assert len(cs.output) == 1
    assert cs.input[0].guard == "PiiGuard"
    assert cs.input[0].action == Action.BLOCK
    assert cs.output[0].action == Action.REDACT

    ia = policy.profiles["internal_analyst"]
    assert len(ia.input) == 1
    assert ia.output == []
