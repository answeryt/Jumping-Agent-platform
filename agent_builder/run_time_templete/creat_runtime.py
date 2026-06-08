from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Dict


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _agent_base_source() -> str:
    return textwrap.dedent(
        '''
        from __future__ import annotations

        import sys
        from abc import ABC, abstractmethod
        from pathlib import Path
        from typing import Any, Optional


        for _parent in Path(__file__).resolve().parents:
            if (_parent / "backend" / "agent_run_time" / "prompt_runtime.py").exists():
                sys.path.insert(0, str(_parent))
                break

        from backend.agent_run_time.prompt_runtime import RuntimePromptLoader as PromptLoader


        class BaseAgent(ABC):
            def __init__(
                self,
                agent_type: str,
                model: Any = None,
                config: Any = None,
                prompt_loader: Optional[PromptLoader] = None,
            ) -> None:
                self.agent_type = agent_type
                self.model = model
                self.config = config
                self.prompt_loader = prompt_loader or PromptLoader(
                    prompt_dir=Path(__file__).resolve().parents[1] / "Prompt"
                )

            def load_prompt(self) -> str:
                if self.config is None or not getattr(self.config, "prompt_file", ""):
                    raise ValueError("Agent config.prompt_file is required")
                return self.prompt_loader.load(self.config.prompt_file, self.agent_type)

            @abstractmethod
            def run(self, user_input: str, **kwargs: Any) -> str:
                raise NotImplementedError
        '''
    ).strip() + "\n"


def _model_base_source() -> str:
    return textwrap.dedent(
        '''
        from __future__ import annotations

        from abc import ABC, abstractmethod
        from typing import Any, Dict, List, TypedDict


        class ChatMessage(TypedDict):
            role: str
            content: str


        class BaseModel(ABC):
            @abstractmethod
            def chat_with_system(self, system_message: str, user_message: str, **kwargs: Any) -> Dict[str, Any]:
                raise NotImplementedError

            @abstractmethod
            def get_model_name(self) -> str:
                raise NotImplementedError
        '''
    ).strip() + "\n"


def _openai_model_source() -> str:
    return textwrap.dedent(
        '''
        from __future__ import annotations

        from typing import Any, Dict, Optional

        from Config.settings import LLMConfig, load_settings
        from Model.base_model import BaseModel

        try:
            from openai import OpenAI
        except Exception:  # pragma: no cover
            OpenAI = None  # type: ignore


        class OpenAIModel(BaseModel):
            def __init__(self, config: Optional[LLMConfig] = None) -> None:
                llm_config = config or load_settings().llm_default
                self.model_name = llm_config.model
                self.temperature = llm_config.temperature
                self.max_tokens = llm_config.max_tokens
                self.stream = llm_config.stream
                self.base_url = llm_config.base_url
                self.api_key = llm_config.api_key

            def _build_client(self):
                if OpenAI is None:
                    raise RuntimeError("openai package is required to run generated projects")
                if not self.api_key:
                    raise RuntimeError("Configured api_key is required")
                if self.base_url:
                    return OpenAI(api_key=self.api_key, base_url=self.base_url)
                return OpenAI(api_key=self.api_key)

            def chat_with_system(self, system_message: str, user_message: str, **kwargs: Any) -> Dict[str, Any]:
                client = self._build_client()
                response = client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": user_message},
                    ],
                    temperature=kwargs.get("temperature", self.temperature),
                    max_tokens=kwargs.get("max_tokens", self.max_tokens),
                    stream=bool(kwargs.get("stream", self.stream)),
                )

                if bool(kwargs.get("stream", self.stream)):
                    full_text = ""
                    for chunk in response:
                        if not getattr(chunk, "choices", None):
                            continue
                        delta = chunk.choices[0].delta
                        content = getattr(delta, "content", None)
                        if content:
                            full_text += content
                    return {"content": full_text}

                message = response.choices[0].message
                text = message.content or ""
                return {"content": text}

            def get_model_name(self) -> str:
                return self.model_name
        '''
    ).strip() + "\n"


def _settings_source() -> str:
    return textwrap.dedent(
        '''
        from __future__ import annotations

        from dataclasses import dataclass
        import os
        from pathlib import Path
        from typing import Any, Dict, Optional

        import tomllib


        @dataclass(frozen=True)
        class LLMConfig:
            model: str
            api_key: str
            base_url: Optional[str] = None
            temperature: float = 0.7
            max_tokens: Optional[int] = None
            stream: bool = True


        @dataclass(frozen=True)
        class AppSettings:
            llm_default: LLMConfig


        _SETTINGS_CACHE: Optional[AppSettings] = None
        _ENV_LOADED = False


        def _config_file_path() -> Path:
            return Path(__file__).resolve().parent / "model_config.toml"


        def _dotenv_file_path() -> Path:
            return Path(__file__).resolve().parent.parent / ".env"


        def _load_env_once() -> None:
            global _ENV_LOADED
            if _ENV_LOADED:
                return

            dotenv_path = _dotenv_file_path()
            if dotenv_path.exists():
                with dotenv_path.open("r", encoding="utf-8") as f:
                    for raw_line in f:
                        line = raw_line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if line.startswith("export "):
                            line = line[7:].strip()
                        if "=" not in line:
                            continue
                        key, value = line.split("=", 1)
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        if key:
                            os.environ.setdefault(key, value)

            _ENV_LOADED = True


        def _to_llm_config(data: Dict[str, Any]) -> LLMConfig:
            model = str(data.get("model", "")).strip()
            api_key_env = str(data.get("api_key_env", "")).strip()
            api_key = os.getenv(api_key_env, "").strip() if api_key_env else ""
            base_url_raw = data.get("base_url")
            base_url = str(base_url_raw).strip() if base_url_raw else None

            if not model:
                raise ValueError("配置缺少 llm.default.model")
            if not api_key:
                if api_key_env:
                    raise ValueError(f"环境变量未设置: {api_key_env}")
                raise ValueError("配置缺少 llm.default.api_key_env")

            max_tokens_raw = data.get("max_tokens")
            max_tokens = int(max_tokens_raw) if max_tokens_raw is not None else None

            return LLMConfig(
                model=model,
                api_key=api_key,
                base_url=base_url,
                temperature=float(data.get("temperature", 0.7)),
                max_tokens=max_tokens,
                stream=bool(data.get("stream", True)),
            )


        def load_settings(force_reload: bool = False) -> AppSettings:
            global _SETTINGS_CACHE
            if _SETTINGS_CACHE is not None and not force_reload:
                return _SETTINGS_CACHE

            _load_env_once()

            path = _config_file_path()
            if not path.exists():
                raise FileNotFoundError(f"配置文件不存在: {path}")

            with path.open("rb") as f:
                raw = tomllib.load(f)

            llm_section = raw.get("llm", {})
            default_llm = llm_section.get("default", {})
            llm_default = _to_llm_config(default_llm)

            _SETTINGS_CACHE = AppSettings(llm_default=llm_default)
            return _SETTINGS_CACHE


        PROJECT_ROOT = Path(__file__).resolve().parents[1]
        DEFAULT_MODEL_NAME = load_settings().llm_default.model
        '''
    ).strip() + "\n"


def _workflow_base_source() -> str:
    return textwrap.dedent(
        r'''
        from __future__ import annotations

        import importlib
        from abc import ABC, abstractmethod
        from dataclasses import dataclass
        from typing import Any, Dict, List, Optional, Protocol

        class StepParserProtocol(Protocol):
            def parse(self, agent_type: str, raw_text: str) -> "ParsedFlowStep":
                ...


        @dataclass
        class AgentOutput:
            result: str = "none"


        @dataclass
        class AgentState:
            output: AgentOutput


        class AgentRunnerProtocol(Protocol):
            def run(self, user_input: str, history: Optional[List[Dict[str, str]]] = None) -> str:
                ...


        @dataclass
        class ParsedFlowStep:
            state: AgentState
            next_agent: str
            next_task: str
            should_stop: bool = False


        @dataclass
        class FlowTurnResult:
            turn_index: int
            agent_key: str
            task_text: str
            raw_output: str
            parsed: ParsedFlowStep


        @dataclass
        class FlowExecutionResult:
            stopped_by: str
            turns: List[FlowTurnResult]
            final_output: str
            final_agent: str


        class BaseFlow(ABC):
            def __init__(
                self,
                *args: Any,
                agents: Optional[Dict[str, AgentRunnerProtocol]] = None,
                step_parser: Optional[StepParserProtocol] = None,
                flow_type: Optional[str] = None,
                **kwargs: Any,
            ) -> None:
                self.agents: Dict[str, AgentRunnerProtocol] = dict(agents or {})
                self._step_parser = step_parser
                self.flow_type = flow_type or self.__class__.__name__.replace("Flow", "").lower()

            @staticmethod
            def _preview_text(value: Any, limit: int = 160) -> str:
                text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
                text = text.replace("\n", "\\n")
                if len(text) <= limit:
                    return text
                return f"{text[:limit]} ...[truncated]"

            @staticmethod
            def _log_runtime(message: str) -> None:
                print(message, flush=True)

            def _log_turn_result(self, turn: FlowTurnResult) -> None:
                next_agent = str(turn.parsed.next_agent or "").strip() or "none"
                next_task = str(turn.parsed.next_task or "").strip() or "none"
                if next_agent == "none" and next_task != "none":
                    handoff_text = f"task_only={self._preview_text(next_task, limit=120)}"
                elif next_agent != "none" and next_task != "none":
                    handoff_text = (
                        f"next_agent={next_agent}, "
                        f"next_task={self._preview_text(next_task, limit=120)}"
                    )
                else:
                    handoff_text = next_agent
                self._log_runtime(
                    "[Flow][Turn {turn}] agent={agent} input={input_preview} output={output_preview} "
                    "stop={stop_flag} handoff={handoff}".format(
                        turn=turn.turn_index,
                        agent=turn.agent_key,
                        input_preview=self._preview_text(turn.task_text),
                        output_preview=self._preview_text(turn.raw_output),
                        stop_flag=turn.parsed.should_stop,
                        handoff=handoff_text,
                    )
                )

            def register_agents(self, agents: Dict[str, AgentRunnerProtocol]) -> None:
                self.agents = dict(agents)

            def list_agents(self) -> List[str]:
                return sorted(self.agents.keys())

            def _default_parsed_step(self, raw_output: str) -> ParsedFlowStep:
                return ParsedFlowStep(
                    state=AgentState(output=AgentOutput(result=raw_output or "none")),
                    next_agent="none",
                    next_task="none",
                    should_stop=False,
                )

            def _resolve_step_parser(self) -> Optional[StepParserProtocol]:
                if self._step_parser is not None:
                    return self._step_parser
                parser_name = self.__class__.__name__.replace("Flow", "StepParser")
                module = importlib.import_module(self.__class__.__module__)
                parser_cls = getattr(module, parser_name, None)
                if parser_cls is None:
                    return None
                self._step_parser = parser_cls()
                return self._step_parser

            def run_turn(
                self,
                turn_index: int,
                agent_key: str,
                task_text: str,
                history: Optional[List[Dict[str, str]]] = None,
            ) -> FlowTurnResult:
                if agent_key not in self.agents:
                    raise RuntimeError(f"Unknown agent: {agent_key}")
                agent_runner = self.agents[agent_key]
                raw_output = agent_runner.run(task_text, history=history or [])
                parser = self._resolve_step_parser()
                parsed = parser.parse(agent_key, raw_output) if parser is not None else self._default_parsed_step(raw_output)
                turn = FlowTurnResult(
                    turn_index=turn_index,
                    agent_key=agent_key,
                    task_text=task_text,
                    raw_output=raw_output,
                    parsed=parsed,
                )
                self._log_turn_result(turn)
                return turn

            @abstractmethod
            def execute(self, user_request: str, **kwargs: Any) -> FlowExecutionResult:
                raise NotImplementedError

            def run_with_trace(self, user_input: str, **kwargs: Any) -> FlowExecutionResult:
                return self.execute(user_input, **kwargs)

            def run(self, user_input: str, **kwargs: Any) -> str:
                result = self.run_with_trace(user_input, **kwargs)
                return result.final_output

            def __call__(self, user_input: str, **kwargs: Any) -> str:
                return self.run(user_input, **kwargs)
        '''
    ).strip() + "\n"


def _project_runtime_source() -> str:
    return textwrap.dedent(
        r'''
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
                runtime_system_prompt = self.tool_runtime.format_system_tool_prompt(
                    agent_id=self.agent_id
                )
                reply = self.agent.run(
                    merged_input,
                    runtime_system_prompt=runtime_system_prompt,
                )
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
                    reply = self.agent.run(
                        followup,
                        runtime_system_prompt=runtime_system_prompt,
                    )
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
        '''
    ).strip() + "\n"


def _run_project_source() -> str:
    return textwrap.dedent(
        '''
        from __future__ import annotations

        import sys
        from pathlib import Path

        PROJECT_ROOT = Path(__file__).resolve().parent
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))

        from project_runtime import main as run_cli


        if __name__ == "__main__":
            run_cli()
        '''
    ).strip() + "\n"


def runtime_files() -> Dict[str, str]:
    return {
        "project_runtime.py": _project_runtime_source(),
        "run_project.py": _run_project_source(),
        "Agent/__init__.py": "",
        "Agent/base_agent.py": _agent_base_source(),
        "Model/__init__.py": "",
        "Model/base_model.py": _model_base_source(),
        "Model/openai_model.py": _openai_model_source(),
        "Workflow/__init__.py": "",
        "Workflow/base_flow.py": _workflow_base_source(),
        "Config/__init__.py": "",
        "Config/settings.py": _settings_source(),
    }
