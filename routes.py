"""Loopback-only PromptServer routes. Import-safe outside ComfyUI."""

from __future__ import annotations

import asyncio
import importlib
import ipaddress
import threading
from typing import Any
from urllib.parse import quote, urlsplit

from .nodes.core import core, inside, page_path, project_root

_EDITOR_LOCK = threading.Lock()
_REGISTERED = False
MAX_REQUEST_BYTES = 16384


def is_loopback(host: str) -> bool:
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return address.is_loopback


def allowed_request(remote: str, host: str, origin: str | None) -> bool:
    if not is_loopback(remote):
        return False
    try:
        authority = urlsplit(f"//{host}")
        hostname = authority.hostname or ""
        if hostname.lower() != "localhost" and not is_loopback(hostname):
            return False
        if origin:
            url = urlsplit(origin)
            if url.scheme not in {"http", "https"} or url.netloc.lower() != host.lower():
                return False
    except ValueError:
        return False
    return True


def list_pages(project_dir: str) -> list[dict]:
    root = project_root(project_dir)
    io = core("io")
    return [
        {"id": p.stem, "description": io.load_page(page_path(root, p.stem)).description}
        for p in sorted(inside(root, "pages").glob("*.json"))
    ]


def editor_start(project_dir: str, page_id: str = "") -> dict:
    root = project_root(project_dir)
    edit = core("edit")
    if page_id:
        core("io").load_page(page_path(root, page_id))
    # Store performs the same project validation as the core CLI before launch.
    core("server.store").Store(root)
    state_path = inside(root, ".soda/server.json")
    with _EDITOR_LOCK:
        state = edit.read_state(state_path)
        port = state.get("port", 0)
        health = edit.health(port)
        reused = edit.same_project(health, root)
        if not reused:
            _, port, health = edit.launch(root, 0, detach=True)
        edit.write_state(state_path, port, health)
    suffix = f"#page={quote(page_id, safe='')}" if page_id else ""
    return {"url": f"http://127.0.0.1:{port}/{suffix}", "port": port, "reused": reused}


def editor_stop(project_dir: str) -> dict:
    root = project_root(project_dir)
    with _EDITOR_LOCK:
        return core("edit").stop(root, inside(root, ".soda/server.json"))


async def dispatch(request: Any, action: str) -> Any:
    web = importlib.import_module("aiohttp.web")
    if not allowed_request(request.remote or "", request.host, request.headers.get("Origin")):
        return web.json_response({"error": "仅允许回环地址和同源请求访问分镜接口"}, status=403)
    try:
        if action == "pages":
            value = await asyncio.to_thread(list_pages, request.query.get("project_dir", ""))
            return web.json_response({"pages": value})
        if request.content_length is None or request.content_length > MAX_REQUEST_BYTES:
            return web.json_response({"error": "请求体缺少长度或过大"}, status=413)
        body = await request.json()
        if not isinstance(body, dict) or not isinstance(body.get("project_dir"), str):
            return web.json_response({"error": "请填写 project_dir"}, status=400)
        if action == "start":
            page_id = body.get("page_id", "")
            if not isinstance(page_id, str):
                return web.json_response({"error": "page_id 必须是字符串"}, status=400)
            result = await asyncio.to_thread(editor_start, body["project_dir"], page_id)
        else:
            result = await asyncio.to_thread(editor_stop, body["project_dir"])
        return web.json_response(result)
    except (ValueError, OSError, RuntimeError) as exc:
        return web.json_response({"error": str(exc)}, status=400)


def register_routes() -> None:
    global _REGISTERED  # noqa: PLW0603 -- one registration per extension import
    if _REGISTERED:
        return
    try:
        prompt_server = importlib.import_module("server").PromptServer
    except (ImportError, AttributeError):
        return
    if not hasattr(prompt_server, "instance"):
        return
    routes = prompt_server.instance.routes

    @routes.get("/soda_storyboard/pages")
    async def pages(request: Any) -> Any:
        return await dispatch(request, "pages")

    @routes.post("/soda_storyboard/editor/start")
    async def start(request: Any) -> Any:
        return await dispatch(request, "start")

    @routes.post("/soda_storyboard/editor/stop")
    async def stop(request: Any) -> Any:
        return await dispatch(request, "stop")

    _REGISTERED = True
