from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from backend.agent_run_time.agent_runtime import AgentRuntimeRegistry
from backend.agent_run_time.lsm_layer import LSMFallbackLayer, LSMRepairRequest
from backend.tools.catalog import create_default_runtime_tools
from backend.tools.core import BackendTool
from backend.tools.runtime_shared import GatewayCaller, ProviderCaller
from backend.tools.tool_bridge import ParsedToolCall, ParsedToolRequest, ToolBridge


@dataclass
class ToolExecutionObservation:
    tool_name: str
    status: str
    raw_call: str
    args: List[Any] = field(default_factory=list)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    result: Any = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "tool_name": self.tool_name,
            "status": self.status,
            "raw_call": self.raw_call,
        }
        if self.args:
            payload["args"] = self.args
        if self.kwargs:
            payload["kwargs"] = self.kwargs
        if self.error is not None:
            payload["error"] = self.error
        else:
            payload["result"] = self.result
        return payload


@dataclass
class RuntimeToolStep:
    has_tool_call: bool
    has_tool_request: bool = False
    parsed_requests: List[ParsedToolRequest] = field(default_factory=list)
    parsed_calls: List[ParsedToolCall] = field(default_factory=list)
    observations: List[ToolExecutionObservation] = field(default_factory=list)
    feedback_to_llm: Optional[str] = None
    needs_llm_retry: bool = False
    terminate: bool = False
    repair: Optional[LSMRepairRequest] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "has_tool_request": self.has_tool_request,
            "has_tool_call": self.has_tool_call,
            "parsed_requests": [
                {
                    "request_name": request.request_name,
                    "args": request.args,
                    "kwargs": request.kwargs,
                    "raw": request.raw,
                }
                for request in self.parsed_requests
            ],
            "parsed_calls": [
                {
                    "tool_name": call.tool_name,
                    "args": call.args,
                    "kwargs": call.kwargs,
                    "raw": call.raw,
                }
                for call in self.parsed_calls
            ],
            "observations": [item.to_dict() for item in self.observations],
            "feedback_to_llm": self.feedback_to_llm,
            "needs_llm_retry": self.needs_llm_retry,
            "terminate": self.terminate,
            "repair": None
            if self.repair is None
            else {
                "reason": self.repair.reason,
                "message": self.repair.message,
                "raw_call": self.repair.raw_call,
                "available_tools": self.repair.available_tools,
            },
        }


class AgentToolRuntime:
    """Runtime helper that executes LLM-emitted tool_call(...) text."""

    def __init__(
        self,
        tools: Optional[Iterable[BackendTool]] = None,
        *,
        agent_registry: Optional[AgentRuntimeRegistry] = None,
        lsm_layer: Optional[LSMFallbackLayer] = None,
    ) -> None:
        self.bridge = ToolBridge()
        self.agent_registry = agent_registry
        self.lsm_layer = lsm_layer or LSMFallbackLayer()
        self._backend_tools: Dict[str, BackendTool] = {}
        for tool in tools or []:
            self.register_backend_tool(tool)

    @classmethod
    def from_default_tools(
        cls,
        *,
        gateway: Optional[GatewayCaller] = None,
        web_search_provider: Optional[ProviderCaller] = None,
        image_provider: Optional[ProviderCaller] = None,
        pdf_provider: Optional[ProviderCaller] = None,
        image_generate_provider: Optional[ProviderCaller] = None,
        music_generate_provider: Optional[ProviderCaller] = None,
        video_generate_provider: Optional[ProviderCaller] = None,
        tts_provider: Optional[ProviderCaller] = None,
        lsm_layer: Optional[LSMFallbackLayer] = None,
        agent_registry: Optional[AgentRuntimeRegistry] = None,
    ) -> "AgentToolRuntime":
        tools = create_default_runtime_tools(
            gateway=gateway,
            web_search_provider=web_search_provider,
            image_provider=image_provider,
            pdf_provider=pdf_provider,
            image_generate_provider=image_generate_provider,
            music_generate_provider=music_generate_provider,
            video_generate_provider=video_generate_provider,
            tts_provider=tts_provider,
        )
        return cls(tools, agent_registry=agent_registry, lsm_layer=lsm_layer)

    def register_backend_tool(self, tool: BackendTool) -> None:
        self._backend_tools[tool.name] = tool
        self.bridge.register_tool(tool.name, self._call_backend_tool(tool))

    def available_tool_names(self, agent_id: Optional[str] = None) -> List[str]:
        if self.agent_registry is None or agent_id is None:
            return sorted(self._backend_tools)
        allowed = set(self.agent_registry.tool_names_for_agent(agent_id))
        return sorted(tool_name for tool_name in self._backend_tools if tool_name in allowed)

    def run_tool_calls(self, llm_output: str, *, agent_id: Optional[str] = None) -> RuntimeToolStep:
        """Parse, execute, and format feedback for one LLM output."""

        has_tool_request = self.bridge.contains_tool_request(llm_output)
        has_tool_call = self.bridge.contains_tool_call(llm_output)
        if has_tool_request:
            raw_request_spans = self.bridge._extract_request_spans(llm_output)
            requests = self.bridge.parse_tool_requests(llm_output)
            if not requests or len(requests) != len(raw_request_spans):
                return RuntimeToolStep(
                    has_tool_request=True,
                    has_tool_call=has_tool_call,
                    feedback_to_llm=self._format_tool_request_parse_error(),
                    needs_llm_retry=True,
                )
            feedback = self._format_tool_requests(requests, agent_id=agent_id)
            return RuntimeToolStep(
                has_tool_request=True,
                has_tool_call=has_tool_call,
                parsed_requests=requests,
                feedback_to_llm=feedback,
                needs_llm_retry=True,
            )

        if not has_tool_call:
            return RuntimeToolStep(has_tool_call=False)

        raw_call_spans = self.bridge._extract_call_spans(llm_output)
        calls = self.bridge.parse_tool_calls(llm_output)
        if not calls or len(calls) != len(raw_call_spans):
            repair = self.lsm_layer.parse_error(
                text=llm_output,
                bridge=self.bridge,
                available_tools=self.available_tool_names(agent_id),
            )
            return RuntimeToolStep(
                has_tool_call=True,
                feedback_to_llm=repair.message,
                needs_llm_retry=True,
                repair=repair,
            )

        observations: List[ToolExecutionObservation] = []
        repair: Optional[LSMRepairRequest] = None
        terminate = False

        for call in calls:
            if not self._has_available_tool(call.tool_name, agent_id=agent_id):
                repair = self.lsm_layer.unknown_tool(
                    tool_name=call.tool_name,
                    raw_call=call.raw,
                    original_text=llm_output,
                    available_tools=self.available_tool_names(agent_id),
                )
                observations.append(
                    ToolExecutionObservation(
                        tool_name=call.tool_name,
                        status="error",
                        raw_call=call.raw,
                        args=list(call.args),
                        kwargs=dict(call.kwargs),
                        error=repair.message,
                    )
                )
                break

            try:
                result = self.bridge.execute_call(call)
                if isinstance(result, dict) and result.get("terminate") is True:
                    terminate = True
                observations.append(
                    ToolExecutionObservation(
                        tool_name=call.tool_name,
                        status="ok",
                        raw_call=call.raw,
                        result=result,
                    )
                )
            except Exception as exc:
                repair = self.lsm_layer.execution_error(
                    tool_name=call.tool_name,
                    error=exc,
                    raw_call=call.raw,
                    original_text=llm_output,
                    available_tools=self.available_tool_names(agent_id),
                )
                observations.append(
                    ToolExecutionObservation(
                        tool_name=call.tool_name,
                        status="error",
                        raw_call=call.raw,
                        args=list(call.args),
                        kwargs=dict(call.kwargs),
                        error=repair.message,
                    )
                )
                break

        feedback = repair.message if repair else self._format_observations(observations)
        return RuntimeToolStep(
            has_tool_call=True,
            parsed_calls=calls,
            observations=observations,
            feedback_to_llm=feedback,
            needs_llm_retry=not terminate,
            terminate=terminate,
            repair=repair,
        )

    def _has_available_tool(self, tool_name: str, *, agent_id: Optional[str] = None) -> bool:
        if not self.bridge.has_tool(tool_name):
            return False
        if self.agent_registry is None or agent_id is None:
            return True
        return tool_name in set(self.available_tool_names(agent_id))

    @staticmethod
    def _call_backend_tool(tool: BackendTool):
        def call(*args: Any, **kwargs: Any) -> Dict[str, Any]:
            params = AgentToolRuntime._coerce_tool_params(args, kwargs)
            return tool.run(**params)

        return call

    @staticmethod
    def _coerce_tool_params(args: tuple[Any, ...], kwargs: Dict[str, Any]) -> Dict[str, Any]:
        if not args:
            return dict(kwargs)
        if len(args) == 1 and isinstance(args[0], dict):
            params = dict(args[0])
            params.update(kwargs)
            return params
        raise ValueError("Backend tool calls require keyword arguments or one dict positional argument.")

    @staticmethod
    def _format_observations(observations: Iterable[ToolExecutionObservation]) -> str:
        lines: List[str] = []
        for observation in observations:
            if observation.status == "ok":
                payload = json.dumps(observation.result, ensure_ascii=False, default=str)
                lines.append(f"Observation: [{observation.tool_name}] {payload}")
            else:
                lines.append(f"Observation: [{observation.tool_name}] [ERROR] {observation.error}")
        return "\n".join(lines)

    def _format_tool_requests(
        self,
        requests: Iterable[ParsedToolRequest],
        *,
        agent_id: Optional[str] = None,
    ) -> str:
        lines: List[str] = []
        for request in requests:
            if request.request_name != "available_tools":
                lines.append(
                    "Observation: [TOOL_REQUEST_ERROR] "
                    f"Unsupported tool_request `{request.request_name}`. "
                    'Use tool_request("available_tools").'
                )
                continue
            lines.append(self._format_available_tools(agent_id=agent_id))
        return "\n".join(lines)

    def _format_available_tools(self, *, agent_id: Optional[str] = None) -> str:
        tool_lines = [
            f'  "{tool_name}",'
            for tool_name in self.available_tool_names(agent_id)
        ]
        if not tool_lines:
            tool_lines = ["  # none"]
        lines = [
            "System Parsed:",
            "available_tools = [",
            *tool_lines,
            "]",
        ]
        prompt_lines = self._format_tool_prompt_lines(agent_id=agent_id)
        if prompt_lines:
            lines.extend(["tool_prompts = {", *prompt_lines, "}"])
        lines.append('tool_call_format = \'tool_call("tool_name", key=value)\'')
        return "\n".join(lines)

    def _format_tool_prompt_lines(self, *, agent_id: Optional[str] = None) -> List[str]:
        if self.agent_registry is None:
            return []
        lines: List[str] = []
        for tool_name in self.available_tool_names(agent_id):
            prompt = self.agent_registry.tool_prompt(tool_name)
            if prompt:
                lines.append(f"  {json.dumps(tool_name, ensure_ascii=False)}: {json.dumps(prompt, ensure_ascii=False)},")
        return lines

    @staticmethod
    def _format_tool_request_parse_error() -> str:
        return "\n".join(
            [
                "Observation: [TOOL_REQUEST_PARSE_ERROR] tool_request could not be parsed.",
                'Required format: tool_request("available_tools").',
            ]
        )


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Execute backend tool_call(...) snippets from LLM output.")
    parser.add_argument("text", nargs="?", help="LLM output text. If omitted, stdin is used.")
    parser.add_argument("--pretty", action="store_true", help="Print formatted feedback_to_llm only.")
    args = parser.parse_args(argv)

    llm_output = args.text if args.text is not None else sys.stdin.read()
    runtime = AgentToolRuntime.from_default_tools()
    step = runtime.run_tool_calls(llm_output)

    if args.pretty:
        print(step.feedback_to_llm or "")
    else:
        print(json.dumps(step.to_dict(), ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
