from __future__ import annotations

import hashlib
import os
import socket
import subprocess
import time
from dataclasses import dataclass
from typing import Dict, Iterable, Optional
from urllib import error as urllib_error
from urllib import request as urllib_request


DEFAULT_SANDBOX_IMAGE = "ghcr.io/agent-infra/sandbox:latest"
DEFAULT_PORT_START = 18080
DEFAULT_PORT_END = 18180


@dataclass(frozen=True)
class SandboxInstance:
    agent_name: str
    container_name: str
    host_port: int
    base_url: str
    mcp_url: str
    dashboard_url: str
    vnc_url: str

    def model_dump(self) -> Dict[str, str | int]:
        return {
            "agentName": self.agent_name,
            "containerName": self.container_name,
            "hostPort": self.host_port,
            "sandboxUrl": self.base_url,
            "baseUrl": self.base_url,
            "mcpUrl": self.mcp_url,
            "dashboardUrl": self.dashboard_url,
            "vncUrl": self.vnc_url,
        }


class SandboxManager:
    """Starts one AIO Sandbox Docker container per generated agent."""

    def __init__(
        self,
        *,
        image: Optional[str] = None,
        port_start: Optional[int] = None,
        port_end: Optional[int] = None,
        bind_host: Optional[str] = None,
        public_host: Optional[str] = None,
        startup_timeout_seconds: Optional[float] = None,
    ) -> None:
        self.image = image or os.getenv("AIO_SANDBOX_IMAGE", DEFAULT_SANDBOX_IMAGE)
        self.port_start = port_start or _int_env("AIO_SANDBOX_PORT_START", DEFAULT_PORT_START)
        self.port_end = port_end or _int_env("AIO_SANDBOX_PORT_END", DEFAULT_PORT_END)
        self.bind_host = bind_host or os.getenv("AIO_SANDBOX_BIND_HOST", "127.0.0.1")
        self.public_host = public_host or os.getenv("AIO_SANDBOX_PUBLIC_HOST", "localhost")
        self.startup_timeout_seconds = startup_timeout_seconds or float(
            os.getenv("AIO_SANDBOX_STARTUP_TIMEOUT", "45")
        )

        if self.port_end < self.port_start:
            raise ValueError("AIO_SANDBOX_PORT_END must be greater than or equal to AIO_SANDBOX_PORT_START")

    def ensure_agent_sandboxes(
        self,
        *,
        project_name: str,
        agents: Iterable[tuple[str, str]],
    ) -> Dict[str, SandboxInstance]:
        instances: Dict[str, SandboxInstance] = {}
        reserved_ports: set[int] = set()

        for node_id, agent_name in agents:
            container_name = self._container_name(project_name, agent_name, node_id)
            self._remove_existing_container(container_name)
            host_port = self._allocate_port(reserved_ports)
            reserved_ports.add(host_port)
            instance = self._start_container(agent_name, container_name, host_port)
            instances[agent_name] = instance

        return instances

    def _container_name(self, project_name: str, agent_name: str, node_id: str) -> str:
        base = _docker_name_part(f"fatcat-{project_name}-{agent_name}")
        digest = hashlib.sha1(f"{project_name}:{agent_name}:{node_id}".encode("utf-8")).hexdigest()[:8]
        return f"{base[:48]}-{digest}"

    def _allocate_port(self, reserved_ports: set[int]) -> int:
        for port in range(self.port_start, self.port_end + 1):
            if port in reserved_ports:
                continue
            if _is_port_available(self.bind_host, port):
                return port
        raise RuntimeError(
            f"No free AIO Sandbox host ports in range {self.port_start}-{self.port_end}"
        )

    def _remove_existing_container(self, container_name: str) -> None:
        result = _run_docker(["docker", "rm", "-f", container_name], check=False)
        if result.returncode not in (0, 1):
            raise RuntimeError(
                f"Failed to remove existing sandbox container {container_name}: {result.stderr.strip()}"
            )

    def _start_container(
        self,
        agent_name: str,
        container_name: str,
        host_port: int,
    ) -> SandboxInstance:
        command = [
            "docker",
            "run",
            "-d",
            "--name",
            container_name,
            "--security-opt",
            "seccomp=unconfined",
            "-p",
            f"{self.bind_host}:{host_port}:8080",
            "-e",
            "WORKSPACE=/home/gem",
            self.image,
        ]
        result = _run_docker(command, check=False)
        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to start AIO Sandbox for {agent_name}: {result.stderr.strip()}"
            )

        base_url = f"http://{self.public_host}:{host_port}"
        instance = SandboxInstance(
            agent_name=agent_name,
            container_name=container_name,
            host_port=host_port,
            base_url=base_url,
            mcp_url=f"{base_url}/mcp",
            dashboard_url=f"{base_url}/index.html",
            vnc_url=f"{base_url}/vnc/index.html?autoconnect=true",
        )
        self._wait_until_ready(instance)
        return instance

    def _wait_until_ready(self, instance: SandboxInstance) -> None:
        deadline = time.monotonic() + self.startup_timeout_seconds
        last_error = ""
        while time.monotonic() < deadline:
            try:
                request = urllib_request.Request(f"{instance.base_url}/v1/sandbox", method="GET")
                with urllib_request.urlopen(request, timeout=2) as response:
                    if response.status < 500:
                        return
            except urllib_error.URLError as exc:
                last_error = str(exc)
            except TimeoutError as exc:
                last_error = str(exc)
            time.sleep(1)

        raise RuntimeError(
            f"AIO Sandbox container {instance.container_name} did not become ready "
            f"at {instance.base_url}: {last_error}"
        )


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return int(value)


def _docker_name_part(value: str) -> str:
    chars = []
    previous_dash = False
    for char in value.lower():
        if char.isalnum() or char in ("_", "."):
            chars.append(char)
            previous_dash = False
        elif not previous_dash:
            chars.append("-")
            previous_dash = True
    return "".join(chars).strip("-_.") or "fatcat-agent"


def _is_port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def _run_docker(command: list[str], *, check: bool) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            check=check,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("Docker CLI was not found. Install Docker before starting agent sandboxes.") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Docker command timed out: {' '.join(command)}") from exc
