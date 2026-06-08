from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

RUNTIME_ROOT = Path(__file__).resolve().parent
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from Agent.base_agent import BaseAgent, PromptLoader
from Model.openai_model import OpenAIModel
from Workflow.base_flow import BaseFlow, FlowExecutionResult


def _load_env_file() -> None:
    env_path = RUNTIME_ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = value.strip()


def load_build_plan() -> Dict[str, Any]:
    build_plan_path = RUNTIME_ROOT / "build_plan.json"
    if not build_plan_path.exists():
        return {}
    try:
        return json.loads(build_plan_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError("build_plan.json is not valid JSON") from exc


def build_chat_input(
    user_input: str,
    history: Optional[List[Dict[str, str]]] = None,
) -> str:
    request_text = str(user_input or "").strip()
    entries = list(history or [])
    if not entries:
        return request_text

    lines: List[str] = ["Conversation context:"]
    for item in entries:
        role = str(item.get("role", "unknown")).strip() or "unknown"
        content = str(item.get("content", "")).strip()
        if not content:
            continue
        lines.append(f"[{role}] {content}")
    lines.append("")
    lines.append("Current task:")
    lines.append(request_text)
    return "\n".join(lines).strip()


def _agent_tools_from_build_plan() -> Dict[str, List[str]]:
    payload = load_build_plan()
    tools_by_agent: Dict[str, List[str]] = {}
    for item in payload.get("agents") or []:
        if not isinstance(item, dict):
            continue
        agent_name = str(item.get("agent_name") or "").strip()
        raw_tools = item.get("tools") or []
        if not agent_name or not isinstance(raw_tools, list):
            continue
        tools: List[str] = []
        seen = set()
        for raw_tool in raw_tools:
            tool_name = str(raw_tool or "").strip()
            if not tool_name or tool_name in seen:
                continue
            seen.add(tool_name)
            tools.append(tool_name)
        tools_by_agent[agent_name] = tools
    return tools_by_agent


def _discover_agent_classes() -> Dict[str, Type[BaseAgent]]:
    agent_dir = RUNTIME_ROOT / "Agent"
    discovered: Dict[str, Type[BaseAgent]] = {}
    for path in sorted(agent_dir.glob("*_agent.py")):
        if path.name == "base_agent.py":
            continue
        module = importlib.import_module(f"Agent.{path.stem}")
        for value in vars(module).values():
            if isinstance(value, type) and issubclass(value, BaseAgent) and value is not BaseAgent:
                discovered[path.stem[:-6]] = value
                break
    return discovered


def _discover_flow_class() -> Optional[Type[BaseFlow]]:
    payload = load_build_plan()
    preferred_stem: Optional[str] = None
    flow = payload.get("flow") or {}
    flow_type = str(flow.get("type", "")).strip()
    if flow_type and flow_type != "single":
        preferred_stem = f"{flow_type}_flow"

    workflow_dir = RUNTIME_ROOT / "Workflow"
    candidates = [path for path in sorted(workflow_dir.glob("*_flow.py")) if path.name != "base_flow.py"]
    if not candidates:
        return None

    selected = None
    if preferred_stem is not None:
        for path in candidates:
            if path.stem == preferred_stem:
                selected = path
                break
    if selected is None:
        if len(candidates) > 1:
            raise RuntimeError("Multiple flow files found. build_plan.json must declare which one to run.")
        selected = candidates[0]

    module = importlib.import_module(f"Workflow.{selected.stem}")
    for value in vars(module).values():
        if isinstance(value, type) and issubclass(value, BaseFlow) and value is not BaseFlow:
            return value
    raise RuntimeError(f"No flow class found in {selected.name}")


def _ensure_backend_on_path() -> bool:
    for parent in RUNTIME_ROOT.parents:
        if (parent / "backend" / "memory" / "working_memory").exists():
            if str(parent) not in sys.path:
                sys.path.insert(0, str(parent))
            return True
    return False


def _resolve_small_session_binding(
    big_session_id: str,
    small_session_id: Optional[str] = None,
) -> Dict[str, Any]:
    if not big_session_id:
        raise ValueError("big_session_id is required (orchestrator must allocate it)")
    if not _ensure_backend_on_path():
        raise RuntimeError("backend/memory/working_memory not reachable from runtime")
    from backend.memory.working_memory import SessionManager

    manager = SessionManager()
    if small_session_id:
        big_dir = manager.big_session_dir(big_session_id)
        md_path = big_dir / f"{small_session_id}.md"
        if not md_path.exists():
            from backend.memory.working_memory import create_session_memory_template

            md_path.parent.mkdir(parents=True, exist_ok=True)
            create_session_memory_template(dest_path=md_path)
        return {
            "big_session_id": big_session_id,
            "small_session_id": small_session_id,
            "md_path": str(md_path),
        }
    binding = manager.pick_or_create_small_session(big_session_id)
    return {
        "big_session_id": binding.big_session_id,
        "small_session_id": binding.small_session_id,
        "md_path": str(binding.md_path),
    }


def _record_user_turn(big_session_id: str, small_session_id: str) -> None:
    if not _ensure_backend_on_path():
        return
    try:
        from backend.memory.working_memory import SessionManager, SmallSessionBinding
    except Exception:
        return
    manager = SessionManager()
    big_dir = manager.big_session_dir(big_session_id)
    md_path = big_dir / f"{small_session_id}.md"
    try:
        manager.record_user_turn(
            SmallSessionBinding(
                big_session_id=big_session_id,
                small_session_id=small_session_id,
                md_path=md_path,
                turns_used=0,
            )
        )
    except Exception as exc:
        _log_runtime(f"[Session] failed to record turn for {big_session_id}/{small_session_id}: {exc}")


def _preview_text(value: Any, limit: int = 200) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\n", "\\n")
    if len(text) <= limit:
        return text
    return f"{text[:limit]} ...[truncated]"


def _log_runtime(message: str) -> None:
    print(message, flush=True)


class RuntimeAgentRunner:
    def __init__(
        self,
        agent_name: str,
        agent: BaseAgent,
        runtime_root: Optional[Path] = None,
        agent_id: str = "",
        tool_runtime: Optional[Any] = None,
    ) -> None:
        self.agent_name = agent_name
        self.agent_id = agent_id
        self.agent = agent
        self.runtime_root = (runtime_root or RUNTIME_ROOT).resolve()
        if tool_runtime is None:
            raise ValueError("tool_runtime is required")
        self.tool_runtime = tool_runtime

    def run(self, user_input: str, history: Optional[List[Dict[str, str]]] = None) -> str:
        merged_input = build_chat_input(user_input=user_input, history=history)
        reply = self.agent.run(merged_input)
        _log_runtime(
            f"[Agent {self.agent_name}] reply={_preview_text(reply)}"
        )
        for iteration in range(1, 6):
            step = self.tool_runtime.run_tool_calls(reply, agent_id=self.agent_id)
            if not step.has_tool_request and not step.has_tool_call:
                return reply
            feedback = step.feedback_to_llm or ""
            _log_runtime(
                f"[Agent {self.agent_name}][ToolRuntime {iteration}] feedback={_preview_text(feedback)}"
            )
            if step.terminate:
                return feedback
            followup = (
                f"{merged_input}\n\n"
                f"Previous assistant reply:\n{reply}\n\n"
                f"{feedback}\n\n"
                "请基于以上系统反馈继续回答；如果要查看可用工具，请使用同一个请求代码 "
                '`tool_request("available_tools")`；如果要执行工具，请只输出一条 tool_call(...)。'
            )
            reply = self.agent.run(followup)
            _log_runtime(
                f"[Agent {self.agent_name}] tool_runtime_followup={_preview_text(reply)}"
            )
        return reply


def _build_agents() -> Dict[str, BaseAgent]:
    _load_env_file()
    model = OpenAIModel()
    prompt_loader = PromptLoader(prompt_dir=RUNTIME_ROOT / "Prompt")
    agents: Dict[str, BaseAgent] = {}
    for name, cls in _discover_agent_classes().items():
        agents[name] = cls(model=model, prompt_loader=prompt_loader)
    if not agents:
        raise RuntimeError("No generated agent files found.")
    return agents


def _build_agent_runners(agents: Dict[str, BaseAgent]) -> Dict[str, RuntimeAgentRunner]:
    if not _ensure_backend_on_path():
        raise RuntimeError("backend not reachable; cannot activate backend tools")
    from backend.agent_run_time import AgentRuntimeRegistry, AgentToolRuntime

    tools_by_agent = _agent_tools_from_build_plan()
    agent_registry = AgentRuntimeRegistry()
    tool_runtime = AgentToolRuntime.from_default_tools(agent_registry=agent_registry)
    return {
        name: RuntimeAgentRunner(
            name,
            agent,
            RUNTIME_ROOT,
            agent_registry.register_agent(name, tools_by_agent.get(name, [])),
            tool_runtime,
        )
        for name, agent in agents.items()
    }


def run_project_with_trace(
    user_input: str,
    *,
    history: Optional[List[Dict[str, str]]] = None,
    user_id: str,
    big_session_id: str,
    small_session_id: Optional[str] = None,
) -> Dict[str, Any]:
    if not user_id:
        raise ValueError("user_id is required (no default fallback)")
    if not big_session_id:
        raise ValueError("big_session_id is required (no default fallback)")

    binding = _resolve_small_session_binding(big_session_id, small_session_id)
    resolved_small = binding["small_session_id"]
    composite_session_id = f"{big_session_id}/{resolved_small}"

    agents = _build_agents()
    runners = _build_agent_runners(agents)
    flow_cls = _discover_flow_class()

    if flow_cls is not None:
        flow = flow_cls(
            agents=runners,
            user_id=user_id,
            session_id=composite_session_id,
            big_session_id=big_session_id,
            small_session_id=resolved_small,
            md_path=binding["md_path"],
        )
        result = flow.run_with_trace(
            user_input,
            user_id=user_id,
            session_id=composite_session_id,
            big_session_id=big_session_id,
            small_session_id=resolved_small,
            md_path=binding["md_path"],
        )
        _record_user_turn(big_session_id, resolved_small)
        return {
            "result": result,
            "binding": binding,
        }
    if len(runners) == 1:
        reply = next(iter(runners.values())).run(user_input, history=history)
        result = FlowExecutionResult(
            stopped_by="single_agent_complete",
            turns=[],
            final_output=reply,
            final_agent=next(iter(runners.keys())),
        )
        _record_user_turn(big_session_id, resolved_small)
        return {"result": result, "binding": binding}
    raise RuntimeError("Multiple agents were generated but no executable flow was found.")


def run_project(
    user_input: str,
    *,
    history: Optional[List[Dict[str, str]]] = None,
    user_id: str,
    big_session_id: str,
    small_session_id: Optional[str] = None,
) -> str:
    outcome = run_project_with_trace(
        user_input,
        history=history,
        user_id=user_id,
        big_session_id=big_session_id,
        small_session_id=small_session_id,
    )
    return outcome["result"].final_output


def run_project_and_describe(
    user_input: str,
    *,
    history: Optional[List[Dict[str, str]]] = None,
    user_id: str,
    big_session_id: str,
    small_session_id: Optional[str] = None,
) -> Dict[str, Any]:
    outcome = run_project_with_trace(
        user_input,
        history=history,
        user_id=user_id,
        big_session_id=big_session_id,
        small_session_id=small_session_id,
    )
    binding = outcome["binding"]
    return {
        "answer": outcome["result"].final_output,
        "user_id": user_id,
        "big_session_id": binding["big_session_id"],
        "small_session_id": binding["small_session_id"],
        "memory_md_path": binding["md_path"],
    }


def chat(user_input: str, **kwargs: Any) -> Any:
    describe = bool(kwargs.pop("return_session_info", False))
    if describe:
        return run_project_and_describe(user_input, **kwargs)
    return run_project(user_input, **kwargs)


def _interactive_chat_loop() -> None:
    print("Interactive agent session started. Type 'exit' or 'quit' to stop.")
    if not _ensure_backend_on_path():
        raise RuntimeError("backend not reachable; cannot allocate session ids")
    from backend.memory.working_memory import SessionManager

    manager = SessionManager()
    user_id = os.environ.get("AGENT_RUNTIME_USER_ID", "cli_user")
    big_session_id = manager.start_big_session()
    print(f"big_session_id={big_session_id} user_id={user_id}")

    history: List[Dict[str, str]] = []
    while True:
        try:
            user_input = input("You> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            break
        described = run_project_and_describe(
            user_input,
            history=history,
            user_id=user_id,
            big_session_id=big_session_id,
        )
        reply = described["answer"]
        print(reply)
        history.append({"role": "user", "content": user_input})
        history.append({"role": "assistant", "content": reply})


def main() -> None:
    _interactive_chat_loop()


__all__ = [
    "RuntimeAgentRunner",
    "_build_agent_runners",
    "_build_agents",
    "_resolve_small_session_binding",
    "build_chat_input",
    "chat",
    "load_build_plan",
    "run_project",
    "run_project_and_describe",
]


if __name__ == "__main__":
    main()
