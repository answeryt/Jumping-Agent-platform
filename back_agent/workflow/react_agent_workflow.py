from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from agent.base_agent import PromptLoader
from agent.react import ReactAgent, ReactAgentConfig
from context.react_agent_skill_context import ReactAgentSkillContextManager
from Model.base_model import BaseModel, ChatMessage
from tools.shell_tool_adapter import build_sandbox_bridge
from tools.tool_bridge import ParsedToolCall, ToolBridge
from workflow.baseflow import BaseFlow


_MAX_REACT_ITERATIONS = 15


class _RuntimeReactAgent(ReactAgent):
    """为 workflow 提供可运行的 ReactAgent 默认实现。"""

    def run(self, user_input: str, **kwargs: Any) -> str:
        """单轮快捷接口：用于 skill 选择等单次推理场景。"""
        if self.model is None:
            raise ValueError("ReactAgent 运行失败: model 不能为空。")

        system_prompt = self.load_prompt()
        retries = int(kwargs.pop("max_retries", self.config.max_retries))
        last_error: Optional[Exception] = None

        for _ in range(max(1, retries + 1)):
            try:
                response = self.model.chat_with_system(
                    system_message=system_prompt,
                    user_message=user_input,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                    stream=self.config.stream,
                    **kwargs,
                )
                content = str(response.get("content", "")).strip()
                if content:
                    return content
                raise RuntimeError("模型返回了空内容。")
            except Exception as exc:  # noqa: PERF203
                last_error = exc

        raise RuntimeError(f"ReactAgent 调用失败: {last_error}") from last_error

    def run_turn(self, messages: List[ChatMessage], **kwargs: Any) -> str:
        """多轮推理原语：接受完整 messages 历史，执行单次推理。

        供 _run_with_tools ReAct 循环逐轮调用，调用方负责维护 messages 列表。
        kwargs 中的 stop、temperature 等参数直接透传给 model.chat()。
        """
        if self.model is None:
            raise ValueError("ReactAgent 运行失败: model 不能为空。")

        response = self.model.chat(
            messages=messages,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            stream=self.config.stream,
            **kwargs,
        )
        content = str(response.get("content", "")).strip()
        if not content:
            raise RuntimeError("模型返回了空内容。")
        return content


@dataclass
class ReactAgentWorkflowConfig:
    """ReactAgentWorkflow 的配置。"""

    flow_type: str = "react"
    enable_progressive_skill_disclosure: bool = True


class ReactAgentWorkflow(BaseFlow):
    """ReAct 具体 flow 实现，属于下游可直接运行脚本。"""

    def __init__(
        self,
        agent: Optional[ReactAgent] = None,
        model: Optional[BaseModel] = None,
        agent_config: Optional[ReactAgentConfig] = None,
        prompt_loader: Optional[PromptLoader] = None,
        config: Optional[ReactAgentWorkflowConfig] = None,
    ) -> None:
        workflow_config = config or ReactAgentWorkflowConfig()
        super().__init__(flow_type=workflow_config.flow_type)

        self.config = workflow_config
        self.agent = agent or _RuntimeReactAgent(
            model=model,
            config=agent_config,
            prompt_loader=prompt_loader,
        )
        self.skill_context_manager = ReactAgentSkillContextManager()
        self.tool_bridge = ToolBridge()
        self._register_default_tools()

    def run(self, user_input: str, **kwargs: Any) -> str:
        progressive_enabled = bool(
            kwargs.pop(
                "enable_progressive_skill_disclosure",
                self.config.enable_progressive_skill_disclosure,
            )
        )
        return self._run_with_tools(
            user_input=user_input,
            progressive_skill_disclosure=progressive_enabled,
            **kwargs,
        )

    def _register_default_tools(self) -> None:
        sandbox_bridge, _ = build_sandbox_bridge()

        combined = ToolBridge()

        # 沙盒读写工具（load_project / tree / find / get / config /
        #               write_file / patch_symbol / replace_lines）
        for name, func in sandbox_bridge._tools.items():
            combined.register_tool(name, func)

        self.tool_bridge = combined

    def _run_with_tools(
        self,
        user_input: str,
        progressive_skill_disclosure: bool = True,
        **kwargs: Any,
    ) -> str:
        """真正的 ReAct 循环。

        每轮 LLM 输出到 Action 后由 stop 序列截断，workflow 执行真实工具，
        将真实 Observation 注入 messages，再驱动下一轮推理，直到出现
        Final Answer 或无工具调用或达到最大轮次为止。
        """
        if not isinstance(self.agent, _RuntimeReactAgent):
            # 外部传入了不支持 run_turn 的自定义 agent，降级为单次模式
            first_reply = self.agent.run(user_input=user_input, **kwargs)
            calls = self.tool_bridge.parse_tool_calls(first_reply)
            if not calls:
                return first_reply
            observations = self._execute_tool_calls(calls)
            obs_text = _format_observation_text(observations)
            followup = (
                f"{first_reply}\n\n{obs_text}\n\n"
                "请基于以上工具执行结果，输出 Final Answer。"
            )
            return self.agent.run(user_input=followup, **kwargs)

        system_prompt = self.skill_context_manager.enrich_system_prompt(self.agent.load_prompt())
        initial_user_input = user_input
        if progressive_skill_disclosure:
            metadata_context = self.skill_context_manager.build_initial_metadata_context()
            initial_user_input = _compose_user_input(
                user_input=user_input,
                context_block=metadata_context,
                title="Skill Metadata",
            )

        messages: List[ChatMessage] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": initial_user_input},
        ]

        # 如果用户消息本身携带了 [SELECT_SKILL] 标签（例如 orchestrator 构造的任务
        # 提示词），则在第一轮 LLM 调用前立即注入 skill 正文，无需等待 agent 主动
        # 在回复中请求，节省一轮往返并确保 agent 首轮就能读到完整 skill 内容。
        if progressive_skill_disclosure:
            pre_disclosure = self.skill_context_manager.disclose_from_agent_reply(user_input)
            if pre_disclosure.selected:
                pre_disclosure_context = self.skill_context_manager.build_disclosure_context(
                    pre_disclosure
                )
                messages.append(
                    {
                        "role": "user",
                        "content": _format_skill_disclosure_text(
                            selected=pre_disclosure.selected,
                            disclosure_context=pre_disclosure_context,
                        ),
                    }
                )

        max_iterations = int(kwargs.pop("max_react_iterations", _MAX_REACT_ITERATIONS))
        last_reply = ""

        for _ in range(max_iterations):
            reply = self.agent.run_turn(messages, stop=["\nObservation:"], **kwargs)
            messages.append({"role": "assistant", "content": reply})
            last_reply = reply

            skill_selected = False
            if progressive_skill_disclosure:
                disclosure = self.skill_context_manager.disclose_from_agent_reply(reply)
                if disclosure.selected:
                    skill_selected = True
                    disclosure_context = self.skill_context_manager.build_disclosure_context(disclosure)
                    messages.append(
                        {
                            "role": "user",
                            "content": _format_skill_disclosure_text(
                                selected=disclosure.selected,
                                disclosure_context=disclosure_context,
                            ),
                        }
                    )

            calls = self.tool_bridge.parse_tool_calls(reply)
            if calls:
                observations = self._execute_tool_calls(calls)
                obs_text = _format_observation_text(observations)
                messages.append({"role": "user", "content": obs_text})
                continue

            if self.tool_bridge.contains_tool_call(reply):
                # reply 中含有 tool_call( 但解析失败（最常见原因：Windows 路径中的
                # 反斜杠包含 \U \D 等非法 Python 转义序列），将错误作为 Observation
                # 反馈给 Agent，让它有机会修正后重试。
                parse_error_obs = (
                    "Observation: [PARSE_ERROR] tool_call 解析失败。"
                    "最可能的原因：路径字符串中含有 Windows 反斜杠（如 C:\\Users\\...），"
                    "其中 \\U、\\D 等字符是非法的 Python 字符串转义序列。"
                    "请将所有路径改为正斜杠（如 C:/Users/...）后重试。"
                )
                messages.append({"role": "user", "content": parse_error_obs})
                continue

            if skill_selected:
                continue

            if "Final Answer:" in reply:
                return reply

            return reply

        return last_reply

    def _execute_tool_calls(self, calls: List[ParsedToolCall]) -> List[Dict[str, Any]]:
        observations: List[Dict[str, Any]] = []
        for call in calls:
            if not self.tool_bridge.has_tool(call.tool_name):
                observations.append(
                    {
                        "tool_name": call.tool_name,
                        "status": "error",
                        "error": f"未注册的工具: {call.tool_name}",
                        "args": list(call.args),
                        "kwargs": dict(call.kwargs),
                    }
                )
                continue

            try:
                result = self.tool_bridge.execute_call(call)
                observations.append(
                    {
                        "tool_name": call.tool_name,
                        "status": "ok",
                        "result": result,
                    }
                )
            except Exception as exc:
                observations.append(
                    {
                        "tool_name": call.tool_name,
                        "status": "error",
                        "error": str(exc),
                        "args": list(call.args),
                        "kwargs": dict(call.kwargs),
                    }
                )
        return observations


def _compose_user_input(
    user_input: str,
    context_block: str,
    title: str,
    prior_answer: Optional[str] = None,
) -> str:
    """拼接 workflow 注入上下文，不承载 skill 解析逻辑。"""
    parts = [f"[{title}]\n{context_block}", f"[User Task]\n{user_input}"]
    if prior_answer:
        parts.append(f"[Prior Agent Reply]\n{prior_answer}")
        parts.append("[Instruction]\n基于已选择的 skill 完整内容，输出最终回答。")
    return "\n\n".join(parts)


def _format_observation_text(observations: List[Dict[str, Any]]) -> str:
    """将工具执行结果格式化为 ReAct 格式的 Observation 文本，注入 messages。"""
    lines: List[str] = []
    for item in observations:
        if item.get("status") == "ok":
            result = item.get("result", {})
            if isinstance(result, dict):
                # ShellResult dict: 优先 stdout，无输出时附上 stderr，都空则显示退出码
                output = result.get("stdout", "").strip()
                stderr = result.get("stderr", "").strip()
                if not output and stderr:
                    output = f"[stderr] {stderr}"
                elif output and stderr:
                    output = f"{output}\n[stderr] {stderr}"
                if not output:
                    output = f"[exit {result.get('returncode', '?')}]"
            else:
                output = str(result)
            lines.append(f"Observation: {output}")
        else:
            lines.append(f"Observation: [ERROR] {item.get('error', '未知错误')}")
    return "\n".join(lines)


def _format_skill_disclosure_text(selected: List[str], disclosure_context: str) -> str:
    """将 skill 选择与正文加载结果转成下一轮可消费的 Observation。"""
    selected_text = ", ".join(selected)
    return (
        f"Observation: [SKILL_SELECTED] {selected_text}\n\n"
        f"{disclosure_context}\n\n"
        "请继续基于已加载的 skill 执行后续推理；"
        "如需操作仓库，请先输出 Action: tool_call(...)。"
    )

