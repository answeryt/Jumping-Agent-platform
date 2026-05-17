from __future__ import annotations

import json
import http.client
import os
import shlex
import time
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Sequence
from urllib import error as urllib_error
from urllib import request as urllib_request


DEFAULT_SANDBOX_URL = "http://localhost:8080"
CONTAINER_PREFIX = "/workspace/"


@dataclass
class CommandResult:
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0


@dataclass
class WriteResult:
    ok: bool = True
    stderr: str = ""


class SandboxExecutor:
    """Small adapter for the sandbox-main AIO Sandbox HTTP API."""

    def __init__(self, base_url: str | None = None, workspace_root: str | None = None) -> None:
        self.base_url = (base_url or os.getenv("AIO_SANDBOX_URL") or DEFAULT_SANDBOX_URL).rstrip("/")
        self._workspace_root = workspace_root or os.getenv("AIO_SANDBOX_WORKSPACE")

    def run(self, cmd: Sequence[str], **kwargs: Any) -> CommandResult:
        if not cmd:
            return CommandResult(returncode=1, stderr="empty command")

        mapped = self._map_command_paths(list(cmd))
        payload: dict[str, Any] = {
            "command": shlex.join(mapped),
            "async_mode": False,
            "truncate": False,
        }

        timeout = kwargs.get("timeout")
        if timeout is not None:
            payload["timeout"] = timeout
            payload["hard_timeout"] = timeout

        response = self._post_json("/v1/shell/exec", payload)
        if not response.get("success", False):
            return CommandResult(returncode=1, stderr=response.get("message") or json.dumps(response))

        data = response.get("data") or {}
        return CommandResult(
            returncode=int(data.get("exit_code") if data.get("exit_code") is not None else 0),
            stdout=data.get("output") or "",
            stderr=response.get("message") or "",
        )

    def write_file(self, container_path: str, content: str) -> WriteResult:
        sandbox_path = self._to_sandbox_path(container_path)
        parent = str(PurePosixPath(sandbox_path).parent)
        mkdir = self.run(["mkdir", "-p", parent])
        if not mkdir.ok:
            return WriteResult(ok=False, stderr=mkdir.stderr or mkdir.stdout)

        response = self._post_json(
            "/v1/file/write",
            {
                "file": sandbox_path,
                "content": content,
                "encoding": "utf-8",
                "append": False,
                "leading_newline": False,
                "trailing_newline": False,
                "sudo": False,
            },
        )
        if response.get("success", False):
            return WriteResult()
        return WriteResult(ok=False, stderr=response.get("message") or json.dumps(response))

    def list_mcp_servers(self) -> dict[str, Any]:
        return self._get_json("/v1/mcp/servers")

    def list_mcp_tools(self, server_name: str) -> dict[str, Any]:
        return self._get_json(f"/v1/mcp/{server_name}/tools")

    def execute_mcp_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._post_json(f"/v1/mcp/{server_name}/tools/{tool_name}", arguments or {})

    def _map_command_paths(self, cmd: list[str]) -> list[str]:
        return [self._to_sandbox_path(part) if part.startswith("/workspace") else part for part in cmd]

    def _to_sandbox_path(self, container_path: str) -> str:
        if container_path == "/workspace":
            return self._get_workspace_root()
        if container_path.startswith(CONTAINER_PREFIX):
            return str(PurePosixPath(self._get_workspace_root()) / container_path[len(CONTAINER_PREFIX) :])
        return container_path

    def _get_workspace_root(self) -> str:
        if self._workspace_root:
            return self._workspace_root.rstrip("/")

        response = self._get_json("/v1/sandbox")
        workspace = response.get("workspace") or response.get("home_dir")
        if not workspace:
            detail = response.get("detail") or {}
            system = detail.get("system") or {}
            workspace = system.get("workspace") or system.get("home_dir")
        self._workspace_root = str(workspace or "/home/gem").rstrip("/")
        return self._workspace_root

    def _get_json(self, path: str) -> dict[str, Any]:
        return self._request_json("GET", path)

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request_json("POST", path, payload)

    def _request_json(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib_request.Request(
            f"{self.base_url}{path}",
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        last_error: BaseException | None = None
        for attempt in range(1, 4):
            try:
                with urllib_request.urlopen(request, timeout=60) as response:
                    body = response.read().decode("utf-8")
                break
            except urllib_error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"AIO Sandbox API {method} {path} failed: {exc.code} {body}") from exc
            except (urllib_error.URLError, http.client.RemoteDisconnected, ConnectionResetError) as exc:
                last_error = exc
                if attempt == 3:
                    raise RuntimeError(f"AIO Sandbox is not reachable at {self.base_url}: {exc}") from exc
                time.sleep(0.5 * attempt)
        else:
            raise RuntimeError(f"AIO Sandbox is not reachable at {self.base_url}: {last_error}")

        if not body:
            return {}
        return json.loads(body)
