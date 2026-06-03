import pytest
from rampart.exceptions import PolicyLoadError
from rampart.policy.registry import FileRegistry, HttpRegistry, create_registry


def test_file_registry_load(tmp_path):
    f = tmp_path / "policy.yaml"
    f.write_text('version: "1.0.0"\nprofiles: {}\n', encoding="utf-8")
    registry = FileRegistry(f"file://{f}")
    data = registry.load()
    assert data["version"] == "1.0.0"


def test_file_registry_missing():
    registry = FileRegistry("file:///no/such/file.yaml")
    with pytest.raises(PolicyLoadError, match="not found"):
        registry.load()


def test_file_registry_invalid_yaml(tmp_path):
    f = tmp_path / "bad.yaml"
    f.write_text("{{{{not valid yaml", encoding="utf-8")
    registry = FileRegistry(f"file://{f}")
    with pytest.raises(PolicyLoadError, match="Invalid YAML"):
        registry.load()


def test_create_registry_file(tmp_path):
    f = tmp_path / "p.yaml"
    f.write_text('version: "1"\nprofiles: {}\n', encoding="utf-8")
    registry = create_registry(f"file://{f}")
    assert isinstance(registry, FileRegistry)


def test_create_registry_http():
    registry = create_registry("https://example.com/policy.yaml")
    assert isinstance(registry, HttpRegistry)


def test_create_registry_unsupported():
    with pytest.raises(PolicyLoadError, match="Unsupported"):
        create_registry("s3://bucket/policy.yaml")


def test_file_registry_strips_prefix(tmp_path):
    f = tmp_path / "policy.yaml"
    f.write_text('version: "2"\nprofiles: {}\n', encoding="utf-8")
    registry = FileRegistry(f"file://{f}")
    assert registry.path == f
