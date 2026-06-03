"""
rampart/__init__.py

Public API surface for the Rampart package. Import Rampart, BaseGuard,
and the response/error types from here — internal implementation modules
(pipeline, audit, policy, providers) are not part of the public API.
"""
from rampart.base_guard import BaseGuard
from rampart.client import Rampart
from rampart.exceptions import PolicyViolationError, RampartError
from rampart.models import Action, GuardResult, RampartResponse

__version__ = "0.1.1"

__all__ = [
    "Rampart",
    "BaseGuard",
    "GuardResult",
    "Action",
    "RampartResponse",
    "PolicyViolationError",
    "RampartError",
]
