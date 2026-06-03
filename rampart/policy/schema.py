"""
rampart/policy/schema.py

Pydantic models that define the structure of a Rampart policy YAML file.
A Policy contains a version string and a map of named profiles; each
profile declares an ordered list of GuardConfig objects for the input
and output pipelines.
"""
from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field

from rampart.models import Action


class GuardConfig(BaseModel):
    """Configuration for a single guard within a policy profile.

    Loaded from the guards list under a profile's input or output key.

    Attributes:
        guard: Guard class name (e.g. 'PiiGuard', 'PromptInjectionGuard').
               Must be importable from the module specified by module.
        module: Fully-qualified Python module path (e.g.
                'rampart.guards.pii'). Loaded via importlib at pipeline
                construction time.
        engine: Detection engine mode passed to the guard constructor.
                Standard values: 'classifier', 'llm', 'hybrid'.
        action: Enforcement action the pipeline should take when the
                guard fails. Overrides the guard's default action.
        config: Guard-specific configuration dict. Each guard defines its
                own recognised keys.
    """

    guard: str
    module: str
    engine: str = "classifier"
    action: Action = Action.BLOCK
    config: Dict[str, Any] = Field(default_factory=dict)


class ProfileConfig(BaseModel):
    """Configuration for a named policy profile.

    A profile groups the guards that run on input (user messages) and
    output (LLM responses) into separate ordered lists.

    Attributes:
        input: Ordered list of guards to run on user messages.
        output: Ordered list of guards to run on LLM responses.
    """

    input: List[GuardConfig] = Field(default_factory=list)
    output: List[GuardConfig] = Field(default_factory=list)


class Policy(BaseModel):
    """Top-level Rampart policy document.

    Parsed from the policy YAML by PolicyLoader. The version string is
    used by the Rampart client to detect when a background reload has
    fetched a new policy version and pipeline caches should be cleared.

    Attributes:
        version: Semver or date string identifying the policy revision.
        description: Optional human-readable description of the policy.
        profiles: Map of profile name to ProfileConfig. Each application
                  invocation selects one profile by name.
    """

    version: str
    description: str = ""
    profiles: Dict[str, ProfileConfig] = Field(default_factory=dict)
