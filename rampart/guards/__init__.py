"""
rampart/guards/__init__.py

Re-exports the built-in Rampart guards. Additional custom guards can be
registered by pointing GuardConfig.module at any importable Python module
containing a class that extends BaseGuard.
"""
from rampart.guards.pii import PiiGuard
from rampart.guards.prompt_injection import PromptInjectionGuard

__all__ = ["PiiGuard", "PromptInjectionGuard"]
