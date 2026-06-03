"""
rampart/policy/registry.py

Registry abstraction for policy sources. FileRegistry loads policy from
a local YAML file; HttpRegistry fetches from an HTTP endpoint with
ETag-based conditional requests and a background polling thread for
automatic policy refresh. create_registry() is the factory function
that selects the right implementation based on the URI scheme.
"""
from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, Optional

import requests
import yaml

from rampart.exceptions import PolicyLoadError


class BaseRegistry(ABC):
    """Abstract interface for a policy source.

    Implementations provide a load() method that returns a raw dict
    parsed from the policy YAML, and optionally start_polling() to
    register a background reload callback.
    """

    @abstractmethod
    def load(self) -> dict:
        """Fetch and parse the policy YAML from the source.

        Returns:
            Dict representation of the policy YAML document.

        Raises:
            PolicyLoadError: If the policy cannot be fetched or parsed.
        """
        ...

    def start_polling(self, interval: int, callback: Callable[[dict], None]) -> None:
        """Start a background thread that polls for policy updates.

        The default implementation is a no-op. Override in registries
        that support live updates (e.g. HttpRegistry).

        Args:
            interval: Polling interval in seconds.
            callback: Called with the new policy dict when a change is
                      detected. Must be thread-safe.
        """
        pass


class FileRegistry(BaseRegistry):
    """Loads a policy from a local YAML file.

    Args:
        uri: ``file://`` URI pointing to the policy YAML file.
             The ``file://`` prefix is stripped before resolving the path.
    """

    def __init__(self, uri: str) -> None:
        self.path = Path(uri.removeprefix("file://"))

    def load(self) -> dict:
        """Read and parse the policy YAML file from disk.

        Returns:
            Dict representation of the policy YAML document.

        Raises:
            PolicyLoadError: If the file does not exist or contains
                             invalid YAML.
        """
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise PolicyLoadError(f"Policy file not found: {self.path}")
        try:
            return yaml.safe_load(raw)
        except yaml.YAMLError as e:
            raise PolicyLoadError(f"Invalid YAML in policy file: {e}") from e


class HttpRegistry(BaseRegistry):
    """Fetches a policy from an HTTP or HTTPS endpoint.

    Uses ETag-based conditional GET requests to avoid re-downloading an
    unchanged policy. When start_polling() is called, a daemon thread
    polls the endpoint at the configured interval and invokes the callback
    only when a new policy version is detected.

    Args:
        url: HTTP or HTTPS URL of the policy YAML endpoint.
    """

    def __init__(self, url: str) -> None:
        self.url = url
        # ETag from the last successful fetch; sent as If-None-Match on
        # subsequent requests to avoid re-parsing an unchanged policy.
        self._etag: Optional[str] = None

    def load(self) -> dict:
        """Fetch and parse the policy YAML from the HTTP endpoint.

        Sends the stored ETag as If-None-Match to take advantage of
        server-side caching. If the server responds with 304 Not Modified,
        raises _NotModified to signal that the cached policy is still valid.

        Returns:
            Dict representation of the policy YAML document.

        Raises:
            PolicyLoadError: If the request fails or the response body
                             contains invalid YAML.
            _NotModified: If the server returns 304, indicating the
                          cached policy has not changed.
        """
        headers: dict[str, str] = {}
        if self._etag:
            headers["If-None-Match"] = self._etag
        try:
            response = requests.get(self.url, headers=headers, timeout=10)
        except requests.RequestException as e:
            raise PolicyLoadError(f"Failed to fetch policy from {self.url}: {e}") from e

        if response.status_code == 304:
            # Server confirmed the ETag matches — no new policy to parse.
            raise _NotModified

        try:
            response.raise_for_status()
        except requests.HTTPError as e:
            raise PolicyLoadError(f"HTTP error fetching policy from {self.url}: {e}") from e

        # Store the new ETag for the next conditional request.
        self._etag = response.headers.get("ETag")
        try:
            return yaml.safe_load(response.text)
        except yaml.YAMLError as e:
            raise PolicyLoadError(f"Invalid YAML from {self.url}: {e}") from e

    def start_polling(self, interval: int, callback: Callable[[dict], None]) -> None:
        """Start a daemon thread that polls the endpoint for policy changes.

        The thread runs for the lifetime of the process. On each poll,
        it calls load(). If load() returns new data the callback is
        invoked. If the server responds with 304 (or any other exception
        occurs) the cached policy is left unchanged.

        Args:
            interval: Seconds to sleep between poll attempts.
            callback: Invoked with the new policy dict when a change is
                      detected. Runs on the polling thread.
        """
        def _poll() -> None:
            while True:
                time.sleep(interval)
                try:
                    data = self.load()
                    callback(data)
                except (_NotModified, Exception):
                    # _NotModified: policy unchanged, nothing to do.
                    # Any other exception: swallow and retry next interval.
                    pass

        thread = threading.Thread(target=_poll, daemon=True)
        thread.start()


class _NotModified(Exception):
    """Raised internally by HttpRegistry when the server returns HTTP 304.

    Used as a control-flow signal to distinguish 'no change' from a
    genuine error without relying on status code inspection in the caller.
    """


def create_registry(uri: str) -> BaseRegistry:
    """Factory function that creates the appropriate registry for a URI.

    Args:
        uri: Policy source URI. Supported schemes: ``file://`` and
             ``http://`` / ``https://``.

    Returns:
        FileRegistry for ``file://`` URIs, HttpRegistry for HTTP(S) URIs.

    Raises:
        PolicyLoadError: If the URI scheme is not supported.
    """
    if uri.startswith("file://"):
        return FileRegistry(uri)
    if uri.startswith("http://") or uri.startswith("https://"):
        return HttpRegistry(uri)
    raise PolicyLoadError(f"Unsupported registry URI scheme: {uri!r}")
