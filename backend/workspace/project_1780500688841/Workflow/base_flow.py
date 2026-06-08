from __future__ import annotations

import importlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol

class StepParserProtocol(Protocol):
    def parse(self, agent_type: str, raw_text: str) -> "ParsedFlowStep":
        ...


@dataclass
class AgentContext:
    goal: str = "none"
    user_request: str = "none"
    known_info: str = "none"
    phase: str = "none"
    constraints: str = "none"


@dataclass
class AgentOutput:
    result: str = "none"


@dataclass
class AgentTrace:
    steps: str = "none"
    skills_used: str = "none"


@dataclass
class AgentHandoff:
    next_agent: str = "none"
    next_task: str = "none"
    notes: str = "none"


@dataclass
class AgentState:
    context: AgentContext
    output: AgentOutput
    trace: AgentTrace
    handoff: AgentHandoff


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
            state=AgentState(
                context=AgentContext(),
                output=AgentOutput(result=raw_output or "none"),
                trace=AgentTrace(),
                handoff=AgentHandoff(),
            ),
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
