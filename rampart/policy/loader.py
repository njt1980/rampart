"""
rampart/policy/loader.py

Thread-safe policy loader that fetches and caches the active policy from
a configured registry. Supports on-disk YAML files (via FileRegistry) and
HTTP endpoints (via HttpRegistry) with optional background polling for
live policy reloads without restarting the application.
"""
from __future__ import annotations

import threading
from typing import Optional

from rampart.exceptions import PolicyLoadError
from rampart.policy.registry import BaseRegistry, create_registry
from rampart.policy.schema import Policy, ProfileConfig


class PolicyLoader:
    """Loads and caches a Rampart policy from a registry URI.

    The policy is fetched synchronously at construction time. For HTTP
    registries, a background daemon thread is started to poll for updates
    at the configured interval. All reads and writes to the cached policy
    are protected by an RLock so concurrent requests see a consistent view.

    Args:
        registry_uri: URI identifying the policy source. Supported schemes:
                      - ``file://./path/to/policy.yaml`` for local files.
                      - ``https://host/path`` for HTTP-served policies.
        reload_interval: Seconds between background reload checks for HTTP
                         registries. Set to 0 to disable polling.
    """

    def __init__(self, registry_uri: str, reload_interval: int = 300) -> None:
        self._registry: BaseRegistry = create_registry(registry_uri)
        self._policy: Optional[Policy] = None
        # RLock allows _on_reload to acquire the lock from the same thread
        # that holds it during _load (e.g. if a registry calls back inline).
        self._lock = threading.RLock()
        self._load()
        # Only start polling for HTTP registries — file registries do not
        # change between reads and do not benefit from background polling.
        if reload_interval > 0 and registry_uri.startswith("http"):
            self._registry.start_polling(reload_interval, self._on_reload)

    def _load(self) -> None:
        """Perform an initial synchronous policy load at construction time."""
        data = self._registry.load()
        with self._lock:
            self._policy = Policy(**data)

    def _on_reload(self, data: dict) -> None:
        """Callback invoked by the registry polling thread when new data arrives.

        Args:
            data: Raw policy dict parsed from the registry source.
        """
        with self._lock:
            self._policy = Policy(**data)

    @property
    def policy(self) -> Policy:
        """Return the currently cached Policy, thread-safely.

        Returns:
            The active Policy object.

        Raises:
            PolicyLoadError: If the policy has not been loaded yet.
                             Should not occur in practice since _load()
                             is called at construction time.
        """
        with self._lock:
            if self._policy is None:
                raise PolicyLoadError("Policy not loaded")
            return self._policy

    def get_profile(self, name: str) -> ProfileConfig:
        """Return the ProfileConfig for the named profile.

        Args:
            name: Profile name to look up.

        Returns:
            The ProfileConfig for the named profile.

        Raises:
            KeyError: If the profile name is not found in the policy.
        """
        policy = self.policy
        if name not in policy.profiles:
            raise KeyError(
                f"Profile {name!r} not found in policy {policy.version!r}. "
                f"Available profiles: {list(policy.profiles)}"
            )
        return policy.profiles[name]
