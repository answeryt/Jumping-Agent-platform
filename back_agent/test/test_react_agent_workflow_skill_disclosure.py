from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, List

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import context.react_agent_skill_context as skill_context_module
from agent.base_agent import PromptLoader
from agent.react import ReactAgentConfig
from Model.base_model import BaseModel, ChatMessage, ModelResponse
from skill.skill_registry import Skill
from workflow.react_agent_workflow import ReactAgentWorkflow


class _ScriptedModel(BaseModel):
    def __init__(self, responses: List[str]) -> None:
        self._responses = list(responses)
        self.message_counts: List[int] = []
        self.message_snapshots: List[List[ChatMessage]] = []
        self._stream = False

    def set_stream_mode(self, stream: bool) -> None:
        self._stream = stream

    def chat(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        stream: bool | None = None,
        **kwargs: Any,
    ) -> ModelResponse:
        self.message_counts.append(len(messages))
        self.message_snapshots.append([dict(message) for message in messages])
        if not self._responses:
            raise AssertionError("No scripted model response left.")
        return {"content": self._responses.pop(0)}

    def chat_with_system(
        self,
        system_message: str,
        user_message: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> ModelResponse:
        if not self._responses:
            raise AssertionError("No scripted model response left.")
        return {"content": self._responses.pop(0)}

    def get_model_name(self) -> str:
        return "scripted-model"


def _build_flow(model: BaseModel) -> ReactAgentWorkflow:
    prompt_loader = PromptLoader(prompt_dir=PROJECT_ROOT / "prompt")
    config = ReactAgentConfig(prompt_file="react_agent_prompt.md")
    return ReactAgentWorkflow(model=model, agent_config=config, prompt_loader=prompt_loader)


@pytest.fixture()
def fake_skill_registry(monkeypatch: pytest.MonkeyPatch) -> list[Skill]:
    common_skill = Skill(
        name="common-agent-skill",
        path=Path("common_agent_skill.md"),
        content=(
            "---\n"
            "name: common-agent-skill\n"
            "description: common skill\n"
            "---\n"
            "\n"
            "## Common\n"
            "Use the repository tools."
        ),
        description="common skill",
    )
    single_skill = Skill(
        name="single-agent-skill",
        path=Path("single_agent_skill.md"),
        content=(
            "---\n"
            "name: single-agent-skill\n"
            "description: single skill\n"
            "---\n"
            "\n"
            "## Single\n"
            "Answer the user directly."
        ),
        description="single skill",
    )
    skills = [common_skill, single_skill]

    monkeypatch.setattr(skill_context_module, "list_skills", lambda: skills)

    def _get_skill(name: str) -> Skill:
        lookup = name.strip().lower()
        for skill in skills:
            if skill.name.strip().lower() == lookup:
                return skill
        raise KeyError(name)

    monkeypatch.setattr(skill_context_module, "get_skill", _get_skill)
    return skills


def test_workflow_resets_skill_disclosure_between_runs(fake_skill_registry: list[Skill]):
    model = _ScriptedModel(
        responses=[
            "Final Answer: first run",
            "Final Answer: second run",
        ]
    )
    flow = _build_flow(model)

    first = flow.run("[SELECT_SKILL]common-agent-skill[/SELECT_SKILL]\n[SELECT_SKILL]single-agent-skill[/SELECT_SKILL]\nfirst task")
    second = flow.run("[SELECT_SKILL]common-agent-skill[/SELECT_SKILL]\n[SELECT_SKILL]single-agent-skill[/SELECT_SKILL]\nsecond task")

    assert first == "Final Answer: first run"
    assert second == "Final Answer: second run"
    assert model.message_counts == [3, 3]
    assert "Observation: [SKILL_SELECTED] common-agent-skill, single-agent-skill" in model.message_snapshots[0][-1]["content"]
    assert "Observation: [SKILL_SELECTED] common-agent-skill, single-agent-skill" in model.message_snapshots[1][-1]["content"]


def test_workflow_continues_when_skill_is_reselected_in_same_run(fake_skill_registry: list[Skill]):
    model = _ScriptedModel(
        responses=[
            "Plan:\n1. load skill\nThought: continue\nAction: [SELECT_SKILL]common-agent-skill[/SELECT_SKILL]",
            "Final Answer: continued after duplicate skill selection",
        ]
    )
    flow = _build_flow(model)

    answer = flow.run("[SELECT_SKILL]common-agent-skill[/SELECT_SKILL]\n[SELECT_SKILL]single-agent-skill[/SELECT_SKILL]\ncomplete the agent")

    assert answer == "Final Answer: continued after duplicate skill selection"
    assert model.message_counts == [3, 5]
    assert "Observation: [SKILL_SELECTED] common-agent-skill" in model.message_snapshots[1][-1]["content"]
    assert "## Skill:" not in model.message_snapshots[1][-1]["content"]
