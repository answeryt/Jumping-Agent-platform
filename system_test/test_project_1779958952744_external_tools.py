"""
End-to-end test: run a generated project agent with the project's actual model
configuration and verify it can invoke mounted backend external tools.

Run:
  python system_test/test_project_1779958952744_external_tools.py

This script intentionally does not edit generated Agent files. The generated
agent is instantiated with backend/workspace/project_1779958952744/Model/OpenAIModel,
so model credentials and options come from that generated project.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import threading
from dataclasses import dataclass
from contextlib import contextmanager
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GENERATED_PROJECT_ROOT = PROJECT_ROOT / "backend" / "workspace" / "project_1779958952744"
PDF_FIXTURE = PROJECT_ROOT / "（2026.5.31）公路隧道下穿高压输电铁塔施工风险分析及防控技术(2)(1).pdf"
VOICE_FIXTURE = PROJECT_ROOT / "7614053350010588425.voice.wav"

for _path in (PROJECT_ROOT, GENERATED_PROJECT_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from Agent.base_agent import BaseAgent, PromptLoader  # type: ignore[import-not-found]  # noqa: E402
from backend.agent_run_time import AgentRuntimeRegistry, AgentToolRuntime  # noqa: E402
from Model.openai_model import OpenAIModel  # type: ignore[import-not-found]  # noqa: E402
from project_runtime import RuntimeAgentRunner, _discover_agent_classes, load_build_plan  # type: ignore[import-not-found]  # noqa: E402


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


EXTERNAL_TOOL_NAMES = [
    "web_search",
    "web_fetch",
    "image",
    "pdf",
    "image_generate",
    "music_generate",
    "video_generate",
    "tts",
]


@dataclass(frozen=True)
class ToolScenario:
    tool: str
    question: str


class RecordingToolRuntime:
    """Proxy around AgentToolRuntime that keeps every tool execution step."""

    def __init__(self, runtime: AgentToolRuntime) -> None:
        self.runtime = runtime
        self.steps = []

    def run_tool_calls(self, llm_output: str, *, agent_id: Optional[str] = None):
        step = self.runtime.run_tool_calls(llm_output, agent_id=agent_id)
        self.steps.append(step)
        return step


@contextmanager
def _local_web_page() -> Iterator[str]:
    with tempfile.TemporaryDirectory(prefix="external-tool-web-fetch-") as tmp:
        root = Path(tmp)
        (root / "index.html").write_text(
            "<html><body><h1>Backend tool smoke page</h1><p>web_fetch reached local HTTP.</p></body></html>",
            encoding="utf-8",
        )

        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                super().__init__(*args, directory=str(root), **kwargs)

            def log_message(self, _format: str, *_args: Any) -> None:
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}/index.html"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


@contextmanager
def _local_image_file() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="external-tool-image-") as tmp:
        image_path = Path(tmp) / "sample_architecture.svg"
        image_path.write_text(
            """<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360">
  <rect width="640" height="360" fill="#f5f7fb"/>
  <rect x="60" y="120" width="130" height="70" fill="#d9e8ff" stroke="#3465a4"/>
  <text x="125" y="160" text-anchor="middle" font-size="18">User</text>
  <rect x="255" y="120" width="130" height="70" fill="#d8f0df" stroke="#2e7d32"/>
  <text x="320" y="160" text-anchor="middle" font-size="18">Agent</text>
  <rect x="450" y="120" width="130" height="70" fill="#fff1cc" stroke="#ad7b00"/>
  <text x="515" y="160" text-anchor="middle" font-size="18">Tools</text>
  <path d="M190 155 H255 M385 155 H450" stroke="#333" stroke-width="3" marker-end="url(#arrow)"/>
  <defs>
    <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="#333"/>
    </marker>
  </defs>
</svg>""",
            encoding="utf-8",
        )
        yield image_path


def _build_tool_runtime() -> AgentToolRuntime:
    return AgentToolRuntime.from_default_tools(agent_registry=AgentRuntimeRegistry())


def _external_tools_from_build_plan(agent_name: str) -> List[str]:
    for item in load_build_plan().get("agents") or []:
        if item.get("agent_name") == agent_name:
            configured = [str(name) for name in item.get("tools") or []]
            return [name for name in configured if name in EXTERNAL_TOOL_NAMES]
    return []


def _make_agent(agent_name: str) -> BaseAgent:
    agent_classes = _discover_agent_classes()
    if agent_name not in agent_classes:
        raise AssertionError(f"Generated agent not found: {agent_name}. Available: {sorted(agent_classes)}")
    prompt_loader = PromptLoader(prompt_dir=GENERATED_PROJECT_ROOT / "Prompt")
    return agent_classes[agent_name](model=OpenAIModel(), prompt_loader=prompt_loader)


def _register_agent(runtime: AgentToolRuntime, agent_name: str, tools: Iterable[str]) -> str:
    if runtime.agent_registry is None:
        raise AssertionError("AgentToolRuntime was built without an AgentRuntimeRegistry")
    return runtime.agent_registry.register_agent(agent_name, tools)


def _tool_scenarios(web_fetch_url: str, image_path: Path) -> Dict[str, ToolScenario]:
    pdf_path = str(PDF_FIXTURE)
    voice_path = str(VOICE_FIXTURE)
    image_file = str(image_path)
    return {
        "web_search": ToolScenario(
            tool="web_search",
            question=(
                "请先调用 web_search 工具搜索“2026年美国访问的国家是哪些”，"
                "工具返回后再给出关键国家列表和依据。"
            ),
        ),
        "web_fetch": ToolScenario(
            tool="web_fetch",
            question=(
                f"请先调用 web_fetch 工具抓取 {web_fetch_url}，"
                "判断页面是否说明 web_fetch 已经访问到本地 HTTP 内容。"
            ),
        ),
        "image": ToolScenario(
            tool="image",
            question=(
                f"请先调用 image 工具分析这张测试架构图图片：{image_file}，"
                "工具返回后说明图中可能表达的系统结构。"
            ),
        ),
        "pdf": ToolScenario(
            tool="pdf",
            question=(
                f"请先调用 pdf 工具分析这份 PDF：{pdf_path}，"
                "工具返回后总结公路隧道下穿高压输电铁塔施工的核心风险和防控技术。"
            ),
        ),
        "image_generate": ToolScenario(
            tool="image_generate",
            question=(
                "请先调用 image_generate 工具生成一张公路隧道下穿高压输电铁塔施工风险防控技术示意图，"
                "画面包含隧道、铁塔、监测点、加固区。"
            ),
        ),
        "music_generate": ToolScenario(
            tool="music_generate",
            question=(
                f"请先调用 music_generate 工具，基于这个语音 WAV 素材生成一个简短的安全培训提示音频方案：{voice_path}。"
            ),
        ),
        "video_generate": ToolScenario(
            tool="video_generate",
            question=(
                f"请先调用 video_generate 工具，用这个语音 WAV 作为音频参考生成施工风险防控短视频方案：{voice_path}，"
                "画面包含隧道、铁塔、监测预警和现场管控。"
            ),
        ),
        "tts": ToolScenario(
            tool="tts",
            question=(
                "请先调用 tts 工具，把这段施工安全提醒转换成语音："
                "施工前请确认监测数据稳定，严格执行高压输电铁塔保护区作业方案。"
            ),
        ),
    }


def _assert_step_ok(tool_name: str, recording_runtime: RecordingToolRuntime) -> None:
    if not recording_runtime.steps:
        raise AssertionError(f"{tool_name}: agent did not emit a backend tool call")
    failure_count = 0
    last_error: Optional[str] = None
    for step in recording_runtime.steps:
        for observation in step.observations:
            if observation.tool_name != tool_name:
                continue
            if observation.status != "ok":
                failure_count += 1
                last_error = observation.error
                if failure_count >= 5:
                    raise AssertionError(
                        f"{tool_name}: tool failed {failure_count} times; last error: {last_error}"
                    )
                continue
            if _result_mentions_missing_provider(observation.result):
                raise AssertionError(
                    f"{tool_name}: backend tool is mounted but has no real provider configured: {observation.result}"
                )
            return
    if failure_count:
        raise AssertionError(
            f"{tool_name}: backend runtime produced no successful observation after "
            f"{failure_count} failed attempt(s); last error: {last_error}"
        )
    raise AssertionError(f"{tool_name}: backend runtime produced no successful observation")


def _result_mentions_missing_provider(result: Any) -> bool:
    text = json.dumps(result, ensure_ascii=False, default=str).lower()
    return "no provider configured" in text or "no web search provider configured" in text


def _assert_final_not_scripted(tool_name: str, final_text: str) -> None:
    if "tool smoke test complete" in final_text:
        raise AssertionError(f"{tool_name}: final answer came from the removed scripted smoke-test model")
    if "scripted-tool-call-model" in final_text:
        raise AssertionError(f"{tool_name}: scripted model output leaked into final answer")


def _run_one_tool(agent_name: str, scenario: ToolScenario, tools_to_test: Iterable[str]) -> Dict[str, Any]:
    tool_name = scenario.tool
    runtime = _build_tool_runtime()
    agent_id = _register_agent(runtime, agent_name, tools_to_test)
    available = runtime.available_tool_names(agent_id)
    if tool_name not in available:
        raise AssertionError(f"{tool_name}: not available to {agent_name}. Available: {available}")

    recording_runtime = RecordingToolRuntime(runtime)
    agent = _make_agent(agent_name)
    runner = RuntimeAgentRunner(
        agent_name=agent_name,
        agent=agent,
        runtime_root=GENERATED_PROJECT_ROOT,
        agent_id=agent_id,
        tool_runtime=recording_runtime,
    )

    final_text = runner.run(scenario.question)
    _assert_step_ok(tool_name, recording_runtime)
    _assert_final_not_scripted(tool_name, final_text)

    tool_step = next(step for step in recording_runtime.steps if step.observations)
    return {
        "tool": tool_name,
        "status": "ok",
        "question": scenario.question,
        "terminate": tool_step.terminate,
        "final_preview": final_text[:160],
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Test generated agent external backend tool calls with the real model.")
    parser.add_argument("--agent", default="tech_branch", help="Generated agent name to test.")
    parser.add_argument(
        "--all-external-tools",
        action="store_true",
        help="Also test external tools not declared for this agent in build_plan.json.",
    )
    args = parser.parse_args(argv)

    configured_tools = _external_tools_from_build_plan(args.agent)
    tools_to_test = EXTERNAL_TOOL_NAMES if args.all_external_tools else configured_tools
    if not tools_to_test:
        raise AssertionError(f"No external tools configured for agent {args.agent!r}")
    if not PDF_FIXTURE.exists():
        raise AssertionError(f"PDF fixture not found: {PDF_FIXTURE}")
    if not VOICE_FIXTURE.exists():
        raise AssertionError(f"Voice fixture not found: {VOICE_FIXTURE}")

    print(f"[setup] project={GENERATED_PROJECT_ROOT}")
    print(f"[setup] agent={args.agent}")
    print(f"[setup] build_plan_external_tools={configured_tools}")
    print(f"[setup] mounted_external_tools={tools_to_test}")
    print("[setup] model=project OpenAIModel")
    print(f"[setup] pdf_fixture={PDF_FIXTURE}")
    print(f"[setup] voice_fixture={VOICE_FIXTURE}")

    results: List[Dict[str, Any]] = []
    with _local_web_page() as web_fetch_url, _local_image_file() as image_path:
        scenarios = _tool_scenarios(web_fetch_url, image_path)
        for tool_name in tools_to_test:
            scenario = scenarios[tool_name]
            print(f"[run] {tool_name}: {scenario.question}")
            results.append(_run_one_tool(args.agent, scenario, tools_to_test))
            print(f"[ok]  {tool_name}")

    print("[summary]")
    print(json.dumps(results, ensure_ascii=False, indent=2))
    print("[pass] generated agent invoked mounted backend external tools with the project model")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
