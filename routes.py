"""Loopback-only PromptServer routes. Import-safe outside ComfyUI."""

from __future__ import annotations

import asyncio
import importlib
import ipaddress
import os
import signal
import subprocess
import threading
from typing import Any
from urllib.parse import quote, urlsplit

from .nodes.bundles import MAX_FILE_BYTES, file_path, list_files, original_filename, store_upload
from .nodes.core import core, editable_id, inside, page_path, project_root
from .nodes.workspaces import export_copy, inspect_import, inspect_link, materialize

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
        editable_id(page_id)
        core("io").load_page(page_path(root, page_id))
    # Store performs the same project validation as the core CLI before launch.
    core("server.store").Store(root)
    state_path = inside(root, ".soda/server.json")
    with _EDITOR_LOCK:
        state = edit.read_state(state_path)
        port = state.get("port", 0)
        health = edit.health(port)
        reused = edit.same_project(health, root)
        process = None
        if not reused:
            process, port, health = edit.launch(root, 0, detach=True)
        try:
            edit.write_state(state_path, port, health)
        except BaseException:
            if process is not None and process.poll() is None:
                # Match the core CLI: a Windows venv launcher can have a
                # different PID from the interpreter serving this instance.
                if edit.matches(edit.health(port), health, root):
                    os.kill(health["pid"], signal.SIGTERM)
                else:
                    process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            raise
    suffix = f"#page={quote(page_id, safe='')}" if page_id else ""
    return {"url": f"http://127.0.0.1:{port}/{suffix}", "port": port, "reused": reused}


def editor_stop(project_dir: str) -> dict:
    root = project_root(project_dir)
    with _EDITOR_LOCK:
        return core("edit").stop(root, inside(root, ".soda/server.json"))


class RequestTooLargeError(ValueError):
    pass


async def inspect_request(request: Any, action: str) -> dict:
    options = {
        "dialogue_mode": request.query.get("dialogue_mode", "跟随页面"),
        "slant_mode": request.query.get("slant_mode", "cut"),
        "include_triggers": request.query.get("include_triggers", "true") == "true",
    }
    if action == "inspect":
        result = await asyncio.to_thread(
            inspect_import,
            request.query.get("filename", ""),
            **options,
            width=int(request.query.get("width", 0)),
            height=int(request.query.get("height", 0)),
        )
    else:
        result = await asyncio.to_thread(
            inspect_link, request.query.get("project_dir", ""), request.query.get("page_id", ""), **options
        )
    if result["revision"] == request.query.get("revision"):
        return {"unchanged": True, "revision": result["revision"]}
    return {key: value for key, value in result.items() if key != "result"}


async def upload_request(request: Any) -> dict:
    if request.content_length and request.content_length > MAX_FILE_BYTES + MAX_REQUEST_BYTES:
        msg = "上传文件过大"
        raise RequestTooLargeError(msg)
    reader = await request.multipart()
    field = await reader.next()
    if field is None or field.name != "file" or not field.filename:
        msg = "请选择 JSON 文件"
        raise ValueError(msg)
    payload = bytearray()
    while chunk := await field.read_chunk():
        payload.extend(chunk)
        if len(payload) > MAX_FILE_BYTES:
            msg = "上传文件不能超过 16 MiB"
            raise RequestTooLargeError(msg)
    name = await asyncio.to_thread(
        store_upload, field.filename, bytes(payload), request.query.get("kind", "storyboard")
    )
    return {
        "name": name,
        "original_filename": await asyncio.to_thread(original_filename, name),
        "subfolder": "soda-storyboard",
        "type": "input",
    }


async def mutation_request(request: Any, action: str) -> dict:
    if request.content_length is None or request.content_length > MAX_REQUEST_BYTES:
        msg = "请求体缺少长度或过大"
        raise RequestTooLargeError(msg)
    body = await request.json()
    if not isinstance(body, dict):
        msg = "请求体必须为对象"
        raise TypeError(msg)
    if action in {"edit_import", "export"}:
        if not isinstance(body.get("filename"), str):
            msg = "请先导入分镜包"
            raise ValueError(msg)
        if action == "export":
            name = await asyncio.to_thread(export_copy, body["filename"])
            bundle = await asyncio.to_thread(core("io").read_json, file_path(name))
            return {"name": name, "bundle": bundle}
        root, page_id = await asyncio.to_thread(
            materialize,
            body["filename"],
            convert_moss=body.get("convert_moss") is True,
            width=int(body.get("width", 0)),
            height=int(body.get("height", 0)),
        )
        result = await asyncio.to_thread(editor_start, str(root), page_id)
        return {**result, "project_dir": str(root), "page_id": page_id}
    if not isinstance(body.get("project_dir"), str):
        msg = "请填写 project_dir"
        raise TypeError(msg)
    if action == "stop":
        return await asyncio.to_thread(editor_stop, body["project_dir"])
    page_id = body.get("page_id", "")
    if not isinstance(page_id, str):
        msg = "page_id 必须是字符串"
        raise TypeError(msg)
    return await asyncio.to_thread(editor_start, body["project_dir"], page_id)


async def dispatch(request: Any, action: str) -> Any:
    web = importlib.import_module("aiohttp.web")
    if not allowed_request(request.remote or "", request.host, request.headers.get("Origin")):
        return web.json_response({"error": "仅允许回环地址和同源请求访问分镜接口"}, status=403)
    try:
        if action == "pages":
            result = {"pages": await asyncio.to_thread(list_pages, request.query.get("project_dir", ""))}
        elif action == "files":
            files = await asyncio.to_thread(list_files, request.query.get("kind", "storyboard"))
            labels = await asyncio.to_thread(lambda: {name: original_filename(name) for name in files})
            result = {"files": files, "file_labels": labels}
        elif action in {"inspect", "link"}:
            result = await inspect_request(request, action)
        elif action == "upload":
            result = await upload_request(request)
        else:
            result = await mutation_request(request, action)
        return web.json_response(result)
    except RequestTooLargeError as exc:
        return web.json_response({"error": str(exc)}, status=413)
    except (ValueError, TypeError, KeyError, OSError, RuntimeError) as exc:
        return web.json_response({"error": str(exc)}, status=400)


def route_handler(action: str) -> Any:
    async def handler(request: Any) -> Any:
        return await dispatch(request, action)

    return handler


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
    for method, path, action in (
        ("get", "pages", "pages"),
        ("get", "files", "files"),
        ("get", "inspect", "inspect"),
        ("get", "link", "link"),
        ("post", "upload", "upload"),
        ("post", "import/edit", "edit_import"),
        ("post", "import/export", "export"),
        ("post", "editor/start", "start"),
        ("post", "editor/stop", "stop"),
    ):
        getattr(routes, method)(f"/soda_storyboard/{path}")(route_handler(action))
    _REGISTERED = True
