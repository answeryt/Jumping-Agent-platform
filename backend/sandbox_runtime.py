from __future__ import annotations

import ast
import json
import sys
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_ROOT = Path(__file__).resolve().parent
SANDBOX_MAIN_ROOT = PROJECT_ROOT / "sandbox-main"
SANDBOX_ADAPTER_ROOT = PROJECT_ROOT / "sandbox"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
if str(SANDBOX_ADAPTER_ROOT) not in sys.path:
    sys.path.insert(0, str(SANDBOX_ADAPTER_ROOT))

from backend.memory.working_memory import AgentWorkingMemory, MemorySessionContext  # noqa: E402
from sandbox_manager import SandboxInstance, SandboxManager  # noqa: E402
from sandbox_executor import SandboxExecutor  # type: ignore  # noqa: E402


@dataclass
class SandboxToolEvent:
    """One step in the sandbox tool execution lifecycle (start/finish/error)."""

    event_id: str
    call_id: str
    agent_name: str
    server_name: str
    tool_name: str
    status: str
    timestamp: float
    duration_ms: Optional[int] = None
    arguments_preview: Optional[str] = None
    result_preview: Optional[str] = None
    error: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


_TOOL_TRACE_LISTENERS: List[Callable[[SandboxToolEvent], None]] = []
_TOOL_TRACE_LOCK = threading.RLock()
_TOOL_TRACE_BUFFER: List[SandboxToolEvent] = []
_TOOL_TRACE_BUFFER_MAX = 200


def register_tool_trace_listener(
    listener: Callable[[SandboxToolEvent], None],
) -> Callable[[], None]:
    """Subscribe a listener for ``SandboxToolEvent`` updates.

    Returns an unsubscribe callable.
    """
    with _TOOL_TRACE_LOCK:
        _TOOL_TRACE_LISTENERS.append(listener)

    def _unsubscribe() -> None:
        with _TOOL_TRACE_LOCK:
            try:
                _TOOL_TRACE_LISTENERS.remove(listener)
            except ValueError:
                pass

    return _unsubscribe


def recent_tool_events(limit: int = 50) -> List[Dict[str, Any]]:
    with _TOOL_TRACE_LOCK:
        events = list(_TOOL_TRACE_BUFFER[-limit:])
    return [event.to_dict() for event in events]


def _emit_tool_event(event: SandboxToolEvent) -> None:
    with _TOOL_TRACE_LOCK:
        _TOOL_TRACE_BUFFER.append(event)
        if len(_TOOL_TRACE_BUFFER) > _TOOL_TRACE_BUFFER_MAX:
            del _TOOL_TRACE_BUFFER[: len(_TOOL_TRACE_BUFFER) - _TOOL_TRACE_BUFFER_MAX]
        listeners = list(_TOOL_TRACE_LISTENERS)
    for listener in listeners:
        try:
            listener(event)
        except Exception:
            continue


def _preview_payload(value: Any, limit: int = 240) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        text = str(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n")
    if len(text) <= limit:
        return text
    return f"{text[:limit]} ...[truncated]"


def load_mcp_agent_prompt() -> str:
    """Load the MCP-oriented agent prompt from sandbox-main instead of duplicating it."""
    agent_loop_path = SANDBOX_MAIN_ROOT / "evaluation" / "agent_loop.py"
    if agent_loop_path.exists():
        tree = ast.parse(agent_loop_path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "DEFAULT_SYSTEM_PROMPT":
                        value = ast.literal_eval(node.value)
                        if isinstance(value, str) and value.strip():
                            return value.strip()
    return (
        "You are an AI assistant with access to AIO Sandbox MCP tools. "
        "Use MCP tools when sandbox inspection, browsing, files, or shell execution are needed."
    )


def _extract_tool_specs(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    data = payload.get("data", payload)
    if isinstance(data, dict):
        raw_tools = data.get("tools") or data.get("items") or data.get("result") or []
    elif isinstance(data, list):
        raw_tools = data
    else:
        raw_tools = []

    tools: List[Dict[str, Any]] = []
    for item in raw_tools:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            description = str(item.get("description") or item.get("title") or "").strip()
            input_schema = item.get("inputSchema") or item.get("input_schema") or item.get("parameters")
        else:
            name = str(item or "").strip()
            description = ""
            input_schema = None
        if name:
            tools.append(
                {
                    "name": name,
                    "description": description,
                    "input_schema": input_schema if isinstance(input_schema, dict) else None,
                }
            )
    return tools


def _format_json_preview(value: Any, limit: int = 1200) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    if len(text) <= limit:
        return text
    return f"{text[:limit]} ...[truncated]"


def _format_tool_catalog(tool_catalog: Optional[Dict[str, List[Dict[str, Any]]]]) -> str:
    if not tool_catalog:
        return "- No MCP servers were discovered. Do not emit sandbox_tool_call until the backend injects a non-empty catalog."
    lines: List[str] = []
    for server_name, tools in tool_catalog.items():
        lines.append(f"- Server `{server_name}`:")
        if not tools:
            lines.append("  - No tools reported by this server.")
            continue
        for tool in tools:
            description = tool.get("description", "")
            suffix = f" - {description}" if description else ""
            lines.append(f"  - `{tool['name']}`{suffix}")
            input_schema = tool.get("input_schema")
            if input_schema:
                lines.append(f"    args: `{_format_json_preview(input_schema)}`")
    return "\n".join(lines)


def build_mcp_usage_prompt(
    instance: SandboxInstance,
    tool_catalog: Optional[Dict[str, List[Dict[str, Any]]]] = None,
) -> str:
    catalog_text = _format_tool_catalog(tool_catalog)
    return "\n\n".join(
        [
            "## AIO Sandbox MCP Context",
            load_mcp_agent_prompt(),
            f"Sandbox base URL: {instance.base_url}",
            f"MCP endpoint: {instance.mcp_url}",
            "Live MCP server/tool catalog from /v1/mcp/servers and /v1/mcp/{server}/tools:",
            catalog_text,
            (
                "Use only the exact `server_name` and `tool_name` values listed above. "
                "Capability names such as browser, vscode, or jupyter are not MCP tool names."
            ),
            (
                "When a sandbox tool is needed, do not claim the tool was already used. "
                "First emit exactly one JSON object and wait for the backend result:\n"
                '{"sandbox_tool_call":{"server_name":"<server_name>",'
                '"tool_name":"<tool_name>","arguments":{...}}}'
            ),
        ]
    )


class BackendSandboxRuntime:
    """Backend-owned AIO Sandbox binding and MCP adapter."""

    def __init__(
        self,
        *,
        manager: Optional[SandboxManager] = None,
        base_url: Optional[str] = None,
        agent_base_urls: Optional[Dict[str, str]] = None,
        require_agent_base_urls: bool = False,
    ) -> None:
        self.manager = manager or SandboxManager()
        self.base_url = base_url
        self.agent_base_urls = dict(agent_base_urls or {})
        self.require_agent_base_urls = require_agent_base_urls
        self._instances: Dict[str, SandboxInstance] = {}
        self._executors: Dict[str, SandboxExecutor] = {}

    def bind_existing(self, agent_name: str, base_url: Optional[str] = None) -> SandboxInstance:
        resolved_base_url = base_url or self.agent_base_urls.get(agent_name) or self.base_url
        if self.require_agent_base_urls and not resolved_base_url:
            raise RuntimeError(f"No sandbox endpoint recorded for agent `{agent_name}`")
        instance = self.manager.attach_existing_sandbox(
            agent_name=agent_name,
            base_url=resolved_base_url,
        )
        self._instances[agent_name] = instance
        self._executors[agent_name] = SandboxExecutor(base_url=instance.base_url)
        return instance

    def instance(self, agent_name: str) -> SandboxInstance:
        return self._instances.get(agent_name) or self.bind_existing(agent_name)

    def executor(self, agent_name: str) -> SandboxExecutor:
        if agent_name not in self._executors:
            self.instance(agent_name)
        return self._executors[agent_name]

    def list_servers(self, agent_name: str) -> List[str]:
        payload = self.executor(agent_name).list_mcp_servers()
        data = payload.get("data", payload)
        def _server_name(item: Any) -> str:
            if isinstance(item, dict):
                return str(item.get("name") or item.get("id") or item.get("server") or "").strip()
            return str(item or "").strip()
        if isinstance(data, list):
            return [name for name in (_server_name(item) for item in data) if name]
        if isinstance(data, dict):
            values = data.get("servers") or data.get("items") or data.get("result")
            if isinstance(values, list):
                return [name for name in (_server_name(item) for item in values) if name]
        return []

    def list_tools(self, agent_name: str, server_name: str) -> Dict[str, Any]:
        return self.executor(agent_name).list_mcp_tools(server_name)

    def tool_catalog(self, agent_name: str) -> Dict[str, List[Dict[str, Any]]]:
        catalog: Dict[str, List[Dict[str, Any]]] = {}
        for server_name in self.list_servers(agent_name):
            try:
                catalog[server_name] = _extract_tool_specs(self.list_tools(agent_name, server_name))
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to list MCP tools for server `{server_name}` on agent `{agent_name}`: {exc}"
                ) from exc
        return catalog

    def _validate_tool_call(self, agent_name: str, server_name: str, tool_name: str) -> None:
        catalog = self.tool_catalog(agent_name)
        if server_name not in catalog:
            available = ", ".join(catalog) or "none"
            raise ValueError(
                f"MCP server `{server_name}` is not available. Available servers: {available}. "
                "Use a server_name from the injected MCP catalog."
            )
        available_tools = {tool["name"] for tool in catalog[server_name]}
        if tool_name not in available_tools:
            preview = ", ".join(sorted(available_tools)[:20]) or "none"
            raise ValueError(
                f"MCP tool `{tool_name}` is not available on server `{server_name}`. "
                f"Available tools include: {preview}. Use a tool_name from the injected MCP catalog."
            )

    def call_tool(
        self,
        agent_name: str,
        server_name: str,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        call_id = uuid.uuid4().hex
        start_ts = time.time()
        instance = self.instance(agent_name)
        sandbox_meta = {
            "base_url": instance.base_url,
            "dashboard_url": instance.dashboard_url,
            "vnc_url": instance.vnc_url,
        }
        try:
            self._validate_tool_call(agent_name, server_name, tool_name)
        except Exception as exc:
            _emit_tool_event(
                SandboxToolEvent(
                    event_id=uuid.uuid4().hex,
                    call_id=call_id,
                    agent_name=agent_name,
                    server_name=server_name,
                    tool_name=tool_name,
                    status="error",
                    timestamp=time.time(),
                    duration_ms=int((time.time() - start_ts) * 1000),
                    error=str(exc),
                    extra={"sandbox": sandbox_meta},
                )
            )
            raise
        _emit_tool_event(
            SandboxToolEvent(
                event_id=uuid.uuid4().hex,
                call_id=call_id,
                agent_name=agent_name,
                server_name=server_name,
                tool_name=tool_name,
                status="start",
                timestamp=start_ts,
                arguments_preview=_preview_payload(arguments or {}),
                extra={"sandbox": sandbox_meta},
            )
        )
        try:
            result = self.executor(agent_name).execute_mcp_tool(
                server_name, tool_name, arguments or {}
            )
        except Exception as exc:
            _emit_tool_event(
                SandboxToolEvent(
                    event_id=uuid.uuid4().hex,
                    call_id=call_id,
                    agent_name=agent_name,
                    server_name=server_name,
                    tool_name=tool_name,
                    status="error",
                    timestamp=time.time(),
                    duration_ms=int((time.time() - start_ts) * 1000),
                    error=str(exc),
                    extra={"sandbox": sandbox_meta},
                )
            )
            raise
        _emit_tool_event(
            SandboxToolEvent(
                event_id=uuid.uuid4().hex,
                call_id=call_id,
                agent_name=agent_name,
                server_name=server_name,
                tool_name=tool_name,
                status="finish",
                timestamp=time.time(),
                duration_ms=int((time.time() - start_ts) * 1000),
                result_preview=_preview_payload(result),
                extra={"sandbox": sandbox_meta},
            )
        )
        return result

    def prompt_for_agent(self, agent_name: str) -> str:
        instance = self.instance(agent_name)
        return self.memory_scoped_prompt_for_agent(agent_name, instance=instance)

    def memory_scoped_prompt_for_agent(
        self,
        agent_name: str,
        *,
        instance: Optional[SandboxInstance] = None,
        user_id: str = "default_user",
        session_id: str = "default_session",
    ) -> str:
        instance = instance or self.instance(agent_name)
        prompt = build_mcp_usage_prompt(instance, self.tool_catalog(agent_name))
        history = self.load_prompt_into_memory(
            agent_name,
            prompt=prompt,
            user_id=user_id,
            session_id=session_id,
        )
        return "\n\n".join(
            f"[{item.get('role', 'system')}]\n{item.get('content', '')}".strip()
            for item in history
            if str(item.get("content", "")).strip()
        )

    def load_prompt_into_memory(
        self,
        agent_name: str,
        *,
        prompt: Optional[str] = None,
        user_id: str = "default_user",
        session_id: str = "default_session",
    ) -> List[Dict[str, str]]:
        prompt_text = prompt or build_mcp_usage_prompt(self.instance(agent_name), self.tool_catalog(agent_name))
        memory = AgentWorkingMemory(
            context=MemorySessionContext(user_id=user_id, session_id=session_id),
        )
        agent_key = f"sandbox:{agent_name}"
        history = memory.build_context(agent_key=agent_key, include_shared=False)
        if not any(
            item.get("role") == "system" and item.get("content") == prompt_text
            for item in history
        ):
            memory.append(
                "system",
                prompt_text,
                agent_key=agent_key,
                metadata={
                    "source": "sandbox_mcp_prompt",
                    "agent_name": agent_name,
                },
            )
            history = memory.build_context(agent_key=agent_key, include_shared=False)
        return history
