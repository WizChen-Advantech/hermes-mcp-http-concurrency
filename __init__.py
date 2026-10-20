"""Let MCP calls to HTTP servers run in parallel.

Hermes gives every MCP server one ``asyncio.Lock`` (``MCPServerTask._rpc_lock``)
and holds it for the whole ``tools/call``. In the gateway every session shares
that one server object, so one person's 60-second tool call makes everybody
else's tool calls wait. The lock exists for stdio, where requests share a single
JSON-RPC stream; over Streamable HTTP each request has its own id and the
server can answer them in any order.

This plugin replaces each server's lock with one that still locks for stdio and
does nothing for HTTP. It patches the class, for servers connected after the
plugin loads, and the servers already connected.

If a Hermes release renames what this relies on, the plugin logs one warning and
changes nothing; Hermes then behaves exactly as without it.
"""

from __future__ import annotations

import contextvars
import logging
import os
import threading
import time
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

_MARK = "_mcp_http_concurrency_patched"
# The first calls after start-up are logged with how many HTTP calls were in
# flight at that moment, so "did they really run together?" can be answered
# from the gateway log. Then it goes quiet.
_TRACE_CALLS = 60
_trace_lock = threading.Lock()
_trace = {"seen": 0, "in_flight": 0}
# Each call runs in its own asyncio task, so its start time is per call here,
# not on the lock object every session shares.
_call_started: contextvars.ContextVar[float] = contextvars.ContextVar("mcp_http_call_started")


def _trace_enter(server_name: str) -> float:
    with _trace_lock:
        _trace["in_flight"] += 1
        _trace["seen"] += 1
        seen, in_flight = _trace["seen"], _trace["in_flight"]
    if seen <= _TRACE_CALLS:
        logger.info("mcp-http-concurrency: call #%d to %s starts, %d HTTP call(s) in flight",
                    seen, server_name, in_flight)
    return time.monotonic()


def _trace_exit(server_name: str, started: float) -> None:
    with _trace_lock:
        _trace["in_flight"] -= 1
        seen = _trace["seen"]
    if seen <= _TRACE_CALLS:
        logger.info("mcp-http-concurrency: a call to %s ended after %.1fs",
                    server_name, time.monotonic() - started)


def _environment() -> str:
    """Versions and proxy hosts (never credentials), for reading the log."""
    parts = []
    try:
        from importlib.metadata import version
        for dist in ("hermes-agent", "mcp", "httpx"):
            try:
                parts.append(f"{dist}={version(dist)}")
            except Exception:  # noqa: BLE001
                parts.append(f"{dist}=?")
    except Exception:  # noqa: BLE001
        pass
    for name in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY"):
        value = os.environ.get(name)
        if value:
            host = urlsplit(value if "://" in value else f"http://{value}")
            parts.append(f"{name}={host.hostname}:{host.port or ''}")
    if os.environ.get("NO_PROXY") or os.environ.get("no_proxy"):
        parts.append("NO_PROXY=set")
    return " ".join(parts)


class _HttpAwareLock:
    """The server's own lock for stdio; never waits for HTTP.

    Whether a server is HTTP is read on every entry from its config ("url" set),
    which does not change while it runs, so entry and exit always agree.
    """

    def __init__(self, server, lock):
        self._server = server
        self._lock = lock

    def _http(self) -> bool:
        try:
            return bool(self._server._is_http())
        except Exception:  # noqa: BLE001 - unknown shape: behave like the real lock
            return False

    async def __aenter__(self):
        if not self._http():
            await self._lock.acquire()
        else:
            _call_started.set(_trace_enter(getattr(self._server, "name", "?")))
        return None

    async def __aexit__(self, exc_type, exc, tb):
        if not self._http():
            self._lock.release()
        else:
            _trace_exit(getattr(self._server, "name", "?"), _call_started.get(time.monotonic()))
        return False

    def locked(self) -> bool:
        return self._lock.locked()


def _wrap(server) -> bool:
    lock = getattr(server, "_rpc_lock", None)
    if lock is None or isinstance(lock, _HttpAwareLock):
        return False
    server._rpc_lock = _HttpAwareLock(server, lock)
    return True


def apply() -> bool:
    """Patch Hermes's MCP client. True when the patch is in place."""
    try:
        from tools import mcp_tool
    except Exception as exc:  # noqa: BLE001
        logger.warning("mcp-http-concurrency: cannot import tools.mcp_tool (%s); not applied", exc)
        return False
    task_class = getattr(mcp_tool, "MCPServerTask", None)
    if task_class is None or not hasattr(task_class, "_is_http"):
        logger.warning("mcp-http-concurrency: this Hermes has no MCPServerTask._is_http; "
                       "not applied")
        return False
    if not getattr(task_class, _MARK, False):
        original_init = task_class.__init__

        def __init__(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            _wrap(self)

        task_class.__init__ = __init__
        setattr(task_class, _MARK, True)
    wrapped = []
    with mcp_tool._lock:
        servers = dict(getattr(mcp_tool, "_servers", {}))
    for name, server in servers.items():
        if _wrap(server):
            wrapped.append(name)
    logger.info("mcp-http-concurrency: HTTP MCP calls run in parallel "
                "(already connected: %s; %s)", ", ".join(wrapped) or "none", _environment())
    return True


def register(ctx) -> None:
    apply()
