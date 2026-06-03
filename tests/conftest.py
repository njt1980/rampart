import pytest


@pytest.fixture
def policy_yaml_content():
    return """\
version: "1.0.0"
description: "Test policy"
profiles:
  default:
    input:
      - guard: PiiGuard
        module: rampart.guards.pii
        engine: classifier
        action: block
        config:
          entities: [CREDIT_CARD]
    output:
      - guard: PiiGuard
        module: rampart.guards.pii
        engine: classifier
        action: redact
        config:
          entities: [CREDIT_CARD]
  minimal:
    input: []
    output: []
"""


@pytest.fixture
def policy_file(tmp_path, policy_yaml_content):
    path = tmp_path / "policy.yaml"
    path.write_text(policy_yaml_content, encoding="utf-8")
    return str(path)


@pytest.fixture
def policy_uri(policy_file):
    return f"file://{policy_file}"
