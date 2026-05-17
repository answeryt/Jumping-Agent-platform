from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from agent.base_agent import PromptLoader
from agent.react import ReactAgent, ReactAgentConfig
from context.react_agent_skill_context import ReactAgentSkillContextManager
from Model.base_model import BaseModel, ChatMessage
from tools.shell_tool_adapter import build_sandbox_bridge
from tools.tool_bridge import ParsedToolCall, ToolBridge
from workflow.baseflow import BaseFlow


_MAX_REACT_ITERATIONS = 100


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

    @staticmethod
    def _log_runtime(message: str) -> None:
        print(message, flush=True)

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
        self.skill_context_manager.reset_runtime_state()
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
        """ReAct 循环执行入口。

        workflow 仍按多轮 messages 驱动模型与工具交互，但更适合将其理解为：
        先形成必要的共享判断，再按任务需要推进成组实现与集中收尾，
        而不是在同一组共享文件上反复往返。
        """
        self._log_runtime("[Workflow] Starting ReAct workflow")
        self._log_runtime(f"[Workflow] progressive_skill_disclosure={progressive_skill_disclosure}")
        self._log_runtime(f"[Workflow] user_input_preview={_preview_text(user_input)}")
        if not isinstance(self.agent, _RuntimeReactAgent):
            # 外部传入了不支持 run_turn 的自定义 agent，降级为单次模式
            self._log_runtime("[Workflow] fallback single-turn mode")
            first_reply = self.agent.run(user_input=user_input, **kwargs)
            self._log_runtime(f"[Workflow] first_reply_preview={_preview_text(first_reply)}")
            calls = self.tool_bridge.parse_tool_calls(first_reply)
            if not calls:
                self._log_runtime("[Workflow] no tool call in fallback reply")
                return first_reply
            self._log_runtime(f"[Workflow] fallback parsed_tool_calls={len(calls)}")
            observations = self._execute_tool_calls(calls)
            obs_text = _format_observation_text(observations)
            self._log_runtime(f"[Workflow] fallback observation_preview={_preview_text(obs_text)}")
            followup = (
                f"{first_reply}\n\n{obs_text}\n\n"
                "请基于以上工具执行结果，输出 Final Answer。"
            )
            final_reply = self.agent.run(user_input=followup, **kwargs)
            self._log_runtime(f"[Workflow] fallback final_reply_preview={_preview_text(final_reply)}")
            return final_reply

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
            {
                "role": "user",
                "content": (
                    "[Execution Style]\n"
                    "若任务中存在共享 contract、同构骨架或可成组处理的文件，"
                    "可以先形成一次性分析摘要，再批量推进实现，最后集中做检查与收尾。"
                ),
            },
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

        for iteration in range(1, max_iterations + 1):
            self._log_runtime(
                f"[Workflow][Iteration {iteration}] sending {len(messages)} messages to model"
            )
            reply = self.agent.run_turn(messages, stop=["\nObservation:"], **kwargs)
            messages.append({"role": "assistant", "content": reply})
            last_reply = reply
            self._log_runtime(
                f"[Workflow][Iteration {iteration}] model_reply_preview={_preview_text(reply)}"
            )

            skill_selected = False
            requested_skill_names: List[str] = []
            if progressive_skill_disclosure:
                requested_skill_names = self.skill_context_manager.extract_selected_skill_names(reply)
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
                elif requested_skill_names:
                    skill_selected = True
                    messages.append(
                        {
                            "role": "user",
                            "content": _format_skill_already_loaded_text(requested_skill_names),
                        }
                    )

            # Check for Final Answer BEFORE parsing tool calls to avoid
            # false positives where Ellipsis literals (...) in the answer
            # text get parsed as tool_call(Ellipsis) and trigger a loop.
            if "Final Answer:" in reply:
                self._log_runtime(
                    f"[Workflow][Iteration {iteration}] final answer reached"
                )
                return reply

            calls = self.tool_bridge.parse_tool_calls(reply)
            if calls:
                self._log_runtime(
                    f"[Workflow][Iteration {iteration}] parsed_tool_calls={len(calls)}"
                )
                observations = self._execute_tool_calls(calls)
                obs_text = _format_observation_text(observations)
                self._log_runtime(
                    f"[Workflow][Iteration {iteration}] observation_preview={_preview_text(obs_text)}"
                )
                messages.append({"role": "user", "content": obs_text})
                continue

            if self.tool_bridge.contains_tool_call(reply):
                # reply 中含有 tool_call( 但解析失败（最常见原因：Windows 路径中的
                # 反斜杠包含 \U \D 等非法 Python 转义序列），将错误作为 Observation
                # 反馈给 Agent，让它有机会修正后重试。
                self._log_runtime(
                    f"[Workflow][Iteration {iteration}] tool_call detected but parsing failed"
                )
                parse_error_obs = (
                    "Observation: [PARSE_ERROR] tool_call 解析失败。"
                    "最可能的原因：路径字符串中含有 Windows 反斜杠（如 C:\\Users\\...），"
                    "其中 \\U、\\D 等字符是非法的 Python 字符串转义序列。"
                    "请将所有路径改为正斜杠（如 C:/Users/...）后重试。"
                )
                self._log_runtime(
                    f"[Workflow][Iteration {iteration}] observation_preview={_preview_text(parse_error_obs)}"
                )
                messages.append({"role": "user", "content": parse_error_obs})
                continue

            if skill_selected:
                self._log_runtime(
                    f"[Workflow][Iteration {iteration}] skill disclosure appended"
                )
                continue

            self._log_runtime(
                f"[Workflow][Iteration {iteration}] exiting without Final Answer"
            )
            return reply

        self._log_runtime("[Workflow] max iterations reached")
        return last_reply

    def _execute_tool_calls(self, calls: List[ParsedToolCall]) -> List[Dict[str, Any]]:
        observations: List[Dict[str, Any]] = []
        for index, call in enumerate(calls, start=1):
            self._log_runtime(
                "[Workflow][Tool {index}] executing {tool} args={args} kwargs={kwargs}".format(
                    index=index,
                    tool=call.tool_name,
                    args=_preview_text(_safe_json(call.args)),
                    kwargs=_preview_text(_safe_json(call.kwargs)),
                )
            )
            if not self.tool_bridge.has_tool(call.tool_name):
                error_message = f"未注册的工具: {call.tool_name}"
                self._log_runtime(f"[Workflow][Tool {index}] error={error_message}")
                observations.append(
                    {
                        "tool_name": call.tool_name,
                        "status": "error",
                        "error": error_message,
                        "args": list(call.args),
                        "kwargs": dict(call.kwargs),
                    }
                )
                continue

            try:
                result = self.tool_bridge.execute_call(call)
                self._log_runtime(
                    f"[Workflow][Tool {index}] result={_preview_text(_safe_json(result))}"
                )
                observations.append(
                    {
                        "tool_name": call.tool_name,
                        "status": "ok",
                        "result": result,
                    }
                )
            except Exception as exc:
                self._log_runtime(f"[Workflow][Tool {index}] error={exc}")
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


def _safe_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return str(value)


def _preview_text(value: Any, limit: int = 600) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\n", "\\n")
    if len(text) <= limit:
        return text
    return f"{text[:limit]} ...[truncated]"


def _normalize_observation_text(value: Any) -> str:
    text = str(value or "")
    text = text.replace("\\", "/")
    return text


def _format_tool_result(result: Dict[str, Any]) -> str:
    stdout = _normalize_observation_text(result.get("stdout", "")).strip()
    stderr = _normalize_observation_text(result.get("stderr", "")).strip()
    returncode = result.get("returncode", "?")

    parts: List[str] = []
    if stdout:
        parts.append(f"stdout={stdout}")
    if stderr:
        parts.append(f"stderr={stderr}")
    if not parts:
        parts.append(f"exit={returncode}")
    elif returncode not in (None, 0, "0"):
        parts.append(f"exit={returncode}")
    return " | ".join(parts)


def _format_observation_text(observations: List[Dict[str, Any]]) -> str:
    """将工具执行结果格式化为 ReAct 格式的 Observation 文本，注入 messages。"""
    lines: List[str] = []
    for item in observations:
        tool_name = item.get("tool_name", "unknown")
        if item.get("status") == "ok":
            result = item.get("result", {})
            if isinstance(result, dict):
                output = _format_tool_result(result)
            else:
                output = str(result)
            lines.append(f"Observation: [{tool_name}] {output}")
        else:
            error_text = _normalize_observation_text(item.get('error', '未知错误'))
            lines.append(f"Observation: [{tool_name}] [ERROR] {error_text}")
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


def _format_skill_already_loaded_text(selected: List[str]) -> str:
    """当 skill 已在当前请求中加载时，回注 observation 以驱动下一轮推理。"""
    selected_text = ", ".join(selected)
    return (
        f"Observation: [SKILL_SELECTED] {selected_text}\n\n"
        "该 skill 已在当前请求中加载，请直接基于已加载的 skill 继续后续推理；"
        "如需操作仓库，请先输出 Action: tool_call(...)。"
    )
