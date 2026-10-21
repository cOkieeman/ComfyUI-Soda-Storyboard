from __future__ import annotations

import asyncio
import importlib
import sys
from types import ModuleType, SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize(
    ("remote", "host", "origin", "expected"),
    [
        ("127.0.0.1", "127.0.0.1:8188", "http://127.0.0.1:8188", True),
        ("::1", "[::1]:8188", "http://[::1]:8188", True),
        ("::ffff:127.0.0.1", "localhost:8188", None, True),
        ("192.168.1.2", "127.0.0.1:8188", None, False),
        ("127.0.0.1", "evil.example:8188", None, False),
        ("127.0.0.1", "127.0.0.1:8188", "http://evil.example", False),
        ("127.0.0.1", "127.0.0.1:8188", "null", False),
        ("127.0.0.1", "127.0.0.1:8188", "http://127.0.0.1:9000", False),
        ("not-an-ip", "localhost:8188", None, False),
    ],
)
def test_loopback_and_origin(
    plugin: ModuleType, remote: str, host: str, origin: str | None, *, expected: bool
) -> None:
    routes = importlib.import_module(f"{plugin.__name__}.routes")
    assert routes.allowed_request(remote, host, origin) is expected


def test_pages_and_editor_identity(
    plugin: ModuleType, project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    routes = importlib.import_module(f"{plugin.__name__}.routes")
    edit = importlib.import_module("soda_storyboard.edit")
    assert routes.list_pages(str(project)) == [{"id": "p1", "description": ""}]
    health = {"service": "soda-storyboard", "pid": 123, "instance_id": "demo", "project_dir": str(project)}
    launch = Mock(return_value=(None, 8780, health))
    monkeypatch.setattr(edit, "launch", launch)
    monkeypatch.setattr(edit, "health", lambda _: {})
    first = routes.editor_start(str(project), "p1")
    assert first == {"url": "http://127.0.0.1:8780/#page=p1", "port": 8780, "reused": False}
    assert (project / ".soda/server.json").is_file()
    monkeypatch.setattr(edit, "health", lambda _: health)
    assert routes.editor_start(str(project), "p1")["reused"] is True
    assert launch.call_count == 1
    # Core stop refuses a stale PID/instance identity; os.kill must never run.
    monkeypatch.setattr(edit, "health", lambda _: {**health, "instance_id": "other"})
    kill = Mock(side_effect=AssertionError("must not terminate another process"))
    monkeypatch.setattr(edit.os, "kill", kill)
    assert routes.editor_stop(str(project))["stopped"] is False
    kill.assert_not_called()


def test_route_dispatch_blocks_remote(plugin: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    routes = importlib.import_module(f"{plugin.__name__}.routes")
    web = ModuleType("aiohttp.web")
    web.json_response = lambda payload, status=200: (status, payload)
    monkeypatch.setitem(sys.modules, "aiohttp.web", web)
    launch = Mock(side_effect=AssertionError("must reject before launching"))
    monkeypatch.setattr(routes, "editor_start", launch)
    request = SimpleNamespace(remote="10.0.0.1", host="localhost:8188", headers={})
    response = asyncio.run(routes.dispatch(request, "start"))
    assert response[0] == 403
    launch.assert_not_called()


def test_route_registration(plugin: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    routes = importlib.import_module(f"{plugin.__name__}.routes")
    registered = []

    def decorator(method: str, path: str) -> object:
        def wrap(handler: object) -> object:
            registered.append((method, path, handler))
            return handler

        return wrap

    server = ModuleType("server")
    server.PromptServer = SimpleNamespace(
        instance=SimpleNamespace(
            routes=SimpleNamespace(
                get=lambda path: decorator("GET", path), post=lambda path: decorator("POST", path)
            )
        )
    )
    monkeypatch.setitem(sys.modules, "server", server)
    monkeypatch.setattr(routes, "_REGISTERED", False)
    routes.register_routes()
    routes.register_routes()
    assert len(registered) == 9
